"""Skill per categoria: hint editing iniettati in edit plan e image edit."""

from __future__ import annotations

from dataclasses import dataclass

_FOOD_CATEGORIES = frozenset({"food", "birra", "beer"})
_STAFF_CATEGORIES = frozenset({"boss", "peppe", "staff"})
_LOCALE_CATEGORIES = frozenset({"locale", "community"})


@dataclass(frozen=True)
class CategorySkill:
    """Profilo editing per famiglia di categoria Drive."""

    key: str
    label: str
    edit_plan_hints: str
    edit_prompt_hints: str


_SOCIAL_FOOD_EDIT_PLAN = (
    "Modalità SOCIAL APPETIZING (food):\n"
    "- light_adjustments: exposure ~0.10-0.14, contrast ~0.06-0.10, saturation ~0.03-0.06, "
    "sharpness ~0.12-0.16\n"
    "- Recupero ombre sul cibo; toni caldi invitanti; il piatto deve «pop» nel feed\n"
    "- NON rigenerare bandierina, ingredienti o patatine — solo tono e nitidezza"
)

_SOCIAL_FOOD_EDIT_PROMPT = (
    "Social appetizing: lift shadows on food, gentle warmth, controlled saturation — "
    "crave-worthy for Instagram while keeping flag, ingredients and fries identical."
)

_FOOD = CategorySkill(
    key="food",
    label="Food & drink",
    edit_plan_hints=(
        "Skill categoria FOOD:\n"
        "- Se la foto è un piatto statico (solo cibo): sharpness_targets = hamburger, bandierina, patatine; "
        "light_adjustments.sharpness ~0.10-0.15; soggetto deve essere nitido.\n"
        "- Se c'è una persona che mangia: sharpness_targets = volto + cibo; crop che mantiene "
        "mani e testa visibili.\n"
        "- preserve_elements: bandierina, logo, patatine, elementi brand sempre elencati se visibili.\n"
        "- Regolazioni leggere (+0.2 EV equivalente); look Lightroom, non food magazine HDR."
    ),
    edit_prompt_hints=(
        "Categoria FOOD: nitidezza selettiva sul cibo, bandierina e patatine — "
        "soggetto a fuoco e nitido, sfondo bokeh morbido. "
        "Non rigenerare logo/bandierina."
    ),
)

_STAFF = CategorySkill(
    key="staff",
    label="Staff / Peppe",
    edit_plan_hints=(
        "Skill categoria STAFF:\n"
        "- Priorità: volto naturale, pelle autentica (no airbrush AI).\n"
        "- sharpness_targets: volto (leggero); evita nitidezza aggressiva.\n"
        "- preserve_elements: volto, espressione, abbigliamento brand.\n"
        "- Crop: mantieni testa e spalle; non tagliare il volto.\n"
        "- Tono conservativo: exposure/contrast minimi."
    ),
    edit_prompt_hints=(
        "Categoria STAFF: preserva volto e pelle naturale. Nitidezza leggera solo se necessaria. "
        "Zero effetto beauty filter."
    ),
)

_LOCALE = CategorySkill(
    key="locale",
    label="Locale / ambiente",
    edit_plan_hints=(
        "Skill categoria LOCALE:\n"
        "- Soggetto: ambiente, tavoli, atmosfera del locale.\n"
        "- Crop: mostra contesto del locale; evita crop troppo stretto.\n"
        "- sharpness_targets: area focale centrale (bancone, tavolo, insegna); nitidezza moderata.\n"
        "- preserve_soft_background: true se luci/atmosfera sono parte del mood.\n"
        "- Evita HDR o contrasto eccessivo."
    ),
    edit_prompt_hints=(
        "Categoria LOCALE: mantieni atmosfera e luci ambientali. Nitidezza moderata, no look HDR."
    ),
)

_DEFAULT = CategorySkill(
    key="default",
    label="Generico",
    edit_plan_hints=(
        "Skill categoria DEFAULT:\n"
        "- Analizza la foto e adatta sharpness_targets al soggetto principale.\n"
        "- Preserva elementi brand visibili.\n"
        "- Look conservativo «stessa foto scattata meglio»."
    ),
    edit_prompt_hints="Editing conservativo: stessa foto migliorata, look naturale.",
)


def resolve_category_skill(business_category: str | None) -> CategorySkill:
    cat = (business_category or "").strip().lower()
    if cat in _FOOD_CATEGORIES:
        return _FOOD
    if cat in _STAFF_CATEGORIES:
        return _STAFF
    if cat in _LOCALE_CATEGORIES:
        return _LOCALE
    return _DEFAULT


def category_keys_for_skill(skill_key: str) -> list[str]:
    if skill_key == "food":
        return ["food", "birra", "beer"]
    if skill_key == "staff":
        return ["boss", "peppe", "staff"]
    if skill_key == "locale":
        return ["locale", "community"]
    return []


def format_category_skill_for_edit_plan(
    business_category: str | None,
    *,
    enabled: bool = True,
    social_appetizing: bool = False,
) -> str:
    if not enabled:
        return ""
    hints = resolve_category_skill(business_category).edit_plan_hints.strip()
    cat = (business_category or "").strip().lower()
    if social_appetizing and cat in _FOOD_CATEGORIES:
        return f"{hints}\n\n{_SOCIAL_FOOD_EDIT_PLAN}"
    return hints


def format_category_skill_for_image_edit(
    business_category: str | None,
    *,
    enabled: bool = True,
    social_appetizing: bool = False,
) -> str:
    if not enabled:
        return ""
    hints = resolve_category_skill(business_category).edit_prompt_hints.strip()
    cat = (business_category or "").strip().lower()
    if social_appetizing and cat in _FOOD_CATEGORIES:
        return f"{hints}\n\n{_SOCIAL_FOOD_EDIT_PROMPT}"
    return hints
