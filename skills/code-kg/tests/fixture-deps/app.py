"""Tiny app whose imports exercise dependency indexing."""
import helperlib
import missingpkg  # installed nowhere: must stay a plain external
from helperlib.core import clamp


def main() -> int:
    print(clamp(helperlib.DEFAULT, 0, 10))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
