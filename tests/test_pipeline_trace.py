from __future__ import annotations

from social_automation.visual.pipeline_trace import PipelineTrace


def test_pipeline_trace_records_steps() -> None:
    trace = PipelineTrace(photo_id="abc")
    result = trace.run("step_a", lambda: 42)
    trace.skip("step_b", reason="disabled")
    assert result == 42
    assert len(trace.steps) == 2
    assert trace.steps[0].name == "step_a"
    assert trace.steps[0].skipped is False
    assert trace.steps[1].skipped is True
    payload = trace.to_dict()
    assert payload["photo_id"] == "abc"
    assert payload["total_latency_ms"] >= 0
