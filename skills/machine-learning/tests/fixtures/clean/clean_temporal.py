"""Time-ordered data split forward in time. Counter-fixture for
TEMPORAL_SPLIT_MISSING: the date column is present and the split respects it.
"""

import pandas as pd
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import TimeSeriesSplit

SEED = 3407

frame = pd.read_csv("demand.csv", parse_dates=["order_date"])
frame = frame.sort_values("order_date")

label = frame["units_sold"]
features = frame.drop(columns=["units_sold", "order_date"])

splitter = TimeSeriesSplit(n_splits=5, test_size=30)

for fold, (train_index, test_index) in enumerate(splitter.split(features)):
    f_train = features.iloc[train_index]
    f_test = features.iloc[test_index]
    l_train = label.iloc[train_index]
    l_test = label.iloc[test_index]

    reference = DummyRegressor(strategy="median")
    reference.fit(f_train, l_train)

    model = HistGradientBoostingRegressor(random_state=SEED)
    model.fit(f_train, l_train)

    predicted = model.predict(f_test)
    print(
        fold,
        mean_absolute_error(l_test, reference.predict(f_test)),
        mean_absolute_error(l_test, predicted),
        r2_score(l_test, predicted),
    )
