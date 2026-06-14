"""Post-check name/description results against obvious asset-type conflicts."""

from __future__ import annotations

_ASSET_TYPE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "laptop": ("laptop", "notebook", "macbook", "thinkpad", "chromebook"),
    "printer": ("printer", "laserjet", "inkjet", "multifunction", "mfp", "copier"),
    "monitor": ("monitor", "display screen", "led panel"),
    "chair": ("chair", "stool", "seat"),
    "desk": ("desk", "table", "workstation"),
    "phone": ("telephone", "phone", "handset", "ip phone"),
    "ac": ("air conditioner", "split ac", "window ac", "hvac"),
    "vehicle": ("car", "truck", "vehicle", "forklift", "excavator"),
}


def _detect_asset_types(text: str) -> set[str]:
    lower = f" {str(text or '').lower()} "
    found: set[str] = set()
    for category, keywords in _ASSET_TYPE_KEYWORDS.items():
        if any(keyword in lower for keyword in keywords):
            found.add(category)
    return found


def apply_name_description_sanity_check(
    user_asset_name: str,
    user_description: str,
    image_analysis: str,
    detected_asset: str,
    ai_result: dict,
) -> dict:
    """
    Override clearly wrong AI approvals when asset type in the name/description
    contradicts the image or each other (e.g. name=Laptop, image=Printer).
    """
    result = dict(ai_result)
    name = str(user_asset_name or "").strip()
    description = str(user_description or "").strip()
    image_text = f"{image_analysis or ''} {detected_asset or ''}".strip()

    name_types = _detect_asset_types(name)
    description_types = _detect_asset_types(description)
    image_types = _detect_asset_types(image_text)

    if not image_types:
        return result

    reasons: list[str] = []

    if name_types and not name_types.intersection(image_types):
        reasons.append(
            f"Asset name implies {', '.join(sorted(name_types))} but image shows "
            f"{', '.join(sorted(image_types))}."
        )

    if name_types and description_types and not name_types.intersection(description_types):
        reasons.append(
            f"Asset name implies {', '.join(sorted(name_types))} but description implies "
            f"{', '.join(sorted(description_types))}."
        )

    if not reasons:
        return result

    result["namedescriptionmatch"] = "N"
    result["namedescriptionmatchpercent"] = min(int(result.get("namedescriptionmatchpercent") or 0), 25)
    result["reasoning"] = (
        f"User Claim: {name or '(empty)'} / {description or '(empty)'}. "
        f"Image Shows: {detected_asset or image_analysis or 'conflicting asset type'}. "
        f"Verdict: {' '.join(reasons)}"
    )
    return result
