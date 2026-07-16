from __future__ import annotations

from social_automation.settings import Settings
from social_automation.visual.models import VisualReview
from social_automation.visual.review import decision_engine


def test_decision_engine_use_original() -> None:
    review = VisualReview(
        score=8.2,
        approved=True,
        needs_editing=False,
        reasoning="ok",
        suggested_format="instagram_4_5",
    )
    s = Settings(visual_review_score_use_original=8.0, visual_review_score_manual=5.0)
    d = decision_engine(review, settings=s)
    assert d.use_original is True
    assert d.needs_ai_editing is False


def test_decision_engine_needs_ai_editing() -> None:
    review = VisualReview(
        score=6.5,
        approved=True,
        needs_editing=True,
        reasoning="serve luce",
        suggested_format="instagram_4_5",
    )
    s = Settings(visual_review_score_use_original=8.0, visual_review_score_manual=5.0)
    d = decision_engine(review, settings=s)
    assert d.use_original is False
    assert d.needs_ai_editing is True


def test_decision_engine_manual_review() -> None:
    review = VisualReview(
        score=4.0,
        approved=False,
        needs_editing=True,
        reasoning="scarsa",
        suggested_format="instagram_4_5",
    )
    s = Settings(visual_review_score_use_original=8.0, visual_review_score_manual=5.0)
    d = decision_engine(review, settings=s)
    assert d.needs_manual_review is True
