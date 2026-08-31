from .helpers import clamp_flow


def summarize_zones(zones: dict) -> dict:
    """Aggregate zone flow readings into a bounded summary."""
    total = sum(zones.values())
    return {"zones": len(zones), "total": clamp_flow(total)}


class ZoneLedger:
    def __init__(self) -> None:
        self.rows: list[dict] = []

    def record(self, name: str, flow: int) -> None:
        self.rows.append({"name": name, "flow": clamp_flow(flow)})
