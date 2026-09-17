"""Accuracy alone, on a problem the file never says anything about balancing.
Expects METRIC_MISMATCH only.
"""

import pandas as pd
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score
from sklearn.model_selection import train_test_split

SEED = 20240117

frame = pd.read_csv("transactions.csv")
label = frame["is_fraud"]
features = frame.drop(columns=["is_fraud"])

f_train, f_test, l_train, l_test = train_test_split(
    features, label, test_size=0.2, random_state=SEED
)

reference = DummyClassifier(strategy="uniform", random_state=SEED)
reference.fit(f_train, l_train)

model = RandomForestClassifier(n_estimators=200, random_state=SEED)
model.fit(f_train, l_train)

print("reference", accuracy_score(l_test, reference.predict(f_test)))
print("model", accuracy_score(l_test, model.predict(f_test)))
