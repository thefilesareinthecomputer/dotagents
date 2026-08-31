#!/usr/bin/env python3
"""Static auditor for model training code - AST-based, stdlib only.

EXECUTE this against training scripts and notebooks. It reads code, it never
imports or runs it: audited training code is untrusted input, and running it
would also mean waiting for a fit. `ast` does the parsing, so scikit-learn,
XGBoost and pandas are subjects of analysis rather than dependencies, and this
works on a machine with nothing installed.

    python3 ml_check.py train.py
    python3 ml_check.py notebooks/model.ipynb --json
    python3 ml_check.py src/ --recursive --warnings-as-errors

Exit 1 when any error-severity finding is present, or when any warning is too
under --warnings-as-errors. Notes never affect the exit code.

The nine codes are the structural defects that produce a model which scores
well in validation and disappoints in production. Every one of them is decided
from structure alone - order of statements, arguments to a call, which literal
reaches which list - so none of them needs the data. What that buys in safety
it pays for in reach: the checker cannot see a class balance, a column's real
dtype, or whether a grouping column exists under a different name, so
METRIC_MISMATCH and GROUP_LEAK are approximations, documented as such in
references/pitfalls.md and in the rule bodies below.

Notebooks are parsed in cell order, which is not necessarily execution order.
Every notebook gets a NOTEBOOK_ORDER note saying so, and the two order-dependent
findings are downgraded to warnings there.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

ERROR, WARNING, NOTE = "error", "warning", "note"

MAX_BYTES = 2_000_000
SKIP_DIRS = {".git", ".venv", "venv", "env", "node_modules", "__pycache__",
             ".ipynb_checkpoints", ".mypy_cache", ".pytest_cache", "site-packages"}

# Transformers whose statistics are learned from data. Fitting one before the
# split is how test-set information reaches training.
PREPROCESSORS = {
    "StandardScaler", "MinMaxScaler", "RobustScaler", "MaxAbsScaler", "Normalizer",
    "PowerTransformer", "QuantileTransformer", "KBinsDiscretizer",
    "OneHotEncoder", "OrdinalEncoder", "LabelEncoder", "TargetEncoder",
    "SimpleImputer", "KNNImputer", "IterativeImputer",
    "PCA", "TruncatedSVD", "SelectKBest", "SelectPercentile", "RFE",
    "VarianceThreshold", "PolynomialFeatures", "FunctionTransformer",
    "TfidfVectorizer", "CountVectorizer", "HashingVectorizer",
    "ColumnTransformer",
}
# Receiver names that stand in for the constructor when it was imported from a
# local module and the assignment is not visible in this file.
PREPROCESSOR_NAMES = {"scaler", "encoder", "imputer", "vectorizer", "preprocessor",
                      "transformer", "normalizer", "discretizer"}

RESAMPLERS = {
    "SMOTE", "SMOTEN", "SMOTENC", "BorderlineSMOTE", "SVMSMOTE", "KMeansSMOTE",
    "ADASYN", "RandomOverSampler", "RandomUnderSampler", "NearMiss", "TomekLinks",
    "EditedNearestNeighbours", "ClusterCentroids", "SMOTEENN", "SMOTETomek",
}

SPLIT_FUNCS = {"train_test_split"}
CV_SPLITTERS = {
    "KFold", "StratifiedKFold", "ShuffleSplit", "StratifiedShuffleSplit",
    "RepeatedKFold", "RepeatedStratifiedKFold", "GroupKFold", "GroupShuffleSplit",
    "StratifiedGroupKFold", "LeaveOneGroupOut", "LeavePGroupsOut", "LeaveOneOut",
    "TimeSeriesSplit", "PredefinedSplit",
}
GROUP_AWARE = {"GroupKFold", "GroupShuffleSplit", "StratifiedGroupKFold",
               "LeaveOneGroupOut", "LeavePGroupsOut"}
TIME_AWARE = {"TimeSeriesSplit", "PredefinedSplit"}

# Estimators and splitters whose result changes run to run without a seed.
# LogisticRegression and friends are deliberately absent - their random_state
# only matters for some solvers, and flagging them is noise.
STOCHASTIC = {
    "train_test_split", "ShuffleSplit", "StratifiedShuffleSplit", "GroupShuffleSplit",
    "RepeatedKFold", "RepeatedStratifiedKFold", "RandomizedSearchCV",
    "HalvingRandomSearchCV", "BayesSearchCV",
    "RandomForestClassifier", "RandomForestRegressor",
    "ExtraTreesClassifier", "ExtraTreesRegressor",
    "GradientBoostingClassifier", "GradientBoostingRegressor",
    "HistGradientBoostingClassifier", "HistGradientBoostingRegressor",
    "DecisionTreeClassifier", "DecisionTreeRegressor",
    "BaggingClassifier", "BaggingRegressor", "IsolationForest",
    "MLPClassifier", "MLPRegressor", "SGDClassifier", "SGDRegressor",
    "KMeans", "MiniBatchKMeans", "GaussianMixture", "TSNE", "UMAP",
    "XGBClassifier", "XGBRegressor", "LGBMClassifier", "LGBMRegressor",
    "CatBoostClassifier", "CatBoostRegressor",
} | RESAMPLERS
# These shuffle only on request, so they are only unreproducible when asked to be.
SHUFFLE_GATED = {"KFold", "StratifiedKFold", "GroupKFold", "StratifiedGroupKFold"}
STOCHASTIC_METHODS = {"sample", "shuffle", "permutation"}
SEED_KWARGS = {"random_state", "seed", "random_seed", "rng", "generator", "random_seed_"}

ACCURACY_CALLS = {"accuracy_score"}
OTHER_METRICS = {
    "f1_score", "fbeta_score", "precision_score", "recall_score", "roc_auc_score",
    "average_precision_score", "balanced_accuracy_score", "matthews_corrcoef",
    "cohen_kappa_score", "confusion_matrix", "classification_report",
    "precision_recall_curve", "roc_curve", "log_loss", "brier_score_loss",
    "jaccard_score", "top_k_accuracy_score",
}
SCORING_CALLS = ACCURACY_CALLS | OTHER_METRICS | {
    "mean_squared_error", "mean_absolute_error", "r2_score",
    "root_mean_squared_error", "mean_absolute_percentage_error",
    "cross_val_score", "cross_validate",
}
BASELINE_CALLS = {"DummyClassifier", "DummyRegressor"}
BASELINE_WORDS = ("baseline", "naive", "majority", "most_frequent", "prior_rate")

SEARCH_CALLS = {"GridSearchCV", "RandomizedSearchCV", "HalvingGridSearchCV",
                "HalvingRandomSearchCV", "BayesSearchCV",
                "cross_val_score", "cross_validate", "cross_val_predict"}
FIT_METHODS = {"fit", "fit_transform", "partial_fit", "fit_predict"}
RESAMPLE_METHODS = {"fit_resample", "fit_sample"}
# Keyword arguments that carry a dataset into a fit or a search.
DATA_KWARGS = {"eval_set", "validation_data", "eval_data", "X_val", "validation_split_data"}

IMBALANCE_MARKERS = {"class_weight", "sample_weight", "scale_pos_weight", "stratify",
                     "is_unbalance", "balanced_accuracy"}

DATE_RE = re.compile(r"(?i)(?:^|_)(date|time|timestamp|datetime|dt|ts)(?:_|$)|_at$")
ID_RE = re.compile(r"(?i)^(?:[a-z0-9]+_)*(id|uuid|guid)$")
TEST_PARTS = {"test", "holdout", "heldout"}


@dataclass(frozen=True)
class Finding:
    code: str
    severity: str
    file: str
    line: int
    message: str
    fix: str


# --------------------------------------------------------------------- helpers

def call_name(node: ast.AST) -> str:
    """Last component of a call target - `pd.read_csv` reads as `read_csv`."""
    func = node.func if isinstance(node, ast.Call) else node
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return ""


def receiver_name(node: ast.Call) -> str:
    """Name the method was called on - `scaler` in `scaler.fit(X)`."""
    if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
        return node.func.value.id
    return ""


def receiver_ctor(node: ast.Call) -> str:
    """Constructor when the method is chained - `StandardScaler().fit(X)`."""
    if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Call):
        return call_name(node.func.value)
    return ""


def kwarg(node: ast.Call, name: str) -> ast.AST | None:
    for kw in node.keywords:
        if kw.arg == name:
            return kw.value
    return None


def literals(node: ast.AST | None) -> set[str]:
    """Every string constant in a subtree."""
    if node is None:
        return set()
    return {n.value for n in ast.walk(node) if isinstance(n, ast.Constant) and isinstance(n.value, str)}


def names_in(node: ast.AST | None) -> list[str]:
    """Identifiers in a subtree, sorted - output must not depend on set order."""
    if node is None:
        return []
    return sorted({n.id for n in ast.walk(node) if isinstance(n, ast.Name)})


def is_test_name(name: str) -> bool:
    return bool(TEST_PARTS & set(name.lower().split("_")))


def looks_temporal(text: str) -> bool:
    return bool(DATE_RE.search(text))


def target_of(node: ast.Assign) -> str:
    if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
        return node.targets[0].id
    return ""


# ------------------------------------------------------------------- collector

class Collector(ast.NodeVisitor):
    """One pass over the tree, gathering the evidence each rule needs.

    Nothing is decided here. The rules read the collected evidence afterwards,
    which keeps every rule readable on its own and testable in isolation.
    """

    def __init__(self, docstrings: set[int] | None = None) -> None:
        self.docstrings = docstrings or set()       # node ids to read past
        self.var_ctor: dict[str, str] = {}          # scaler -> StandardScaler
        self.split_lines: list[int] = []            # every split event, any kind
        self.random_split_lines: list[int] = []     # shuffled splits only
        self.time_aware = False
        self.group_aware = False
        self.groups_passed = False
        self.preprocess_fits: list[tuple[int, str]] = []
        self.resample_fits: list[tuple[int, str]] = []
        self.test_in_fit: list[tuple[int, str, str]] = []   # line, call, arg name
        self.unseeded: list[tuple[int, str]] = []
        self.accuracy_lines: list[int] = []
        self.other_metric = False
        self.scoring_lines: list[int] = []
        self.baseline = False
        self.imbalance_handled = False
        self.date_signals: list[tuple[int, str]] = []
        self.id_literals: dict[str, int] = {}       # literal -> first line
        self.dropped: set[str] = set()
        self.target_literal = ""
        self.target_line = 0
        self.target_frame = ""
        self.target_popped = False
        self.feature_findings: list[tuple[int, str, str]] = []  # line, kind, detail
        self.manual_temporal_split = False

    # -- assignments ------------------------------------------------------
    def visit_Assign(self, node: ast.Assign) -> None:
        name = target_of(node)
        value = node.value

        if name and isinstance(value, ast.Call):
            self.var_ctor[name] = call_name(value)

        if name:
            self._target_extraction(node, name, value)
            self._feature_matrix(node, name, value)
            if is_test_name(name) or name.lower().startswith("train"):
                if self._has_date_compare(value):
                    self.manual_temporal_split = True
                    self.split_lines.append(node.lineno)

        self.generic_visit(node)

    def _has_date_compare(self, node: ast.AST) -> bool:
        for sub in ast.walk(node):
            if isinstance(sub, ast.Compare):
                if any(looks_temporal(t) for t in literals(sub)):
                    return True
                if any(isinstance(n, ast.Attribute) and n.attr == "dt" for n in ast.walk(sub)):
                    return True
        return False

    def _target_extraction(self, node: ast.Assign, name: str, value: ast.AST) -> None:
        """`y = frame["churned"]` and `y = frame.pop("churned")`."""
        if self.target_literal or name.lower() not in {"y", "target", "label", "labels", "y_all"}:
            return
        if isinstance(value, ast.Subscript) and isinstance(value.value, ast.Name):
            lit = literals(value.slice)
            if len(lit) == 1:
                self.target_literal = next(iter(lit))
                self.target_frame = value.value.id
                self.target_line = node.lineno
        elif isinstance(value, ast.Call) and call_name(value) == "pop":
            lit = literals(value)
            if len(lit) == 1:
                self.target_literal = next(iter(lit))
                self.target_frame = receiver_name(value)
                self.target_line = node.lineno
                self.target_popped = True

    def _feature_matrix(self, node: ast.Assign, name: str, value: ast.AST) -> None:
        """`X = ...` in the three shapes that decide TARGET_IN_FEATURES."""
        if name.lower() not in {"x", "features", "feature_matrix", "x_all", "feats"}:
            return
        if isinstance(value, ast.Name):
            self.feature_findings.append((node.lineno, "whole_frame", value.id))
        elif isinstance(value, ast.Call) and call_name(value) == "drop":
            dropped = literals(kwarg(value, "columns")) | literals(kwarg(value, "labels"))
            if value.args:
                dropped |= literals(value.args[0])
            self.dropped |= dropped
            self.feature_findings.append((node.lineno, "drop", receiver_name(value)))
        elif isinstance(value, ast.Subscript) and isinstance(value.value, ast.Name):
            self.feature_findings.append((node.lineno, "select", value.value.id))
            for lit in literals(value.slice):
                self.feature_findings.append((node.lineno, "selected_column", lit))

    # -- calls ------------------------------------------------------------
    def visit_Call(self, node: ast.Call) -> None:
        name = call_name(node)
        line = node.lineno

        if name in SPLIT_FUNCS:
            self.split_lines.append(line)
            shuffle = kwarg(node, "shuffle")
            if not (isinstance(shuffle, ast.Constant) and shuffle.value is False):
                self.random_split_lines.append(line)
        if name in CV_SPLITTERS:
            self.split_lines.append(line)
            if name in TIME_AWARE:
                self.time_aware = True
            if name in GROUP_AWARE:
                self.group_aware = True
            shuffle = kwarg(node, "shuffle")
            shuffles = name not in SHUFFLE_GATED or (
                isinstance(shuffle, ast.Constant) and shuffle.value is True)
            if shuffles and name not in TIME_AWARE and name not in GROUP_AWARE:
                self.random_split_lines.append(line)
        if name == "split":
            self.split_lines.append(line)
        if kwarg(node, "groups") is not None:
            self.groups_passed = True

        self._record_fits(node, name, line)
        self._record_seed(node, name, line)
        self._record_metrics(node, name, line)

        if name in BASELINE_CALLS:
            self.baseline = True
        if name in {"to_datetime", "date_range"} or kwarg(node, "parse_dates") is not None:
            self.date_signals.append((line, name + "()"))
        if any(kw.arg in IMBALANCE_MARKERS for kw in node.keywords):
            self.imbalance_handled = True
        if name in RESAMPLERS:
            self.imbalance_handled = True

        self.generic_visit(node)

    def _record_fits(self, node: ast.Call, name: str, line: int) -> None:
        if name not in FIT_METHODS and name not in RESAMPLE_METHODS:
            return
        recv, ctor = receiver_name(node), receiver_ctor(node)
        origin = self.var_ctor.get(recv, "") or ctor

        if name in RESAMPLE_METHODS or origin in RESAMPLERS:
            self.resample_fits.append((line, origin or recv or name))
        elif origin in PREPROCESSORS or (not origin and recv.lower() in PREPROCESSOR_NAMES):
            if name in {"fit", "fit_transform"}:
                self.preprocess_fits.append((line, origin or recv))

        # Test data reaching a fit, a search or an early-stopping callback.
        if name in FIT_METHODS or name in SEARCH_CALLS:
            for arg in node.args:
                for n in names_in(arg):
                    if is_test_name(n):
                        self.test_in_fit.append((line, name, n))
            for kw in node.keywords:
                if kw.arg in DATA_KWARGS:
                    for n in names_in(kw.value):
                        if is_test_name(n):
                            self.test_in_fit.append((line, kw.arg, n))

    def _record_seed(self, node: ast.Call, name: str, line: int) -> None:
        seeded = any(kw.arg in SEED_KWARGS for kw in node.keywords)
        if name in STOCHASTIC | SHUFFLE_GATED and not seeded:
            if name in SHUFFLE_GATED:
                shuffle = kwarg(node, "shuffle")
                if not (isinstance(shuffle, ast.Constant) and shuffle.value is True):
                    return
            self.unseeded.append((line, name))
        elif name in STOCHASTIC_METHODS and receiver_name(node) and not seeded:
            self.unseeded.append((line, name))

    def _record_metrics(self, node: ast.Call, name: str, line: int) -> None:
        if name in SCORING_CALLS:
            self.scoring_lines.append(line)
        if name in ACCURACY_CALLS:
            self.accuracy_lines.append(line)
        if name in OTHER_METRICS:
            self.other_metric = True
        if name == "score" and receiver_name(node):
            self.scoring_lines.append(line)
        scoring = kwarg(node, "scoring")
        for lit in literals(scoring):
            if lit == "accuracy":
                self.accuracy_lines.append(line)
            elif lit:
                self.other_metric = True

    # -- constants --------------------------------------------------------
    # Docstrings are skipped. Prose describing the script is not evidence about
    # the script, and a module docstring that happens to say "date" or
    # "baseline" would otherwise decide two rules on its own.
    def visit_Constant(self, node: ast.Constant) -> None:
        if id(node) in self.docstrings:
            return
        if isinstance(node.value, str) and node.value:
            if looks_temporal(node.value):
                self.date_signals.append((node.lineno, node.value))
            if ID_RE.match(node.value):
                self.id_literals.setdefault(node.value, node.lineno)
            if any(w in node.value.lower() for w in BASELINE_WORDS):
                self.baseline = True
            if node.value == "balanced":
                self.imbalance_handled = True
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        if any(w in node.id.lower() for w in BASELINE_WORDS):
            self.baseline = True
        self.generic_visit(node)


# ----------------------------------------------------------------------- rules

def run_rules(c: Collector, path: str) -> list[Finding]:
    out: list[Finding] = []

    def add(code: str, severity: str, line: int, message: str, fix: str) -> None:
        # Messages embed literals lifted from the audited file, which is
        # untrusted input: strip control characters and bound the length so a
        # crafted constant cannot style the terminal or become the report.
        out.append(Finding(code, severity, path, line,
                           safe(clip(message, 600)), safe(clip(fix, 300))))

    first_split = min(c.split_lines) if c.split_lines else None

    # FIT_BEFORE_SPLIT -----------------------------------------------------
    # A learned transformer fitted at a line above every split statement saw
    # rows that later became the test set. Silent when the file never splits:
    # that is a different defect and this rule cannot tell a training script
    # from an inference script.
    if first_split is not None:
        for line, what in c.preprocess_fits:
            if line < first_split:
                add("FIT_BEFORE_SPLIT", ERROR, line,
                    f"{what} is fitted at line {line}, above the split at line {first_split}. "
                    "Its means, categories or imputation values are learned from rows that "
                    "become the test set, so the test score is optimistic by an amount nobody "
                    "can measure after the fact.",
                    "Split first, fit the transformer on the training rows only, and transform "
                    "the test rows with it. A Pipeline does this correctly inside cross-validation.")

    # RESAMPLE_BEFORE_SPLIT ------------------------------------------------
        for line, what in c.resample_fits:
            if line < first_split:
                add("RESAMPLE_BEFORE_SPLIT", WARNING, line,
                    f"{what} resamples at line {line}, above the split at line {first_split}. "
                    "Synthetic minority rows are interpolated from neighbors that end up on "
                    "both sides of the split, so near-duplicates of training rows sit in the "
                    "test set and recall looks far better than it is.",
                    "Split first, resample the training fold only. In cross-validation put the "
                    "sampler inside an imblearn Pipeline so it refits per fold.")

    # TEST_USED_IN_TUNING --------------------------------------------------
    # One finding per call, not per argument: `fit(X_test, y_test)` is one
    # mistake made once.
    seen_calls: dict[tuple[int, str], str] = {}
    for line, where, arg in c.test_in_fit:
        seen_calls.setdefault((line, where), arg)
    for (line, where), arg in seen_calls.items():
        add("TEST_USED_IN_TUNING", WARNING, line,
            f"`{arg}` reaches `{where}` at line {line}. Once the test split has influenced "
            "fitting, early stopping or hyperparameter choice, it is a second validation set "
            "and its score is no longer an estimate of unseen performance.",
            "Carve a validation split out of the training data for tuning and early stopping, "
            "and touch the test split once, at the end.")

    # NO_RANDOM_STATE ------------------------------------------------------
    for line, what in c.unseeded:
        add("NO_RANDOM_STATE", WARNING, line,
            f"{what} at line {line} has no random_state. The split, the shuffle or the "
            "estimator differs on every run, so a reported score cannot be reproduced and "
            "two experiments cannot be compared.",
            "Pass random_state (or seed) from one module-level constant, and record that "
            "constant with the data version and the code version.")

    # TARGET_IN_FEATURES ---------------------------------------------------
    if c.target_literal and not c.target_popped:
        for line, kind, detail in c.feature_findings:
            if kind == "whole_frame" and detail == c.target_frame:
                add("TARGET_IN_FEATURES", WARNING, line,
                    f"The target `{c.target_literal}` was taken from `{c.target_frame}` at line "
                    f"{c.target_line}, and the feature matrix at line {line} is the whole frame. "
                    "The model can read the answer off a column, which is why it scores near "
                    "perfectly and predicts nothing useful.",
                    f"Build the features as {c.target_frame}.drop(columns=['{c.target_literal}']), "
                    "and check for columns derived from the target as well.")
            elif kind == "drop" and detail == c.target_frame and c.target_literal not in c.dropped:
                add("TARGET_IN_FEATURES", WARNING, line,
                    f"The target `{c.target_literal}` is not among the columns dropped at line "
                    f"{line}, so it stays in the feature matrix.",
                    f"Add '{c.target_literal}' to the drop list.")
            elif kind == "selected_column" and detail == c.target_literal:
                add("TARGET_IN_FEATURES", WARNING, line,
                    f"The target `{c.target_literal}` is listed among the selected feature "
                    f"columns at line {line}.",
                    "Remove the target from the feature column list.")

    # NO_BASELINE ----------------------------------------------------------
    if c.scoring_lines and not c.baseline:
        add("NO_BASELINE", WARNING, min(c.scoring_lines),
            "A model is scored here with nothing to compare it against. A number alone is "
            "not evidence - majority class, last observed value or a single rule often lands "
            "within a point of a tuned model, and that is the finding that changes decisions.",
            "Fit a DummyClassifier or DummyRegressor, or the obvious business rule, score it "
            "the same way and report both numbers together.")

    # TEMPORAL_SPLIT_MISSING ----------------------------------------------
    if c.date_signals and c.random_split_lines and not c.time_aware and not c.manual_temporal_split:
        line = min(c.random_split_lines)
        # Name a column literal if one was seen; a parsing call is the fallback.
        col = next((s for _, s in c.date_signals if not s.endswith("()")),
                   c.date_signals[0][1])
        add("TEMPORAL_SPLIT_MISSING", ERROR, line,
            f"The data carries time (`{col}`) and the split at line {line} is random, so "
            "training rows sit after test rows in time. The model is scored on interpolating "
            "between known periods, which is not the task it will face in production.",
            "Split on a cutoff date, or use TimeSeriesSplit, and hold out the most recent "
            "period. If the rows really are exchangeable, say so in a comment and keep the "
            "random split.")

    # METRIC_MISMATCH ------------------------------------------------------
    # Static approximation. Class balance is a property of data, which this
    # checker never reads. The proxy: accuracy is the only metric in the file
    # AND nothing in the file acknowledges imbalance (no class_weight,
    # sample_weight, scale_pos_weight, stratify, 'balanced', no resampler).
    # Either of those clears the finding, so it is quiet on code that has
    # thought about the question and loud on code that has not.
    if c.accuracy_lines and not c.other_metric and not c.imbalance_handled:
        add("METRIC_MISMATCH", WARNING, min(c.accuracy_lines),
            "Accuracy is the only metric here and nothing in the file acknowledges class "
            "balance. At 2 percent positives, predicting the majority class scores 98 percent "
            "and finds nothing. This is a static approximation - the checker cannot see the "
            "data, only that no second metric and no imbalance handling are present.",
            "Report precision, recall and average precision against the positive class, or "
            "state the class balance and why accuracy is the right metric for this decision.")

    # GROUP_LEAK -----------------------------------------------------------
    remaining = {lit: line for lit, line in c.id_literals.items() if lit not in c.dropped}
    if remaining and c.random_split_lines and not c.group_aware and not c.groups_passed:
        lit = sorted(remaining)[0]
        add("GROUP_LEAK", WARNING, min(c.random_split_lines),
            f"`{lit}` looks like an entity id and the split at line {min(c.random_split_lines)} "
            "is row-wise, so rows belonging to the same entity land on both sides. The model "
            "is scored on entities it has already seen, which no production request will be.",
            f"Use GroupShuffleSplit or GroupKFold with groups={lit}, or aggregate to one row "
            "per entity before splitting. If the ids are unique per row, drop the column.")

    return sorted(out, key=lambda f: (f.line, f.code))


# --------------------------------------------------------------------- parsing

class ParseFailure(Exception):
    """Raised with a message a human can act on. Never a traceback."""


def read_python(path: Path) -> str:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ParseFailure(f"could not read the file - {exc}") from None
    if len(raw) > MAX_BYTES:
        raise ParseFailure(f"file is {len(raw)} bytes, above the {MAX_BYTES} byte limit")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ParseFailure(f"file is not valid UTF-8 - {exc}") from None


MAGIC_RE = re.compile(r"^\s*[%!]")


def read_notebook(path: Path) -> tuple[str, list[tuple[int, int]]]:
    """Concatenate code cells in cell order.

    Returns the source and a list of (first_line, cell_index) so a finding can
    name the cell. Line magics and shell escapes become blank lines, which
    keeps every line number aligned with the reconstructed source.
    """
    text = read_python(path)
    try:
        doc = json.loads(text)
    except (json.JSONDecodeError, ValueError) as exc:
        raise ParseFailure(f"not valid notebook JSON - {exc}") from None
    if not isinstance(doc, dict) or not isinstance(doc.get("cells"), list):
        raise ParseFailure("notebook JSON has no `cells` list")

    lines: list[str] = []
    starts: list[tuple[int, int]] = []
    for index, cell in enumerate(doc["cells"]):
        if not isinstance(cell, dict) or cell.get("cell_type") != "code":
            continue
        source = cell.get("source", "")
        if isinstance(source, list):
            source = "".join(str(s) for s in source)
        if not isinstance(source, str):
            raise ParseFailure(f"cell {index} has a source that is neither a string nor a list")
        starts.append((len(lines) + 1, index))
        for line in source.splitlines():
            lines.append("" if MAGIC_RE.match(line) else line)
        lines.append("")
    return "\n".join(lines), starts


def cell_for(line: int, starts: list[tuple[int, int]]) -> int:
    found = -1
    for first, index in starts:
        if first <= line:
            found = index
    return found


def docstring_ids(tree: ast.AST) -> set[int]:
    """Node ids of every module, class and function docstring."""
    holders = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
    out: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, holders) and node.body:
            first = node.body[0]
            if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
                    and isinstance(first.value.value, str)):
                out.add(id(first.value))
    return out


def check_file(path: Path) -> list[Finding]:
    name = safe(str(path))
    notebook = path.suffix == ".ipynb"
    starts: list[tuple[int, int]] = []
    try:
        source, starts = read_notebook(path) if notebook else (read_python(path), [])
    except ParseFailure as exc:
        return [Finding("PARSE_ERROR", ERROR, name, 0,
                        safe(clip(f"Not analyzed - {exc}", 600)),
                        "Fix the file or exclude it from the run. An unparsed file is not a "
                        "clean file, so this exits non-zero rather than reporting nothing.")]

    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        version = ".".join(str(p) for p in sys.version_info[:3])
        detail = f"{exc.msg} at line {exc.lineno or 0}"
        return [Finding("PARSE_ERROR", ERROR, name, exc.lineno or 0,
                        safe(clip(f"Not analyzed - Python {version} could not parse it "
                                  f"({detail}). ", 600)) +
                        "Either the file is malformed, it uses syntax newer than this "
                        "interpreter, or a notebook cell holds something other than Python.",
                        f"Run the checker on Python {version} or newer, or fix the syntax. "
                        "Nothing was analyzed, so treat this file as unchecked.")]
    except (ValueError, RecursionError, MemoryError) as exc:
        return [Finding("PARSE_ERROR", ERROR, name, 0,
                        safe(clip(f"Not analyzed - {type(exc).__name__}: {exc}", 600)),
                        "The file is too deeply nested or contains a value the parser rejects.")]

    collector = Collector(docstring_ids(tree))
    try:
        collector.visit(tree)
    except RecursionError:
        return [Finding("PARSE_ERROR", ERROR, name, 0,
                        "Not analyzed - the syntax tree is too deeply nested to walk.",
                        "Split the file, or exclude it from the run.")]

    findings = run_rules(collector, name)

    if notebook:
        findings = [_notebook_adjust(f, starts) for f in findings]
        if starts:
            findings.append(Finding(
                "NOTEBOOK_ORDER", NOTE, name, 1,
                f"Read as {len(starts)} code cells in cell order. A notebook's execution order "
                "is not its cell order, so any finding that depends on one statement preceding "
                "another is unverifiable here and is reported as a warning rather than an error. "
                "Cell numbers below index every cell in the file, markdown included.",
                "Confirm the order by restarting the kernel and running all cells, or move the "
                "training code into a module and check that."))
    return findings


ORDER_DEPENDENT = {"FIT_BEFORE_SPLIT", "RESAMPLE_BEFORE_SPLIT"}


def _notebook_adjust(f: Finding, starts: list[tuple[int, int]]) -> Finding:
    cell = cell_for(f.line, starts)
    message = f.message if cell < 0 else f"[cell {cell}] {f.message}"
    severity = WARNING if f.code in ORDER_DEPENDENT and f.severity == ERROR else f.severity
    return Finding(f.code, severity, f.file, f.line, message, f.fix)


# ------------------------------------------------------------------------- cli

def iter_targets(paths: list[str], recursive: bool) -> tuple[list[Path], list[str]]:
    found: list[Path] = []
    missing: list[str] = []
    for raw in paths:
        p = Path(raw)
        if p.is_dir():
            pool = p.rglob("*") if recursive else p.glob("*")
            found.extend(
                f for f in sorted(pool)
                if f.is_file() and not f.is_symlink()
                and f.suffix in {".py", ".ipynb"}
                and not set(f.parts) & SKIP_DIRS
            )
        elif p.is_file():
            found.append(p)
        else:
            missing.append(raw)
    return sorted(set(found)), missing


def safe(text: str) -> str:
    """Keep control characters in an audited path out of the terminal."""
    return "".join(ch if ch.isprintable() else "?" for ch in text)


def clip(text: str, limit: int) -> str:
    """Bound text carrying content lifted from an audited file."""
    return text if len(text) <= limit else text[:limit] + "..."


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Static auditor for model training code (AST-based, stdlib only).")
    ap.add_argument("paths", nargs="+", help=".py or .ipynb files, or directories")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--recursive", action="store_true", help="descend into subdirectories")
    ap.add_argument("--warnings-as-errors", action="store_true",
                    help="exit 1 on warnings too (notes never affect the exit code)")
    args = ap.parse_args(argv)

    targets, missing = iter_targets(args.paths, args.recursive)
    findings: list[Finding] = [
        Finding("PARSE_ERROR", ERROR, safe(m), 0, "Not analyzed - path does not exist.",
                "Check the path.")
        for m in missing
    ]
    for t in targets:
        findings.extend(check_file(t))

    errors = [f for f in findings if f.severity == ERROR]
    warnings = [f for f in findings if f.severity == WARNING]

    if args.json:
        print(json.dumps({
            "files": len(targets),
            "counts": {"error": len(errors), "warning": len(warnings),
                       "note": len(findings) - len(errors) - len(warnings)},
            "findings": [asdict(f) for f in findings],
        }, indent=2, sort_keys=True))
    else:
        for f in sorted(findings, key=lambda f: (f.file, f.line, f.code)):
            print(f"{f.file}:{f.line}: {f.severity}: {f.code}: {f.message}")
            print(f"    fix: {f.fix}")
        print(f"\n{len(errors)} error, {len(warnings)} warning, "
              f"{len(findings) - len(errors) - len(warnings)} note, {len(targets)} file(s)")
        if not findings and targets:
            print("clean - the structural checks passed. Whether the improvement is real is a "
                  "separate question this does not answer.")

    if errors:
        return 1
    return 1 if args.warnings_as_errors and warnings else 0


if __name__ == "__main__":
    sys.exit(main())
