"""Accuracy reported alongside explicit imbalance handling. Counter-fixture for
METRIC_MISMATCH via the second clearing path - the file acknowledges the class
balance even though accuracy is the only sklearn metric function it calls.
"""

import pandas as pd
from sklearn.dummy import DummyClassifier
from sklearn.metrics import accuracy_score
from sklearn.model_selection import train_test_split
from sklearn.svm import LinearSVC

SEED = 99

frame = pd.read_csv("transactions.csv")
label = frame["is_fraud"]
features = frame.drop(columns=["is_fraud"])

# Roughly 1 in 700 rows is fraud, so the class weights carry the decision cost
# and accuracy is reported only as a sanity check against the reference.
f_train, f_test, l_train, l_test = train_test_split(
    features, label, test_size=0.3, random_state=SEED, stratify=label
)

reference = DummyClassifier(strategy="most_frequent")
reference.fit(f_train, l_train)

model = LinearSVC(class_weight="balanced", random_state=SEED)
model.fit(f_train, l_train)

print("reference", accuracy_score(l_test, reference.predict(f_test)))
print("model", accuracy_score(l_test, model.predict(f_test)))
