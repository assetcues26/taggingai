"""Phase 1.5 name/description validation prompt."""

from __future__ import annotations

from prompts._loader import load_template
from prompts.helpers import format_description_for_name_match

_TEMPLATE = load_template("name_description_match.txt")


def build_name_description_match_prompt(
    user_asset_name: str,
    user_description: str,
    image_analysis: str,
) -> str:
    """Build the Gemini name/description match prompt."""
    return _TEMPLATE.substitute(
        user_asset_name=user_asset_name,
        user_description=format_description_for_name_match(user_description),
        image_analysis=image_analysis or "(no image analysis available)",
    )
