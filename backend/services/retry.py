"""Exponential-backoff retry for Gemini API calls.

Retries on transient server-side errors (503, 429, 500, connection issues).
Passes through non-retryable errors (400, 401, 403, 404) immediately.
"""

from __future__ import annotations

import asyncio
import logging
import random

logger = logging.getLogger(__name__)

# HTTP status codes / error substrings that indicate a transient failure
_RETRYABLE_SIGNALS = (
    "503",
    "500",
    "429",
    "resource exhausted",
    "unavailable",
    "internal",
    "deadline exceeded",
    "connection",
    "timeout",
    "overloaded",
    "too many requests",
)

_NON_RETRYABLE_SIGNALS = (
    "400",
    "401",
    "403",
    "404",
    "invalid",
    "api key",
    "not found",
    "permission",
)


def _is_retryable(exc: Exception) -> bool:
    msg = str(exc).lower()
    if any(s in msg for s in _NON_RETRYABLE_SIGNALS):
        return False
    return any(s in msg for s in _RETRYABLE_SIGNALS)


async def call_with_retry(
    fn,
    *args,
    max_retries: int = 3,
    base_delay: float = 2.0,
    **kwargs,
):
    """Run ``fn(*args, **kwargs)`` in a thread with exponential-backoff retry.

    Args:
        fn:          Synchronous callable to run via asyncio.to_thread.
        max_retries: Maximum number of retry attempts (default 3).
        base_delay:  Initial backoff in seconds; doubles each retry.

    Returns:
        Whatever ``fn`` returns.

    Raises:
        The last exception if all attempts fail or error is non-retryable.
    """
    last_exc: Exception | None = None

    for attempt in range(max_retries + 1):
        try:
            return await asyncio.to_thread(fn, *args, **kwargs)
        except Exception as exc:
            last_exc = exc

            if not _is_retryable(exc) or attempt == max_retries:
                raise

            wait = base_delay * (2 ** attempt) + random.uniform(0, 1)
            logger.warning(
                "Gemini API transient error (attempt %d/%d): %s — retrying in %.1fs",
                attempt + 1,
                max_retries,
                exc,
                wait,
            )
            await asyncio.sleep(wait)

    raise last_exc  # type: ignore[misc]
