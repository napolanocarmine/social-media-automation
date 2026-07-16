from __future__ import annotations

from social_automation.visual.models import ImageEditPlan


def test_image_edit_plan_from_dict_full() -> None:
    plan = ImageEditPlan.from_dict(
        {
            "subjects": ["hamburger", "patatine"],
            "preserve_elements": ["bandierina", "patatine"],
            "crop_plan": "Centra l'hamburger; patatine visibili a destra.",
            "sharpness_targets": ["hamburger"],
            "preserve_soft_background": True,
            "adjustments_notes": "+0.2 EV",
            "reasoning": "Piatto food statico",
        }
    )
    assert plan.subjects == ("hamburger", "patatine")
    assert plan.preserve_elements == ("bandierina", "patatine")
    assert plan.crop_plan.startswith("Centra")
    assert plan.sharpness_targets == ("hamburger",)
    assert plan.preserve_soft_background is True
    assert plan.has_content is True


def test_image_edit_plan_from_dict_partial() -> None:
    plan = ImageEditPlan.from_dict({})
    assert plan.subjects == ()
    assert plan.crop_plan == ""
    assert plan.preserve_soft_background is False
    assert plan.light_adjustments.exposure == 0.0
    assert plan.has_content is False


def test_image_edit_plan_person_food() -> None:
    plan = ImageEditPlan.from_dict(
        {
            "subjects": ["persona", "cibo"],
            "sharpness_targets": ["volto", "cibo"],
            "crop_plan": "Volto in alto a sinistra.",
            "preserve_soft_background": True,
        }
    )
    assert plan.sharpness_targets == ("volto", "cibo")
    assert plan.has_content is True
