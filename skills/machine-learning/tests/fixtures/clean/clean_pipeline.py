"""Pipeline form. Preprocessing and resampling refit inside every fold.

Counter-fixture for FIT_BEFORE_SPLIT, RESAMPLE_BEFORE_SPLIT and
TEST_USED_IN_TUNING: the search only ever sees the training split.
"""

import pandas as pd
from imblearn.over_sampling import SMOTE
from imblearn.pipeline import Pipeline
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import accuracy_score, average_precision_score
from sklearn.model_selection import GridSearchCV, train_test_split
from sklearn.preprocessing import StandardScaler

SEED = 7

frame = pd.read_csv("applications.csv")
label = frame["defaulted"]
features = frame.drop(columns=["defaulted"])

f_train, f_test, l_train, l_test = train_test_split(
    features, label, test_size=0.25, random_state=SEED, stratify=label
)

pipeline = Pipeline(
    steps=[
        ("scale", StandardScaler()),
        ("resample", SMOTE(random_state=SEED)),
        ("model", GradientBoostingClassifier(random_state=SEED)),
    ]
)

search = GridSearchCV(
    pipeline,
    param_grid={"model__max_depth": [2, 3, 4]},
    scoring="average_precision",
    cv=5,
)
search.fit(f_train, l_train)

reference = DummyClassifier(strategy="prior")
reference.fit(f_train, l_train)

scores = search.best_estimator_.predict_proba(f_test)[:, 1]
print("reference", average_precision_score(l_test, reference.predict_proba(f_test)[:, 1]))
print("model", average_precision_score(l_test, scores))
print("accuracy", accuracy_score(l_test, search.best_estimator_.predict(f_test)))
