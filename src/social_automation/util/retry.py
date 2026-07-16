"""Retry con backoff esponenziale per chiamate idempotenti o sicure da ripetere."""

from __future__ import annotations

import random
import time
from collections.abc import Callable, Sequence
from typing import TypeVar

import httpx

T = TypeVar("T")


def retry_http(
    fn: Callable[[], T],
    *,
    max_attempts: int = 4,
    base_delay_s: float = 1.0,
    max_delay_s: float = 30.0,
    retry_statuses: Sequence[int] = (429, 500, 502, 503, 504),
) -> T:
    """Esegue ``fn``; ritenta su HTTP status ammessi o errori di rete (httpx)."""
    for attempt in range(max_attempts):
        try:
            return fn()
        except httpx.HTTPStatusError as e:
            code = e.response.status_code
            if code not in retry_statuses or attempt == max_attempts - 1:
                raise
        except (httpx.TransportError, httpx.TimeoutException) as e:
            if attempt == max_attempts - 1:
                raise e
        delay = min(max_delay_s, base_delay_s * (2**attempt))
        time.sleep(delay + random.uniform(0, 0.25))
    raise RuntimeError("retry_http: unexpected fallthrough")
