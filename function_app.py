import gc
import json
import logging
import os
import threading
import time
import uuid
from datetime import datetime
from typing import ClassVar

import azure.functions as func
import google.generativeai as genai

from gemini_content import build_gemini_content
from image_utils import resize_image_if_needed
from prompts import (
    GENERIC_SAFE_WORDS,
    MAX_PROMPT_LENGTH,
    build_name_description_match_prompt,
    build_phase1_vision_prompt,
    build_phase2_subcat_model_prompt,
    normalize_description,
)
from request_parser import RequestParseError, parse_asset_analysis_request

# Optional memory monitoring (install with: pip install psutil)
try:
    import psutil

    MEMORY_MONITORING = True
except ImportError:
    MEMORY_MONITORING = False
    logging.warning("psutil not available - memory monitoring disabled")


# Environment variables are handled by Azure Functions

# Configure production-ready logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s - %(funcName)s:%(lineno)d",
)


# Structured logger for production monitoring
class StructuredLogger:
    """
    Production-ready structured logger that:
    - Never logs sensitive data (passwords, API keys, uploaded images, full user data)
    - Provides structured JSON output for Azure Application Insights
    - Includes request context and performance metrics
    """

    SENSITIVE_FIELDS: ClassVar[set[str]] = {
        "password",
        "api_key",
        "apikey",
        "token",
        "secret",
        "assetimage",
        "barcodeimage",
        "GEMINI_API_KEY",
    }

    def __init__(self, request_id, logger_name="asset_analysis"):
        self.request_id = request_id
        self.logger = logging.getLogger(logger_name)

    def _sanitize_data(self, data):
        """Remove sensitive fields from log data"""
        if isinstance(data, dict):
            return {
                k: "***REDACTED***"
                if k.lower() in self.SENSITIVE_FIELDS
                else (self._sanitize_data(v) if isinstance(v, dict | list) else v)
                for k, v in data.items()
            }
        elif isinstance(data, list):
            return [self._sanitize_data(item) for item in data]
        return data

    def _log(self, level, message, **kwargs):
        """Internal logging method with structured output"""
        sanitized_kwargs = self._sanitize_data(kwargs)
        log_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "request_id": self.request_id,
            "message": message,
            **sanitized_kwargs,
        }
        getattr(self.logger, level)(json.dumps(log_data))

    def info(self, message, **kwargs):
        """Log informational message"""
        self._log("info", message, **kwargs)

    def warning(self, message, **kwargs):
        """Log warning message"""
        self._log("warning", message, **kwargs)

    def error(self, message, **kwargs):
        """Log error message"""
        self._log("error", message, **kwargs)

    def critical(self, message, **kwargs):
        """Log critical error message"""
        self._log("critical", message, **kwargs)

    def debug(self, message, **kwargs):
        """Log debug message (only in development)"""
        self._log("debug", message, **kwargs)

    def log_api_call(self, api_name, response_time_ms, success=True, **kwargs):
        """Log API call with performance metrics"""
        self.info(
            f"API call: {api_name}",
            api_name=api_name,
            response_time_ms=response_time_ms,
            success=success,
            **kwargs,
        )

    def log_request_complete(self, total_time_ms, status_code, **kwargs):
        """Log request completion with comprehensive metrics"""
        self.info(
            "Request completed", total_time_ms=total_time_ms, status_code=status_code, **kwargs
        )


# =============================================================================
# CRITICAL API COST PROTECTION - PREVENT UNEXPECTED BILLS
# =============================================================================

# API Usage Tracking and Limits
# Note: Time fields initialized to None and set on first check to avoid stale module-level datetime values
api_usage_tracker = {
    "daily_calls": 0,
    "hourly_calls": 0,
    "minute_calls": 0,
    "last_reset_day": None,  # Lazy init on first check
    "last_reset_hour": None,  # Lazy init on first check
    "last_reset_minute": None,  # Lazy init on first check
    "lock": threading.Lock(),
}

# SAFETY LIMITS - ADJUST THESE BASED ON YOUR BUDGET
API_LIMITS = {
    "MAX_CALLS_PER_MINUTE": 2000,  # Protect against sudden bursts
    "MAX_CALLS_PER_HOUR": 10000,  # Hourly protection
    "MAX_CALLS_PER_DAY": 100000,  # Daily budget protection
    "MAX_RETRIES": 2,  # Reduced from 5 to prevent retry storms
    "CIRCUIT_BREAKER_THRESHOLD": 15,  # Stop after 15 consecutive failures
    "CIRCUIT_BREAKER_TIMEOUT": 300,  # 5 minutes cooldown
}

# Circuit Breaker for API failures
circuit_breaker = {
    "failure_count": 0,
    "last_failure_time": 0,
    "is_open": False,
    "lock": threading.Lock(),
}


def check_api_limits():
    """Check if we're within API usage limits - CRITICAL COST PROTECTION"""
    with api_usage_tracker["lock"]:
        now = datetime.now()

        # Initialize time fields on first run (lazy initialization)
        if api_usage_tracker["last_reset_day"] is None:
            api_usage_tracker["last_reset_day"] = now.day
            api_usage_tracker["last_reset_hour"] = now.hour
            api_usage_tracker["last_reset_minute"] = now.minute
            logging.info("API usage tracker initialized")

        # Reset counters if time periods have passed
        if now.day != api_usage_tracker["last_reset_day"]:
            api_usage_tracker["daily_calls"] = 0
            api_usage_tracker["last_reset_day"] = now.day
            logging.info("Daily API counter reset")

        if now.hour != api_usage_tracker["last_reset_hour"]:
            api_usage_tracker["hourly_calls"] = 0
            api_usage_tracker["last_reset_hour"] = now.hour
            logging.info("Hourly API counter reset")

        if now.minute != api_usage_tracker["last_reset_minute"]:
            api_usage_tracker["minute_calls"] = 0
            api_usage_tracker["last_reset_minute"] = now.minute

        # Debug logging for API usage
        logging.debug(
            f"API Usage Check - Daily: {api_usage_tracker['daily_calls']}/{API_LIMITS['MAX_CALLS_PER_DAY']}, "
            f"Hourly: {api_usage_tracker['hourly_calls']}/{API_LIMITS['MAX_CALLS_PER_HOUR']}, "
            f"Minute: {api_usage_tracker['minute_calls']}/{API_LIMITS['MAX_CALLS_PER_MINUTE']}"
        )

        # Check limits
        if api_usage_tracker["daily_calls"] >= API_LIMITS["MAX_CALLS_PER_DAY"]:
            raise Exception(
                f"DAILY API LIMIT EXCEEDED ({API_LIMITS['MAX_CALLS_PER_DAY']} calls) - COST PROTECTION ACTIVATED"
            )

        if api_usage_tracker["hourly_calls"] >= API_LIMITS["MAX_CALLS_PER_HOUR"]:
            raise Exception(
                f"HOURLY API LIMIT EXCEEDED ({API_LIMITS['MAX_CALLS_PER_HOUR']} calls) - COST PROTECTION ACTIVATED"
            )

        if api_usage_tracker["minute_calls"] >= API_LIMITS["MAX_CALLS_PER_MINUTE"]:
            raise Exception(
                f"MINUTE API LIMIT EXCEEDED ({API_LIMITS['MAX_CALLS_PER_MINUTE']} calls) - COST PROTECTION ACTIVATED"
            )


def record_api_call():
    """Record an API call for tracking - PREVENT BILLING SURPRISES"""
    with api_usage_tracker["lock"]:
        api_usage_tracker["daily_calls"] += 1
        api_usage_tracker["hourly_calls"] += 1
        api_usage_tracker["minute_calls"] += 1

        # Log usage warnings
        if api_usage_tracker["daily_calls"] % 100 == 0:  # Every 100 calls
            logging.warning(
                f"API USAGE ALERT: {api_usage_tracker['daily_calls']} calls today, "
                f"{api_usage_tracker['hourly_calls']} this hour"
            )


def check_circuit_breaker():
    """Circuit breaker pattern to prevent API failure loops"""
    with circuit_breaker["lock"]:
        current_time = time.time()

        # Reset circuit breaker after timeout
        if (
            circuit_breaker["is_open"]
            and current_time - circuit_breaker["last_failure_time"]
            > API_LIMITS["CIRCUIT_BREAKER_TIMEOUT"]
        ):
            circuit_breaker["is_open"] = False
            circuit_breaker["failure_count"] = 0
            logging.info("Circuit breaker reset - API calls resumed")

        if circuit_breaker["is_open"]:
            raise Exception("CIRCUIT BREAKER OPEN - API calls suspended due to repeated failures")


def record_api_failure():
    """Record API failure for circuit breaker"""
    with circuit_breaker["lock"]:
        circuit_breaker["failure_count"] += 1
        circuit_breaker["last_failure_time"] = time.time()

        if circuit_breaker["failure_count"] >= API_LIMITS["CIRCUIT_BREAKER_THRESHOLD"]:
            circuit_breaker["is_open"] = True
            logging.error(
                f"CIRCUIT BREAKER OPENED - {circuit_breaker['failure_count']} consecutive API failures"
            )


def record_api_success():
    """Record API success to reset failure counter"""
    with circuit_breaker["lock"]:
        circuit_breaker["failure_count"] = 0  # Reset on success


# Memory-efficient global model instance (shared across requests)
_vision_model = None
_model_lock = threading.Lock()


def get_shared_model():
    """Get shared Gemini model instance to reduce memory usage across requests."""
    global _vision_model

    with _model_lock:
        ensure_gemini_configured()
        model_name = os.getenv("GEMINI_MODEL_NAME")
        if not model_name:
            raise ValueError("GEMINI_MODEL_NAME environment variable not set.")
        if _vision_model is None:
            _vision_model = genai.GenerativeModel(model_name)
            logging.info("Initialized shared Gemini model")

    return _vision_model


def log_memory_usage(request_id, stage):
    """Log memory usage for Base Plan monitoring (optional)"""
    if not MEMORY_MONITORING:
        return

    try:
        process = psutil.Process()
        memory_info = process.memory_info()
        memory_mb = memory_info.rss / 1024 / 1024
        logging.info(f"[{request_id}] Memory usage at {stage}: {memory_mb:.1f}MB")

        # Warning if approaching Base Plan limits
        if memory_mb > 1200:  # 1.2GB warning threshold
            logging.warning(
                f"[{request_id}] HIGH MEMORY USAGE: {memory_mb:.1f}MB - approaching Base Plan limits"
            )
    except Exception as e:
        logging.debug(f"Memory monitoring failed: {e}")


# Configure Gemini lazily so Vercel builds and imports do not require secrets.
_gemini_configured = False


def ensure_gemini_configured() -> None:
    global _gemini_configured
    if _gemini_configured:
        return
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY environment variable not set.")
    genai.configure(api_key=api_key)
    _gemini_configured = True


# --- Utility helpers ---


def create_error_response(
    message: str, status_code: int = 400, request_id: str | None = None, **extra_fields
):
    """Standardized error response format for consistent API contract

    Args:
        message: Human-readable error message
        status_code: HTTP status code (400, 401, 403, 429, 500, 503, 504)
        request_id: Optional request ID for tracing
        **extra_fields: Additional fields to include in error response

    Returns:
        func.HttpResponse with standardized JSON error format
    """
    error_response = {
        "success": False,
        "error": {
            "message": message,
            "code": status_code,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        },
    }

    if request_id:
        error_response["error"]["request_id"] = request_id

    # Add any extra fields at root level
    error_response.update(extra_fields)

    return func.HttpResponse(
        json.dumps(error_response),
        mimetype="application/json",
        status_code=status_code,
        headers={"X-Request-ID": request_id or "unknown", "X-Error-Code": str(status_code)},
    )


def to_int_or_none(value):
    """Safely convert possibly messy strings (e.g., "1001, ") to int or return None.
    Accepts ints, numeric strings, and strings with stray non-digit separators.
    """
    if value is None:
        return None
    if isinstance(value, int):
        return value
    try:
        s = str(value).strip()
        # Remove common trailing punctuation and whitespace
        # Keep optional leading minus and digits only
        import re

        cleaned = re.sub(r"[^0-9\-]+", "", s)
        if cleaned in ("", "-"):
            return None
        return int(cleaned)
    except Exception:
        return None


# --- Image Handling ---


def format_barcode_position(value):
    """Normalize barcode position output to an object with a `position` field."""
    position_value = value.get("position") if isinstance(value, dict) else value

    if isinstance(position_value, str):
        if position_value.strip() == "":
            position_value = None
    elif position_value is not None:
        # Coerce unexpected types (e.g. lists/numbers) to string for consistency
        position_value = str(position_value)

    return {"position": position_value if position_value is not None else None}


def compare_tag_numbers(detected, user_provided, request_id=""):
    """
    Compare tag numbers with proper normalization and business rules.

    Business Rules:
    - Leading zeros MATTER (e.g., "001" != "1")
    - Whitespace is trimmed (e.g., " 123 " == "123")
    - "UNREADABLE" is treated as no match
    - None/empty values return no match

    Returns: (match_status, match_percent)
    """
    # Handle None/empty cases
    if not detected or not user_provided:
        logging.info(f"[{request_id}] Tag number comparison: One or both values are empty/None")
        return "N", 0

    # Handle UNREADABLE case (case-insensitive)
    detected_str = str(detected).strip()
    if detected_str.upper() == "UNREADABLE":
        logging.info(f"[{request_id}] Tag number comparison: Detected tag is UNREADABLE")
        return "N", 0

    # Normalize: convert to string and strip whitespace (but preserve leading zeros)
    user_str = str(user_provided).strip()

    # Exact match comparison (preserving leading zeros as per business requirements)
    if detected_str == user_str:
        logging.info(
            f"[{request_id}] Tag number comparison: MATCH - '{detected_str}' == '{user_str}'"
        )
        return "Y", 100
    else:
        logging.info(
            f"[{request_id}] Tag number comparison: MISMATCH - '{detected_str}' != '{user_str}'"
        )
        return "N", 0


def call_gemini_with_retry(
    model, prompt, inline_images=None, max_tokens=None, retries=None, response_mime_type=None
):
    """
    COST-PROTECTED Gemini API call with comprehensive safeguards.
    Uses Gemini inline_data parts for direct image bytes (no base64).
    """
    if retries is None:
        retries = API_LIMITS["MAX_RETRIES"]  # Use safe retry limit

    # COST PROTECTION: Always set max_tokens limit
    # Added safety fallback:
    if max_tokens is None:
        max_tokens = 200  # Default safe limit for output tokens

    generation_config = genai.types.GenerationConfig(temperature=0.1, max_output_tokens=max_tokens)

    # Force JSON output if requested (for recommendation stages)
    if response_mime_type == "application/json":
        generation_config.response_mime_type = "application/json"

    # CRITICAL: Check all safety limits before making ANY API call
    try:
        check_api_limits()  # Cost protection
        check_circuit_breaker()  # Failure protection
    except Exception as safety_error:
        logging.error(f"API SAFETY CHECK FAILED: {safety_error}")
        # Return safety fallback - this is different from API failure
        return {"error": f"API_LIMIT_PROTECTION: API call blocked by safety system: {safety_error}"}

    # COST PROTECTION: Validate input prompt length (input tokens cost money too!)
    # Increased limit to 20000 chars to accommodate detailed "Universal Validator" and "Optical Zoom" prompts
    if len(prompt) > MAX_PROMPT_LENGTH:
        logging.error(
            f"PROMPT_TOO_LONG: {len(prompt)} chars exceeds {MAX_PROMPT_LENGTH} char limit"
        )
        return {"error": "PROMPT_TOO_LONG"}

    last_error = None

    for attempt in range(retries):
        try:
            # Record this attempt AFTER safety checks pass
            record_api_call()

            content = build_gemini_content(prompt, inline_images) if inline_images else prompt

            start_time = time.time()
            response = model.generate_content(content, generation_config=generation_config)
            response_time = time.time() - start_time

            # Log API usage for cost monitoring
            logging.info(
                f"Gemini API call successful in {response_time:.2f}s (attempt {attempt + 1}, "
                f"daily: {api_usage_tracker['daily_calls']}, hourly: {api_usage_tracker['hourly_calls']})"
            )

            # Clean and parse JSON response - handle markdown code blocks and explanatory text
            raw_text = response.text.strip()

            # Remove markdown code blocks (both opening and closing)
            if raw_text.startswith("```json"):
                raw_text = raw_text[7:]  # Remove ```json
            elif raw_text.startswith("```"):
                raw_text = raw_text[3:]  # Remove ```

            # Remove trailing markdown code block if present
            if raw_text.endswith("```"):
                raw_text = raw_text[:-3]  # Remove closing ```

            # Clean up any remaining whitespace
            raw_text = raw_text.strip()

            # ENHANCED: Handle LLM responses that include explanatory text
            # Look for JSON object anywhere in the response
            json_start = raw_text.find("{")
            if json_start == -1:
                # No JSON object found at all
                raise json.JSONDecodeError("No JSON object found in response", raw_text, 0)

            # Extract everything from the first '{' onward
            raw_text = raw_text[json_start:]

            # Find the matching closing brace for the JSON object
            if raw_text.startswith("{"):
                # SECURITY: Limit JSON parsing to prevent DoS from malicious responses
                MAX_JSON_LENGTH = 50000  # ~10k tokens max response
                if len(raw_text) > MAX_JSON_LENGTH:
                    logging.warning(
                        f"AI response too large ({len(raw_text)} chars), truncating to {MAX_JSON_LENGTH}"
                    )
                    raw_text = raw_text[:MAX_JSON_LENGTH]

                brace_count = 0
                json_end = -1
                for i, char in enumerate(raw_text):
                    if char == "{":
                        brace_count += 1
                    elif char == "}":
                        brace_count -= 1
                        if brace_count == 0:
                            # Found the end of the JSON object
                            json_end = i + 1
                            break

                if json_end != -1:
                    # Extract only the JSON object, ignore everything after
                    raw_text = raw_text[:json_end]

            # Final cleanup: ensure valid JSON
            raw_text = raw_text.strip()

            parsed_response = json.loads(raw_text)

            # JSON Schema Validation: Ensure response has expected structure
            if not isinstance(parsed_response, dict):
                raise ValueError(
                    f"AI response must be a JSON object, got {type(parsed_response).__name__}"
                )

            # Validate that response doesn't contain unexpected keys that could overwrite critical fields
            # This prevents malicious/malformed AI responses from corrupting the output
            dangerous_keys = {
                "assetid",
                "assettaggingdetailid",
                "customerid",
                "companyid",
                "error",
                "success",
            }
            unexpected_keys = dangerous_keys.intersection(parsed_response.keys())
            if unexpected_keys:
                logging.warning(
                    f"AI response contains dangerous keys that will be filtered: {unexpected_keys}"
                )
                for key in unexpected_keys:
                    del parsed_response[key]

            # Record success (resets circuit breaker)
            record_api_success()

            if attempt > 0:
                logging.info(f"Gemini API recovered on attempt {attempt + 1}")

            return parsed_response

        except json.JSONDecodeError as e:
            last_error = f"Invalid JSON from Gemini API: {e}"
            logging.warning(f"Gemini API JSON error (attempt {attempt + 1}/{retries}): {e}")

            # Log the problematic response for debugging
            if len(raw_text) < 500:  # Only log if response is reasonably short
                logging.warning(f"Problematic response text: {raw_text!r}")
            else:
                logging.warning(
                    f"Large response ({len(raw_text)} chars), first 200: {raw_text[:200]!r}"
                )

            # Try to extract partial data from truncated JSON for recommendations
            if "recommendedsubcategory" in raw_text and "recommendedmakemodel" in raw_text:
                try:
                    # Attempt to fix truncated JSON by closing it
                    if raw_text.count('"') % 2 == 1:  # Odd number of quotes = unclosed string
                        raw_text += '"'  # Close the unterminated string
                    if not raw_text.strip().endswith("}"):
                        raw_text += " }"  # Close the JSON object

                    parsed_response = json.loads(raw_text)
                    logging.info(
                        f"Successfully recovered from truncated JSON on attempt {attempt + 1}"
                    )
                    record_api_success()
                    return parsed_response
                except json.JSONDecodeError:
                    logging.warning("Failed to recover from truncated JSON")

            if attempt < retries - 1:
                time.sleep(0.5 * (attempt + 1))  # Linear backoff to prevent rapid retries
                continue

        except Exception as e:
            last_error = f"Gemini API error: {e}"
            logging.warning(f"Gemini API failed (attempt {attempt + 1}/{retries}): {e}")

            if attempt < retries - 1:
                time.sleep(1.0 * (attempt + 1))  # Longer backoff for other errors
                continue

    # All retries exhausted - record failure (this is actual API failure, not safety block)
    record_api_failure()
    error_msg = f"Gemini API failed after {retries} attempts. Last error: {last_error}"
    logging.error(error_msg)

    # Return API failure response (different from safety block)
    logging.critical("RETURNING SAFE FALLBACK DUE TO ACTUAL API FAILURES")
    return {"error": f"API_FAILURE: API failed after {retries} attempts: {last_error}"}


# --- Main Function App ---

app = func.FunctionApp()


def process_asset_analysis(req: func.HttpRequest) -> func.HttpResponse:
    """
    Ultra-optimized asset analysis function with zero-failure guarantee and ASAP response times.
    Enhanced with comprehensive monitoring, caching, and error recovery.
    """
    # Generate unique request ID and start monitoring (with API cost protection)
    request_id = str(uuid.uuid4())[:8]
    start_time = time.time()

    # Initialize structured logger for this request
    logger = StructuredLogger(request_id)

    # Log request start with API usage monitoring
    active_threads = threading.active_count()
    log_memory_usage(request_id, "start")
    logger.info(
        "Asset analysis request started",
        active_threads=active_threads,
        api_calls_today=api_usage_tracker["daily_calls"],
        api_calls_hour=api_usage_tracker["hourly_calls"],
    )

    try:
        ensure_gemini_configured()
    except ValueError as e:
        logger.error("Gemini configuration missing", error=str(e))
        return create_error_response(str(e), status_code=500, request_id=request_id)

    try:
        parsed_request = parse_asset_analysis_request(req)
    except RequestParseError as e:
        logger.error("Invalid multipart request", error=str(e))
        return create_error_response(str(e), status_code=400, request_id=request_id)

    req_body = parsed_request.metadata
    asset_image = parsed_request.asset_image
    barcode_image = parsed_request.barcode_image

    user_cost = req_body.get("cost")
    user_acquisition_date = req_body.get("acquisitiondate")

    # --- Prepare response structure ---
    output = {
        "assetid": req_body.get("assetid"),
        "assetname": req_body.get("assetname"),
        "description": req_body.get("description"),
        "tagnumber": req_body.get("tagnumber"),
        "assetnumber": req_body.get("assetnumber"),
        "assetclassid": req_body.get("assetclassid"),
        "assettaggingdetailid": req_body.get("assettaggingdetailid"),
        "assetclassname": req_body.get("assetclassname"),
        "categoryid": req_body.get("categoryid"),
        "categoryname": req_body.get("categoryname"),
        "subcategoryid": req_body.get("subcategoryid"),
        "subcategoryname": req_body.get("subcategoryname"),
        "makemodelname": req_body.get("makemodelname"),
        "companyid": req_body.get("companyid"),
        "company": req_body.get("company"),
        "makemodelid": req_body.get("makemodelid"),
        "customerid": req_body.get("customerid"),
        "imageAnalysis": None,  # NEW: Detailed 50-word analysis of what's in the image
        "detectedAsset": None,
        "imageReadability": "Y",  # Default to "Y" - will be changed to "E" if errors occur
        "namedescriptionmatch": "N",
        "namedescriptionmatchpercent": 0,
        "reasoning": None,  # NEW: Human-readable explanation (max 50 words) why match/no-match
        "subcatmodelmatch": "N",
        "subcatmodelmatchpercent": 0,
        "recommendedsubcategory": None,
        "recommendedmakemodel": None,
        "detectedtagnumber": None,
        "detectedtagnumbermatch": "N",
        "detectedtagnumbermatchpercent": 0,
        # "barcodereadconfidence": None,  # NEW: Indicates barcode reading confidence (COMMENTED OUT)
        "barcodeposition": {"position": None},
        "damage_assessment": None,
        "condition": None,  # NEW: One-line asset condition from image
        "costvalidation": {  # NEW: Cost validation result
            "estimatedcost": None,  # AI-estimated cost (Indian market, INR)
            "usercost": None,  # Echo of user-provided cost
            "costmatch": "N",  # Y/N - does cost match estimate?
            "reasoning": None,  # Brief explanation with INR amounts
        },
        "acquisitiondatevalidation": {  # NEW: Acquisition date validation result
            "estimatedyear": None,  # AI-estimated manufacture/release year
            "estimatedmarketstatus": None,  # AI-estimated: AVAILABLE or DISCONTINUED
            "useracquisitiondate": None,  # Echo of user-provided date
            "datematch": "N",  # Y/N - is the date plausible?
            "reasoning": None,  # Brief explanation
        },
        "error": None,
    }

    inline_images: list[tuple[bytes, str]] = []

    # --- Image Processing ---
    try:
        if asset_image:
            asset_bytes, asset_mime = resize_image_if_needed(
                asset_image.data,
                request_id=request_id,
                is_barcode=False,
                mime_type=asset_image.mime_type,
            )
            inline_images.append((asset_bytes, asset_mime))
        if barcode_image:
            barcode_bytes, barcode_mime = resize_image_if_needed(
                barcode_image.data,
                request_id=request_id,
                is_barcode=True,
                mime_type=barcode_image.mime_type,
            )
            # Barcode first for Gemini vision, matching prompt expectations.
            inline_images.insert(0, (barcode_bytes, barcode_mime))
    except ValueError as e:
        # Return 400 for bad image data (invalid format, too large, etc.)
        return create_error_response(
            str(e),
            status_code=400,
            request_id=request_id,
            details={"phase": "image_processing", "image_type": "asset_or_barcode"},
        )
    except Exception as e:
        logging.error(f"Unexpected error during image processing: {e}")
        return create_error_response(
            "Image processing failed due to unexpected error",
            status_code=500,
            request_id=request_id,
            details={"phase": "image_processing"},
        )

    # --- Phase 1: Gemini Multimodal Analysis (Memory Optimized) ---
    user_asset_name = str(req_body.get("assetname") or "").strip()
    user_description_for_prompt = normalize_description(req_body.get("description"))
    gemini_prompt_phase1 = build_phase1_vision_prompt(
        user_asset_name=user_asset_name,
        user_description=user_description_for_prompt,
        user_cost=user_cost,
    )

    try:
        # Use shared models to reduce memory usage
        vision_model = get_shared_model()
        log_memory_usage(request_id, "after_model_load")

        if not inline_images:
            output["imageReadability"] = "E"
            logging.warning(f"[{request_id}] No images provided - imageReadability set to 'E'")

        if inline_images:
            log_memory_usage(request_id, "before_gemini_vision")
            try:
                gemini_output = call_gemini_with_retry(
                    vision_model,
                    gemini_prompt_phase1,
                    inline_images=inline_images,
                    max_tokens=1500,
                )

                # Handle API protection fallback
                if gemini_output and gemini_output.get("error") == "API_LIMIT_PROTECTION":
                    logging.warning(f"[{request_id}] Vision API protected - using safe defaults")
                    output["imageReadability"] = "E"  # Error due to API limits
                    output["detectedAsset"] = "Unable to analyze due to API limits"
                    output["error"] = "API_PROTECTED"
                elif gemini_output:
                    output.update(gemini_output)
                    output["barcodeposition"] = format_barcode_position(
                        output.get("barcodeposition")
                    )

                log_memory_usage(request_id, "after_gemini_vision")

                # Handle UNREADABLE barcode case - set imageReadability to "E"
                if (
                    output.get("detectedtagnumber")
                    and str(output["detectedtagnumber"]).upper() == "UNREADABLE"
                ):
                    output["imageReadability"] = "E"
                    # output["barcodereadconfidence"] = "LOW"  # COMMENTED OUT
                    logging.warning(
                        f"[{request_id}] Barcode is UNREADABLE - setting imageReadability to 'E'"
                    )
                elif output.get("detectedtagnumber"):
                    # Barcode was read successfully
                    # output["barcodereadconfidence"] = "HIGH"  # COMMENTED OUT
                    logging.info(
                        f"[{request_id}] Barcode read successfully: {output['detectedtagnumber']}"
                    )
                else:
                    # No barcode detected
                    # output["barcodereadconfidence"] = "NONE"  # COMMENTED OUT
                    pass

                # Keep inline images for Phase 1.5 visual verification.

                # Tag number matching logic using proper comparison function
                match_status, match_percent = compare_tag_numbers(
                    output.get("detectedtagnumber"), output.get("tagnumber"), request_id
                )
                output["detectedtagnumbermatch"] = match_status
                output["detectedtagnumbermatchpercent"] = match_percent

                # --- Acquisition Date Validation (Post-processing) ---
                if user_acquisition_date is not None:
                    try:
                        # Parse DD-MM-YYYY format used across the platform
                        date_str = str(user_acquisition_date).strip()
                        if "-" in date_str and len(date_str) >= 10:
                            # Full DD-MM-YYYY format
                            user_year = int(date_str.split("-")[2][:4])
                        elif "-" in date_str and len(date_str) <= 7:
                            # Partial format like MM-YYYY or YYYY
                            parts = date_str.split("-")
                            user_year = (
                                int(parts[-1][:4]) if len(parts[-1]) == 4 else int(parts[0][:4])
                            )
                        else:
                            # Just year (e.g., "2024")
                            user_year = int(date_str[:4])

                        import datetime

                        current_year = datetime.datetime.now().year
                        estimated_year = to_int_or_none(output.get("estimatedyear")) or 0
                        market_status = (
                            str(output.get("estimatedmarketstatus") or "UNKNOWN").strip().upper()
                        )

                        if estimated_year > 0:
                            # Rule 1: Acquisition BEFORE manufacture year - impossible
                            if user_year < estimated_year:
                                date_match = "N"
                                date_reasoning = f"Acquisition year {user_year} is before estimated manufacture year {estimated_year}. Asset cannot be purchased before it was manufactured."

                            # Rule 2: Acquisition in the FUTURE - impossible
                            elif user_year > current_year:
                                date_match = "N"
                                date_reasoning = f"Acquisition year {user_year} is in the future (current year: {current_year}). Likely a data entry error."

                            # Rule 3: Model is AVAILABLE in market - valid
                            elif market_status == "AVAILABLE":
                                date_match = "Y"
                                date_reasoning = f"Asset model is still available in the market. Acquisition year {user_year} is valid (manufactured {estimated_year}, still being sold)."

                            # Rule 4: Model is DISCONTINUED - check gap
                            elif market_status == "DISCONTINUED":
                                year_diff = user_year - estimated_year
                                if year_diff > 7:
                                    date_match = "N"
                                    date_reasoning = f"Asset model manufactured around {estimated_year} and is now discontinued. Acquisition in {user_year} ({year_diff} years later) is unusual."
                                else:
                                    date_match = "Y"
                                    date_reasoning = f"Asset model manufactured around {estimated_year}, discontinued but acquired within reasonable timeframe ({user_year})."

                            # Rule 5: Unknown market status - use conservative gap check
                            else:
                                year_diff = user_year - estimated_year
                                if year_diff > 7:
                                    date_match = "N"
                                    date_reasoning = f"Asset manufactured around {estimated_year}, acquired in {user_year} ({year_diff} years later). Asset may be outdated by this date."
                                else:
                                    date_match = "Y"
                                    date_reasoning = f"Acquisition year {user_year} is within reasonable range of manufacture year {estimated_year}."
                        else:
                            date_match = "N"
                            date_reasoning = "Unable to estimate manufacture year from image."

                        output["acquisitiondatevalidation"] = {
                            "estimatedyear": estimated_year if estimated_year > 0 else None,
                            "estimatedmarketstatus": market_status
                            if market_status != "UNKNOWN"
                            else None,
                            "useracquisitiondate": str(user_acquisition_date),
                            "datematch": date_match,
                            "reasoning": date_reasoning,
                        }
                        logging.info(
                            f"[{request_id}] Acquisition date validation: {date_match} (user_year={user_year}, estimated_year={estimated_year}, market={market_status})"
                        )
                    except (ValueError, TypeError, IndexError) as e:
                        logging.warning(f"[{request_id}] Acquisition date validation error: {e}")
                        output["acquisitiondatevalidation"] = {
                            "estimatedyear": None,
                            "estimatedmarketstatus": None,
                            "useracquisitiondate": str(user_acquisition_date),
                            "datematch": "N",
                            "reasoning": "Invalid acquisition date format. Expected DD-MM-YYYY.",
                        }

                # --- Cost Validation (Using Model's AI Comparison) ---
                if user_cost is not None:
                    try:
                        user_cost_val = float(str(user_cost).replace(",", "").strip())
                        estimated_cost = float(output.get("estimatedcost") or 0)
                        cost_comparison = str(output.get("costcomparison") or "N").strip().upper()
                        cost_comparison_reasoning = str(
                            output.get("costcomparisonreasoning") or ""
                        ).strip()

                        # Use model's AI judgment for cost match (no fixed deviation rule)
                        cost_match = cost_comparison if cost_comparison in ["Y", "N"] else "N"

                        output["costvalidation"] = {
                            "estimatedcost": estimated_cost if estimated_cost > 0 else None,
                            "usercost": user_cost_val,
                            "costmatch": cost_match,
                            "reasoning": cost_comparison_reasoning
                            if cost_comparison_reasoning
                            else "Unable to compare costs.",
                        }
                        logging.info(
                            f"[{request_id}] Cost validation (AI): {cost_match} (user={user_cost_val}, estimated={estimated_cost})"
                        )
                    except (ValueError, TypeError) as e:
                        logging.warning(f"[{request_id}] Cost validation error: {e}")
                        output["costvalidation"] = {
                            "estimatedcost": None,
                            "usercost": str(user_cost),
                            "costmatch": "N",
                            "reasoning": "Invalid cost format provided.",
                        }

            except Exception as e:
                logging.error(f"Failed to process with Gemini Vision after retries: {e}")
                return create_error_response(
                    "Gemini Vision API failed after multiple attempts",
                    status_code=503,
                    request_id=request_id,
                    details={"phase": "gemini_vision", "error_type": str(type(e).__name__)},
                )
    except Exception as e:
        logging.error(f"Error initializing Gemini Vision model: {e}")
        return create_error_response(
            "Failed to initialize AI model",
            status_code=500,
            request_id=request_id,
            details={"phase": "model_initialization", "error_type": str(type(e).__name__)},
        )

    # --- Phase 1.5: Name/Description Match (Memory Optimized) ---
    try:
        user_asset_name = str(req_body.get("assetname") or "").strip()
        user_description = normalize_description(req_body.get("description"))
        image_analysis = output.get("imageAnalysis", "").strip()

        gemini_prompt_name_match = build_name_description_match_prompt(
            user_asset_name=user_asset_name,
            user_description=user_description,
            image_analysis=image_analysis,
        )

        log_memory_usage(request_id, "before_name_match")

        # --- ROBUST RETRY LOGIC ---
        gemini_output = None
        try:
            # Attempt 1: Try with Vision (Best Accuracy)
            # We create a list copy to avoid issues if the list was modified
            current_images = list(inline_images) if inline_images else None

            gemini_output = call_gemini_with_retry(
                vision_model,
                gemini_prompt_name_match,
                inline_images=current_images,
                max_tokens=600,
            )
        except Exception as e_vision:
            logging.warning(
                f"[{request_id}] Phase 1.5 Vision attempt failed: {e_vision}. Falling back to Text-Only."
            )

            # Attempt 2: Fallback to Text-Only (If image stream is exhausted/invalid)
            try:
                gemini_output = call_gemini_with_retry(
                    vision_model,
                    gemini_prompt_name_match,
                    inline_images=None,
                    max_tokens=600,
                )
            except Exception as e_text:
                logging.error(f"[{request_id}] Phase 1.5 Text-Only fallback failed: {e_text}")

        # Update output if we got a result
        if gemini_output:
            output.update(gemini_output)
        else:
            # Attempt 3: SAFETY NET - Local Fallback for obvious generics
            # If AI failed completely, don't fail the asset if it looks generic
            lower_name = user_asset_name.lower()
            if any(word in lower_name for word in GENERIC_SAFE_WORDS):
                logging.info(
                    f"[{request_id}] AI failed but generic keyword detected. Applying safety net approval."
                )
                output["namedescriptionmatch"] = "Y"
                output["namedescriptionmatchpercent"] = 90
                output["reasoning"] = (
                    "System Safety Net: Generic asset name detected (AI service unavailable)."
                )

        log_memory_usage(request_id, "after_name_match")

    except Exception as e:
        logging.error(f"Error in name/description matching wrapper: {e}")
        # Continue processing - this is not critical
        pass

    # --- Phase 2: Subcategory / Make-Model validation ---
    try:
        gemini_prompt_phase2 = build_phase2_subcat_model_prompt(
            categoryname=str(req_body.get("categoryname") or "").strip(),
            user_subcategory=str(req_body.get("subcategoryname") or "").strip(),
            user_makemodel=str(req_body.get("makemodelname") or "").strip(),
            detected_asset=str(output.get("detectedAsset") or "").strip(),
            image_analysis=str(output.get("imageAnalysis") or "").strip(),
        )

        log_memory_usage(request_id, "before_subcat_model_match")

        phase2_output = call_gemini_with_retry(
            vision_model,
            gemini_prompt_phase2,
            inline_images=None,
            max_tokens=200,
            response_mime_type="application/json",
        )

        if phase2_output and "error" not in phase2_output:
            for key in (
                "subcatmodelmatch",
                "subcatmodelmatchpercent",
                "recommendedsubcategory",
                "recommendedmakemodel",
            ):
                if key in phase2_output:
                    output[key] = phase2_output[key]

            match_value = str(output.get("subcatmodelmatch") or "N").strip().upper()
            output["subcatmodelmatch"] = "Y" if match_value == "Y" else "N"

            try:
                output["subcatmodelmatchpercent"] = max(
                    0, min(100, int(output.get("subcatmodelmatchpercent") or 0))
                )
            except (TypeError, ValueError):
                output["subcatmodelmatchpercent"] = 0

            for rec_key in ("recommendedsubcategory", "recommendedmakemodel"):
                rec_value = output.get(rec_key)
                if rec_value is not None and str(rec_value).strip().upper() in {
                    "",
                    "N/A",
                    "NA",
                    "NULL",
                    "NONE",
                }:
                    output[rec_key] = None

            logging.info(
                f"[{request_id}] Phase 2 complete: match={output['subcatmodelmatch']}, "
                f"percent={output['subcatmodelmatchpercent']}, "
                f"recommended_subcategory={output.get('recommendedsubcategory')}, "
                f"recommended_makemodel={output.get('recommendedmakemodel')}"
            )
        else:
            logging.warning(
                f"[{request_id}] Phase 2 skipped - AI unavailable: "
                f"{phase2_output.get('error') if phase2_output else 'no response'}"
            )

        log_memory_usage(request_id, "after_subcat_model_match")

    except Exception as e:
        logging.error(f"Error in subcategory/make-model validation: {e}")
        pass

    # Ensure barcode position is always normalized before further processing/caching
    output["barcodeposition"] = format_barcode_position(output.get("barcodeposition"))

    # Remove intermediate AI fields (already captured in validation objects)
    output.pop("estimatedcost", None)
    output.pop("estimatedyear", None)
    output.pop("estimatedmarketstatus", None)
    output.pop("costcomparison", None)
    output.pop("costcomparisonreasoning", None)
    output.pop("tag_detection_reasoning", None)

    # Enhanced memory cleanup for Base Plan optimization
    try:
        # Explicit cleanup of all large objects using proper del statements
        # Note: Variables must exist in local scope to be deleted
        if "inline_images" in locals():
            del inline_images
        if "gemini_output" in locals():
            del gemini_output
        if "user_asset_name" in locals():
            del user_asset_name
        if "user_description" in locals():
            del user_description
        if "image_analysis" in locals():
            del image_analysis
        if "gemini_prompt_phase1" in locals():
            del gemini_prompt_phase1
        if "gemini_prompt_name_match" in locals():
            del gemini_prompt_name_match
        if "gemini_prompt_phase2" in locals():
            del gemini_prompt_phase2

        # Force garbage collection for Base Plan
        collected = gc.collect()
        log_memory_usage(request_id, "after_cleanup")

        if collected > 0:
            logging.debug(f"[{request_id}] Garbage collected {collected} objects")

    except Exception as e:
        logging.warning(f"[{request_id}] Memory cleanup warning: {e}")

    # Calculate total response time
    total_time = time.time() - start_time

    # Log completion with memory, performance, and API usage metrics
    log_memory_usage(request_id, "completion")
    logger.log_request_complete(
        total_time_ms=round(total_time * 1000, 2),
        status_code=200,
        api_calls_today=api_usage_tracker["daily_calls"],
        api_calls_hour=api_usage_tracker["hourly_calls"],
        has_recommendations=bool(
            output.get("recommendedsubcategory") or output.get("recommendedmakemodel")
        ),
    )

    # Return response with comprehensive monitoring info
    memory_header = "unknown"
    if MEMORY_MONITORING:
        try:
            memory_mb = psutil.Process().memory_info().rss / 1024 / 1024
            memory_header = f"{memory_mb:.1f}MB"
        except Exception:
            memory_header = "unavailable"

    return func.HttpResponse(
        json.dumps(output),
        mimetype="application/json",
        status_code=200,
        headers={
            "X-Request-ID": request_id,
            "X-Response-Time": f"{total_time:.2f}s",
            "X-Memory-Usage": memory_header,
            "X-API-Calls-Today": str(api_usage_tracker["daily_calls"]),
            "X-API-Calls-Hour": str(api_usage_tracker["hourly_calls"]),
        },
    )


@app.route(route="asset_analysis", auth_level=func.AuthLevel.ANONYMOUS)
def asset_analysis(req: func.HttpRequest) -> func.HttpResponse:
    return process_asset_analysis(req)
