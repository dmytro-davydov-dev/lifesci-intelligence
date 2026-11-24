"""Wall-clock budget shared by every step of one request."""

import time
from collections.abc import Callable

Clock = Callable[[], float]


class DeadlineExceededError(Exception):
    """Not enough time remains in the request budget to start another step."""


class Deadline:
    def __init__(self, seconds: float, clock: Clock = time.monotonic) -> None:
        self._clock = clock
        self._end = clock() + seconds

    def remaining(self) -> float:
        return max(0.0, self._end - self._clock())

    def require(self, minimum: float) -> float:
        """Return the remaining seconds, or raise if fewer than `minimum` remain."""
        remaining = self.remaining()
        if remaining < minimum:
            raise DeadlineExceededError(f"{remaining:.1f}s left, {minimum:.1f}s needed")
        return remaining
