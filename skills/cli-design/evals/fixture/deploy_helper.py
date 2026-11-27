#!/usr/bin/env python3
"""Deploy the current build to an environment."""
import sys


def main():
    env = sys.argv[1] if len(sys.argv) > 1 else "staging"
    print("About to deploy to %s." % env)
    answer = input("Continue? [y/N] ")
    if answer.strip().lower() != "y":
        print("Cancelled.")
        return 0
    print("Deploying to %s..." % env)
    print("Deployed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
