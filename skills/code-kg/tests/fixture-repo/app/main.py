"""Entry point: reads a report query and prints totals."""
import json

import app.missing  # deliberately unresolved: exercises the worklist
from app.util import summarize_zones

REPORT_SQL = "queries/report.sql"


def load_report_sql() -> str:
    with open(REPORT_SQL, encoding="utf-8") as fh:
        return fh.read()


def main() -> int:
    zones = {"north": 3, "south": 5}
    print(json.dumps(summarize_zones(zones)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
