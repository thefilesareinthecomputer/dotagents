#!/usr/bin/env python3
"""stats.py - a statistics calculator that carries its assumptions with it.

Every command reports n, the rows it could not use, the method it chose and the
assumption that would overturn the answer. Every randomized command takes
--seed and records it. Every command takes --json and --manifest PATH; the
manifest is the input format for stats_check.py, the auditor.

Floor is the Python 3.10+ standard library. numpy, scipy and pandas are
detected at import and used only where they cannot change a primary number:
pandas reads non-CSV tabular input, and numpy or scipy supply an independent
cross-check of results computed here. A primary number is always the stdlib
number, so the same input and seed give the same output on a machine with the
optional libraries and on one without.

Numbers are rounded only when rendered as text. --json carries full precision.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import math
import random
import re
import statistics
import sys
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Sequence

MAD_TO_SIGMA = 1.4826  # consistency factor: makes MAD estimate sigma on normal data
MODIFIED_Z_CUTOFF = 3.5  # Iglewicz & Hoaglin (1993)
DEFAULT_ALPHA = 0.05
DEFAULT_REPS = 10_000

# Asymptotic Dickey-Fuller tau critical values, constant-only case, from
# Fuller (1976) as reproduced in every standard time-series text. Asymptotic,
# not finite-sample: they are reported labeled as such and never as exact.
ADF_TAU_MU = {"1%": -3.43, "5%": -2.86, "10%": -2.57}


# --------------------------------------------------------------------------
# optional backends
# --------------------------------------------------------------------------

def _optional(name: str):
    try:
        module = __import__(name, fromlist=["*"])
    except Exception:  # ImportError, and broken installs that raise other things
        return None
    return module


numpy = _optional("numpy")
scipy_stats = _optional("scipy.stats")
pandas = _optional("pandas")

AVAILABLE = {
    "numpy": numpy is not None,
    "scipy": scipy_stats is not None,
    "pandas": pandas is not None,
}


class Backend:
    """Records which optional library actually did work in this run."""

    def __init__(self) -> None:
        self.used: list[str] = []

    def note(self, name: str) -> None:
        if name not in self.used:
            self.used.append(name)

    def report(self) -> dict:
        return {
            "primary": "stdlib",
            "also_used": list(self.used),
            "available": dict(AVAILABLE),
        }


# --------------------------------------------------------------------------
# errors
# --------------------------------------------------------------------------

class DegenerateSpread(ValueError):
    """Raised when a robust scale estimate is 0 and dividing by it is nonsense."""


class DataError(ValueError):
    """Raised when the input cannot be read at all. Untidy is not unreadable."""


# --------------------------------------------------------------------------
# distributions - regularized incomplete beta and gamma on math.lgamma
# --------------------------------------------------------------------------

def _betacf(a: float, b: float, x: float) -> float:
    """Continued fraction for the incomplete beta (Lentz's method)."""
    maxit, eps, fpmin = 400, 3e-16, 1e-300
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < fpmin:
        d = fpmin
    d = 1.0 / d
    h = d
    for m in range(1, maxit + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < fpmin:
            d = fpmin
        c = 1.0 + aa / c
        if abs(c) < fpmin:
            c = fpmin
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < fpmin:
            d = fpmin
        c = 1.0 + aa / c
        if abs(c) < fpmin:
            c = fpmin
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < eps:
            break
    return h


def betainc(a: float, b: float, x: float) -> float:
    """Regularized incomplete beta I_x(a, b). Basis of the t and F CDFs."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    lbeta = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
    if x < (a + 1.0) / (a + b + 2.0):
        front = math.exp(lbeta + a * math.log(x) + b * math.log1p(-x))
        return front * _betacf(a, b, x) / a
    front = math.exp(lbeta + b * math.log1p(-x) + a * math.log(x))
    return 1.0 - front * _betacf(b, a, 1.0 - x) / b


def _gser(a: float, x: float) -> float:
    """Series expansion for the lower regularized incomplete gamma."""
    ap, total, delta = a, 1.0 / a, 1.0 / a
    for _ in range(1000):
        ap += 1.0
        delta *= x / ap
        total += delta
        if abs(delta) < abs(total) * 3e-16:
            break
    return total * math.exp(-x + a * math.log(x) - math.lgamma(a))


def _gcf(a: float, x: float) -> float:
    """Continued fraction for the upper regularized incomplete gamma."""
    fpmin, eps = 1e-300, 3e-16
    b = x + 1.0 - a
    c = 1.0 / fpmin
    d = 1.0 / b
    h = d
    for i in range(1, 1000):
        an = -i * (i - a)
        b += 2.0
        d = an * d + b
        if abs(d) < fpmin:
            d = fpmin
        c = b + an / c
        if abs(c) < fpmin:
            c = fpmin
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < eps:
            break
    return h * math.exp(-x + a * math.log(x) - math.lgamma(a))


def gammainc_upper(a: float, x: float) -> float:
    """Regularized upper incomplete gamma Q(a, x). Basis of the chi-square SF."""
    if x <= 0.0:
        return 1.0
    if x < a + 1.0:
        return 1.0 - _gser(a, x)
    return _gcf(a, x)


_NORMAL = statistics.NormalDist()


def norm_cdf(z: float) -> float:
    return _NORMAL.cdf(z)


def norm_ppf(p: float) -> float:
    return _NORMAL.inv_cdf(p)


def t_sf(t: float, df: float) -> float:
    """P(T > t) for Student's t with df degrees of freedom."""
    if df <= 0:
        return float("nan")
    x = df / (df + t * t)
    tail = 0.5 * betainc(df / 2.0, 0.5, x)
    return tail if t >= 0 else 1.0 - tail


def t_cdf(t: float, df: float) -> float:
    return 1.0 - t_sf(t, df)


def t_two_sided_p(t: float, df: float) -> float:
    return 2.0 * t_sf(abs(t), df)


def t_ppf(p: float, df: float) -> float:
    """Quantile of Student's t by bisection on t_sf. Accurate to ~1e-12."""
    if not 0.0 < p < 1.0:
        raise ValueError("t_ppf needs 0 < p < 1")
    lo, hi = -1e4, 1e4
    for _ in range(300):
        mid = (lo + hi) / 2.0
        if t_cdf(mid, df) < p:
            lo = mid
        else:
            hi = mid
        if hi - lo < 1e-13 * max(1.0, abs(mid)):
            break
    return (lo + hi) / 2.0


def chi2_sf(x: float, df: float) -> float:
    """P(X > x) for chi-square with df degrees of freedom."""
    if x < 0:
        return 1.0
    return gammainc_upper(df / 2.0, x / 2.0)


def f_sf(f: float, df1: float, df2: float) -> float:
    """P(F > f). Computed from the upper tail directly, so small p stays exact."""
    if f <= 0:
        return 1.0
    return betainc(df2 / 2.0, df1 / 2.0, df2 / (df2 + df1 * f))


# --------------------------------------------------------------------------
# input - untidy is fine, unreadable is not
# --------------------------------------------------------------------------

NA_STRINGS = {
    "", "na", "n/a", "n.a.", "nan", "null", "none", "nil", "-", "--", ".",
    "?", "missing", "unknown", "#n/a", "#na", "<na>",
}

_CURRENCY = "$€£¥₹₽¢"
_NUM_RE = re.compile(r"^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$")


def coerce_number(raw: str) -> tuple[float | None, str]:
    """Parse one cell. Returns (value, tag) where tag says what happened.

    Tags: "ok", "coerced" (symbols or separators removed), "missing", "bad".
    Percent signs are stripped and the number is kept in percent units rather
    than divided by 100, because dividing would silently change the scale of a
    column someone already reported in percent.
    """
    s = raw.strip()
    if s.lower() in NA_STRINGS:
        return None, "missing"
    if _NUM_RE.match(s):
        return float(s), "ok"
    cleaned = s
    changed = False
    if cleaned.startswith("(") and cleaned.endswith(")"):
        cleaned = "-" + cleaned[1:-1]
        changed = True
    for ch in _CURRENCY:
        if ch in cleaned:
            cleaned = cleaned.replace(ch, "")
            changed = True
    for ch in (",", "_", " ", " ", " ", "'"):
        if ch in cleaned:
            cleaned = cleaned.replace(ch, "")
            changed = True
    if "−" in cleaned:  # unicode minus
        cleaned = cleaned.replace("−", "-")
        changed = True
    if cleaned.endswith("%"):
        cleaned = cleaned[:-1]
        changed = True
    cleaned = cleaned.strip()
    if _NUM_RE.match(cleaned):
        return float(cleaned), ("coerced" if changed else "ok")
    return None, "bad"


@dataclass
class Table:
    path: str
    columns: list[str]
    rows: list[list[str]]
    delimiter: str
    had_header: bool
    notes: list[str] = field(default_factory=list)


def _sniff_delimiter(sample: str) -> str:
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except Exception:
        counts = {d: sample.count(d) for d in (",", ";", "\t", "|")}
        best = max(counts, key=lambda d: counts[d])
        return best if counts[best] else ","


def _looks_like_header(row: Sequence[str]) -> bool:
    if not row:
        return False
    numeric = sum(1 for cell in row if coerce_number(cell)[0] is not None)
    return numeric < max(1, len(row) // 2)


def load_table(
    path: str,
    delimiter: str | None = None,
    has_header: bool | None = None,
    encoding: str = "utf-8",
    backend: Backend | None = None,
) -> Table:
    """Read a tabular file. Sniffs the delimiter and the header when not told.

    pandas, when installed, is used only for formats the stdlib cannot read
    (.parquet, .xlsx, .json). CSV always goes through the csv module, so a
    machine without pandas reads a CSV identically.
    """
    lower = path.lower()
    if lower.endswith((".parquet", ".xlsx", ".xls", ".json")) and pandas is not None:
        if backend:
            backend.note("pandas")
        if lower.endswith(".parquet"):
            frame = pandas.read_parquet(path)
        elif lower.endswith(".json"):
            frame = pandas.read_json(path)
        else:
            frame = pandas.read_excel(path)
        cols = [str(c) for c in frame.columns]
        rows = [["" if v is None else str(v) for v in rec] for rec in frame.itertuples(index=False)]
        return Table(path, cols, rows, delimiter="n/a", had_header=True,
                     notes=["read with pandas"])
    if lower.endswith((".parquet", ".xlsx", ".xls")) and pandas is None:
        raise DataError(f"{path}: reading this format needs pandas, which is not installed")

    try:
        with open(path, "r", encoding=encoding, newline="", errors="replace") as handle:
            text = handle.read()
    except OSError as exc:
        raise DataError(f"cannot read {path}: {exc}") from exc
    if not text.strip():
        raise DataError(f"{path} is empty")

    delim = delimiter or _sniff_delimiter(text[:8192])
    raw_rows = [r for r in csv.reader(io.StringIO(text), delimiter=delim) if any(c.strip() for c in r)]
    if not raw_rows:
        raise DataError(f"{path} has no data rows")

    header_present = _looks_like_header(raw_rows[0]) if has_header is None else has_header
    notes: list[str] = []
    if header_present:
        columns = [c.strip() for c in raw_rows[0]]
        rows = raw_rows[1:]
        for i, name in enumerate(columns):
            if not name:
                columns[i] = f"c{i}"
    else:
        width = max(len(r) for r in raw_rows)
        columns = [f"c{i}" for i in range(width)]
        rows = raw_rows
        notes.append("no header row detected; columns named c0..cN")
    if not rows:
        raise DataError(f"{path} has a header but no data rows")
    return Table(path, columns, rows, delim, header_present, notes)


def resolve_column(table: Table, token: str | None, *, numeric_default: bool = True) -> int:
    """Column by name (case-insensitive), by index, or the first usable column."""
    if token is None or token == "":
        if numeric_default:
            for idx in range(len(table.columns)):
                vals, rep = column_values(table, idx)
                if len(vals) >= max(2, 0.5 * rep["rows_total"]):
                    return idx
        return 0
    for idx, name in enumerate(table.columns):
        if name == token:
            return idx
    lowered = token.strip().lower()
    for idx, name in enumerate(table.columns):
        if name.strip().lower() == lowered:
            return idx
    for idx, name in enumerate(table.columns):
        if re.sub(r"\W+", "", name.lower()) == re.sub(r"\W+", "", lowered):
            return idx
    if re.fullmatch(r"-?\d+", token.strip()):
        idx = int(token.strip())
        if -len(table.columns) <= idx < len(table.columns):
            return idx
    raise DataError(f"column {token!r} not found; available: {', '.join(table.columns)}")


def column_values(table: Table, idx: int) -> tuple[list[float], dict]:
    """Numeric values from one column, with a full account of what was skipped."""
    values: list[float] = []
    missing = nonnumeric = coerced = 0
    short = 0
    examples: list[str] = []
    for row in table.rows:
        if idx >= len(row):
            short += 1
            missing += 1
            continue
        value, tag = coerce_number(row[idx])
        if tag == "missing":
            missing += 1
        elif tag == "bad":
            nonnumeric += 1
            if len(examples) < 3 and row[idx].strip():
                examples.append(row[idx].strip()[:24])
        else:
            if tag == "coerced":
                coerced += 1
            values.append(value)  # type: ignore[arg-type]
    report = {
        "column": table.columns[idx] if idx < len(table.columns) else f"c{idx}",
        "rows_total": len(table.rows),
        "n_used": len(values),
        "n_missing": missing,
        "n_nonnumeric": nonnumeric,
        "n_short_rows": short,
        "n_coerced": coerced,
        "nonnumeric_examples": examples,
        "rows_dropped": missing + nonnumeric,
        "rows_dropped_reported": True,
    }
    return values, report


def column_strings(table: Table, idx: int) -> list[str]:
    return [(row[idx].strip() if idx < len(row) else "") for row in table.rows]


def paired_columns(table: Table, idx_a: int, idx_b: int) -> tuple[list[float], list[float], dict]:
    """Row-aligned numeric pairs, dropping only rows unusable in both columns."""
    xs: list[float] = []
    ys: list[float] = []
    dropped = 0
    for row in table.rows:
        a = coerce_number(row[idx_a])[0] if idx_a < len(row) else None
        b = coerce_number(row[idx_b])[0] if idx_b < len(row) else None
        if a is None or b is None:
            dropped += 1
            continue
        xs.append(a)
        ys.append(b)
    report = {
        "rows_total": len(table.rows),
        "n_used": len(xs),
        "rows_dropped": dropped,
        "rows_dropped_reported": True,
    }
    return xs, ys, report


# --------------------------------------------------------------------------
# descriptive and robust statistics
# --------------------------------------------------------------------------

def quantile(xs: Sequence[float], q: float) -> float:
    """Type-7 (linear interpolation) quantile, matching numpy's default."""
    if not xs:
        raise statistics.StatisticsError("quantile of an empty sample")
    ordered = sorted(xs)
    if len(ordered) == 1:
        return ordered[0]
    pos = (len(ordered) - 1) * q
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return ordered[int(pos)]
    return ordered[lo] + (pos - lo) * (ordered[hi] - ordered[lo])


def skewness(xs: Sequence[float]) -> float:
    """Sample skewness g1 (biased), matching scipy.stats.skew defaults.

    Wrong tool on n < 20 or on heavy tails: its own sampling variance is large
    enough that a value near 1 is compatible with a symmetric population.
    """
    n = len(xs)
    if n < 3:
        return float("nan")
    m = statistics.fmean(xs)
    m2 = sum((x - m) ** 2 for x in xs) / n
    m3 = sum((x - m) ** 3 for x in xs) / n
    if m2 == 0:
        return 0.0
    return m3 / m2 ** 1.5


def excess_kurtosis(xs: Sequence[float]) -> float:
    """Sample excess kurtosis g2 (biased), matching scipy.stats.kurtosis defaults."""
    n = len(xs)
    if n < 4:
        return float("nan")
    m = statistics.fmean(xs)
    m2 = sum((x - m) ** 2 for x in xs) / n
    m4 = sum((x - m) ** 4 for x in xs) / n
    if m2 == 0:
        return 0.0
    return m4 / m2 ** 2 - 3.0


def mad(xs: Sequence[float]) -> float:
    """Median absolute deviation. Breakdown point 50%, against 0% for stdev."""
    med = statistics.median(xs)
    return statistics.median([abs(x - med) for x in xs])


def modified_z(xs: Sequence[float]) -> list[float]:
    """Robust z-scores. Raises on a degenerate column rather than returning inf.

    MAD is 0 whenever more than half the values are identical - which in ETL is
    the normal case, not the edge case: status flags, zero-filled amounts,
    defaulted columns. Dividing by it yields inf and flags every distinct value
    as an outlier, so the caller is told to switch estimator instead.
    """
    m = mad(xs)
    if m == 0:
        raise DegenerateSpread(
            "MAD is 0: over half the values are identical. Use the "
            "mean-absolute-deviation fallback, or treat this column as "
            "categorical - it has no scale to measure against."
        )
    med = statistics.median(xs)
    return [0.6745 * (x - med) / m for x in xs]


def mean_abs_deviation(xs: Sequence[float]) -> float:
    """Mean absolute deviation about the median. The fallback when MAD is 0."""
    med = statistics.median(xs)
    return statistics.fmean([abs(x - med) for x in xs])


def trimmed_mean(xs: Sequence[float], proportion: float = 0.1) -> float:
    """Mean after discarding `proportion` from each tail.

    Wrong tool when the tail is the subject: trimming a returns series removes
    exactly the days a risk estimate is about.
    """
    ordered = sorted(xs)
    n = len(ordered)
    k = int(math.floor(n * proportion))
    kept = ordered[k:n - k] if n - 2 * k > 0 else ordered
    return statistics.fmean(kept)


def winsorized(xs: Sequence[float], proportion: float = 0.1) -> list[float]:
    """Values with each tail clamped to the `proportion` quantile."""
    ordered = sorted(xs)
    n = len(ordered)
    k = int(math.floor(n * proportion))
    if n - 2 * k <= 0:
        return list(xs)
    lo, hi = ordered[k], ordered[n - k - 1]
    return [min(max(x, lo), hi) for x in xs]


def ci_mean(xs: Sequence[float], alpha: float = DEFAULT_ALPHA) -> tuple[float, float]:
    """t interval for the mean.

    Wrong tool for a median, a quantile or a ratio, and wrong for a mean when
    n is small and the data are visibly skewed - bootstrap those instead.
    """
    n = len(xs)
    if n < 2:
        raise statistics.StatisticsError("a mean interval needs at least 2 observations")
    m = statistics.fmean(xs)
    se = statistics.stdev(xs) / math.sqrt(n)
    crit = t_ppf(1 - alpha / 2, n - 1)
    return m - crit * se, m + crit * se


def bootstrap_ci(
    xs: Sequence[float],
    stat: Callable[[Sequence[float]], float] = statistics.median,
    reps: int = DEFAULT_REPS,
    alpha: float = DEFAULT_ALPHA,
    seed: int | None = None,
) -> tuple[float, float, float]:
    """Percentile bootstrap interval. Returns (lo, hi, point).

    Percentile, not BCa: BCa's bias correction needs a jackknife pass and the
    accuracy gain does not survive the n < 30 cases this is mostly used on.
    Stated here so the choice is not mistaken for an oversight.

    Wrong tool for an extreme quantile of a small sample: the bootstrap cannot
    resample values the sample never contained, so the interval on a 99th
    percentile from n = 40 is optimistically narrow.
    """
    rng = random.Random(seed)
    n = len(xs)
    if n < 2:
        raise statistics.StatisticsError("bootstrap needs at least 2 observations")
    pool = list(xs)
    reps_out = sorted(stat(rng.choices(pool, k=n)) for _ in range(reps))
    lo = reps_out[int((alpha / 2) * reps)]
    hi = reps_out[int((1 - alpha / 2) * reps) - 1]
    return lo, hi, stat(pool)


def bootstrap_diff_ci(
    a: Sequence[float],
    b: Sequence[float],
    stat: Callable[[Sequence[float]], float],
    reps: int = DEFAULT_REPS,
    alpha: float = DEFAULT_ALPHA,
    seed: int | None = None,
) -> tuple[float, float, float]:
    """Percentile bootstrap interval for stat(a) - stat(b), resampled separately."""
    rng = random.Random(seed)
    la, lb = list(a), list(b)
    na, nb = len(la), len(lb)
    draws = sorted(
        stat(rng.choices(la, k=na)) - stat(rng.choices(lb, k=nb)) for _ in range(reps)
    )
    lo = draws[int((alpha / 2) * reps)]
    hi = draws[int((1 - alpha / 2) * reps) - 1]
    return lo, hi, stat(la) - stat(lb)


def permutation_p(
    a: Sequence[float],
    b: Sequence[float],
    stat: Callable[[Sequence[float]], float],
    reps: int = DEFAULT_REPS,
    seed: int | None = None,
) -> tuple[float, float]:
    """Two-sided permutation p-value for stat(a) - stat(b). Returns (p, observed).

    The +1 in numerator and denominator is Phipson & Smyth (2010): an exact
    permutation p-value can never honestly be 0, because the observed labeling
    is itself one of the permutations.
    """
    rng = random.Random(seed)
    observed = stat(list(a)) - stat(list(b))
    pool = list(a) + list(b)
    na = len(a)
    at_least = 0
    for _ in range(reps):
        rng.shuffle(pool)
        diff = stat(pool[:na]) - stat(pool[na:])
        if abs(diff) >= abs(observed) - 1e-15:
            at_least += 1
    return (at_least + 1) / (reps + 1), observed


# --------------------------------------------------------------------------
# ordinary least squares - Householder QR on centered columns
# --------------------------------------------------------------------------

@dataclass
class OLSFit:
    names: list[str]
    coefficients: list[float]
    se: list[float]
    n: int
    p: int
    residuals: list[float]
    fitted: list[float]
    r2: float
    adj_r2: float
    sigma: float
    fstat: float
    f_df: tuple[int, int]
    leverage: list[float]
    cov_slopes: list[list[float]]


def _householder_r(matrix: list[list[float]], rhs: list[float]) -> tuple[list[list[float]], list[float]]:
    """Reduce [A | y] to [R | Q'y] in place. Returns (R, Q'y)."""
    a = [row[:] for row in matrix]
    y = list(rhs)
    n, k = len(a), len(a[0]) if a else 0
    for j in range(k):
        norm = math.sqrt(sum(a[i][j] ** 2 for i in range(j, n)))
        if norm == 0.0:
            continue
        if a[j][j] > 0:
            norm = -norm
        v = [0.0] * n
        for i in range(j, n):
            v[i] = a[i][j]
        v[j] -= norm
        vnorm2 = sum(v[i] ** 2 for i in range(j, n))
        if vnorm2 == 0.0:
            continue
        for col in range(j, k):
            dot = sum(v[i] * a[i][col] for i in range(j, n))
            factor = 2.0 * dot / vnorm2
            for i in range(j, n):
                a[i][col] -= factor * v[i]
        dot = sum(v[i] * y[i] for i in range(j, n))
        factor = 2.0 * dot / vnorm2
        for i in range(j, n):
            y[i] -= factor * v[i]
    r = [[a[i][j] for j in range(k)] for i in range(k)]
    return r, y[:k]


def _back_substitute(r: list[list[float]], qty: list[float]) -> list[float]:
    k = len(r)
    out = [0.0] * k
    for i in range(k - 1, -1, -1):
        total = qty[i] - sum(r[i][j] * out[j] for j in range(i + 1, k))
        if r[i][i] == 0.0:
            out[i] = 0.0
        else:
            out[i] = total / r[i][i]
    return out


def _invert_upper(r: list[list[float]]) -> list[list[float]]:
    k = len(r)
    inv = [[0.0] * k for _ in range(k)]
    for i in range(k - 1, -1, -1):
        if r[i][i] == 0.0:
            continue
        inv[i][i] = 1.0 / r[i][i]
        for j in range(i + 1, k):
            total = sum(r[i][m] * inv[m][j] for m in range(i + 1, k))
            inv[i][j] = -total / r[i][i]
    return inv


def ols(y: Sequence[float], columns: Sequence[Sequence[float]], names: Sequence[str]) -> OLSFit:
    """OLS with an intercept, solved by Householder QR on mean-centered columns.

    Centering plus QR rather than the normal equations: X'X squares the
    condition number, which is the reason a textbook implementation fails the
    NIST Longley benchmark while this one does not.

    Wrong tool when the residuals are serially correlated (the standard errors
    are then too small) or when a predictor was chosen by looking at this same
    data - run --diagnostics and read the assumptions it prints.
    """
    n = len(y)
    k = len(columns)
    if n <= k + 1:
        raise statistics.StatisticsError(f"OLS needs more rows than predictors (n={n}, p={k})")
    ybar = statistics.fmean(y)
    xbars = [statistics.fmean(col) for col in columns]
    xc = [[columns[j][i] - xbars[j] for j in range(k)] for i in range(n)]
    yc = [y[i] - ybar for i in range(n)]
    r, qty = _householder_r(xc, yc)
    slopes = _back_substitute(r, qty)
    intercept = ybar - sum(slopes[j] * xbars[j] for j in range(k))
    coefficients = [intercept] + slopes

    fitted = [intercept + sum(slopes[j] * columns[j][i] for j in range(k)) for i in range(n)]
    residuals = [y[i] - fitted[i] for i in range(n)]
    sse = sum(e * e for e in residuals)
    sst = sum((v - ybar) ** 2 for v in y)
    dfe = n - k - 1
    sigma2 = sse / dfe
    rinv = _invert_upper(r)
    cov = [[sum(rinv[i][m] * rinv[j][m] for m in range(k)) for j in range(k)] for i in range(k)]
    se_slopes = [math.sqrt(max(sigma2 * cov[j][j], 0.0)) for j in range(k)]
    quad = sum(xbars[i] * cov[i][j] * xbars[j] for i in range(k) for j in range(k))
    se_intercept = math.sqrt(max(sigma2 * (1.0 / n + quad), 0.0))
    leverage = [
        1.0 / n + sum(xc[i][a] * cov[a][b] * xc[i][b] for a in range(k) for b in range(k))
        for i in range(n)
    ]
    r2 = 1.0 - sse / sst if sst > 0 else float("nan")
    adj = 1.0 - (1.0 - r2) * (n - 1) / dfe if sst > 0 else float("nan")
    ssr = sst - sse
    fstat = (ssr / k) / sigma2 if k and sigma2 > 0 else float("nan")
    return OLSFit(
        names=["(intercept)"] + list(names),
        coefficients=coefficients,
        se=[se_intercept] + se_slopes,
        n=n,
        p=k,
        residuals=residuals,
        fitted=fitted,
        r2=r2,
        adj_r2=adj,
        sigma=math.sqrt(sigma2),
        fstat=fstat,
        f_df=(k, dfe),
        leverage=leverage,
        cov_slopes=cov,
    )


# --------------------------------------------------------------------------
# classification metrics
# --------------------------------------------------------------------------

def _average_ranks(xs: Sequence[float]) -> list[float]:
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    ranks = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for m in range(i, j + 1):
            ranks[order[m]] = avg
        i = j + 1
    return ranks


def auc_roc(truth: Sequence[int], score: Sequence[float]) -> float:
    """AUC by the rank identity (equivalent to the Mann-Whitney U statistic).

    Wrong tool as the headline number on a heavily imbalanced problem: AUC is
    insensitive to prevalence, so 0.95 can coexist with a precision of 0.05.
    """
    pos = [s for t, s in zip(truth, score) if t == 1]
    neg = [s for t, s in zip(truth, score) if t == 0]
    if not pos or not neg:
        return float("nan")
    ranks = _average_ranks(list(score))
    rank_sum = sum(r for r, t in zip(ranks, truth) if t == 1)
    n1, n0 = len(pos), len(neg)
    return (rank_sum - n1 * (n1 + 1) / 2.0) / (n1 * n0)


def brier_score(truth: Sequence[int], score: Sequence[float]) -> float:
    return statistics.fmean([(s - t) ** 2 for t, s in zip(truth, score)])


def calibration_bins(truth: Sequence[int], score: Sequence[float], bins: int = 10) -> tuple[list[dict], float]:
    """Equal-width reliability bins and the expected calibration error."""
    buckets: list[list[tuple[int, float]]] = [[] for _ in range(bins)]
    for t, s in zip(truth, score):
        idx = min(bins - 1, max(0, int(s * bins)))
        buckets[idx].append((t, s))
    out = []
    ece = 0.0
    total = len(truth)
    for i, bucket in enumerate(buckets):
        if not bucket:
            continue
        mean_p = statistics.fmean([s for _, s in bucket])
        observed = statistics.fmean([t for t, _ in bucket])
        out.append({
            "bin": f"[{i / bins:.1f}, {(i + 1) / bins:.1f})",
            "n": len(bucket),
            "mean_predicted": mean_p,
            "observed_rate": observed,
            "gap": observed - mean_p,
        })
        ece += len(bucket) / total * abs(observed - mean_p)
    return out, ece


# --------------------------------------------------------------------------
# series
# --------------------------------------------------------------------------

def acf(xs: Sequence[float], lags: int) -> list[float]:
    """Sample autocorrelation, the standard biased (divide by n) estimator."""
    n = len(xs)
    m = statistics.fmean(xs)
    denom = sum((x - m) ** 2 for x in xs)
    if denom == 0:
        return [float("nan")] * (lags + 1)
    out = []
    for k in range(lags + 1):
        num = sum((xs[i] - m) * (xs[i - k] - m) for i in range(k, n))
        out.append(num / denom)
    return out


def ljung_box(rho: Sequence[float], n: int, lags: int) -> tuple[float, float]:
    """Ljung-Box Q on lags 1..lags. Returns (Q, p) against chi-square(lags)."""
    q = n * (n + 2) * sum((rho[k] ** 2) / (n - k) for k in range(1, lags + 1))
    return q, chi2_sf(q, lags)


def adf_statistic(xs: Sequence[float], lags: int = 1) -> tuple[float, int]:
    """Augmented Dickey-Fuller tau for the constant-only case.

    Returns (tau, lags used). The critical values are asymptotic; a finite
    sample of a few hundred points sits a little to the left of them, so a tau
    close to a cutoff is not a decision.
    """
    diffs = [xs[i] - xs[i - 1] for i in range(1, len(xs))]
    n = len(diffs)
    lags = max(0, min(lags, n // 4))
    start = lags
    y = diffs[start:]
    level = [xs[i] for i in range(start, n)]
    cols = [level]
    for lag in range(1, lags + 1):
        cols.append([diffs[i - lag] for i in range(start, n)])
    names = ["level"] + [f"dlag{i}" for i in range(1, lags + 1)]
    fit = ols(y, cols, names)
    gamma, se_gamma = fit.coefficients[1], fit.se[1]
    tau = gamma / se_gamma if se_gamma > 0 else float("nan")
    return tau, lags


def max_drawdown(returns: Sequence[float]) -> float:
    """Largest peak-to-trough fall of the cumulative product of 1 + r."""
    peak = equity = 1.0
    worst = 0.0
    for r in returns:
        equity *= (1.0 + r)
        peak = max(peak, equity)
        worst = min(worst, equity / peak - 1.0)
    return worst


# --------------------------------------------------------------------------
# manifest
# --------------------------------------------------------------------------

def make_manifest(
    command: str,
    backend: Backend,
    data: dict,
    results: list[dict],
    *,
    design: dict | None = None,
    randomization: dict | None = None,
    comparisons: dict | None = None,
    claims: Iterable[str] = (),
    assumptions: Iterable[str] = (),
    notes: Iterable[str] = (),
) -> dict:
    """Build the analysis manifest that stats_check.py audits.

    `comparisons.tried` counts alternatives searched over - models, cutoffs,
    strategies, group pairs - not the number of coefficients in one model.
    No timestamp anywhere: a seeded command must be byte-identical across runs.
    """
    return {
        "manifest_version": 1,
        "tool": "stats.py",
        "command": command,
        "backend": backend.report(),
        "data": data,
        "design": design or {"observational": True, "randomized_assignment": False},
        "randomization": randomization,
        "comparisons": comparisons or {"tried": 1, "correction": None},
        "results": results,
        "claims": list(claims),
        "assumptions": list(assumptions),
        "notes": list(notes),
    }


def result_entry(
    name: str,
    *,
    n: int,
    estimate: float | None = None,
    effect_size: dict | None = None,
    interval: dict | None = None,
    p_value: float | None = None,
    method: str = "",
    assumption: str = "",
    interval_omitted_reason: str | None = None,
) -> dict:
    """One result in the manifest.

    A p-value without an interval is a defect the auditor reports, so a result
    that genuinely cannot carry one states `interval_omitted_reason` instead.
    """
    entry = {
        "name": name,
        "n": n,
        "estimate": estimate,
        "effect_size": effect_size,
        "interval": interval,
        "p_value": p_value,
        "method": method,
        "assumption": assumption,
    }
    if interval_omitted_reason:
        entry["interval_omitted_reason"] = interval_omitted_reason
    return entry


def interval_entry(lo: float, hi: float, kind: str, level: float) -> dict:
    return {"kind": kind, "level": level, "lo": lo, "hi": hi}


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------

def _load_for(args, backend: Backend) -> Table:
    return load_table(
        args.path,
        delimiter=args.delimiter,
        has_header=(False if getattr(args, "no_header", False) else None),
        encoding=args.encoding,
        backend=backend,
    )


def _drop_note(report: dict) -> list[str]:
    notes = []
    if report.get("rows_dropped"):
        notes.append(
            f"{report['rows_dropped']} of {report['rows_total']} rows unusable "
            f"({report['n_missing']} missing, {report['n_nonnumeric']} non-numeric)"
        )
    if report.get("n_coerced"):
        notes.append(f"{report['n_coerced']} values coerced (symbols or separators stripped)")
    return notes


def cmd_describe(args, backend: Backend) -> tuple[dict, dict]:
    table = _load_for(args, backend)
    idx = resolve_column(table, args.col)
    xs, report = column_values(table, idx)
    if len(xs) < 1:
        raise DataError(f"column {report['column']!r} has no usable numeric values")
    n = len(xs)
    warnings: list[str] = []
    payload: dict[str, Any] = {
        "command": "describe",
        "column": report["column"],
        "n": n,
        "rows": report,
        "backend": backend.report(),
    }
    payload["mean"] = statistics.fmean(xs)
    payload["median"] = statistics.median(xs)
    payload["min"] = min(xs)
    payload["max"] = max(xs)
    if n >= 2:
        sd = statistics.stdev(xs)
        payload["sd"] = sd
        payload["se_mean"] = sd / math.sqrt(n)
        lo, hi = ci_mean(xs, args.alpha)
        payload["ci_mean"] = {"level": 1 - args.alpha, "lo": lo, "hi": hi, "kind": "t interval"}
    else:
        warnings.append("n = 1: no spread and no interval can be computed")
    payload["quantiles"] = {
        "p05": quantile(xs, 0.05),
        "q1": quantile(xs, 0.25),
        "q3": quantile(xs, 0.75),
        "p95": quantile(xs, 0.95),
        "iqr": quantile(xs, 0.75) - quantile(xs, 0.25),
    }
    payload["mad"] = mad(xs)
    payload["mad_scaled"] = mad(xs) * MAD_TO_SIGMA
    payload["skewness"] = skewness(xs)
    payload["excess_kurtosis"] = excess_kurtosis(xs)
    if n >= 8 and abs(payload["skewness"]) > 1:
        warnings.append(
            "skewness beyond 1: the mean and its t interval describe this column "
            "poorly - prefer the median with a bootstrap interval (boot --stat median)"
        )
    assumptions = [
        "the t interval on the mean assumes the sampling distribution of the mean "
        "is approximately normal, which n >= 30 or a symmetric distribution buys",
        "every statistic here assumes the rows are a sample of the population you "
        "mean to describe, not a filtered subset",
    ]
    payload["assumptions"] = assumptions
    payload["warnings"] = warnings + _drop_note(report)
    results = [result_entry(
        "mean",
        n=n,
        estimate=payload["mean"],
        effect_size={"name": "mean", "value": payload["mean"]},
        interval=(interval_entry(payload["ci_mean"]["lo"], payload["ci_mean"]["hi"],
                                 "t interval", 1 - args.alpha) if n >= 2 else None),
        method="stdlib descriptives",
        assumption=assumptions[0],
    )]
    manifest = make_manifest(
        "describe", backend, _data_block(table, report), results,
        assumptions=assumptions, notes=payload["warnings"],
    )
    return payload, manifest


def _data_block(table: Table, report: dict) -> dict:
    return {
        "source": table.path,
        "column": report.get("column"),
        "n": report.get("n_used"),
        "rows_total": report.get("rows_total"),
        "n_missing": report.get("n_missing", 0),
        "n_nonnumeric": report.get("n_nonnumeric", 0),
        "rows_dropped": report.get("rows_dropped", 0),
        "rows_dropped_reported": True,
    }


def _group_samples(table: Table, col_idx: int, by_idx: int) -> tuple[dict[str, list[float]], dict]:
    groups: dict[str, list[float]] = {}
    missing = nonnumeric = 0
    labels = column_strings(table, by_idx)
    for row_i, row in enumerate(table.rows):
        if col_idx >= len(row):
            missing += 1
            continue
        value, tag = coerce_number(row[col_idx])
        if tag == "missing":
            missing += 1
            continue
        if tag == "bad":
            nonnumeric += 1
            continue
        key = labels[row_i] or "(blank)"
        groups.setdefault(key, []).append(value)  # type: ignore[arg-type]
    report = {
        "column": table.columns[col_idx],
        "rows_total": len(table.rows),
        "n_used": sum(len(v) for v in groups.values()),
        "n_missing": missing,
        "n_nonnumeric": nonnumeric,
        "n_coerced": 0,
        "rows_dropped": missing + nonnumeric,
        "rows_dropped_reported": True,
    }
    return groups, report


def _pooled_sd(a: Sequence[float], b: Sequence[float]) -> float:
    na, nb = len(a), len(b)
    va, vb = statistics.variance(a), statistics.variance(b)
    return math.sqrt(((na - 1) * va + (nb - 1) * vb) / (na + nb - 2))


def _cohen_d(a: Sequence[float], b: Sequence[float]) -> tuple[float, float]:
    sp = _pooled_sd(a, b)
    if sp == 0:
        return float("nan"), float("nan")
    d = (statistics.fmean(a) - statistics.fmean(b)) / sp
    g = d * (1 - 3 / (4 * (len(a) + len(b)) - 9))
    return d, g


def _welch(a: Sequence[float], b: Sequence[float]) -> tuple[float, float, float]:
    na, nb = len(a), len(b)
    va, vb = statistics.variance(a) / na, statistics.variance(b) / nb
    if va + vb == 0:
        return float("nan"), float("nan"), float("nan")
    t = (statistics.fmean(a) - statistics.fmean(b)) / math.sqrt(va + vb)
    df = (va + vb) ** 2 / (va ** 2 / (na - 1) + vb ** 2 / (nb - 1))
    return t, df, t_two_sided_p(t, df)


def _student(a: Sequence[float], b: Sequence[float]) -> tuple[float, float, float]:
    na, nb = len(a), len(b)
    sp = _pooled_sd(a, b)
    if sp == 0:
        return float("nan"), float("nan"), float("nan")
    t = (statistics.fmean(a) - statistics.fmean(b)) / (sp * math.sqrt(1 / na + 1 / nb))
    df = na + nb - 2
    return t, df, t_two_sided_p(t, df)


def mann_whitney(a: Sequence[float], b: Sequence[float]) -> tuple[float, float, float]:
    """Mann-Whitney U with the normal approximation and a tie correction.

    Returns (U for the first sample, p, rank-biserial correlation). Wrong tool
    when the two distributions have different shapes: it then answers "is one
    stochastically larger", not "do the medians differ".
    """
    na, nb = len(a), len(b)
    combined = list(a) + list(b)
    ranks = _average_ranks(combined)
    r1 = sum(ranks[:na])
    u1 = r1 - na * (na + 1) / 2.0
    mu = na * nb / 2.0
    counts: dict[float, int] = {}
    for v in combined:
        counts[v] = counts.get(v, 0) + 1
    n = na + nb
    tie_term = sum(c ** 3 - c for c in counts.values())
    sigma2 = na * nb / 12.0 * ((n + 1) - tie_term / (n * (n - 1)))
    if sigma2 <= 0:
        return u1, float("nan"), 2 * u1 / (na * nb) - 1
    z = (u1 - mu - math.copysign(0.5, u1 - mu)) / math.sqrt(sigma2)
    p = 2 * (1 - norm_cdf(abs(z)))
    return u1, p, 2 * u1 / (na * nb) - 1


def _anova(groups: dict[str, list[float]]) -> tuple[float, int, int, float, float]:
    all_values = [v for vs in groups.values() for v in vs]
    grand = statistics.fmean(all_values)
    ssb = sum(len(vs) * (statistics.fmean(vs) - grand) ** 2 for vs in groups.values())
    ssw = sum((v - statistics.fmean(vs)) ** 2 for vs in groups.values() for v in vs)
    k = len(groups)
    n = len(all_values)
    df1, df2 = k - 1, n - k
    if df2 <= 0 or ssw == 0:
        return float("nan"), df1, df2, float("nan"), float("nan")
    f = (ssb / df1) / (ssw / df2)
    eta2 = ssb / (ssb + ssw)
    return f, df1, df2, eta2, f_sf(f, df1, df2)


def holm_adjust(pvalues: Sequence[float]) -> list[float]:
    """Holm-Bonferroni step-down adjusted p-values, monotone and clipped to 1."""
    m = len(pvalues)
    order = sorted(range(m), key=lambda i: pvalues[i])
    adjusted = [0.0] * m
    running = 0.0
    for rank, idx in enumerate(order):
        value = min(1.0, (m - rank) * pvalues[idx])
        running = max(running, value)
        adjusted[idx] = running
    return adjusted


def cmd_test(args, backend: Backend) -> tuple[dict, dict]:
    table = _load_for(args, backend)
    tokens = [t for t in (args.col or "").split(",") if t.strip()] if args.col else []
    warnings: list[str] = []
    reps = args.reps
    if args.by:
        col_idx = resolve_column(table, tokens[0] if tokens else None)
        by_idx = resolve_column(table, args.by, numeric_default=False)
        groups, report = _group_samples(table, col_idx, by_idx)
        label = report["column"]
    elif len(tokens) >= 2:
        ia, ib = resolve_column(table, tokens[0]), resolve_column(table, tokens[1])
        va, ra = column_values(table, ia)
        vb, rb = column_values(table, ib)
        groups = {table.columns[ia]: va, table.columns[ib]: vb}
        report = {
            "column": f"{table.columns[ia]},{table.columns[ib]}",
            "rows_total": ra["rows_total"],
            "n_used": len(va) + len(vb),
            "n_missing": ra["n_missing"] + rb["n_missing"],
            "n_nonnumeric": ra["n_nonnumeric"] + rb["n_nonnumeric"],
            "n_coerced": ra["n_coerced"] + rb["n_coerced"],
            "rows_dropped": ra["rows_dropped"] + rb["rows_dropped"],
            "rows_dropped_reported": True,
        }
        label = report["column"]
    else:
        col_idx = resolve_column(table, tokens[0] if tokens else None)
        xs, report = column_values(table, col_idx)
        groups = {report["column"]: xs}
        label = report["column"]

    groups = {k: v for k, v in groups.items() if len(v) >= 2 or len(groups) == 1}
    keys = sorted(groups)
    payload: dict[str, Any] = {
        "command": "test",
        "column": label,
        "backend": backend.report(),
        "groups": {k: {"n": len(groups[k]), "mean": statistics.fmean(groups[k]),
                       "median": statistics.median(groups[k]),
                       "sd": statistics.stdev(groups[k]) if len(groups[k]) > 1 else float("nan")}
                   for k in keys},
        "rows": report,
        "seed": args.seed,
    }
    n_total = sum(len(groups[k]) for k in keys)
    if n_total > 5000 and reps == DEFAULT_REPS:
        reps = 2000
        warnings.append(f"n = {n_total}: resampling reps reduced to {reps} for runtime")

    results: list[dict] = []
    assumptions: list[str] = []
    comparisons = {"tried": 1, "correction": None}
    randomization: dict | None = None

    if len(keys) == 1:
        xs = groups[keys[0]]
        mu = args.mu if args.mu is not None else 0.0
        n = len(xs)
        m = statistics.fmean(xs)
        sd = statistics.stdev(xs)
        t = (m - mu) / (sd / math.sqrt(n)) if sd > 0 else float("nan")
        p = t_two_sided_p(t, n - 1)
        lo, hi = ci_mean(xs, args.alpha)
        d = (m - mu) / sd if sd > 0 else float("nan")
        payload["method"] = "one-sample t test"
        payload["mu"] = mu
        payload["t"] = t
        payload["df"] = n - 1
        payload["p_value"] = p
        payload["effect_size"] = {"name": "cohen_d", "value": d}
        payload["ci_mean"] = {"lo": lo, "hi": hi, "level": 1 - args.alpha}
        assumptions.append(
            "the one-sample t test assumes the mean's sampling distribution is "
            "approximately normal; with n < 30 and visible skew, use boot instead"
        )
        results.append(result_entry(
            f"mean of {label} vs {mu}", n=n, estimate=m - mu,
            effect_size={"name": "cohen_d", "value": d},
            interval=interval_entry(lo, hi, "t interval", 1 - args.alpha),
            p_value=p, method="one-sample t test", assumption=assumptions[0],
        ))
    elif len(keys) == 2:
        a, b = groups[keys[0]], groups[keys[1]]
        method = args.method
        reason = ""
        if method == "auto":
            skewed = max(abs(skewness(a)), abs(skewness(b))) > 1.0
            heavy = max(excess_kurtosis(a), excess_kurtosis(b)) > 2.0
            small = min(len(a), len(b)) < 15
            if skewed or heavy or small:
                method = "permutation"
                reason = ("resampling chosen: " + ", ".join(
                    [s for s, flag in (("small group", small), ("skewed", skewed),
                                       ("heavy tails", heavy)) if flag]))
            else:
                method = "welch"
                reason = ("Welch chosen: both groups n >= 15, |skew| <= 1 and no heavy "
                          "tails, so the normal approximation for the mean holds")
        payload["method"] = method
        payload["method_reason"] = reason or f"method forced to {method}"
        stat_fn: Callable[[Sequence[float]], float] = (
            statistics.median if args.stat == "median" else statistics.fmean)
        d, g = _cohen_d(a, b)
        if method == "permutation":
            p, observed = permutation_p(a, b, stat_fn, reps=reps, seed=args.seed)
            lo, hi, point = bootstrap_diff_ci(a, b, stat_fn, reps=reps,
                                              alpha=args.alpha, seed=args.seed)
            randomization = {"seeded": args.seed is not None, "seed": args.seed, "reps": reps}
            payload["p_value"] = p
            payload["observed_difference"] = observed
            payload["ci_difference"] = {"lo": lo, "hi": hi, "level": 1 - args.alpha,
                                        "kind": "percentile bootstrap"}
            payload["effect_size"] = {"name": "cohen_d", "value": d, "hedges_g": g}
            assumptions.append(
                "the permutation test assumes the two samples are exchangeable "
                "under the null, which paired or time-ordered data violate"
            )
            results.append(result_entry(
                f"difference in {args.stat} ({keys[0]} - {keys[1]})",
                n=len(a) + len(b), estimate=observed,
                effect_size={"name": "cohen_d", "value": d},
                interval=interval_entry(lo, hi, "percentile bootstrap", 1 - args.alpha),
                p_value=p, method=f"permutation test, {reps} reps",
                assumption=assumptions[-1],
            ))
        elif method == "mannwhitney":
            u, p, rb = mann_whitney(a, b)
            lo, hi, point = bootstrap_diff_ci(a, b, statistics.median, reps=reps,
                                              alpha=args.alpha, seed=args.seed)
            randomization = {"seeded": args.seed is not None, "seed": args.seed, "reps": reps}
            payload["u_statistic"] = u
            payload["p_value"] = p
            payload["effect_size"] = {"name": "rank_biserial", "value": rb}
            payload["ci_difference"] = {"lo": lo, "hi": hi, "level": 1 - args.alpha,
                                        "kind": "percentile bootstrap on medians"}
            assumptions.append(
                "Mann-Whitney assumes similarly shaped distributions if you want to "
                "read it as a difference in medians rather than in stochastic order"
            )
            results.append(result_entry(
                f"stochastic dominance ({keys[0]} vs {keys[1]})", n=len(a) + len(b),
                estimate=u, effect_size={"name": "rank_biserial", "value": rb},
                interval=interval_entry(lo, hi, "percentile bootstrap on medians",
                                        1 - args.alpha),
                p_value=p, method="Mann-Whitney U, normal approximation with tie correction",
                assumption=assumptions[-1],
            ))
        else:
            t, df, p = _welch(a, b) if method == "welch" else _student(a, b)
            diff = statistics.fmean(a) - statistics.fmean(b)
            se = abs(diff / t) if t not in (0.0, float("nan")) and not math.isnan(t) else float("nan")
            crit = t_ppf(1 - args.alpha / 2, df)
            lo, hi = diff - crit * se, diff + crit * se
            payload["t"] = t
            payload["df"] = df
            payload["p_value"] = p
            payload["observed_difference"] = diff
            payload["effect_size"] = {"name": "cohen_d", "value": d, "hedges_g": g}
            payload["ci_difference"] = {"lo": lo, "hi": hi, "level": 1 - args.alpha,
                                        "kind": "t interval"}
            assumptions.append(
                "Welch's t assumes the group means are approximately normally "
                "distributed; it does not assume equal variances, the Student "
                "version does" if method == "welch" else
                "the pooled t test assumes equal variances and approximate normality; "
                "prefer Welch unless the variances are known to match"
            )
            results.append(result_entry(
                f"difference in means ({keys[0]} - {keys[1]})", n=len(a) + len(b),
                estimate=diff, effect_size={"name": "cohen_d", "value": d},
                interval=interval_entry(lo, hi, "t interval", 1 - args.alpha),
                p_value=p, method=("Welch t test" if method == "welch" else "Student t test"),
                assumption=assumptions[-1],
            ))
        if scipy_stats is not None:
            backend.note("scipy")
            try:
                cross = {}
                if method in ("welch", "student"):
                    st = scipy_stats.ttest_ind(a, b, equal_var=(method == "student"))
                    cross["scipy_p"] = float(st.pvalue)
                elif method == "mannwhitney":
                    st = scipy_stats.mannwhitneyu(a, b, alternative="two-sided")
                    cross["scipy_p_exact_or_asymptotic"] = float(st.pvalue)
                else:
                    st = scipy_stats.ttest_ind(a, b, equal_var=False)
                    cross["scipy_welch_p_for_reference"] = float(st.pvalue)
                payload["cross_check"] = cross
            except Exception as exc:  # a cross-check must never break the answer
                payload["cross_check"] = {"error": str(exc)}
    else:
        f, df1, df2, eta2, p_param = _anova(groups)
        payload["method"] = "one-way ANOVA with a permutation p-value"
        rng = random.Random(args.seed)
        pooled = [(k, v) for k in keys for v in groups[k]]
        values = [v for _, v in pooled]
        sizes = [len(groups[k]) for k in keys]
        at_least = 0
        for _ in range(reps):
            rng.shuffle(values)
            cut = 0
            shuffled = {}
            for k, size in zip(keys, sizes):
                shuffled[k] = values[cut:cut + size]
                cut += size
            f_perm = _anova(shuffled)[0]
            if not math.isnan(f_perm) and f_perm >= f - 1e-15:
                at_least += 1
        p_perm = (at_least + 1) / (reps + 1)
        randomization = {"seeded": args.seed is not None, "seed": args.seed, "reps": reps}
        payload["f_statistic"] = f
        payload["df"] = [df1, df2]
        payload["p_value"] = p_perm
        payload["p_value_parametric"] = p_param
        payload["effect_size"] = {"name": "eta_squared", "value": eta2}
        assumptions.append(
            "the parametric ANOVA p-value assumes normal residuals and equal "
            "variances; the permutation p-value assumes only exchangeability"
        )
        results.append(result_entry(
            f"any difference among {len(keys)} groups", n=n_total, estimate=f,
            effect_size={"name": "eta_squared", "value": eta2},
            interval=None, p_value=p_perm,
            method=f"one-way ANOVA, permutation p-value over {reps} reps",
            assumption=assumptions[-1],
            interval_omitted_reason=(
                "an omnibus F has no single quantity to put an interval on; the "
                "pairwise differences do, and --pairwise reports them"),
        ))
        warnings.append("an omnibus test says only that some pair differs; use "
                        "--pairwise to see which, and it will be Holm-corrected")
        if args.pairwise:
            pairs = [(keys[i], keys[j]) for i in range(len(keys)) for j in range(i + 1, len(keys))]
            raw = []
            for ka, kb in pairs:
                raw.append(_welch(groups[ka], groups[kb])[2])
            adjusted = holm_adjust(raw)
            m = len(pairs)
            level = 1 - args.alpha / m
            payload["pairwise"] = []
            comparisons = {"tried": m, "correction": "holm"}
            for (ka, kb), pr, pa in zip(pairs, raw, adjusted):
                a2, b2 = groups[ka], groups[kb]
                diff = statistics.fmean(a2) - statistics.fmean(b2)
                se = math.sqrt(statistics.variance(a2) / len(a2)
                               + statistics.variance(b2) / len(b2))
                df = _welch(a2, b2)[1]
                crit = t_ppf(1 - (args.alpha / m) / 2, df)
                lo_p, hi_p = diff - crit * se, diff + crit * se
                d_pair = _cohen_d(a2, b2)[0]
                payload["pairwise"].append(
                    {"pair": f"{ka} vs {kb}", "p_raw": pr, "p_holm": pa,
                     "cohen_d": d_pair, "difference": diff,
                     "ci_lo": lo_p, "ci_hi": hi_p, "ci_level": level})
                results.append(result_entry(
                    f"difference in means ({ka} - {kb})",
                    n=len(a2) + len(b2), estimate=diff,
                    effect_size={"name": "cohen_d", "value": d_pair},
                    interval=interval_entry(lo_p, hi_p,
                                            "Bonferroni-adjusted t interval", level),
                    p_value=pa,
                    method="Welch t test, Holm-corrected across all pairs",
                    assumption=assumptions[-1],
                ))
            payload["interval_note"] = (
                f"pairwise intervals are widened to the {level:.4g} level so they agree "
                "with the corrected p-values beside them")

    assumptions.append("this compares groups as they arrived; without random "
                       "assignment the difference is an association, not an effect")
    payload["assumptions"] = assumptions
    payload["warnings"] = warnings + _drop_note(report)
    manifest = make_manifest(
        "test", backend, _data_block(table, report), results,
        randomization=randomization, comparisons=comparisons,
        assumptions=assumptions, notes=payload["warnings"],
        claims=[f"{keys[0]} and {keys[-1]} differ in {args.stat}"] if len(keys) > 1 else [],
    )
    if args.pairwise and "interval_note" in payload:
        manifest["notes"].append(payload["interval_note"])
    return payload, manifest


_STAT_FUNCS: dict[str, Callable[[Sequence[float]], float]] = {
    "mean": statistics.fmean,
    "median": statistics.median,
    "sd": lambda xs: statistics.stdev(xs) if len(xs) > 1 else float("nan"),
    "trimmed_mean": lambda xs: trimmed_mean(xs, 0.1),
    "iqr": lambda xs: quantile(xs, 0.75) - quantile(xs, 0.25),
    "min": min,
    "max": max,
}


def cmd_boot(args, backend: Backend) -> tuple[dict, dict]:
    table = _load_for(args, backend)
    idx = resolve_column(table, args.col)
    xs, report = column_values(table, idx)
    if len(xs) < 2:
        raise DataError("bootstrap needs at least 2 usable observations")
    if args.stat.startswith("q"):
        q = float(args.stat[1:]) / 100.0
        stat_fn: Callable[[Sequence[float]], float] = lambda vs, q=q: quantile(vs, q)
        stat_name = f"quantile {q}"
    else:
        stat_fn = _STAT_FUNCS[args.stat]
        stat_name = args.stat
    lo, hi, point = bootstrap_ci(xs, stat_fn, reps=args.reps, alpha=args.alpha, seed=args.seed)
    warnings = _drop_note(report)
    if args.seed is None:
        warnings.append("no --seed given: this interval cannot be reproduced exactly")
    if len(xs) < 20 and args.stat.startswith("q"):
        warnings.append("an extreme quantile from a small sample has a bootstrap "
                        "interval that is too narrow: the resample cannot contain "
                        "values the sample never saw")
    assumptions = [
        "the percentile bootstrap assumes the sample is representative and the "
        "observations are independent; serially correlated data need a block bootstrap",
    ]
    payload = {
        "command": "boot",
        "column": report["column"],
        "statistic": stat_name,
        "n": len(xs),
        "point_estimate": point,
        "ci": {"lo": lo, "hi": hi, "level": 1 - args.alpha, "kind": "percentile bootstrap"},
        "reps": args.reps,
        "seed": args.seed,
        "rows": report,
        "backend": backend.report(),
        "assumptions": assumptions,
        "warnings": warnings,
    }
    results = [result_entry(
        f"{stat_name} of {report['column']}", n=len(xs), estimate=point,
        effect_size={"name": stat_name, "value": point},
        interval=interval_entry(lo, hi, "percentile bootstrap", 1 - args.alpha),
        method=f"percentile bootstrap, {args.reps} reps", assumption=assumptions[0],
    )]
    manifest = make_manifest(
        "boot", backend, _data_block(table, report), results,
        randomization={"seeded": args.seed is not None, "seed": args.seed, "reps": args.reps},
        assumptions=assumptions, notes=warnings,
    )
    return payload, manifest


def cmd_robust(args, backend: Backend) -> tuple[dict, dict]:
    table = _load_for(args, backend)
    idx = resolve_column(table, args.col)
    xs, report = column_values(table, idx)
    if len(xs) < 2:
        raise DataError("robust statistics need at least 2 usable observations")
    warnings = _drop_note(report)
    payload: dict[str, Any] = {
        "command": "robust",
        "column": report["column"],
        "n": len(xs),
        "median": statistics.median(xs),
        "mad": mad(xs),
        "mad_scaled": mad(xs) * MAD_TO_SIGMA,
        "mean_abs_deviation": mean_abs_deviation(xs),
        "trimmed_mean_10": trimmed_mean(xs, 0.10),
        "trimmed_mean_20": trimmed_mean(xs, 0.20),
        "winsorized_mean_10": statistics.fmean(winsorized(xs, 0.10)),
        "iqr": quantile(xs, 0.75) - quantile(xs, 0.25),
        "mean": statistics.fmean(xs),
        "sd": statistics.stdev(xs),
        "backend": backend.report(),
        "rows": report,
    }
    payload["mean_vs_median_gap_in_mad"] = (
        (payload["mean"] - payload["median"]) / payload["mad_scaled"]
        if payload["mad"] > 0 else None
    )
    try:
        zs = modified_z(xs)
        payload["modified_z"] = {
            "max_abs": max(abs(z) for z in zs),
            "n_beyond_cutoff": sum(1 for z in zs if abs(z) > MODIFIED_Z_CUTOFF),
            "cutoff": MODIFIED_Z_CUTOFF,
        }
        payload["degenerate"] = False
    except DegenerateSpread as exc:
        payload["degenerate"] = True
        payload["modified_z"] = None
        payload["degenerate_message"] = str(exc)
        warnings.append(str(exc))
    assumptions = [
        "the 1.4826 factor makes MAD comparable to a standard deviation only if "
        "the bulk of the data is normal; on a lognormal column it understates spread",
    ]
    payload["assumptions"] = assumptions
    payload["warnings"] = warnings
    results = [result_entry(
        f"median of {report['column']}", n=len(xs), estimate=payload["median"],
        effect_size={"name": "mad_scaled", "value": payload["mad_scaled"]},
        interval=None, method="robust descriptives", assumption=assumptions[0],
    )]
    data_block = _data_block(table, report)
    if payload["degenerate"]:
        data_block["degenerate_scale"] = True
    manifest = make_manifest(
        "robust", backend, data_block, results,
        assumptions=assumptions, notes=warnings,
    )
    return payload, manifest


def _outlier_bounds(xs: Sequence[float], method: str, threshold: float) -> tuple[float, float, dict]:
    """Lower and upper cutoff for one method, plus the center/scale it used."""
    if method == "mad":
        med = statistics.median(xs)
        scale = mad(xs)
        if scale == 0:
            raise DegenerateSpread(
                "MAD is 0: over half the values are identical. Use --method iqr, "
                "the mean-absolute-deviation fallback, or treat this column as "
                "categorical - it has no scale to measure against."
            )
        half = threshold * scale / 0.6745
        return med - half, med + half, {"center": med, "scale": scale, "center_kind": "median",
                                        "scale_kind": "MAD"}
    if method == "iqr":
        q1, q3 = quantile(xs, 0.25), quantile(xs, 0.75)
        iqr = q3 - q1
        if iqr == 0:
            raise DegenerateSpread(
                "the interquartile range is 0: the middle half of this column is a "
                "single value. Use a rate or category check instead of a spread check."
            )
        return q1 - threshold * iqr, q3 + threshold * iqr, {
            "center": (q1 + q3) / 2, "scale": iqr, "center_kind": "quartile midpoint",
            "scale_kind": "IQR"}
    m = statistics.fmean(xs)
    sd = statistics.stdev(xs)
    if sd == 0:
        raise DegenerateSpread("standard deviation is 0: this column is constant")
    return m - threshold * sd, m + threshold * sd, {"center": m, "scale": sd,
                                                    "center_kind": "mean", "scale_kind": "sd"}


def cmd_outliers(args, backend: Backend) -> tuple[dict, dict]:
    table = _load_for(args, backend)
    idx = resolve_column(table, args.col)
    xs, report = column_values(table, idx)
    if len(xs) < 3:
        raise DataError("outlier detection needs at least 3 usable observations")
    threshold = args.threshold
    if threshold is None:
        threshold = {"mad": MODIFIED_Z_CUTOFF, "iqr": 1.5, "zscore": 3.0}[args.method]
    warnings = _drop_note(report)
    if args.method == "zscore":
        warnings.append("the z-score rule assumes normality; on skewed or heavy-tailed "
                        "data it flags the wrong tail and misses real anomalies - "
                        "--method mad is the safer default")

    baseline_values = xs
    baseline_report = report
    baseline_source = "the input file itself (in-sample threshold)"
    if args.baseline:
        btable = load_table(args.baseline, delimiter=args.delimiter,
                            has_header=(False if args.no_header else None),
                            encoding=args.encoding, backend=backend)
        bidx = resolve_column(btable, args.col)
        baseline_values, baseline_report = column_values(btable, bidx)
        if len(baseline_values) < 3:
            raise DataError("the baseline window has fewer than 3 usable observations")
        baseline_source = args.baseline
    else:
        warnings.append("no --baseline given: the threshold was fitted on the same rows "
                        "it is judging, so the firing rate below is in-sample")

    payload: dict[str, Any] = {
        "command": "outliers",
        "column": report["column"],
        "method": args.method,
        "threshold": threshold,
        "n": len(xs),
        "baseline": {"source": baseline_source, "n": len(baseline_values)},
        "backend": backend.report(),
        "rows": report,
    }
    try:
        lo, hi, fit = _outlier_bounds(baseline_values, args.method, threshold)
    except DegenerateSpread as exc:
        payload["degenerate"] = True
        payload["error"] = str(exc)
        payload["warnings"] = warnings + [str(exc)]
        payload["assumptions"] = [
            "a spread-based outlier rule assumes the column has a scale to measure "
            "against; this one does not, so no threshold was produced"
        ]
        data_block = _data_block(table, report)
        data_block["degenerate_scale"] = True
        manifest = make_manifest(
            "outliers", backend, data_block, [],
            assumptions=payload["assumptions"], notes=payload["warnings"],
        )
        return payload, manifest

    flagged = [(i, v) for i, v in enumerate(xs) if v < lo or v > hi]
    baseline_flagged = sum(1 for v in baseline_values if v < lo or v > hi)
    payload["degenerate"] = False
    payload["bounds"] = {"lower": lo, "upper": hi, **fit}
    payload["n_flagged"] = len(flagged)
    payload["firing_rate_observed"] = len(flagged) / len(xs)
    payload["firing_rate_expected_from_baseline"] = baseline_flagged / len(baseline_values)
    payload["baseline_false_positive_count"] = baseline_flagged
    payload["flagged_examples"] = [
        {"row": i, "value": v} for i, v in flagged[:args.max_examples]
    ]
    expected_daily = payload["firing_rate_expected_from_baseline"] * len(xs)
    payload["expected_alerts_per_run_of_this_size"] = expected_daily
    if payload["firing_rate_expected_from_baseline"] > 0.05:
        warnings.append(
            f"this gate fires on {payload['firing_rate_expected_from_baseline']:.1%} of a "
            "known-good window: raise --threshold or switch method, or it gets muted"
        )
    assumptions = [
        "the baseline window is assumed to be known-good; a threshold fitted on a "
        "window that already contained the anomaly will not fire on it",
        "the flagged rows are statistically unusual, which is not the same as wrong - "
        "a genuine spike and a broken pipeline look identical to this check",
    ]
    payload["assumptions"] = assumptions
    payload["warnings"] = warnings
    if args.emit_gate:
        payload["gate"] = {
            "gate_version": 1,
            "column": report["column"],
            "check": "value_within_bounds",
            "method": args.method,
            "threshold": threshold,
            "lower_bound": lo,
            "upper_bound": hi,
            "center": fit["center"],
            "center_kind": fit["center_kind"],
            "scale": fit["scale"],
            "scale_kind": fit["scale_kind"],
            "baseline_source": baseline_source,
            "baseline_n": len(baseline_values),
            "expected_firing_rate": payload["firing_rate_expected_from_baseline"],
            "action": "warn" if payload["firing_rate_expected_from_baseline"] > 0.01 else "block",
            "rationale": (
                f"bounds from {fit['center_kind']} +/- {threshold} x {fit['scale_kind']} "
                f"fitted on {len(baseline_values)} baseline rows"
            ),
            "generated_by": "statistics skill, stats.py outliers",
        }
        if args.gate_out:
            with open(args.gate_out, "w", encoding="utf-8") as handle:
                json.dump(payload["gate"], handle, indent=2)
                handle.write("\n")
            payload["gate_written_to"] = args.gate_out
    results = [result_entry(
        f"outlier rate in {report['column']}", n=len(xs),
        estimate=payload["firing_rate_observed"],
        effect_size={"name": "firing_rate", "value": payload["firing_rate_observed"]},
        interval=None, method=f"{args.method} bounds at threshold {threshold}",
        assumption=assumptions[0],
    )]
    manifest = make_manifest(
        "outliers", backend, _data_block(table, report), results,
        assumptions=assumptions, notes=warnings,
    )
    return payload, manifest


def cmd_regress(args, backend: Backend) -> tuple[dict, dict]:
    table = _load_for(args, backend)
    y_idx = resolve_column(table, args.y)
    x_tokens = [t.strip() for t in args.x.split(",") if t.strip()] if args.x else []
    if not x_tokens:
        x_tokens = [c for i, c in enumerate(table.columns) if i != y_idx]
    x_idx = [resolve_column(table, t) for t in x_tokens]
    rows_used: list[tuple[float, list[float]]] = []
    dropped = 0
    for row in table.rows:
        yv = coerce_number(row[y_idx])[0] if y_idx < len(row) else None
        xv = [coerce_number(row[i])[0] if i < len(row) else None for i in x_idx]
        if yv is None or any(v is None for v in xv):
            dropped += 1
            continue
        rows_used.append((yv, [v for v in xv]))  # type: ignore[misc]
    if len(rows_used) <= len(x_idx) + 1:
        raise DataError("not enough complete rows to fit this model")
    y = [r[0] for r in rows_used]
    columns = [[r[1][j] for r in rows_used] for j in range(len(x_idx))]
    names = [table.columns[i] for i in x_idx]
    fit = ols(y, columns, names)
    report = {
        "column": table.columns[y_idx],
        "rows_total": len(table.rows),
        "n_used": len(rows_used),
        "n_missing": dropped,
        "n_nonnumeric": 0,
        "rows_dropped": dropped,
        "rows_dropped_reported": True,
    }
    sd_y = statistics.stdev(y)
    coefs = []
    for j, name in enumerate(fit.names):
        se = fit.se[j]
        t = fit.coefficients[j] / se if se > 0 else float("nan")
        p = t_two_sided_p(t, fit.f_df[1])
        crit = t_ppf(1 - args.alpha / 2, fit.f_df[1])
        std_beta = None
        if j > 0 and sd_y > 0:
            std_beta = fit.coefficients[j] * statistics.stdev(columns[j - 1]) / sd_y
        coefs.append({
            "name": name,
            "coefficient": fit.coefficients[j],
            "se": se,
            "t": t,
            "p_value": p,
            "ci_lo": fit.coefficients[j] - crit * se,
            "ci_hi": fit.coefficients[j] + crit * se,
            "standardized_beta": std_beta,
        })
    payload: dict[str, Any] = {
        "command": "regress",
        "y": table.columns[y_idx],
        "x": names,
        "n": fit.n,
        "coefficients": coefs,
        "r_squared": fit.r2,
        "adj_r_squared": fit.adj_r2,
        "residual_sd": fit.sigma,
        "f_statistic": fit.fstat,
        "f_df": list(fit.f_df),
        "f_p_value": f_sf(fit.fstat, fit.f_df[0], fit.f_df[1]),
        "backend": backend.report(),
        "rows": report,
    }
    warnings = []
    if dropped:
        warnings.append(f"{dropped} of {len(table.rows)} rows dropped for a missing or "
                        "non-numeric value in y or an x")
    if len(names) > 1:
        warnings.append("per-coefficient p-values here are not corrected for the number "
                        "of predictors; with many predictors, read them as descriptive")
    if args.diagnostics:
        e = fit.residuals
        n = fit.n
        dw = (sum((e[i] - e[i - 1]) ** 2 for i in range(1, n)) / sum(v * v for v in e)
              if sum(v * v for v in e) > 0 else float("nan"))
        e2 = [v * v for v in e]
        bp_fit = ols(e2, columns, names)
        bp_lm = n * bp_fit.r2
        bp_p = chi2_sf(bp_lm, len(names))
        s, k = skewness(e), excess_kurtosis(e)
        jb = n / 6.0 * (s ** 2 + (k ** 2) / 4.0)
        jb_p = chi2_sf(jb, 2)
        vifs = {}
        if len(names) > 1:
            for j, name in enumerate(names):
                others = [columns[m] for m in range(len(names)) if m != j]
                other_names = [names[m] for m in range(len(names)) if m != j]
                try:
                    aux = ols(columns[j], others, other_names)
                    vifs[name] = 1.0 / (1.0 - aux.r2) if aux.r2 < 1 else float("inf")
                except statistics.StatisticsError:
                    vifs[name] = float("nan")
        cooks = []
        p_full = len(names) + 1
        for i in range(n):
            h = fit.leverage[i]
            if h >= 1.0:
                cooks.append(float("inf"))
            else:
                cooks.append(e[i] ** 2 * h / (p_full * fit.sigma ** 2 * (1 - h) ** 2))
        payload["diagnostics"] = {
            "durbin_watson": dw,
            "breusch_pagan_lm": bp_lm,
            "breusch_pagan_p": bp_p,
            "residual_skewness": s,
            "residual_excess_kurtosis": k,
            "jarque_bera": jb,
            "jarque_bera_p": jb_p,
            "vif": vifs,
            "max_cooks_distance": max(cooks) if cooks else float("nan"),
            "n_influential_cooks_gt_4_over_n": sum(1 for c in cooks if c > 4.0 / n),
            "max_leverage": max(fit.leverage),
        }
        if dw < 1.5 or dw > 2.5:
            warnings.append(f"Durbin-Watson {dw:.2f}: the residuals are serially "
                            "correlated, so these standard errors are too small")
        if bp_p < 0.05:
            warnings.append(f"Breusch-Pagan p = {bp_p:.4g}: the residual variance moves "
                            "with the fitted value, so the intervals are unreliable - "
                            "use robust standard errors or transform y")
        if jb_p < 0.05:
            warnings.append(f"Jarque-Bera p = {jb_p:.4g}: non-normal residuals; with a "
                            "large n the coefficients are still fine, the prediction "
                            "intervals are not")
        for name, v in vifs.items():
            if v > 10:
                warnings.append(f"VIF for {name} is {v:.1f}: this predictor is nearly a "
                                "linear combination of the others, so its individual "
                                "coefficient means little")
    if numpy is not None:
        backend.note("numpy")
        try:
            design = numpy.column_stack(
                [numpy.ones(fit.n)] + [numpy.asarray(c, dtype=float) for c in columns])
            lstsq_beta = numpy.linalg.lstsq(design, numpy.asarray(y, dtype=float), rcond=None)[0]
            worst = max(
                abs(float(lstsq_beta[j]) - fit.coefficients[j]) /
                max(abs(fit.coefficients[j]), 1e-12)
                for j in range(len(fit.coefficients))
            )
            payload["cross_check"] = {"numpy_lstsq_max_relative_difference": worst}
        except Exception as exc:
            payload["cross_check"] = {"error": str(exc)}
    assumptions = [
        "OLS assumes the relationship is linear in the parameters, the residuals are "
        "independent with constant variance, and no important predictor is omitted",
        "with observational data these coefficients are associations; a coefficient "
        "is a causal effect only under an assignment mechanism this tool cannot see",
    ]
    payload["assumptions"] = assumptions
    payload["warnings"] = warnings
    results = []
    for c in coefs[1:]:
        results.append(result_entry(
            f"coefficient on {c['name']}", n=fit.n, estimate=c["coefficient"],
            effect_size={"name": "standardized_beta", "value": c["standardized_beta"]},
            interval=interval_entry(c["ci_lo"], c["ci_hi"], "t interval", 1 - args.alpha),
            p_value=c["p_value"], method="OLS via Householder QR on centered columns",
            assumption=assumptions[0],
        ))
    results.append(result_entry(
        "model fit", n=fit.n, estimate=fit.r2,
        effect_size={"name": "r_squared", "value": fit.r2},
        interval=None, p_value=payload["f_p_value"],
        method="F test against the intercept-only model", assumption=assumptions[0],
        interval_omitted_reason=(
            "an interval on R-squared needs the noncentral F distribution, which "
            "this tool does not implement; the coefficients above carry intervals"),
    ))
    manifest = make_manifest(
        "regress", backend, _data_block(table, report), results,
        comparisons={"tried": 1, "correction": None,
                     "coefficient_tests": len(names)},
        claims=[f"{n} is associated with {table.columns[y_idx]}" for n in names],
        assumptions=assumptions, notes=warnings,
    )
    return payload, manifest


def cmd_evaluate(args, backend: Backend) -> tuple[dict, dict]:
    table = _load_for(args, backend)
    t_idx = resolve_column(table, args.truth, numeric_default=False)
    s_idx = resolve_column(table, args.score)
    truth: list[int] = []
    score: list[float] = []
    dropped = 0
    bad_labels = 0
    for row in table.rows:
        tv = coerce_number(row[t_idx])[0] if t_idx < len(row) else None
        sv = coerce_number(row[s_idx])[0] if s_idx < len(row) else None
        if tv is None and t_idx < len(row):
            raw = row[t_idx].strip().lower()
            if raw in ("true", "yes", "y", "pos", "positive"):
                tv = 1.0
            elif raw in ("false", "no", "n", "neg", "negative"):
                tv = 0.0
        if tv is None or sv is None:
            dropped += 1
            continue
        if tv not in (0.0, 1.0):
            bad_labels += 1
            dropped += 1
            continue
        truth.append(int(tv))
        score.append(sv)
    if len(truth) < 2 or len(set(truth)) < 2:
        raise DataError("binary evaluation needs at least one positive and one negative row")
    n = len(truth)
    threshold = args.threshold
    tp = sum(1 for t, s in zip(truth, score) if t == 1 and s >= threshold)
    fp = sum(1 for t, s in zip(truth, score) if t == 0 and s >= threshold)
    fn = sum(1 for t, s in zip(truth, score) if t == 1 and s < threshold)
    tn = sum(1 for t, s in zip(truth, score) if t == 0 and s < threshold)
    precision = tp / (tp + fp) if tp + fp else float("nan")
    recall = tp / (tp + fn) if tp + fn else float("nan")
    f1 = (2 * precision * recall / (precision + recall)
          if precision and recall and not math.isnan(precision) and not math.isnan(recall)
          else float("nan"))
    prevalence = sum(truth) / n
    auc = auc_roc(truth, score)
    scores_are_probabilities = all(0.0 <= s <= 1.0 for s in score)
    bins, ece = calibration_bins(truth, score) if scores_are_probabilities else ([], float("nan"))
    rng = random.Random(args.seed)
    auc_draws = []
    idxs = list(range(n))
    skipped = 0
    for _ in range(args.reps):
        sample = [idxs[rng.randrange(n)] for _ in range(n)]
        t_s = [truth[i] for i in sample]
        if len(set(t_s)) < 2:
            skipped += 1
            continue
        auc_draws.append(auc_roc(t_s, [score[i] for i in sample]))
    auc_draws.sort()
    if auc_draws:
        lo = auc_draws[int((args.alpha / 2) * len(auc_draws))]
        hi = auc_draws[min(len(auc_draws) - 1, int((1 - args.alpha / 2) * len(auc_draws)))]
    else:
        lo = hi = float("nan")
    warnings: list[str] = []
    if dropped:
        warnings.append(f"{dropped} of {len(table.rows)} rows unusable "
                        f"({bad_labels} had a truth value that was not 0 or 1)")
    if args.split == "in-sample":
        warnings.append("this is an in-sample number: it describes the fit, not expected "
                        "performance on new data, and it must not be reported as accuracy")
    elif args.split == "unknown":
        warnings.append("--split unknown: nothing here can rule out that the model saw "
                        "these rows in training, which would make every metric optimistic")
    if prevalence < 0.1 or prevalence > 0.9:
        warnings.append(f"base rate is {prevalence:.1%}: accuracy is close to meaningless "
                        "at this imbalance - read precision, recall and the confusion matrix")
    if not scores_are_probabilities:
        warnings.append("scores are not in [0, 1], so Brier score and calibration were "
                        "skipped: they only mean something for probabilities")
    if args.seed is None:
        warnings.append("no --seed given: the AUC interval cannot be reproduced exactly")
    payload = {
        "command": "evaluate",
        "task": "binary",
        "n": n,
        "split": args.split,
        "threshold": threshold,
        "prevalence": prevalence,
        "confusion": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
        "accuracy": (tp + tn) / n,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "auc": auc,
        "auc_ci": {"lo": lo, "hi": hi, "level": 1 - args.alpha,
                   "kind": "percentile bootstrap", "reps": len(auc_draws),
                   "reps_skipped_single_class": skipped},
        "brier": brier_score(truth, score) if scores_are_probabilities else None,
        "expected_calibration_error": ece if scores_are_probabilities else None,
        "calibration_bins": bins,
        "baseline_always_majority_accuracy": max(prevalence, 1 - prevalence),
        "seed": args.seed,
        "backend": backend.report(),
    }
    assumptions = [
        "every metric here assumes these rows are drawn from the population the model "
        "will meet in production; a shifted distribution invalidates all of them",
        "the interval on AUC is a bootstrap over these rows only: it covers sampling "
        "noise, not model risk, and not the choice of threshold",
    ]
    payload["assumptions"] = assumptions
    payload["warnings"] = warnings
    results = [result_entry(
        "AUC", n=n, estimate=auc, effect_size={"name": "auc_above_chance", "value": auc - 0.5},
        interval=interval_entry(lo, hi, "percentile bootstrap", 1 - args.alpha),
        method=f"rank-based AUC with a {args.reps}-rep bootstrap interval",
        assumption=assumptions[0],
    ), result_entry(
        "accuracy against the majority-class baseline", n=n,
        estimate=payload["accuracy"] - payload["baseline_always_majority_accuracy"],
        effect_size={"name": "accuracy_lift_over_majority",
                     "value": payload["accuracy"] - payload["baseline_always_majority_accuracy"]},
        interval=None, method="point comparison against always-predict-majority",
        assumption=assumptions[0],
    )]
    manifest = make_manifest(
        "evaluate", backend,
        {"source": table.path, "column": table.columns[s_idx], "n": n,
         "rows_total": len(table.rows), "n_missing": dropped, "n_nonnumeric": 0,
         "rows_dropped": dropped, "rows_dropped_reported": True},
        results,
        design={"observational": True, "randomized_assignment": False,
                "evaluation_data": {"holdout": "holdout", "in-sample": "in_sample",
                                    "cv": "cross_validated",
                                    "unknown": "unknown"}[args.split]},
        randomization={"seeded": args.seed is not None, "seed": args.seed, "reps": args.reps},
        assumptions=assumptions, notes=warnings,
    )
    return payload, manifest


def cmd_risk(args, backend: Backend) -> tuple[dict, dict]:
    table = _load_for(args, backend)
    idx = resolve_column(table, args.col)
    values, report = column_values(table, idx)
    if len(values) < 20:
        raise DataError("a risk estimate needs at least 20 usable observations")
    warnings = _drop_note(report)
    if args.from_prices:
        rets = [math.log(values[i] / values[i - 1]) for i in range(1, len(values))
                if values[i - 1] > 0 and values[i] > 0]
        source_kind = "log returns computed from a price column"
    else:
        rets = values
        source_kind = "returns as given"
    n = len(rets)
    level = args.var
    tail = 1 - level
    m = statistics.fmean(rets)
    sd = statistics.stdev(rets)
    q = quantile(rets, tail)
    var_hist = -q
    losses = [r for r in rets if r <= q]
    cvar = -statistics.fmean(losses) if losses else float("nan")
    z = norm_ppf(tail)
    var_normal = -(m + z * sd)
    s, k = skewness(rets), excess_kurtosis(rets)
    z_cf = (z + (z ** 2 - 1) * s / 6 + (z ** 3 - 3 * z) * k / 24
            - (2 * z ** 3 - 5 * z) * s ** 2 / 36)
    var_cf = -(m + z_cf * sd)
    horizon = args.horizon
    rho = acf(rets, min(5, n // 4))
    lo, hi, _ = bootstrap_ci(rets, lambda vs: -quantile(vs, tail), reps=args.reps,
                             alpha=args.alpha, seed=args.seed)
    payload = {
        "command": "risk",
        "column": report["column"],
        "input": source_kind,
        "n": n,
        "confidence": level,
        "var_historical": var_hist,
        "var_historical_ci": {"lo": lo, "hi": hi, "level": 1 - args.alpha,
                              "kind": "percentile bootstrap"},
        "cvar_historical": cvar,
        "var_normal": var_normal,
        "var_cornish_fisher": var_cf,
        "mean_return": m,
        "sd_return": sd,
        "skewness": s,
        "excess_kurtosis": k,
        "max_drawdown": max_drawdown(rets),
        "worst_observation": min(rets),
        "horizon": horizon,
        "var_historical_scaled_to_horizon": var_hist * math.sqrt(horizon),
        "lag1_autocorrelation": rho[1] if len(rho) > 1 else float("nan"),
        "seed": args.seed,
        "reps": args.reps,
        "backend": backend.report(),
        "rows": report,
    }
    if k > 1:
        warnings.append(f"excess kurtosis {k:.2f}: the tails are fatter than normal, so "
                        "var_normal understates the loss - prefer the historical or "
                        "Cornish-Fisher figure")
    if abs(payload["lag1_autocorrelation"]) > 2 / math.sqrt(n):
        warnings.append("returns are autocorrelated at lag 1, so the square-root-of-time "
                        "scaling to the horizon is not valid here")
    if n < 250 and level >= 0.99:
        warnings.append(f"a {level:.0%} VaR from n = {n} rests on roughly "
                        f"{max(1, int(n * (1 - level)))} observations: the interval is wide "
                        "for a reason")
    warnings.append("VaR is a quantile of the past, not a bound on the future; it says "
                    "nothing about the size of the loss beyond it, which is what CVaR is for")
    assumptions = [
        "historical VaR assumes the future distribution of returns looks like the "
        "sample period, which fails exactly when it matters",
        "the square-root-of-time scaling assumes independent, identically distributed "
        "returns; check the lag-1 autocorrelation above before using it",
        "the normal VaR additionally assumes normal returns, which financial returns "
        "reliably are not",
    ]
    payload["assumptions"] = assumptions
    payload["warnings"] = warnings
    results = [result_entry(
        f"{level:.0%} VaR", n=n, estimate=var_hist,
        effect_size={"name": "var_as_fraction_of_position", "value": var_hist},
        interval=interval_entry(lo, hi, "percentile bootstrap", 1 - args.alpha),
        method="historical (empirical quantile) VaR", assumption=assumptions[0],
    ), result_entry(
        f"{level:.0%} CVaR", n=n, estimate=cvar,
        effect_size={"name": "expected_shortfall", "value": cvar},
        interval=None, method="mean of the losses beyond the VaR quantile",
        assumption=assumptions[0],
    )]
    manifest = make_manifest(
        "risk", backend, _data_block(table, report), results,
        randomization={"seeded": args.seed is not None, "seed": args.seed, "reps": args.reps},
        assumptions=assumptions, notes=warnings,
    )
    return payload, manifest


def power_two_sample(effect: float, alpha: float, power: float) -> float:
    """n per group for a two-sample difference of means, normal approximation.

    Normal approximation only: it uses z where a t-based calculation would use
    an iterated t quantile, so it understates n by roughly 2 per group below
    n = 30. Add 2 per group there, or run an exact calculation.
    """
    za = norm_ppf(1 - alpha / 2)
    zb = norm_ppf(power)
    return 2 * (za + zb) ** 2 / (effect ** 2)


def cmd_power(args, backend: Backend) -> tuple[dict, dict]:
    alpha, warnings = args.alpha, []
    if args.p1 is not None and args.p2 is not None:
        h = 2 * math.asin(math.sqrt(args.p1)) - 2 * math.asin(math.sqrt(args.p2))
        effect = abs(h)
        effect_kind = "Cohen's h (arcsine-transformed proportions)"
    elif args.effect is not None:
        effect = abs(args.effect)
        effect_kind = "Cohen's d (standardized mean difference)"
    else:
        raise DataError("give --effect, or --p1 and --p2")
    if effect == 0:
        raise DataError("an effect of 0 needs an infinite sample; give a size worth detecting")
    design = args.design
    factor = 2.0 if design == "two-sample" else 1.0
    za = norm_ppf(1 - alpha / 2)
    solved_for = "n"
    n_per_group = achieved_power = detectable = None
    if args.n is None:
        zb = norm_ppf(args.power)
        n_per_group = factor * (za + zb) ** 2 / effect ** 2
        n_per_group = math.ceil(n_per_group)
        achieved_power = norm_cdf(effect * math.sqrt(n_per_group / factor) - za)
    elif args.power_given:
        solved_for = "effect"
        zb = norm_ppf(args.power)
        n_per_group = args.n
        detectable = (za + zb) * math.sqrt(factor / args.n)
        achieved_power = args.power
    else:
        solved_for = "power"
        n_per_group = args.n
        achieved_power = norm_cdf(effect * math.sqrt(args.n / factor) - za)
    if n_per_group is not None and n_per_group < 30:
        warnings.append("normal approximation: below about n = 30 per group this "
                        "understates the required n by roughly 2 - add 2 per group "
                        "or use a t-based calculation")
    warnings.append("an effect size you chose because it is what you hope to see is not "
                    "a power calculation; use the smallest difference that would change "
                    "a decision")
    payload = {
        "command": "power",
        "solved_for": solved_for,
        "design": design,
        "effect": effect,
        "effect_kind": effect_kind,
        "alpha": alpha,
        "target_power": args.power,
        "n_per_group": n_per_group,
        "n_total": (n_per_group * 2 if design == "two-sample" and n_per_group else n_per_group),
        "achieved_power": achieved_power,
        "minimum_detectable_effect": detectable,
        "method": "normal approximation, two-sided",
        "backend": backend.report(),
        "assumptions": [
            "the normal approximation assumes the test statistic is approximately "
            "normal under both hypotheses, which is the large-sample case",
            "power is computed for a single planned comparison; testing several "
            "outcomes needs a corrected alpha, which raises n",
        ],
        "warnings": warnings,
    }
    results = [result_entry(
        "required sample size" if solved_for == "n" else f"solved {solved_for}",
        n=int(n_per_group) if n_per_group else 0,
        estimate=float(n_per_group) if solved_for == "n" else
        (achieved_power if solved_for == "power" else detectable),
        effect_size={"name": effect_kind, "value": effect},
        interval=None, method="normal approximation power calculation",
        assumption=payload["assumptions"][0],
    )]
    manifest = make_manifest(
        "power", backend,
        {"source": "none (planning calculation)", "n": int(n_per_group or 0),
         "rows_total": 0, "n_missing": 0, "n_nonnumeric": 0,
         "rows_dropped": 0, "rows_dropped_reported": True},
        results, assumptions=payload["assumptions"], notes=warnings,
    )
    return payload, manifest


def decimal_odds(value: float, fmt: str) -> float:
    """Convert american or fractional odds to decimal. Fractional as a/b."""
    if fmt == "decimal":
        return value
    if fmt == "american":
        return 1 + (value / 100.0 if value > 0 else 100.0 / abs(value))
    raise DataError("fractional odds go in as --odds a/b with --format fractional")


def cmd_ev(args, backend: Backend) -> tuple[dict, dict]:
    raw = args.odds
    if args.format == "fractional":
        if "/" not in raw:
            raise DataError("fractional odds look like 5/2")
        num, den = raw.split("/", 1)
        dec = 1 + float(num) / float(den)
    else:
        dec = decimal_odds(float(raw), args.format)
    p = args.p
    if not 0 < p < 1:
        raise DataError("--p is a probability strictly between 0 and 1")
    b = dec - 1
    stake = args.stake
    implied = 1 / dec
    edge = p * dec - 1
    ev = stake * (p * b - (1 - p))
    variance = stake ** 2 * p * (1 - p) * dec ** 2
    sd = math.sqrt(variance)
    kelly = (p * b - (1 - p)) / b if b > 0 else float("nan")
    payload: dict[str, Any] = {
        "command": "ev",
        "odds_decimal": dec,
        "odds_input": f"{raw} ({args.format})",
        "implied_probability": implied,
        "your_probability": p,
        "edge": edge,
        "stake": stake,
        "expected_value": ev,
        "expected_value_per_unit_staked": ev / stake if stake else float("nan"),
        "sd_per_bet": sd,
        "variance_per_bet": variance,
        "kelly_fraction": kelly,
        "breakeven_probability": implied,
        "backend": backend.report(),
    }
    warnings = [
        "this is arithmetic, not advice: it computes what your stated probability "
        "implies, and says nothing about whether that probability is right",
        f"the edge is entirely a claim about p = {p}: at the market's implied "
        f"{implied:.4f} the edge is exactly 0",
    ]
    if edge <= 0:
        warnings.append("edge is not positive at your stated probability")
    if args.bankroll:
        n_bets = args.bets
        rng = random.Random(args.seed)
        ruined = 0
        for _ in range(args.sims):
            bank = args.bankroll
            for _ in range(n_bets):
                if bank < stake:
                    ruined += 1
                    break
                bank += stake * b if rng.random() < p else -stake
            else:
                if bank < stake:
                    ruined += 1
        payload["risk_of_ruin"] = {
            "estimate": ruined / args.sims,
            "method": f"Monte Carlo, {args.sims} simulations of {n_bets} flat bets",
            "bankroll": args.bankroll,
            "bets": n_bets,
            "seed": args.seed,
            "monte_carlo_se": math.sqrt(
                max(ruined / args.sims * (1 - ruined / args.sims), 0) / args.sims),
        }
        if abs(b - 1.0) < 1e-12 and p != 0.5:
            units = args.bankroll / stake
            payload["risk_of_ruin"]["closed_form_even_money"] = ((1 - p) / p) ** units
        if args.seed is None:
            warnings.append("no --seed given: the ruin simulation cannot be reproduced")
    assumptions = [
        "expected value assumes your probability is calibrated; an EV computed from "
        "a wrong p is a precise statement about a wrong belief",
        "variance and ruin assume independent bets at a fixed stake, and no limits, "
        "correlation between outcomes, or changes in the odds",
    ]
    payload["assumptions"] = assumptions
    payload["warnings"] = warnings
    results = [result_entry(
        "expected value per bet", n=1, estimate=ev,
        effect_size={"name": "edge", "value": edge}, interval=None,
        method="closed-form expected value", assumption=assumptions[0],
    )]
    randomization = None
    if args.bankroll:
        randomization = {"seeded": args.seed is not None, "seed": args.seed, "reps": args.sims}
    manifest = make_manifest(
        "ev", backend,
        {"source": "none (parametric calculation)", "n": 1, "rows_total": 0,
         "n_missing": 0, "n_nonnumeric": 0, "rows_dropped": 0,
         "rows_dropped_reported": True},
        results, randomization=randomization,
        assumptions=assumptions, notes=warnings,
    )
    return payload, manifest


def cmd_series(args, backend: Backend) -> tuple[dict, dict]:
    table = _load_for(args, backend)
    idx = resolve_column(table, args.col)
    values, report = column_values(table, idx)
    if len(values) < 10:
        raise DataError("a series check needs at least 10 usable observations")
    warnings = _drop_note(report)
    series = values
    kind = "levels as given"
    if args.returns:
        series = [math.log(values[i] / values[i - 1]) for i in range(1, len(values))
                  if values[i - 1] > 0 and values[i] > 0]
        kind = "log returns"
    n = len(series)
    lags = min(args.acf, max(1, n // 4))
    rho = acf(series, lags)
    band = 1.96 / math.sqrt(n)
    q, q_p = ljung_box(rho, n, lags)
    payload: dict[str, Any] = {
        "command": "series",
        "column": report["column"],
        "transform": kind,
        "n": n,
        "acf": [{"lag": k, "rho": rho[k], "beyond_band": abs(rho[k]) > band}
                for k in range(1, lags + 1)],
        "acf_band_95": band,
        "ljung_box_q": q,
        "ljung_box_df": lags,
        "ljung_box_p": q_p,
        "seed": args.seed,
        "backend": backend.report(),
        "rows": report,
    }
    significant = [k for k in range(1, lags + 1) if abs(rho[k]) > band]
    if significant:
        warnings.append(f"autocorrelation beyond the 95% band at lags {significant[:5]}: "
                        "observations are not independent, so any interval computed as "
                        "if they were is too narrow")
    if args.stationarity:
        tau, used_lags = adf_statistic(series, args.adf_lags)
        half = n // 2
        first, second = series[:half], series[half:]
        payload["stationarity"] = {
            "adf_tau": tau,
            "adf_lags": used_lags,
            "adf_critical_values_asymptotic": dict(ADF_TAU_MU),
            "adf_reading": (
                "reject a unit root at 5%" if tau < ADF_TAU_MU["5%"]
                else "cannot reject a unit root at 5%"),
            "split_half_mean_first": statistics.fmean(first),
            "split_half_mean_second": statistics.fmean(second),
            "split_half_sd_first": statistics.stdev(first),
            "split_half_sd_second": statistics.stdev(second),
            "variance_ratio_second_over_first": (
                statistics.variance(second) / statistics.variance(first)
                if statistics.variance(first) > 0 else float("nan")),
        }
        if tau >= ADF_TAU_MU["5%"]:
            warnings.append("a unit root cannot be rejected: this series wanders, so a "
                            "regression on its level will find a relationship whether or "
                            "not one exists - difference it or model returns instead")
        vr = payload["stationarity"]["variance_ratio_second_over_first"]
        if not math.isnan(vr) and (vr > 2 or vr < 0.5):
            warnings.append(f"variance changed by {vr:.1f}x between the first and second "
                            "half: a single volatility estimate describes neither half")
    assumptions = [
        "the autocorrelation band assumes white noise under the null; with strong "
        "trend the band is not the right reference",
        "the Dickey-Fuller critical values printed here are asymptotic for the "
        "constant-only case; a value near a cutoff is not a decision",
    ]
    payload["assumptions"] = assumptions
    payload["warnings"] = warnings
    results = [result_entry(
        f"serial dependence in {report['column']}", n=n, estimate=rho[1],
        effect_size={"name": "lag1_autocorrelation", "value": rho[1]},
        interval=interval_entry(-band, band, "white-noise band", 0.95),
        p_value=q_p, method=f"Ljung-Box Q over {lags} lags",
        assumption=assumptions[0],
    )]
    manifest = make_manifest(
        "series", backend, _data_block(table, report), results,
        assumptions=assumptions, notes=warnings,
    )
    return payload, manifest


# --------------------------------------------------------------------------
# output
# --------------------------------------------------------------------------

def _sanitize(obj: Any) -> Any:
    """Replace NaN and infinity with None so the JSON stays strict JSON."""
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize(v) for v in obj]
    return obj


def _fmt(value: Any) -> str:
    if isinstance(value, bool) or value is None:
        return str(value)
    if isinstance(value, float):
        if math.isnan(value):
            return "nan"
        if math.isinf(value):
            return "inf" if value > 0 else "-inf"
        return f"{value:.6g}"
    return str(value)


def render_text(payload: dict) -> str:
    lines: list[str] = []

    def walk(obj: Any, indent: int, key: str | None) -> None:
        pad = "  " * indent
        if isinstance(obj, dict):
            if key is not None:
                lines.append(f"{pad}{key}:")
            for k, v in obj.items():
                walk(v, indent + (1 if key is not None else 0), k)
        elif isinstance(obj, list):
            if not obj:
                return
            if all(not isinstance(v, (dict, list)) for v in obj):
                lines.append(f"{pad}{key}: " + ", ".join(_fmt(v) for v in obj))
                return
            lines.append(f"{pad}{key}:")
            for item in obj:
                walk(item, indent + 1, "-")
        else:
            lines.append(f"{pad}{key}: {_fmt(obj)}")

    walk(payload, 0, None)
    return "\n".join(lines)


def emit(payload: dict, manifest: dict, args) -> int:
    if args.manifest:
        with open(args.manifest, "w", encoding="utf-8") as handle:
            json.dump(_sanitize(manifest), handle, indent=2)
            handle.write("\n")
    if args.json:
        print(json.dumps(_sanitize(payload), indent=2))
    else:
        print(render_text(payload))
    return 0


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def _add_common(parser: argparse.ArgumentParser, *, needs_path: bool = True) -> None:
    if needs_path:
        parser.add_argument("path", help="CSV or other tabular file")
        parser.add_argument("--delimiter", default=None,
                            help="column delimiter (sniffed when omitted)")
        parser.add_argument("--no-header", action="store_true",
                            help="the file has no header row")
        parser.add_argument("--encoding", default="utf-8")
    parser.add_argument("--alpha", type=float, default=DEFAULT_ALPHA,
                        help=f"significance level (default {DEFAULT_ALPHA})")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--manifest", default=None,
                        help="write the analysis manifest here for stats_check.py")
    parser.add_argument("--seed", type=int, default=None,
                        help="seed for any resampling in this command")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="stats.py",
        description="Statistics with the assumptions attached. Every command reports n, "
                    "what it could not use, and what would overturn the answer.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("describe", help="descriptives with an interval on the mean")
    _add_common(p)
    p.add_argument("--col", default=None, help="column by name or index")
    p.set_defaults(func=cmd_describe)

    p = sub.add_parser("test", help="compare groups, method chosen and justified")
    _add_common(p)
    p.add_argument("--col", default=None, help="value column, or two columns as a,b")
    p.add_argument("--by", default=None, help="grouping column")
    p.add_argument("--method", default="auto",
                   choices=["auto", "permutation", "welch", "student", "mannwhitney"])
    p.add_argument("--stat", default="mean", choices=["mean", "median"],
                   help="statistic compared by the resampling methods")
    p.add_argument("--mu", type=float, default=None,
                   help="one-sample null value when there is no grouping column")
    p.add_argument("--reps", type=int, default=DEFAULT_REPS)
    p.add_argument("--pairwise", action="store_true",
                   help="all pairwise comparisons, Holm-corrected")
    p.set_defaults(func=cmd_test)

    p = sub.add_parser("boot", help="percentile bootstrap interval for a statistic")
    _add_common(p)
    p.add_argument("--col", default=None)
    p.add_argument("--stat", default="median",
                   help="mean, median, sd, trimmed_mean, iqr, min, max, or q95 for a quantile")
    p.add_argument("--reps", type=int, default=DEFAULT_REPS)
    p.set_defaults(func=cmd_boot)

    p = sub.add_parser("robust", help="median, MAD, trimmed and winsorized statistics")
    _add_common(p)
    p.add_argument("--col", default=None)
    p.set_defaults(func=cmd_robust)

    p = sub.add_parser("outliers", help="flag unusual values and emit a gate definition")
    _add_common(p)
    p.add_argument("--col", default=None)
    p.add_argument("--method", default="mad", choices=["mad", "iqr", "zscore"])
    p.add_argument("--threshold", type=float, default=None,
                   help="default 3.5 for mad, 1.5 for iqr, 3.0 for zscore")
    p.add_argument("--baseline", default=None,
                   help="known-good window the threshold is fitted on")
    p.add_argument("--emit-gate", action="store_true",
                   help="include a gate definition a pipeline can enforce")
    p.add_argument("--gate-out", default=None, help="also write the gate to this path")
    p.add_argument("--max-examples", type=int, default=10)
    p.set_defaults(func=cmd_outliers)

    p = sub.add_parser("regress", help="OLS with intervals and diagnostics")
    _add_common(p)
    p.add_argument("--y", default=None, help="outcome column")
    p.add_argument("--x", default=None, help="predictor columns, comma separated")
    p.add_argument("--diagnostics", action="store_true")
    p.set_defaults(func=cmd_regress)

    p = sub.add_parser("evaluate", help="binary classifier metrics with an AUC interval")
    _add_common(p)
    p.add_argument("--truth", default=None, help="0/1 outcome column")
    p.add_argument("--score", default=None, help="predicted score or probability column")
    p.add_argument("--task", default="binary", choices=["binary"])
    p.add_argument("--threshold", type=float, default=0.5)
    p.add_argument("--reps", type=int, default=2000)
    p.add_argument("--split", required=True, choices=["holdout", "in-sample", "cv", "unknown"],
                   help="what data these predictions are on; required, because an "
                        "unstated split is how in-sample numbers get reported as performance")
    p.set_defaults(func=cmd_evaluate)

    p = sub.add_parser("risk", help="VaR, CVaR, drawdown, with the assumptions named")
    _add_common(p)
    p.add_argument("--col", default=None)
    p.add_argument("--var", type=float, default=0.95, help="confidence level")
    p.add_argument("--horizon", type=int, default=1, help="periods to scale to")
    p.add_argument("--from-prices", action="store_true",
                   help="the column is prices; convert to log returns first")
    p.add_argument("--reps", type=int, default=2000)
    p.set_defaults(func=cmd_risk)

    p = sub.add_parser("power", help="sample size, power or detectable effect")
    _add_common(p, needs_path=False)
    p.add_argument("--effect", type=float, default=None, help="standardized effect size")
    p.add_argument("--p1", type=float, default=None, help="proportion in group 1")
    p.add_argument("--p2", type=float, default=None, help="proportion in group 2")
    p.add_argument("--power", type=float, default=0.8)
    p.add_argument("--power-given", action="store_true",
                   help="with --n, solve for the minimum detectable effect")
    p.add_argument("--n", type=int, default=None, help="n per group, to solve for power")
    p.add_argument("--design", default="two-sample", choices=["two-sample", "one-sample"])
    p.set_defaults(func=cmd_power)

    p = sub.add_parser("ev", help="edge, expected value, variance and ruin as arithmetic")
    _add_common(p, needs_path=False)
    p.add_argument("--odds", required=True, help="decimal 2.10, american +110, or 5/2")
    p.add_argument("--format", default="decimal", choices=["decimal", "american", "fractional"])
    p.add_argument("--p", type=float, required=True, help="your probability of winning")
    p.add_argument("--stake", type=float, default=100.0)
    p.add_argument("--bankroll", type=float, default=None,
                   help="simulate risk of ruin over --bets flat bets")
    p.add_argument("--bets", type=int, default=1000)
    p.add_argument("--sims", type=int, default=10000)
    p.set_defaults(func=cmd_ev)

    p = sub.add_parser("series", help="autocorrelation and a stationarity check")
    _add_common(p)
    p.add_argument("--col", default=None)
    p.add_argument("--acf", type=int, default=20, help="lags to report")
    p.add_argument("--stationarity", action="store_true")
    p.add_argument("--adf-lags", type=int, default=1)
    p.add_argument("--returns", action="store_true",
                   help="convert a price column to log returns first")
    p.set_defaults(func=cmd_series)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    backend = Backend()
    try:
        payload, manifest = args.func(args, backend)
    except (DataError, DegenerateSpread, statistics.StatisticsError, ValueError) as exc:
        message = {"error": type(exc).__name__, "message": str(exc)}
        if getattr(args, "json", False):
            print(json.dumps(message, indent=2))
        else:
            print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    return emit(payload, manifest, args)


if __name__ == "__main__":
    raise SystemExit(main())
