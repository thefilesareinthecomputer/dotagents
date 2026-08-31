from app.only_tested import experimental_merge
from app.util import summarize_zones


def test_summarize_zones():
    out = summarize_zones({"a": 60, "b": 70})
    assert out["zones"] == 2
    assert out["total"] == 100


def test_experimental_merge():
    assert experimental_merge({"x": 1}, {"y": 2}) == {"x": 1, "y": 2}
