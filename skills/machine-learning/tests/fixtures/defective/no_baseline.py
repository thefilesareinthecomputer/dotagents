"""A score with nothing to compare it against. Expects NO_BASELINE only."""

import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, f1_score
from sklearn.model_selection import train_test_split

SEED = 20240117

frame = pd.read_csv("customers.csv")
label = frame["churned"]
features = frame.drop(columns=["churned"])

f_train, f_test, l_train, l_test = train_test_split(
    features, label, test_size=0.2, random_state=SEED, stratify=label
)

model = RandomForestClassifier(n_estimators=200, random_state=SEED)
model.fit(f_train, l_train)
predicted = model.predict(f_test)

print("accuracy", accuracy_score(l_test, predicted))
print("f1", f1_score(l_test, predicted))
