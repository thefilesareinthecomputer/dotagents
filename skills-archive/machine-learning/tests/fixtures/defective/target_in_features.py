"""The label column never left the feature matrix. Expects TARGET_IN_FEATURES only."""

import pandas as pd
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, f1_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

SEED = 20240117

frame = pd.read_csv("customers.csv")
label = frame["churned"]
features = frame

f_train, f_test, l_train, l_test = train_test_split(
    features, label, test_size=0.2, random_state=SEED, stratify=label
)

scaler = StandardScaler()
f_train_scaled = scaler.fit_transform(f_train)
f_test_scaled = scaler.transform(f_test)

reference = DummyClassifier(strategy="most_frequent")
reference.fit(f_train_scaled, l_train)

model = RandomForestClassifier(n_estimators=200, random_state=SEED)
model.fit(f_train_scaled, l_train)
predicted = model.predict(f_test_scaled)

print("reference", accuracy_score(l_test, reference.predict(f_test_scaled)))
print("model", accuracy_score(l_test, predicted), f1_score(l_test, predicted))
