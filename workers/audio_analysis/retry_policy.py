def retry_delay_seconds(attempt_count: int, base_seconds: int = 2, maximum_seconds: int = 60) -> int:
    if attempt_count < 1:
        raise ValueError("attempt_count must be at least 1")
    if base_seconds < 1 or maximum_seconds < base_seconds:
        raise ValueError("retry delay bounds are invalid")
    return min(maximum_seconds, base_seconds * (2 ** (attempt_count - 1)))
