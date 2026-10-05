import pytest

from workers.audio_analysis.retry_policy import retry_delay_seconds


def test_retry_delay_is_bounded_exponential() -> None:
    assert [retry_delay_seconds(attempt) for attempt in range(1, 7)] == [2, 4, 8, 16, 32, 60]


def test_retry_delay_rejects_invalid_attempt() -> None:
    with pytest.raises(ValueError):
        retry_delay_seconds(0)
