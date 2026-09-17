"""SMOTE run over the whole frame before splitting. Expects
RESAMPLE_BEFORE_SPLIT only.
"""

import pandas as pd
from imblearn.over_sampling import SMOTE
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, recall_score
from sklearn.model_selection import train_test_split

SEED = 20240117

frame = pd.read_csv("transactions.csv")
label = frame["is_fraud"]
features = frame.drop(columns=["is_fraud"])

sampler = SMOTE(random_state=SEED)
features_balanced, label_balanced = sampler.fit_resample(features, label)

f_train, f_test, l_train, l_test = train_test_split(
    features_balanced, label_balanced, test_size=0.2, random_state=SEED
)

reference = DummyClassifier(strategy="most_frequent")
reference.fit(f_train, l_train)

model = RandomForestClassifier(n_estimators=200, random_state=SEED)
model.fit(f_train, l_train)
predicted = model.predict(f_test)

print("reference", accuracy_score(l_test, reference.predict(f_test)))
print("model", accuracy_score(l_test, predicted), recall_score(l_test, predicted))
