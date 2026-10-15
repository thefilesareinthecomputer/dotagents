"""Entry point: reads a report query and prints totals."""
import argparse
import json
import sys

from app.export import to_csv
from app.util import summarize_zones

REPORT_SQL = "queries/report.sql"


def load_report_sql() -> str:
    with open(REPORT_SQL, encoding="utf-8") as fh:
        return fh.read()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--format", choices=("json", "csv"), default="json")
    args = ap.parse_args(argv)
    zones = {"north": 3, "south": 5}
    summary = summarize_zones(zones)
    if args.format == "csv":
        sys.stdout.write(to_csv([("zone", "flow"), *zones.items(), ("total", summary["total"])]))
    else:
        print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
