"""
Retry utility with exponential backoff for Twitch Marker Agent.

Provides a synchronous retry decorator/wrapper for API calls that may
fail due to rate limits, network issues, or temporary Twitch errors.

TODO: Add async variant once EventSub WS implementation details are decided.
"""

from __future__ import annotations

import logging
import random
import time
from typing import Callable, TypeVar, ParamSpec

P = ParamSpec("P")
T = TypeVar("T")


class RetryError(Exception):
    """Raised when all retry attempts are exhausted."""

    def __init__(self, message: str, last_exception: Exception | None = None) -> None:
        super().__init__(message)
        self.last_exception = last_exception


def calculate_backoff(
    attempt: int,
    base_delay: float,
    max_delay: float,
    jitter: bool = True,
) -> float:
    """
    Calculate exponential backoff delay for a given attempt.

    Args:
        attempt: Current attempt number (0-indexed).
        base_delay: Base delay in seconds.
        max_delay: Maximum delay cap in seconds.
        jitter: If True, add random jitter to prevent thundering herd.

    Returns:
        Delay in seconds before next retry.
    """
    # Exponential: base_delay * 2^attempt
    delay = base_delay * (2 ** attempt)

    # Cap at max_delay
    delay = min(delay, max_delay)

    # Add jitter (±25%)
    if jitter:
        jitter_range = delay * 0.25
        delay = delay + random.uniform(-jitter_range, jitter_range)

    return max(0, delay)


def retry_with_backoff(
    fn: Callable[P, T],
    max_attempts: int = 5,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    retryable_exceptions: tuple[type[Exception], ...] = (Exception,),
    logger: logging.Logger | None = None,
) -> T:
    """
    Execute a function with exponential backoff retry.

    Args:
        fn: Function to execute (should be a zero-argument callable,
            use functools.partial or lambda to wrap functions with args).
        max_attempts: Maximum number of attempts before giving up.
        base_delay: Initial delay between retries in seconds.
        max_delay: Maximum delay between retries in seconds.
        retryable_exceptions: Tuple of exception types that trigger retry.
        logger: Optional logger for retry messages.

    Returns:
        Return value of the function on success.

    Raises:
        RetryError: If all attempts are exhausted.

    Example:
        >>> from functools import partial
        >>> result = retry_with_backoff(
        ...     partial(fetch_markers, video_id="12345"),
        ...     max_attempts=3,
        ...     base_delay=1.0,
        ... )
    """
    last_exception: Exception | None = None

    for attempt in range(max_attempts):
        try:
            return fn()
        except retryable_exceptions as e:
            last_exception = e

            if attempt == max_attempts - 1:
                # Last attempt, don't retry
                break

            delay = calculate_backoff(attempt, base_delay, max_delay)

            if logger:
                logger.warning(
                    f"Attempt {attempt + 1}/{max_attempts} failed: {e}. "
                    f"Retrying in {delay:.2f}s..."
                )

            time.sleep(delay)

    raise RetryError(
        f"All {max_attempts} attempts failed",
        last_exception=last_exception,
    )


# TODO: Async variant for use with EventSub WebSocket
# async def retry_with_backoff_async(
#     fn: Callable[P, Awaitable[T]],
#     max_attempts: int = 5,
#     base_delay: float = 1.0,
#     max_delay: float = 60.0,
#     retryable_exceptions: tuple[type[Exception], ...] = (Exception,),
#     logger: logging.Logger | None = None,
# ) -> T:
#     """Async version of retry_with_backoff."""
#     raise NotImplementedError("TODO: Implement async retry")
