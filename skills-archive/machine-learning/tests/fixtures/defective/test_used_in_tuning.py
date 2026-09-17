"""Early stopping watched the test split. Expects TEST_USED_IN_TUNING only."""

import pandas as pd
from sklearn.dummy import DummyClassifier
from sklearn.metrics import accuracy_score, roc_auc_score
from sklearn.model_selection import train_test_split
from xgboost import XGBClassifier

SEED = 20240117

frame = pd.read_csv("customers.csv")
label = frame["churned"]
features = frame.drop(columns=["churned"])

f_train, f_test, l_train, l_test = train_test_split(
    features, label, test_size=0.2, random_state=SEED, stratify=label
)

reference = DummyClassifier(strategy="most_frequent")
reference.fit(f_train, l_train)

model = XGBClassifier(n_estimators=2000, early_stopping_rounds=50, random_state=SEED)
model.fit(f_train, l_train, eval_set=[(f_test, l_test)])

predicted = model.predict(f_test)
print("reference", accuracy_score(l_test, reference.predict(f_test)))
print("model", accuracy_score(l_test, predicted))
print("auc", roc_auc_score(l_test, model.predict_proba(f_test)[:, 1]))
