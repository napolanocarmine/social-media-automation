"""Filtraggio sezioni KB per task (riduce token input)."""

from __future__ import annotations

import re
from enum import StrEnum
from functools import lru_cache

_SECTION_HEADER_RE = re.compile(r"^# (\d+)\.\s", re.MULTILINE)


class KbScope(StrEnum):
    """Ambiti di knowledge base da iniettare nel system prompt."""

    FULL = "full"
    COPY = "copy"
    EDIT = "edit"
    EDIT_PLAN = "edit_plan"
    RETOUCH = "retouch"
    VISUAL_REVIEW = "visual_review"
    IMAGE_EDIT = "image_edit"


_SCOPE_SECTIONS: dict[KbScope, frozenset[int]] = {
    KbScope.FULL: frozenset(range(1, 18)),
    KbScope.COPY: frozenset({1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14}),
    KbScope.EDIT: frozenset({2, 8, 9, 15, 16, 17}),
    KbScope.EDIT_PLAN: frozenset({8, 9, 15, 16, 17}),
    KbScope.RETOUCH: frozenset({15, 16, 17}),
    KbScope.VISUAL_REVIEW: frozenset({8, 15, 16}),
    KbScope.IMAGE_EDIT: frozenset({2, 8, 9, 15, 16, 17}),
}


def scope_for_task(task: str) -> KbScope:
    """Mappa nome task → scope KB."""
    mapping = {
        "copy": KbScope.COPY,
        "retouch": KbScope.RETOUCH,
        "auto": KbScope.COPY,
        "edit_plan": KbScope.EDIT_PLAN,
        "visual_review": KbScope.VISUAL_REVIEW,
        "image_edit": KbScope.IMAGE_EDIT,
        "produce": KbScope.EDIT,
    }
    return mapping.get(task.strip().lower(), KbScope.FULL)


@lru_cache(maxsize=64)
def filter_business_rules(text: str, scope: KbScope) -> str:
    """
    Estrae solo le sezioni numerate rilevanti per lo scope.

    Se il testo non contiene sezioni numerate, restituisce il testo intero
    (retrocompatibilità con KB legacy non strutturate).
    """
    raw = (text or "").strip()
    if not raw or scope == KbScope.FULL:
        return raw

    matches = list(_SECTION_HEADER_RE.finditer(raw))
    if not matches:
        return raw

    allowed = _SCOPE_SECTIONS.get(scope, _SCOPE_SECTIONS[KbScope.FULL])
    parts: list[str] = []
    for idx, match in enumerate(matches):
        section_num = int(match.group(1))
        if section_num not in allowed:
            continue
        start = match.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(raw)
        chunk = raw[start:end].strip()
        if chunk:
            parts.append(chunk)
    return "\n\n---\n\n".join(parts).strip()
