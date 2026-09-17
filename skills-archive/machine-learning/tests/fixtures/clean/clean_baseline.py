"""Correct tabular training script. The checker must be silent on this file.

Not executed by the tests. It exists so that every rule has something it must
not fire on: a checker that fires on correct code gets muted, and a muted
checker protects nothing.
"""

import pandas as pd
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, f1_score, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

SEED = 20240117

frame = pd.read_csv("customers.csv")
label = frame["churned"]
features = frame.drop(columns=["churned"])

f_train, f_test, l_train, l_test = train_test_split(
    features, label, test_size=0.2, random_state=SEED, stratify=label
)

scaler = StandardScaler()
f_train_scaled = scaler.fit_transform(f_train)
f_test_scaled = scaler.transform(f_test)

reference = DummyClassifier(strategy="most_frequent")
reference.fit(f_train_scaled, l_train)
reference_accuracy = accuracy_score(l_test, reference.predict(f_test_scaled))

model = RandomForestClassifier(
    n_estimators=200, random_state=SEED, class_weight="balanced"
)
model.fit(f_train_scaled, l_train)
predicted = model.predict(f_test_scaled)

print("reference", reference_accuracy)
print("model", accuracy_score(l_test, predicted), f1_score(l_test, predicted))
print("auc", roc_auc_score(l_test, model.predict_proba(f_test_scaled)[:, 1]))
