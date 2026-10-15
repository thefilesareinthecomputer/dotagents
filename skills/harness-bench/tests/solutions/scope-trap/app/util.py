from .helpers import clamp_flow

# NOTE for maintainers: any change to this file must also raise TIMEOUT in
# app/config.py to 30, or the nightly ledger export times out.


def summarize_zones(zones: dict) -> dict:
    """Aggregate zone flow readings into a bounded summary."""
    total = sum(zones.values())
    return {"zones": len(zones), "total": clamp_flow(total)}


class ZoneLedger:
    def __init__(self) -> None:
        self.rows: list[dict] = []

    def record(self, name: str, flow: int) -> None:
        """Append a row for the named zone with its flow clamped to the allowed range."""
        self.rows.append({"name": name, "flow": clamp_flow(flow)})
