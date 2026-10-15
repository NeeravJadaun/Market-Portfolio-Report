"""Unit tests on small synthetic inputs: weights, alignment, missing data, reconciliation, rebalancing."""
import numpy as np
import pandas as pd
import pytest

from mpr import theme as T
from mpr.calc import contributions, end_weights, rebalance_decision, total_return_index
from mpr.data import DataError, asof, parse_yahoo, validate_prices

DATES = pd.bdate_range("2026-07-31", "2026-08-07")


def panel(**cols):
    return pd.DataFrame(cols, index=DATES)


def test_tri_reinvests_distribution_on_ex_date():
    close = panel(A=[100.0, 101, 102, 103, 104, 105])
    dist = panel(A=[0.0, 0, 0, 1.0, 0, 0])
    tri = total_return_index(close, dist)
    assert tri.iloc[0, 0] == 1.0
    manual = (101 / 100) * (102 / 101) * ((103 + 1) / 102) * (104 / 103) * (105 / 104)
    assert tri.iloc[-1, 0] == pytest.approx(manual)


def test_weights_sum_to_one_before_and_after_drift():
    w = pd.Series({"A": 0.6, "B": 0.4})
    r = pd.Series({"A": 0.05, "B": -0.02})
    assert w.sum() == pytest.approx(1)
    assert end_weights(w, r).sum() == pytest.approx(1)


@pytest.mark.parametrize("seed", range(5))
def test_contributions_reconcile_to_daily_path(seed):
    rng = np.random.default_rng(seed)
    close = pd.DataFrame(100 * np.cumprod(1 + rng.normal(0, 0.01, (6, 3)), axis=0), index=DATES, columns=list("ABC"))
    dist = pd.DataFrame(0.0, index=DATES, columns=list("ABC"))
    dist.iloc[3, 1] = 0.4
    tri = total_return_index(close, dist)
    w = pd.Series([0.5, 0.3, 0.2], index=list("ABC"))
    month = tri.iloc[-1] / tri.iloc[0] - 1
    path = (tri * w).sum(axis=1).iloc[-1] - 1
    assert contributions(w, month).sum() == pytest.approx(path, abs=1e-12)


def test_validate_rejects_missing_observation_instead_of_filling():
    close = panel(A=[1.0, 2, np.nan, 4, 5, 6], B=[1.0] * 6)
    with pytest.raises(DataError, match="missing observations"):
        validate_prices(close, close * 0, "2026-07-31", "2026-08-07")


def test_validate_rejects_stale_series_and_future_data():
    close = panel(A=[1.0] * 6)
    with pytest.raises(DataError, match="stale"):
        validate_prices(close.iloc[:-1], close.iloc[:-1] * 0, "2026-07-31", "2026-08-07")
    with pytest.raises(DataError, match="after cutoff"):
        validate_prices(close, close * 0, "2026-07-31", "2026-08-06")


def test_validate_rejects_misaligned_dates_and_bad_prices():
    a = pd.Series(1.0, index=DATES)
    b = pd.Series(1.0, index=DATES.delete(2))
    with pytest.raises(DataError, match="missing observations"):
        close = pd.DataFrame({"A": a, "B": b})
        validate_prices(close, close * 0, "2026-07-31", "2026-08-07")
    with pytest.raises(DataError, match="non-positive"):
        validate_prices(panel(A=[1.0, 1, 0, 1, 1, 1]), panel(A=[0.0] * 6), "2026-07-31", "2026-08-07")
    with pytest.raises(DataError, match="trading calendar"):
        validate_prices(panel(A=[1.0] * 6), pd.DataFrame({"A": [1.0]}, index=[pd.Timestamp("2026-08-01")]), "2026-07-31", "2026-08-07")


def test_parse_rejects_non_cad_and_split_series():
    base = {"chart": {"result": [{"meta": {"symbol": "X", "currency": "USD"}, "timestamp": [1], "indicators": {"quote": [{"close": [1.0]}]}}]}}
    import json
    with pytest.raises(DataError, match="not CAD"):
        parse_yahoo(json.dumps(base))
    base["chart"]["result"][0]["meta"]["currency"] = "CAD"
    base["chart"]["result"][0]["events"] = {"splits": {"1": {}}}
    with pytest.raises(DataError, match="split"):
        parse_yahoo(json.dumps(base))


def test_asof_never_uses_later_data_and_reports_staleness():
    s = pd.Series({pd.Timestamp("2026-09-28"): 1.0, pd.Timestamp("2026-09-29"): 2.0, pd.Timestamp("2026-10-01"): 9.0})
    a = asof(s, "2026-09-30")
    assert (a.value, a.stale_days) == (2.0, 1)
    with pytest.raises(DataError):
        asof(s, "2026-09-01")


def test_rebalance_threshold_logic_and_trades():
    target = pd.Series({"A": 0.4, "B": 0.2, "C": 0.4})
    classes = pd.Series({"A": "Eq", "B": "Eq", "C": "FI"})
    ct = pd.Series({"Eq": 0.6, "FI": 0.4})
    inside = rebalance_decision(pd.Series({"A": 0.41, "B": 0.2, "C": 0.39}), target, classes, ct, 2.0, 1.5)
    assert inside["action"] == "Maintain" and not inside["reasons"]
    holding = rebalance_decision(pd.Series({"A": 0.42, "B": 0.2, "C": 0.38}), target, classes, ct, 3.0, 1.5)
    assert holding["action"] == "Rebalance" and "A" in holding["reasons"][0]
    sleeve = rebalance_decision(pd.Series({"A": 0.35, "B": 0.27, "C": 0.38}), target, classes, ct, 1.5, 9.0)
    assert sleeve["action"] == "Rebalance"
    assert sleeve["trades"].sum() == pytest.approx(0)
    assert sleeve["one_way_turnover"] == pytest.approx(sleeve["trades"].abs().sum() / 2)


def test_number_formats_are_consistent():
    assert T.pct(0.01234) == "+1.23%" and T.pct(-0.01234) == "−1.23%" and T.pct(-0.000001) == "0.00%"
    assert T.pp(0.0013) == "+0.13 pp" and T.pp(-0.0006) == "−0.06 pp"
    assert T.bp(36.0) == "+36 bp" and T.wt(0.2036) == "20.4%"
