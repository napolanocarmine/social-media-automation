"""Tracing step pipeline AI (latency, skip, metadati)."""

from __future__ import annotations

import logging
import time
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Callable, TypeVar

_LOG = logging.getLogger(__name__)

T = TypeVar("T")

_current_trace: ContextVar[PipelineTrace | None] = ContextVar(
    "pipeline_trace",
    default=None,
)


@dataclass
class PipelineStepRecord:
    name: str
    latency_ms: float
    skipped: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PipelineTrace:
    photo_id: str = ""
    steps: list[PipelineStepRecord] = field(default_factory=list)

    def record_step(
        self,
        name: str,
        *,
        latency_ms: float,
        skipped: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.steps.append(
            PipelineStepRecord(
                name=name,
                latency_ms=latency_ms,
                skipped=skipped,
                metadata=metadata or {},
            )
        )

    def run(self, name: str, fn: Callable[[], T], **metadata: Any) -> T:
        start = time.perf_counter()
        try:
            result = fn()
        except Exception as exc:
            elapsed = (time.perf_counter() - start) * 1000.0
            self.record_step(
                name,
                latency_ms=elapsed,
                metadata={**metadata, "error": str(exc)},
            )
            raise
        elapsed = (time.perf_counter() - start) * 1000.0
        self.record_step(name, latency_ms=elapsed, metadata=metadata)
        return result

    def skip(self, name: str, *, reason: str = "") -> None:
        self.record_step(
            name,
            latency_ms=0.0,
            skipped=True,
            metadata={"reason": reason} if reason else {},
        )

    @property
    def total_latency_ms(self) -> float:
        return sum(s.latency_ms for s in self.steps if not s.skipped)

    def to_dict(self) -> dict[str, Any]:
        return {
            "photo_id": self.photo_id,
            "total_latency_ms": round(self.total_latency_ms, 1),
            "steps": [
                {
                    "name": s.name,
                    "latency_ms": round(s.latency_ms, 1),
                    "skipped": s.skipped,
                    **({"metadata": s.metadata} if s.metadata else {}),
                }
                for s in self.steps
            ],
        }

    def log_summary(self) -> None:
        parts = []
        for step in self.steps:
            if step.skipped:
                reason = step.metadata.get("reason", "")
                parts.append(f"{step.name}(skip{': ' + reason if reason else ''})")
            else:
                parts.append(f"{step.name}({step.latency_ms:.0f}ms)")
        _LOG.info(
            "Pipeline trace photo=%s total=%.0fms | %s",
            self.photo_id or "?",
            self.total_latency_ms,
            " → ".join(parts),
        )


def start_pipeline_trace(*, photo_id: str = "") -> PipelineTrace:
    trace = PipelineTrace(photo_id=photo_id)
    _current_trace.set(trace)
    return trace


def get_pipeline_trace() -> PipelineTrace | None:
    return _current_trace.get()


def end_pipeline_trace(*, log: bool = True) -> PipelineTrace | None:
    trace = _current_trace.get()
    if trace is None:
        return None
    if log:
        trace.log_summary()
    _current_trace.set(None)
    return trace
