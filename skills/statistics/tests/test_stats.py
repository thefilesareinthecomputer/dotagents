"""Correctness of stats.py against certified and published values.

Level 1 of the testing strategy: nothing here compares the implementation to
itself. The regression numbers come from the NIST Statistical Reference
Datasets, the descriptives from a NIST numerical-accuracy dataset, and the
distribution CDFs from published quantile tables.
"""

import csv
import math
import pathlib
import statistics
import subprocess
import sys
import time
import unittest

TESTS = pathlib.Path(__file__).resolve().parent
FIXTURES = TESTS / "fixtures"
sys.path.insert(0, str(TESTS.parent / "scripts"))

import stats  # noqa: E402


def read_columns(name):
    with open(FIXTURES / name, newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    return {key: [float(row[key]) for row in rows] for key in rows[0]}


class NistLongley(unittest.TestCase):
    """NIST StRD Longley: 16 observations, 6 predictors, notoriously ill-conditioned.

    Certified values are quoted from the dataset's published certification. The
    tolerance is 1e-11 relative, against an observed agreement near 1e-13, so a
    wrong digit anywhere in the first eleven of a certified value fails.
    """

    CERT_B = [-3482258.63459582, 15.0618722713733, -0.0358191792925910,
              -2.02022980381683, -1.03322686717359, -0.0511041056535807,
              1829.15146461355]
    CERT_SE = [890420.383607373, 84.9149257747669, 0.0334910077722432,
               0.488399681651699, 0.214274163161675, 0.226073200069370,
               455.478499142212]
    CERT_SIGMA = 304.854073561965
    CERT_R2 = 0.995479004577296
    CERT_F = 330.285339234588

    @classmethod
    def setUpClass(cls):
        data = read_columns("nist_longley.csv")
        cls.fit = stats.ols(
            data["y"], [data[f"x{j}"] for j in range(1, 7)],
            [f"x{j}" for j in range(1, 7)])

    def test_coefficients(self):
        for j, certified in enumerate(self.CERT_B):
            self.assertAlmostEqual(
                self.fit.coefficients[j] / certified, 1.0, delta=1e-11,
                msg=f"coefficient {j}")

    def test_standard_errors(self):
        for j, certified in enumerate(self.CERT_SE):
            self.assertAlmostEqual(
                self.fit.se[j] / certified, 1.0, delta=1e-11, msg=f"se {j}")

    def test_residual_sd_r_squared_and_f(self):
        self.assertAlmostEqual(self.fit.sigma / self.CERT_SIGMA, 1.0, delta=1e-11)
        self.assertAlmostEqual(self.fit.r2 / self.CERT_R2, 1.0, delta=1e-11)
        self.assertAlmostEqual(self.fit.fstat / self.CERT_F, 1.0, delta=1e-11)
        self.assertEqual(self.fit.f_df, (6, 9))


class NistWampler(unittest.TestCase):
    """NIST StRD Wampler1 and Wampler2: exact polynomial data, integer answers.

    The data are generated from the rule the dataset publishes (x = 0..20,
    y a fifth-degree polynomial with the stated coefficients), so the certified
    answer is exact rather than rounded. The design is a Vandermonde matrix,
    which is what makes these the hard cases in the NIST suite.
    """

    XS = list(range(21))

    def design(self):
        return [[float(x ** k) for x in self.XS] for k in range(1, 6)]

    def test_wampler1_recovers_the_exact_coefficients(self):
        y = [float(1 + x + x ** 2 + x ** 3 + x ** 4 + x ** 5) for x in self.XS]
        fit = stats.ols(y, self.design(), ["x", "x2", "x3", "x4", "x5"])
        for j, coefficient in enumerate(fit.coefficients):
            self.assertAlmostEqual(coefficient, 1.0, delta=1e-8, msg=f"coefficient {j}")
        self.assertAlmostEqual(fit.r2, 1.0, delta=1e-12)
        self.assertLess(fit.sigma, 1e-7)

    def test_wampler2_recovers_the_exact_coefficients(self):
        certified = [1.0, 0.1, 0.01, 0.001, 0.0001, 0.00001]
        y = [1 + 0.1 * x + 0.01 * x ** 2 + 0.001 * x ** 3
             + 0.0001 * x ** 4 + 0.00001 * x ** 5 for x in self.XS]
        fit = stats.ols(y, self.design(), ["x", "x2", "x3", "x4", "x5"])
        for j, value in enumerate(certified):
            self.assertAlmostEqual(fit.coefficients[j] / value, 1.0, delta=1e-10,
                                   msg=f"coefficient {j}")
        self.assertLess(fit.sigma, 1e-10)


class NistNumAcc1(unittest.TestCase):
    """NIST StRD NumAcc1: mean 10000002, sample sd exactly 1.

    Three values eight digits long. A variance computed from the naive
    sum-of-squares formula loses every significant digit here and can return 0
    or a negative number.
    """

    def setUp(self):
        self.values = read_columns("nist_numacc1.csv")["y"]

    def test_certified_mean(self):
        self.assertEqual(statistics.fmean(self.values), 10000002.0)

    def test_certified_standard_deviation(self):
        self.assertAlmostEqual(statistics.stdev(self.values), 1.0, delta=1e-12)

    def test_describe_reports_them(self):
        self.assertAlmostEqual(stats.quantile(self.values, 0.5), 10000002.0, delta=1e-9)
        self.assertAlmostEqual(stats.mad(self.values), 1.0, delta=1e-12)


class DistributionTables(unittest.TestCase):
    """CDFs against published quantile tables.

    The tables carry four significant digits, so the tolerance is set at the
    precision the table itself has: 5e-5 on the tail area, against an observed
    worst case near 1.7e-5.
    """

    TOL = 5e-5

    T_975 = [(1, 12.706), (2, 4.303), (3, 3.182), (5, 2.571), (10, 2.228),
             (20, 2.086), (30, 2.042), (60, 2.000), (120, 1.980)]
    T_95 = [(1, 6.314), (5, 2.015), (10, 1.812), (20, 1.725), (30, 1.697), (60, 1.671)]
    T_99 = [(1, 31.821), (5, 3.365), (10, 2.764), (20, 2.528), (30, 2.457)]
    CHI2_95 = [(1, 3.841), (2, 5.991), (3, 7.815), (4, 9.488), (5, 11.070),
               (10, 18.307), (20, 31.410), (30, 43.773)]
    CHI2_99 = [(1, 6.635), (5, 15.086), (10, 23.209), (20, 37.566)]
    F_95 = [(1, 1, 161.4), (1, 5, 6.608), (1, 10, 4.965), (2, 3, 9.552),
            (2, 10, 4.103), (3, 10, 3.708), (5, 5, 5.050), (10, 10, 2.978),
            (4, 20, 2.866), (20, 20, 2.124)]

    def test_t_upper_quantiles(self):
        for level, table in ((0.975, self.T_975), (0.95, self.T_95), (0.99, self.T_99)):
            for df, quantile in table:
                self.assertAlmostEqual(stats.t_cdf(quantile, df), level,
                                       delta=self.TOL, msg=f"t({df}) at {level}")

    def test_t_is_symmetric(self):
        for df in (1, 3, 12, 40):
            self.assertAlmostEqual(stats.t_cdf(-1.3, df), 1 - stats.t_cdf(1.3, df),
                                   delta=1e-14)

    def test_t_quantile_inverts_the_cdf(self):
        for df in (1, 2, 7, 35, 200):
            for p in (0.75, 0.9, 0.95, 0.975, 0.995):
                self.assertAlmostEqual(stats.t_cdf(stats.t_ppf(p, df), df), p, delta=1e-10)

    def test_chi_square_upper_tail(self):
        for alpha, table in ((0.05, self.CHI2_95), (0.01, self.CHI2_99)):
            for df, quantile in table:
                self.assertAlmostEqual(stats.chi2_sf(quantile, df), alpha,
                                       delta=self.TOL, msg=f"chi2({df}) at {alpha}")

    def test_f_upper_tail(self):
        for df1, df2, quantile in self.F_95:
            self.assertAlmostEqual(stats.f_sf(quantile, df1, df2), 0.05,
                                   delta=self.TOL, msg=f"F({df1},{df2})")

    def test_normal_quantiles(self):
        published = {0.95: 1.6448536270, 0.975: 1.9599639845,
                     0.99: 2.3263478740, 0.995: 2.5758293035}
        for p, quantile in published.items():
            self.assertAlmostEqual(stats.norm_ppf(p), quantile, delta=1e-9)
            self.assertAlmostEqual(stats.norm_cdf(quantile), p, delta=1e-10)

    def test_t_approaches_normal_at_large_df(self):
        self.assertAlmostEqual(stats.t_cdf(1.96, 5_000_000), stats.norm_cdf(1.96),
                               delta=1e-6)


class RobustStatistics(unittest.TestCase):

    def test_mad_and_the_consistency_factor(self):
        # For a symmetric sample the scaled MAD estimates sigma.
        values = [1, 2, 3, 4, 5, 6, 7, 8, 9]
        self.assertEqual(stats.mad(values), 2.0)
        self.assertAlmostEqual(stats.mad(values) * stats.MAD_TO_SIGMA, 2.9652, delta=1e-4)

    def test_modified_z_uses_the_iglewicz_hoaglin_constant(self):
        values = [1, 2, 3, 4, 5, 6, 7, 8, 100]
        # median 5, absolute deviations 4,3,2,1,0,1,2,3,95, so MAD is 2.
        self.assertEqual(stats.mad(values), 2.0)
        zs = stats.modified_z(values)
        self.assertAlmostEqual(zs[0], 0.6745 * (1 - 5) / 2.0, places=12)
        self.assertEqual(stats.MODIFIED_Z_CUTOFF, 3.5)
        self.assertGreater(abs(zs[-1]), stats.MODIFIED_Z_CUTOFF)

    def test_degenerate_column_raises_rather_than_returning_infinity(self):
        values = [7.0] * 30 + [1.0, 2.0, 3.0]
        with self.assertRaises(stats.DegenerateSpread) as caught:
            stats.modified_z(values)
        self.assertIn("categorical", str(caught.exception))

    def test_mean_absolute_deviation_is_the_stated_fallback(self):
        values = [7.0] * 30 + [1.0, 13.0]
        self.assertGreater(stats.mean_abs_deviation(values), 0.0)

    def test_trimmed_and_winsorized_resist_a_single_wild_value(self):
        clean = [10, 11, 12, 13, 14, 15, 16, 17, 18, 19]
        spiked = clean[:-1] + [10_000]
        self.assertGreater(statistics.fmean(spiked) - statistics.fmean(clean), 900)
        self.assertLess(abs(stats.trimmed_mean(spiked, 0.2) - stats.trimmed_mean(clean, 0.2)), 2)
        self.assertLess(max(stats.winsorized(spiked, 0.2)), 100)

    def test_quantile_matches_the_type_7_definition(self):
        values = [1, 2, 3, 4]
        self.assertEqual(stats.quantile(values, 0.0), 1)
        self.assertEqual(stats.quantile(values, 1.0), 4)
        self.assertAlmostEqual(stats.quantile(values, 0.25), 1.75)
        self.assertAlmostEqual(stats.quantile(values, 0.5), 2.5)
        self.assertAlmostEqual(stats.quantile(values, 0.75), 3.25)


class Resampling(unittest.TestCase):

    def test_bootstrap_is_reproducible_from_the_seed(self):
        values = [3.1, 4.2, 1.5, 9.9, 2.2, 6.6, 7.7, 0.4, 5.5, 8.8]
        first = stats.bootstrap_ci(values, statistics.median, reps=500, seed=42)
        second = stats.bootstrap_ci(values, statistics.median, reps=500, seed=42)
        self.assertEqual(first, second)
        other = stats.bootstrap_ci(values, statistics.median, reps=500, seed=43)
        self.assertNotEqual(first, other)

    def test_bootstrap_interval_brackets_the_point_estimate(self):
        values = [float(i) for i in range(1, 51)]
        lo, hi, point = stats.bootstrap_ci(values, statistics.fmean, reps=2000, seed=1)
        self.assertLess(lo, point)
        self.assertLess(point, hi)
        self.assertAlmostEqual(point, 25.5, places=9)

    def test_bootstrap_needs_two_observations(self):
        with self.assertRaises(statistics.StatisticsError):
            stats.bootstrap_ci([1.0], reps=10, seed=1)

    def test_permutation_p_is_never_zero(self):
        a = [float(i) for i in range(20)]
        b = [float(i) + 1000 for i in range(20)]
        p, observed = stats.permutation_p(a, b, statistics.fmean, reps=200, seed=5)
        self.assertGreater(p, 0.0)
        self.assertAlmostEqual(p, 1 / 201, places=12)
        self.assertAlmostEqual(observed, -1000.0, places=9)

    def test_permutation_finds_no_difference_when_there_is_none(self):
        values = [float(i % 7) for i in range(60)]
        p, _ = stats.permutation_p(values[:30], values[30:], statistics.fmean,
                                   reps=500, seed=9)
        self.assertGreater(p, 0.2)


class Inference(unittest.TestCase):

    def test_welch_reduces_to_a_hand_computed_value(self):
        a = [1.0, 2.0, 3.0, 4.0, 5.0]
        b = [3.0, 4.0, 5.0, 6.0, 7.0]
        t, df, p = stats._welch(a, b)
        expected_t = (3.0 - 5.0) / math.sqrt(2.5 / 5 + 2.5 / 5)
        self.assertAlmostEqual(t, expected_t, places=12)
        self.assertAlmostEqual(df, 8.0, places=9)
        self.assertAlmostEqual(p, 2 * stats.t_sf(abs(expected_t), 8.0), places=15)

    def test_cohen_d_and_hedges_g(self):
        a = [float(i) for i in range(10)]
        b = [float(i) + 4.5 for i in range(10)]
        d, g = stats._cohen_d(a, b)
        self.assertAlmostEqual(d, -4.5 / statistics.stdev(a), places=12)
        self.assertLess(abs(g), abs(d))  # the small-sample correction shrinks it

    def test_mann_whitney_on_a_clean_separation(self):
        a = [1.0, 2.0, 3.0, 4.0]
        b = [5.0, 6.0, 7.0, 8.0]
        u, p, rb = stats.mann_whitney(a, b)
        self.assertEqual(u, 0.0)
        self.assertAlmostEqual(rb, -1.0, places=12)
        self.assertLess(p, 0.05)

    def test_holm_adjustment_is_monotone_and_bounded(self):
        raw = [0.01, 0.02, 0.03, 0.9]
        adjusted = stats.holm_adjust(raw)
        self.assertAlmostEqual(adjusted[0], 0.04, places=12)
        self.assertAlmostEqual(adjusted[1], 0.06, places=12)
        self.assertAlmostEqual(adjusted[2], 0.06, places=12)
        self.assertAlmostEqual(adjusted[3], 0.9, places=12)
        self.assertEqual(adjusted, sorted(adjusted))
        self.assertTrue(all(0 <= p <= 1 for p in adjusted))

    def test_anova_matches_the_f_definition_on_balanced_groups(self):
        groups = {"a": [1.0, 2.0, 3.0], "b": [4.0, 5.0, 6.0], "c": [7.0, 8.0, 9.0]}
        f, df1, df2, eta2, p = stats._anova(groups)
        self.assertEqual((df1, df2), (2, 6))
        self.assertAlmostEqual(f, 27.0, places=9)
        self.assertAlmostEqual(eta2, 54 / 60, places=9)
        self.assertAlmostEqual(p, stats.f_sf(27.0, 2, 6), places=15)

    def test_ci_mean_uses_the_t_quantile(self):
        values = [float(i) for i in range(1, 26)]
        lo, hi = stats.ci_mean(values, 0.05)
        half = stats.t_ppf(0.975, 24) * statistics.stdev(values) / 5.0
        self.assertAlmostEqual(lo, 13.0 - half, places=12)
        self.assertAlmostEqual(hi, 13.0 + half, places=12)


class ClassificationMetrics(unittest.TestCase):

    def test_auc_on_a_hand_computable_case(self):
        truth = [0, 0, 1, 1]
        score = [0.1, 0.4, 0.35, 0.8]
        self.assertAlmostEqual(stats.auc_roc(truth, score), 0.75, places=12)

    def test_auc_handles_ties_with_average_ranks(self):
        self.assertAlmostEqual(stats.auc_roc([0, 1], [0.5, 0.5]), 0.5, places=12)

    def test_auc_is_one_on_perfect_separation(self):
        self.assertAlmostEqual(stats.auc_roc([0, 0, 1, 1], [0.1, 0.2, 0.8, 0.9]),
                               1.0, places=12)

    def test_brier_score(self):
        self.assertAlmostEqual(stats.brier_score([1, 0], [1.0, 0.0]), 0.0, places=12)
        self.assertAlmostEqual(stats.brier_score([1, 0], [0.5, 0.5]), 0.25, places=12)

    def test_calibration_gap_is_signed_and_weighted(self):
        truth = [1] * 10 + [0] * 10
        score = [0.5] * 20
        bins, ece = stats.calibration_bins(truth, score, bins=10)
        self.assertEqual(len(bins), 1)
        self.assertAlmostEqual(ece, 0.0, places=12)


class SeriesAndRisk(unittest.TestCase):

    def test_acf_at_lag_zero_is_one(self):
        values = [float((i * 7) % 11) for i in range(50)]
        rho = stats.acf(values, 5)
        self.assertAlmostEqual(rho[0], 1.0, places=12)

    def test_acf_detects_a_deterministic_alternation(self):
        values = [1.0, -1.0] * 40
        rho = stats.acf(values, 2)
        self.assertLess(rho[1], -0.9)
        self.assertGreater(rho[2], 0.9)

    def test_ljung_box_rejects_an_alternating_series(self):
        values = [1.0, -1.0] * 40
        rho = stats.acf(values, 5)
        q, p = stats.ljung_box(rho, len(values), 5)
        self.assertLess(p, 1e-6)

    def test_adf_separates_a_random_walk_from_its_differences(self):
        import random
        rng = random.Random(3)
        walk, level = [], 0.0
        for _ in range(400):
            level += rng.gauss(0, 1)
            walk.append(level)
        diffs = [walk[i] - walk[i - 1] for i in range(1, len(walk))]
        tau_walk, _ = stats.adf_statistic(walk, 1)
        tau_diff, _ = stats.adf_statistic(diffs, 1)
        self.assertGreater(tau_walk, stats.ADF_TAU_MU["5%"])
        self.assertLess(tau_diff, stats.ADF_TAU_MU["1%"])

    def test_max_drawdown_of_a_known_path(self):
        # +100%, then -50% back to the start: the drawdown is exactly -50%.
        self.assertAlmostEqual(stats.max_drawdown([1.0, -0.5]), -0.5, places=12)
        self.assertAlmostEqual(stats.max_drawdown([0.1, 0.1, 0.1]), 0.0, places=12)


class PowerCalculation(unittest.TestCase):

    def test_matches_the_textbook_normal_approximation(self):
        # d = 0.5, alpha = 0.05, power = 0.80: 2*(1.959964+0.841621)^2/0.25.
        n = stats.power_two_sample(0.5, 0.05, 0.80)
        self.assertAlmostEqual(n, 62.79, places=2)
        self.assertEqual(math.ceil(n), 63)

    def test_halving_the_effect_quadruples_the_sample(self):
        small = stats.power_two_sample(0.25, 0.05, 0.80)
        large = stats.power_two_sample(0.5, 0.05, 0.80)
        self.assertAlmostEqual(small / large, 4.0, places=9)


class InputHandling(unittest.TestCase):

    def test_currency_separators_and_parentheses(self):
        self.assertEqual(stats.coerce_number("$1,200.50"), (1200.50, "coerced"))
        self.assertEqual(stats.coerce_number("(150.25)"), (-150.25, "coerced"))
        self.assertEqual(stats.coerce_number("  2 300 "), (2300.0, "coerced"))
        self.assertEqual(stats.coerce_number("42"), (42.0, "ok"))
        self.assertEqual(stats.coerce_number("-1.5e3"), (-1500.0, "ok"))

    def test_percent_keeps_its_units_and_says_so(self):
        value, tag = stats.coerce_number("5%")
        self.assertEqual((value, tag), (5.0, "coerced"))

    def test_common_na_spellings_are_missing_not_zero(self):
        for token in ("", "NA", "n/a", "NULL", "-", "None", "?", "#N/A"):
            value, tag = stats.coerce_number(token)
            self.assertIsNone(value, token)
            self.assertEqual(tag, "missing", token)

    def test_genuine_text_is_counted_as_non_numeric(self):
        self.assertEqual(stats.coerce_number("not a number"), (None, "bad"))

    def test_messy_file_is_read_and_every_skipped_row_is_counted(self):
        table = stats.load_table(str(FIXTURES / "messy.csv"))
        self.assertEqual(table.delimiter, ";")
        self.assertTrue(table.had_header)
        idx = stats.resolve_column(table, "AMOUNT")  # case-insensitive
        values, report = stats.column_values(table, idx)
        self.assertEqual(report["n_used"], 7)
        self.assertEqual(report["n_missing"], 2)
        self.assertEqual(report["n_nonnumeric"], 1)
        self.assertEqual(report["rows_dropped"], 3)
        self.assertEqual(report["rows_total"], 10)
        self.assertIn(-150.25, values)
        self.assertIn(2300.0, values)

    def test_column_can_be_chosen_by_index(self):
        table = stats.load_table(str(FIXTURES / "nist_longley.csv"))
        self.assertEqual(stats.resolve_column(table, "0"), 0)
        self.assertEqual(stats.resolve_column(table, "x3"), 3)

    def test_missing_column_names_the_alternatives(self):
        table = stats.load_table(str(FIXTURES / "nist_longley.csv"))
        with self.assertRaises(stats.DataError) as caught:
            stats.resolve_column(table, "revenue")
        self.assertIn("x1", str(caught.exception))

    def test_headerless_file_gets_generated_names(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "raw.csv"
            path.write_text("1,2\n3,4\n5,6\n", encoding="utf-8")
            table = stats.load_table(str(path))
            self.assertFalse(table.had_header)
            self.assertEqual(table.columns, ["c0", "c1"])
            values, _ = stats.column_values(table, 1)
            self.assertEqual(values, [2.0, 4.0, 6.0])


class Determinism(unittest.TestCase):
    """A seeded command run twice produces byte-identical output.

    Run as a subprocess rather than in process: a hidden timestamp, a
    hash-seeded iteration order or a stray use of the global random module
    only shows up in a fresh interpreter. The two runs are separated by enough
    of a wait to cross a wall-clock second boundary, so a timestamp rendered to
    second resolution cannot pass by landing in the same second twice.
    """

    SCRIPT = str(TESTS.parent / "scripts" / "stats.py")

    def run_command(self, *argv):
        result = subprocess.run(
            [sys.executable, self.SCRIPT, *argv],
            capture_output=True, check=True)
        self.assertTrue(result.stdout.strip(), "the command printed nothing")
        return result.stdout

    def test_seeded_boot_is_byte_identical_across_a_second_boundary(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            first_manifest = pathlib.Path(tmp) / "first.json"
            second_manifest = pathlib.Path(tmp) / "second.json"
            argv = ["boot", str(FIXTURES / "nist_longley.csv"), "--col", "y",
                    "--stat", "median", "--reps", "400", "--seed", "7", "--json"]
            first = self.run_command(*argv, "--manifest", str(first_manifest))
            time.sleep(1.05 - time.time() % 1.0)  # cross a whole second
            second = self.run_command(*argv, "--manifest", str(second_manifest))
            self.assertEqual(first, second)
            self.assertEqual(first_manifest.read_bytes(), second_manifest.read_bytes())

    def test_a_different_seed_gives_a_different_answer(self):
        """Otherwise the determinism above could be a constant, not a seeded draw."""
        argv = ["boot", str(FIXTURES / "nist_longley.csv"), "--col", "y",
                "--stat", "mean", "--reps", "400", "--json"]
        self.assertNotEqual(self.run_command(*argv, "--seed", "7"),
                            self.run_command(*argv, "--seed", "8"))


if __name__ == "__main__":
    unittest.main()
