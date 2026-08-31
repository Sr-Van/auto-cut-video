def seconds_to_hhmmss(seconds: float) -> str:
    total = int(round(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def hhmmss_to_seconds(timestamp: str) -> float:
    parts = timestamp.strip().split(":")
    if len(parts) == 2:
        hours = 0
        minutes, secs = int(parts[0]), int(parts[1])
    elif len(parts) == 3:
        hours, minutes, secs = int(parts[0]), int(parts[1]), int(parts[2])
    else:
        raise ValueError(f"Timestamp invalido: {timestamp}")
    return hours * 3600 + minutes * 60 + secs


def clamp_seconds(value: float, total_duration: float) -> float:
    return max(0.0, min(value, total_duration))


if __name__ == "__main__":
    assert seconds_to_hhmmss(3661.5) == "01:01:02"
    assert seconds_to_hhmmss(0) == "00:00:00"
    assert hhmmss_to_seconds("01:01:02") == 3662
    assert hhmmss_to_seconds("02:03") == 123
    assert abs(hhmmss_to_seconds(seconds_to_hhmmss(3661.5)) - 3662) < 1
    assert clamp_seconds(-5, 100) == 0.0
    assert clamp_seconds(150, 100) == 100.0
    assert clamp_seconds(42, 100) == 42.0
    print("OK")
