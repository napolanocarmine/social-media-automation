from __future__ import annotations

from pathlib import Path


def project_root() -> Path:
    """Root del repository (contiene `src/social_automation/`)."""
    return Path(__file__).resolve().parents[3]
