"""Repeated entities kept whole on one side of the split. Counter-fixture for
GROUP_LEAK: the entity id is present and the split is group-aware.
"""

import pandas as pd
from sklearn.dummy import DummyClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, recall_score
from sklearn.model_selection import GroupShuffleSplit

SEED = 11

frame = pd.read_csv("visits.csv")
groups = frame["patient_id"]
label = frame["readmitted"]
features = frame.drop(columns=["readmitted", "patient_id"])

splitter = GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=SEED)
train_index, test_index = next(splitter.split(features, label, groups=groups))

f_train, f_test = features.iloc[train_index], features.iloc[test_index]
l_train, l_test = label.iloc[train_index], label.iloc[test_index]

reference = DummyClassifier(strategy="most_frequent")
reference.fit(f_train, l_train)

model = LogisticRegression(max_iter=1000, class_weight="balanced")
model.fit(f_train, l_train)
predicted = model.predict(f_test)

print("reference", accuracy_score(l_test, reference.predict(f_test)))
print("model", accuracy_score(l_test, predicted), recall_score(l_test, predicted))
