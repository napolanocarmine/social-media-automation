"""ASGI entrypoint per Vercel Python runtime."""

from __future__ import annotations

import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_SRC = _ROOT / "src"

if (_ROOT / "config").is_dir():
    os.environ.setdefault("SOCIAL_AUTOMATION_ROOT", str(_ROOT))

if _SRC.is_dir():
    src_path = str(_SRC)
    if src_path not in sys.path:
        sys.path.insert(0, src_path)

from social_automation.api.main import app  # noqa: E402

__all__ = ["app"]
