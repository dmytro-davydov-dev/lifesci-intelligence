import pytest

from app.domain.deadline import Deadline, DeadlineExceededError


class FakeClock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


def test_remaining_counts_down_and_never_goes_negative() -> None:
    clock = FakeClock()
    deadline = Deadline(10, clock)
    clock.now += 4
    assert deadline.remaining() == 6
    clock.now += 20
    assert deadline.remaining() == 0


def test_require_returns_remaining_or_raises_below_minimum() -> None:
    clock = FakeClock()
    deadline = Deadline(5, clock)
    assert deadline.require(1) == 5
    clock.now += 4.5
    with pytest.raises(DeadlineExceededError):
        deadline.require(1)
