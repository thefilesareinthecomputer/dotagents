MAX_FLOW = 100


def clamp_flow(value: int) -> int:
    return max(0, min(MAX_FLOW, value))
