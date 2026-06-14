"""Load prompt templates from the templates directory."""

from __future__ import annotations

from functools import cache
from pathlib import Path
from string import Template

_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"


@cache
def load_template(name: str) -> Template:
    path = _TEMPLATES_DIR / name
    if not path.is_file():
        raise FileNotFoundError(f"Prompt template not found: {path}")
    return Template(path.read_text(encoding="utf-8"))
