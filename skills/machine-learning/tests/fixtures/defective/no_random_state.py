"""Split and forest both unseeded. Expects NO_RANDOM_STATE only, twice."""

import pandas as pd
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, f1_score
from sklearn.model_selection import train_test_split

frame = pd.read_csv("customers.csv")
label = frame["churned"]
features = frame.drop(columns=["churned"])

f_train, f_test, l_train, l_test = train_test_split(
    features, label, test_size=0.2, stratify=label
)

reference = DummyClassifier(strategy="most_frequent")
reference.fit(f_train, l_train)

model = RandomForestClassifier(n_estimators=200)
model.fit(f_train, l_train)
predicted = model.predict(f_test)

print("reference", accuracy_score(l_test, reference.predict(f_test)))
print("model", accuracy_score(l_test, predicted), f1_score(l_test, predicted))
