from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import Depends

from social_automation.settings import Settings, load_settings


def get_settings() -> Settings:
    return load_settings()


def get_db_path(settings: Annotated[Settings, Depends(get_settings)]) -> Path:
    return settings.db_path


DbPathDep = Annotated[Path, Depends(get_db_path)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
