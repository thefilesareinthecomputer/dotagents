"""Flow unit conversion to litres per minute."""

# lpm: litres per minute; gpm: US gallons per minute; lps: litres per second
FACTORS_TO_LPM = {"lpm": 1.0, "gpm": 3.785411784, "lps": 60.0}


def to_lpm(value: float, unit: str) -> float:
    try:
        return value * FACTORS_TO_LPM[unit]
    except KeyError:
        raise ValueError(f"unknown unit {unit!r}") from None
