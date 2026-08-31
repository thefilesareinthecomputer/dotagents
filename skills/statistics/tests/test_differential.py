"""Differential tests: stats.py against scipy, skipped when scipy is absent.

Level 2 of the testing strategy. The certified-value tests in test_stats.py
prove the formulas are right at the points a published table covers; these
prove they stay right in between, against an independent implementation, and
they are the reason detecting the optional dependency is worth anything.

scipy is never required. Every case here is guarded by skipUnless, so the suite
passes identically on a machine that has never installed it, and stats.py
itself imports nothing from it.

Tolerances are relative and are set an order of magnitude or two above the
agreement actually observed (scipy 1.17 on CPython 3.11), so a real drift
fails rather than being absorbed. Three places need a word:

- The far left tail of a CDF. `t_cdf` is `1 - t_sf`, and for t below about -8
  that subtraction has no relative precision left to give: the absolute error
  stays near 1e-17 while the relative error grows without bound. p-values come
  from the survival function, which is compared relatively, so the CDF is
  compared on the absolute scale out there and relatively everywhere else.
- The far tail of the normal CDF, where `statistics.NormalDist` (C `erfc`) and
  scipy's `ndtr` disagree in the last digits below z = -6.
- The Longley coefficients, where the tolerance is set by scipy's own error
  against the NIST certified values (1.2e-11) rather than by this
  implementation's (6.2e-14). test_stats.py holds the accurate side of that
  comparison to the certified digits; this one only shows the two agree.
"""

import csv
import math
import pathlib
import random
import statistics
import sys
import unittest

TESTS = pathlib.Path(__file__).resolve().parent
FIXTURES = TESTS / "fixtures"
sys.path.insert(0, str(TESTS.parent / "scripts"))

import stats  # noqa: E402

try:
    from scipy import linalg as sp_linalg
    from scipy import special as sp_special
    from scipy import stats as sp_stats
    HAVE_SCIPY = True
except ImportError:  # pragma: no cover - exercised by absence, not by a branch
    HAVE_SCIPY = False

requires_scipy = unittest.skipUnless(HAVE_SCIPY, "scipy is not installed")


class Differential(unittest.TestCase):

    def assertClose(self, ours, theirs, rtol, atol=0.0, msg=""):
        theirs = float(theirs)
        tolerance = atol + rtol * abs(theirs)
        self.assertLessEqual(
            abs(ours - theirs), tolerance,
            msg=f"{msg}: ours={ours!r} scipy={theirs!r} "
                f"diff={abs(ours - theirs):.3e} allowed={tolerance:.3e}")


DFS = (1, 2, 3, 5, 10, 20, 30, 60, 120, 500)
ALPHAS = (0.10, 0.05, 0.025, 0.01, 0.001)


@requires_scipy
class StudentT(Differential):

    def test_survival_function_at_standard_alphas(self):
        for df in DFS:
            for alpha in ALPHAS:
                q = float(sp_stats.t.ppf(1 - alpha, df))
                self.assertClose(stats.t_sf(q, df), sp_stats.t.sf(q, df),
                                 rtol=1e-9, msg=f"t_sf df={df} alpha={alpha}")
                self.assertClose(stats.t_cdf(q, df), sp_stats.t.cdf(q, df),
                                 rtol=1e-9, msg=f"t_cdf df={df} alpha={alpha}")

    def test_cdf_across_the_range(self):
        # atol carries the far left tail, where 1 - sf has no relative
        # precision left; rtol carries everywhere else.
        for df in DFS:
            for t in (-40.0, -8.0, -2.5, -0.3, 0.0, 0.3, 2.5, 8.0, 40.0):
                self.assertClose(stats.t_cdf(t, df), sp_stats.t.cdf(t, df),
                                 rtol=1e-9, atol=1e-16, msg=f"t_cdf({t}, {df})")
                self.assertClose(stats.t_sf(t, df), sp_stats.t.sf(t, df),
                                 rtol=1e-9, atol=1e-16, msg=f"t_sf({t}, {df})")

    def test_two_sided_p_value(self):
        for df in (1, 4, 9, 25, 200):
            for t in (0.2, 1.0, 2.06, 3.5, 7.0):
                self.assertClose(
                    stats.t_two_sided_p(t, df),
                    2 * sp_stats.t.sf(abs(t), df), rtol=1e-10,
                    msg=f"two-sided p at t={t} df={df}")

    def test_quantiles(self):
        for df in DFS:
            for p in (0.75, 0.9, 0.95, 0.975, 0.99, 0.995, 0.999):
                self.assertClose(stats.t_ppf(p, df), sp_stats.t.ppf(p, df),
                                 rtol=1e-9, msg=f"t_ppf({p}, {df})")


@requires_scipy
class ChiSquareAndF(Differential):

    def test_chi_square_survival_at_standard_alphas(self):
        for df in (1, 2, 3, 4, 5, 10, 20, 30, 50, 100):
            for alpha in ALPHAS:
                q = float(sp_stats.chi2.ppf(1 - alpha, df))
                self.assertClose(stats.chi2_sf(q, df), sp_stats.chi2.sf(q, df),
                                 rtol=1e-10, msg=f"chi2_sf df={df} alpha={alpha}")

    def test_chi_square_survival_across_the_range(self):
        for df in (1, 2, 5, 10, 30, 100):
            for x in (0.001, 0.5, 1.0, 5.0, 25.0, 100.0, 300.0):
                self.assertClose(stats.chi2_sf(x, df), sp_stats.chi2.sf(x, df),
                                 rtol=1e-10, atol=1e-300, msg=f"chi2_sf({x}, {df})")

    def test_f_survival_at_standard_alphas(self):
        for df1 in (1, 2, 3, 5, 10, 20):
            for df2 in (1, 2, 5, 10, 20, 60):
                for alpha in ALPHAS:
                    q = float(sp_stats.f.ppf(1 - alpha, df1, df2))
                    self.assertClose(stats.f_sf(q, df1, df2),
                                     sp_stats.f.sf(q, df1, df2), rtol=1e-10,
                                     msg=f"f_sf({df1},{df2}) alpha={alpha}")

    def test_f_survival_across_the_range(self):
        for df1 in (1, 3, 10):
            for df2 in (2, 10, 60):
                for x in (0.25, 1.0, 4.0, 30.0, 200.0):
                    self.assertClose(stats.f_sf(x, df1, df2),
                                     sp_stats.f.sf(x, df1, df2), rtol=1e-10,
                                     msg=f"f_sf({x}, {df1}, {df2})")


@requires_scipy
class NormalAndSpecialFunctions(Differential):

    def test_normal_cdf(self):
        for z in (-6.0, -4.0, -2.5, -1.0, 0.0, 1.0, 2.5, 4.0, 6.0):
            self.assertClose(stats.norm_cdf(z), sp_stats.norm.cdf(z),
                             rtol=1e-9, msg=f"norm_cdf({z})")

    def test_normal_cdf_in_the_far_tail_agrees_absolutely(self):
        # erfc and ndtr part company in the last digits below z = -6; the
        # absolute agreement is what a probability is read for out here.
        for z in (-8.0, -10.0):
            self.assertClose(stats.norm_cdf(z), sp_stats.norm.cdf(z),
                             rtol=0.1, atol=1e-16, msg=f"norm_cdf({z})")

    def test_normal_quantiles(self):
        for p in (0.5, 0.75, 0.9, 0.95, 0.975, 0.99, 0.995, 0.999, 0.9999):
            self.assertClose(stats.norm_ppf(p), sp_stats.norm.ppf(p),
                             rtol=1e-12, msg=f"norm_ppf({p})")

    def test_regularized_incomplete_beta(self):
        for a in (0.5, 1.0, 2.5, 10.0, 40.0):
            for b in (0.5, 1.0, 2.5, 10.0, 40.0):
                for x in (0.01, 0.25, 0.5, 0.75, 0.99):
                    self.assertClose(stats.betainc(a, b, x),
                                     sp_special.betainc(a, b, x), rtol=1e-11,
                                     msg=f"betainc({a}, {b}, {x})")

    def test_regularized_upper_incomplete_gamma(self):
        for a in (0.5, 1.0, 5.0, 25.0):
            for x in (0.1, 1.0, 5.0, 30.0, 90.0):
                self.assertClose(stats.gammainc_upper(a, x),
                                 sp_special.gammaincc(a, x), rtol=1e-11,
                                 msg=f"gammaincc({a}, {x})")


def _samples():
    """Two unequal, unequally-dispersed samples. Fixed seed, so a failure repeats."""
    rng = random.Random(11)
    a = [rng.gauss(10.0, 2.0) for _ in range(23)]
    b = [rng.gauss(11.5, 3.5) for _ in range(31)]
    return a, b


@requires_scipy
class ParametricTests(Differential):

    def setUp(self):
        self.a, self.b = _samples()

    def test_welch_t_test(self):
        t, df, p = stats._welch(self.a, self.b)
        result = sp_stats.ttest_ind(self.a, self.b, equal_var=False)
        self.assertClose(t, result.statistic, rtol=1e-11, msg="welch t")
        self.assertClose(p, result.pvalue, rtol=1e-11, msg="welch p")
        self.assertClose(df, result.df, rtol=1e-12, msg="welch-satterthwaite df")

    def test_student_t_test(self):
        t, df, p = stats._student(self.a, self.b)
        result = sp_stats.ttest_ind(self.a, self.b, equal_var=True)
        self.assertClose(t, result.statistic, rtol=1e-11, msg="student t")
        self.assertClose(p, result.pvalue, rtol=1e-11, msg="student p")
        self.assertEqual(df, len(self.a) + len(self.b) - 2)

    def test_one_way_anova(self):
        rng = random.Random(5)
        groups = {
            "a": [rng.gauss(0.0, 1.0) for _ in range(12)],
            "b": [rng.gauss(0.8, 1.0) for _ in range(15)],
            "c": [rng.gauss(-0.4, 1.4) for _ in range(11)],
        }
        f, df1, df2, _eta2, p = stats._anova(groups)
        result = sp_stats.f_oneway(*groups.values())
        self.assertClose(f, result.statistic, rtol=1e-11, msg="anova F")
        self.assertClose(p, result.pvalue, rtol=1e-11, msg="anova p")
        self.assertEqual((df1, df2), (2, 35))

    def test_mann_whitney_normal_approximation(self):
        u, p, _rb = stats.mann_whitney(self.a, self.b)
        result = sp_stats.mannwhitneyu(self.a, self.b, use_continuity=True,
                                       method="asymptotic", alternative="two-sided")
        self.assertClose(u, result.statistic, rtol=1e-12, msg="U")
        self.assertClose(p, result.pvalue, rtol=1e-11, msg="mann-whitney p")

    def test_auc_equals_the_mann_whitney_statistic_over_the_pair_count(self):
        rng = random.Random(3)
        truth = [0] * 20 + [1] * 25
        score = [rng.random() for _ in range(20)] + [rng.random() + 0.4 for _ in range(25)]
        positive = [s for t, s in zip(truth, score) if t == 1]
        negative = [s for t, s in zip(truth, score) if t == 0]
        result = sp_stats.mannwhitneyu(positive, negative, alternative="two-sided")
        self.assertClose(stats.auc_roc(truth, score),
                         result.statistic / (len(positive) * len(negative)),
                         rtol=1e-12, msg="AUC")

    def test_shape_statistics_use_the_same_definitions_scipy_defaults_to(self):
        for sample in (self.a, self.b):
            self.assertClose(stats.skewness(sample), sp_stats.skew(sample),
                             rtol=1e-11, msg="skewness g1")
            self.assertClose(stats.excess_kurtosis(sample),
                             sp_stats.kurtosis(sample), rtol=1e-11,
                             msg="excess kurtosis g2")

    def test_power_matches_the_normal_quantiles_it_is_built_from(self):
        for effect, alpha, power in ((0.5, 0.05, 0.80), (0.3, 0.01, 0.90)):
            za = float(sp_stats.norm.ppf(1 - alpha / 2))
            zb = float(sp_stats.norm.ppf(power))
            self.assertClose(stats.power_two_sample(effect, alpha, power),
                             2 * (za + zb) ** 2 / effect ** 2, rtol=1e-12,
                             msg=f"n per group at d={effect}")


@requires_scipy
class Regression(Differential):

    def test_simple_regression_against_linregress(self):
        rng = random.Random(17)
        xs = [float(i) + rng.random() for i in range(40)]
        ys = [3.0 + 2.5 * x + rng.gauss(0.0, 2.0) for x in xs]
        fit = stats.ols(ys, [xs], ["x"])
        line = sp_stats.linregress(xs, ys)
        self.assertClose(fit.coefficients[1], line.slope, rtol=1e-11, msg="slope")
        self.assertClose(fit.coefficients[0], line.intercept, rtol=1e-11,
                         msg="intercept")
        self.assertClose(fit.se[1], line.stderr, rtol=1e-11, msg="slope se")
        self.assertClose(fit.se[0], line.intercept_stderr, rtol=1e-11,
                         msg="intercept se")
        self.assertClose(fit.r2, float(line.rvalue) ** 2, rtol=1e-11, msg="r2")
        self.assertClose(
            stats.t_two_sided_p(fit.coefficients[1] / fit.se[1], fit.n - 2),
            line.pvalue, rtol=1e-9, msg="slope p-value")

    def test_longley_coefficients_against_scipy_lstsq(self):
        with open(FIXTURES / "nist_longley.csv", newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        columns = {key: [float(row[key]) for row in rows] for key in rows[0]}
        y = columns["y"]
        design = [[1.0] + [columns[f"x{j}"][i] for j in range(1, 7)]
                  for i in range(len(y))]
        beta = sp_linalg.lstsq(design, y)[0]
        fit = stats.ols(y, [columns[f"x{j}"] for j in range(1, 7)],
                        [f"x{j}" for j in range(1, 7)])
        for j in range(7):
            self.assertClose(fit.coefficients[j], beta[j], rtol=1e-8,
                             msg=f"longley coefficient {j}")

    def test_regression_f_statistic_p_value(self):
        rng = random.Random(23)
        xs = [rng.gauss(0.0, 1.0) for _ in range(60)]
        zs = [rng.gauss(0.0, 1.0) for _ in range(60)]
        ys = [1.0 + 0.7 * x - 0.4 * z + rng.gauss(0.0, 1.0)
              for x, z in zip(xs, zs)]
        fit = stats.ols(ys, [xs, zs], ["x", "z"])
        df1, df2 = fit.f_df
        self.assertClose(stats.f_sf(fit.fstat, df1, df2),
                         sp_stats.f.sf(fit.fstat, df1, df2), rtol=1e-10,
                         msg="regression F p-value")


@requires_scipy
class SeriesAndDescriptives(Differential):

    def test_ljung_box_p_is_the_chi_square_tail(self):
        values = [math.sin(i / 3.0) + 0.1 * i for i in range(120)]
        rho = stats.acf(values, 8)
        q, p = stats.ljung_box(rho, len(values), 8)
        self.assertClose(p, sp_stats.chi2.sf(q, 8), rtol=1e-10, atol=1e-300,
                         msg="ljung-box p")

    def test_ci_mean_matches_the_t_interval_scipy_computes(self):
        values = [float(i) + (i % 5) for i in range(30)]
        lo, hi = stats.ci_mean(values, 0.05)
        half = float(sp_stats.t.ppf(0.975, len(values) - 1)) * \
            statistics.stdev(values) / math.sqrt(len(values))
        mean = statistics.fmean(values)
        self.assertClose(lo, mean - half, rtol=1e-11, msg="ci lower")
        self.assertClose(hi, mean + half, rtol=1e-11, msg="ci upper")


class ScipyDetection(unittest.TestCase):
    """The skip is the feature: absence must never be an error."""

    def test_the_skill_reports_the_same_availability_this_module_detected(self):
        self.assertEqual(stats.AVAILABLE["scipy"], HAVE_SCIPY)

    def test_stats_module_needs_nothing_beyond_the_standard_library(self):
        source = (TESTS.parent / "scripts" / "stats.py").read_text(encoding="utf-8")
        for banned in ("import scipy", "import numpy", "import pandas",
                       "from scipy", "from numpy", "from pandas"):
            self.assertNotIn(f"\n{banned}", source, f"stats.py must not {banned}")


if __name__ == "__main__":
    unittest.main()
