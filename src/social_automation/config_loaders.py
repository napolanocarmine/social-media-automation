from __future__ import annotations

from pathlib import Path

import yaml

from social_automation.models import EditorialSchedule, Platform, ScheduleSlot


def load_schedule_yaml(path: Path) -> EditorialSchedule:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    tz = data.get("timezone", "Europe/Rome")
    slots_raw = data.get("slots", [])
    slots: list[ScheduleSlot] = []
    for row in slots_raw:
        platforms = [Platform(p) for p in row["platforms"]]
        cat_raw = row.get("category")
        category = str(cat_raw).strip().lower() if cat_raw else None
        slots.append(
            ScheduleSlot(
                platforms=platforms,
                weekday=str(row["weekday"]).lower(),
                time_hhmm=str(row["time"]),
                category=category or None,
            )
        )
    return EditorialSchedule(timezone=tz, slots=slots)


def load_categories_yaml(path: Path) -> dict:
    """Restituisce il dict YAML (drive_root_folder_id + categories)."""
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def load_category_aliases(path: Path) -> dict[str, str]:
    """Carica alias categoria raw->business da categories YAML."""
    data = load_categories_yaml(path) or {}
    aliases_raw = data.get("category_aliases", {})
    aliases = {str(k).lower(): str(v).lower() for k, v in aliases_raw.items()}
    if aliases:
        return aliases
    # backward compatibility con vecchio schema categories:
    # categories: {boss: {folder_id...}, birra: {...}}
    categories = data.get("categories", {})
    return {str(name).lower(): str(name).lower() for name in categories.keys()}


def resolve_schedule_path(path: Path | None = None) -> Path:
    """Path al calendario editoriale (operativo o example)."""
    from social_automation.settings import repo_root

    if path is not None and path.is_file():
        return path
    for candidate in (
        repo_root() / "config" / "schedule.yaml",
        repo_root() / "config" / "schedule.example.yaml",
    ):
        if candidate.is_file():
            return candidate
    return repo_root() / "config" / "schedule.yaml"


def load_canva_yaml(path: Path) -> dict:
    """Carica mapping template Canva per piattaforma/categoria."""
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def resolve_drive_folder_id(
    *,
    folder_id_arg: str,
    folder_id_env: str,
    categories_yaml: Path | None = None,
) -> str:
    """Ordine: --folder-id, GOOGLE_DRIVE_FOLDER_ID, drive_root_folder_id nel YAML categorie."""
    fid = (folder_id_arg or "").strip() or (folder_id_env or "").strip()
    if fid:
        return fid
    if categories_yaml is not None and categories_yaml.is_file():
        data = load_categories_yaml(categories_yaml) or {}
        fid = str(data.get("drive_root_folder_id", "") or "").strip()
    return fid
