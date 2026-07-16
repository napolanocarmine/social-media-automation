"""Caricamento knowledge base e configurazione Story AI Assistant."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from social_automation.settings import Settings, load_settings, repo_root

_DEFAULT_SYSTEM = Path("config/brand/story_system.md")
_DEFAULT_BUSINESS_RULES = Path("config/brand/story_business_rules.md")
_DEFAULT_KB_LEGACY = Path("config/brand/Story_Food_Drink_AI_Knowledge_Base_v1.2.md")
_DEFAULT_AGENT_MD = Path("config/brand/story_agent.md")
_DEFAULT_AGENT_YAML = Path("config/brand/story_agent.yaml")

_TASK_SECTION_RE = re.compile(
    r"^# (meta|produce_prompt|retouch_prompt|copy_prompt|auto_prompt)\s*$",
    re.MULTILINE,
)


@dataclass(frozen=True)
class StoryAgentConfig:
    """Configurazione Story AI a 3 layer."""

    name: str
    system_preamble: str
    business_rules_text: str
    retouch_prompt: str
    copy_prompt: str
    produce_prompt: str
    auto_prompt: str

    @property
    def knowledge_text(self) -> str:
        """Alias retrocompatibile → Layer 2."""
        return self.business_rules_text


def _read_text(path: Path) -> str:
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8").strip()


def _parse_task_sections_md(text: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    if not text.strip():
        return sections
    matches = list(_TASK_SECTION_RE.finditer(text))
    for idx, match in enumerate(matches):
        key = match.group(1)
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        sections[key] = text[start:end].strip()
    meta = sections.get("meta", "")
    name = "Story AI Assistant"
    if meta:
        for line in meta.splitlines():
            if line.strip().lower().startswith("name:"):
                name = line.split(":", 1)[1].strip() or name
                break
    sections.setdefault("name", name)
    return sections


def _load_task_sections(path: Path) -> dict[str, str]:
    if path.suffix.lower() == ".md":
        return _parse_task_sections_md(_read_text(path))
    data = yaml.safe_load(_read_text(path) or "{}") or {}
    return {
        "name": str(data.get("name") or "Story AI Assistant"),
        "retouch_prompt": str(data.get("retouch_prompt") or "").strip(),
        "copy_prompt": str(data.get("copy_prompt") or "").strip(),
        "produce_prompt": str(data.get("produce_prompt") or "").strip(),
        "auto_prompt": str(data.get("auto_prompt") or "").strip(),
    }


def _resolve_path(path: Path | None, *, defaults: tuple[Path, ...]) -> Path:
    if path is not None and path.is_file():
        return path
    if path is not None and not path.is_file():
        candidate = path
        if candidate.is_file():
            return candidate
    for candidate in defaults:
        if candidate.is_file():
            return candidate
    return defaults[0]


def load_story_agent_config(
    *,
    agent_yaml: Path | None = None,
    knowledge_path: Path | None = None,
    system_path: Path | None = None,
    business_rules_path: Path | None = None,
) -> StoryAgentConfig:
    """
    Carica la configurazione Story AI.

    Layer 1 — ``story_system.md``: identità agente
    Layer 2 — ``story_business_rules.md``: regole brand (tone, pillar, crop, …)
    Layer 3 — ``story_agent.md``: template task (/produce, /copy, …)
    """
    root = repo_root()
    s = load_settings()

    system_file = _resolve_path(
        system_path or s.story_system_path,
        defaults=(root / _DEFAULT_SYSTEM,),
    )
    rules_file = _resolve_path(
        business_rules_path or s.story_business_rules_path,
        defaults=(
            root / _DEFAULT_BUSINESS_RULES,
            knowledge_path or s.brand_knowledge_path,
            root / _DEFAULT_KB_LEGACY,
        ),
    )
    tasks_file = _resolve_path(
        agent_yaml or s.story_agent_config_path,
        defaults=(root / _DEFAULT_AGENT_MD, root / _DEFAULT_AGENT_YAML),
    )

    tasks = _load_task_sections(tasks_file)
    return StoryAgentConfig(
        name=str(tasks.get("name") or "Story AI Assistant"),
        system_preamble=_read_text(system_file),
        business_rules_text=_read_text(rules_file),
        retouch_prompt=str(tasks.get("retouch_prompt") or "").strip(),
        copy_prompt=str(tasks.get("copy_prompt") or "").strip(),
        produce_prompt=str(tasks.get("produce_prompt") or "").strip(),
        auto_prompt=str(tasks.get("auto_prompt") or "").strip(),
    )


def build_system_message(cfg: StoryAgentConfig) -> str:
    """
    Layer 1 + Layer 2 per chiamate chat (``role: system``).

    Il Layer 3 (task) va nel messaggio user separato.
    """
    parts: list[str] = []
    if cfg.system_preamble.strip():
        parts.append(cfg.system_preamble.strip())
    if cfg.business_rules_text.strip():
        parts.append("\n\n--- BUSINESS RULES ---\n\n")
        parts.append(cfg.business_rules_text.strip())
    return "".join(parts).strip()


def build_brand_context_message(cfg: StoryAgentConfig | None = None) -> str:
    """Layer 1 + 2 (contesto brand completo, senza task)."""
    return build_system_message(cfg or load_story_agent_config())


def pillar_for_category(category: str | None) -> str:
    c = (category or "").strip().lower()
    mapping = {
        "food": "food",
        "birra": "food",
        "beer": "food",
        "boss": "staff",
        "peppe": "staff",
        "locale": "community",
        "community": "community",
    }
    return mapping.get(c, "community")
