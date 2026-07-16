from pathlib import Path

from social_automation.config_loaders import load_schedule_yaml
from social_automation.models import Platform


def test_load_schedule_example() -> None:
    root = Path(__file__).resolve().parents[1]
    sched = load_schedule_yaml(root / "config" / "schedule.example.yaml")
    assert sched.timezone == "Europe/Rome"
    assert len(sched.slots) == 3
    assert sched.slots[0].platforms == [Platform.INSTAGRAM, Platform.FACEBOOK]
