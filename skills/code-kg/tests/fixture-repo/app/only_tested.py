"""Reached by the test suite only - no production path imports it."""


def experimental_merge(a: dict, b: dict) -> dict:
    return {**a, **b}
