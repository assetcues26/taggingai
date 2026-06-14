"""Phase 1 multimodal vision analysis prompt."""

from __future__ import annotations

from prompts._loader import load_template
from prompts.helpers import format_description_for_phase1, format_user_cost

_TEMPLATE = load_template("phase1_vision.txt")


def build_phase1_vision_prompt(
    user_asset_name: str,
    user_description: str,
    user_cost,
) -> str:
    """Build the Gemini Phase 1 vision prompt with request-specific context."""
    return _TEMPLATE.substitute(
        user_asset_name=user_asset_name,
        user_description=format_description_for_phase1(user_description),
        user_cost=format_user_cost(user_cost),
    )
