"""Shared pytest fixtures and environment setup."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("GEMINI_API_KEY", "test-gemini-key")
os.environ.setdefault("GEMINI_MODEL_NAME", "gemini-3.1-flash-lite")


@pytest.fixture(scope="session")
def function_app():
    """Import the Azure Function module once per test session."""
    import function_app as app_module

    return app_module
