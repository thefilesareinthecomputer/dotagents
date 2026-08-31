"""Several rows per patient, split row-wise. Expects GROUP_LEAK only."""

import pandas as pd
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, recall_score
from sklearn.model_selection import train_test_split

SEED = 20240117

frame = pd.read_csv("visits.csv")
print("visits per patient", frame["patient_id"].value_counts().mean())

label = frame["readmitted"]
features = frame.drop(columns=["readmitted"])

f_train, f_test, l_train, l_test = train_test_split(
    features, label, test_size=0.2, random_state=SEED, stratify=label
)

reference = DummyClassifier(strategy="most_frequent")
reference.fit(f_train, l_train)

model = RandomForestClassifier(n_estimators=200, random_state=SEED)
model.fit(f_train, l_train)
predicted = model.predict(f_test)

print("reference", accuracy_score(l_test, reference.predict(f_test)))
print("model", accuracy_score(l_test, predicted), recall_score(l_test, predicted))
