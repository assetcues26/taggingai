"""Prompt-related constants shared with the function app."""

# Fallback approval list when Phase 1.5 AI is unavailable.
GENERIC_SAFE_WORDS = (
    "camera",
    "keyboard",
    "mouse",
    "monitor",
    "screen",
    "cable",
    "wire",
    "chair",
    "desk",
    "table",
    "cabinet",
    "drawer",
    "pedestal",
    "ac",
    "conditioner",
    "fan",
    "light",
    "lamp",
    "ups",
    "battery",
    "laptop",
    "printer",
    "scanner",
    "server",
    "rack",
    "phone",
    "headset",
    "switch",
    "router",
    "firewall",
    "projector",
    "tv",
    "display",
)

# Max prompt length enforced by call_gemini_with_retry (keep in sync).
MAX_PROMPT_LENGTH = 20000
