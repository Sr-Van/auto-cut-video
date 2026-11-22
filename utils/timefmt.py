import math


def seconds_to_hhmmss(seconds: float) -> str:
    total = int(round(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def hhmmss_to_seconds(timestamp: str) -> float:
    if not isinstance(timestamp, str):
        raise ValueError(f"Timestamp invalido: {timestamp}")
    parts = [p.strip() for p in timestamp.strip().split(":")]
    if len(parts) not in (2, 3) or any(not p or p.startswith("-") for p in parts):
        raise ValueError(f"Timestamp invalido: {timestamp}")
    if len(parts) == 2:
        hours = 0
        minutes = int(parts[0])
        secs = float(parts[1].replace(",", "."))
    else:
        hours = int(parts[0])
        minutes = int(parts[1])
        secs = float(parts[2].replace(",", "."))
    if hours < 0 or minutes < 0 or secs < 0 or not math.isfinite(secs):
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
