"""Optional internal-triage trust ladder; never grants publishing authority."""
LEVELS = ("observe", "assist", "recommend")


def adjust_internal_trust(current: str, *, critical_miss: bool = False, clean_cycles: int = 0) -> str:
    if current not in LEVELS:
        current = "observe"
    index = LEVELS.index(current)
    if critical_miss:
        return LEVELS[max(0, index - 1)]
    if clean_cycles >= 3:
        return LEVELS[min(len(LEVELS) - 1, index + 1)]
    return current
