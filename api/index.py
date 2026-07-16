"""ASGI entrypoint per Vercel Python runtime."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _bootstrap_paths() -> Path:
    """Make ``social_automation`` importable in the Vercel ``/var/task`` layout."""
    entry_dir = Path(__file__).resolve().parent
    candidates: list[Path] = [
        entry_dir.parent / "src",
        Path("/var/task/src"),
        entry_dir.parent,
    ]

    project_root: Path | None = None
    for src_dir in candidates:
        if not (src_dir / "social_automation").is_dir():
            continue
        src_path = str(src_dir)
        if src_path not in sys.path:
            sys.path.insert(0, src_path)
        if (src_dir.parent / "config").is_dir():
            project_root = src_dir.parent
        elif (src_dir / "config").is_dir():
            project_root = src_dir
        else:
            project_root = src_dir.parent
        break

    if project_root is None:
        checked = ", ".join(str(path) for path in candidates)
        raise ModuleNotFoundError(
            "No module named 'social_automation' (checked: "
            f"{checked}). Ensure src/ is bundled via includeFiles."
        )

    os.environ.setdefault("SOCIAL_AUTOMATION_ROOT", str(project_root))
    return project_root


_bootstrap_paths()

from social_automation.api.main import app  # noqa: E402

__all__ = ["app"]
