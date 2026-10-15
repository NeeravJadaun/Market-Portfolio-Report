"""Shared results object. Every output (PDF, workbook, deck, charts) reads from `Results`."""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from .config import edition_cfg, load_portfolio
from .data import AsOf, asof, load_macro, load_prices


def total_return_index(close: pd.DataFrame, dist: pd.DataFrame) -> pd.DataFrame:
    """Daily total-return index, 1.0 at the start date. Distributions are reinvested at the ex-date close."""
    factor = (close + dist) / close.shift(1)
    factor.iloc[0] = 1.0
    return factor.cumprod()


def contributions(begin_w: pd.Series, asset_ret: pd.Series) -> pd.Series:
    """Weight x return for one period, with beginning weights. Not formal performance attribution."""
    return begin_w * asset_ret


def end_weights(begin_w: pd.Series, asset_ret: pd.Series) -> pd.Series:
    grown = begin_w * (1 + asset_ret)
    return grown / grown.sum()


def rebalance_decision(end_w: pd.Series, target: pd.Series, classes: pd.Series, class_target: pd.Series,
                       class_band_pp: float, holding_band_pp: float) -> dict:
    h_drift = (end_w - target) * 100
    c_end = end_w.groupby(classes).sum()
    c_drift = (c_end - class_target) * 100
    reasons = []
    for k, v in c_drift.items():
        if abs(v) > class_band_pp:
            reasons.append(f"{k} sleeve {v:+.2f} pp from target (band ±{class_band_pp:.1f} pp)")
    for k, v in h_drift.items():
        if abs(v) > holding_band_pp:
            reasons.append(f"{k} {v:+.2f} pp from target (band ±{holding_band_pp:.1f} pp)")
    trades = (target - end_w)
    return {
        "action": "Rebalance" if reasons else "Maintain",
        "reasons": reasons,
        "max_class_drift_pp": float(c_drift.abs().max()),
        "max_holding_drift_pp": float(h_drift.abs().max()),
        "trades": trades,
        "one_way_turnover": float(trades.abs().sum() / 2),
    }


@dataclass
class Results:
    edition_id: str
    label: str
    start: pd.Timestamp
    cutoff: pd.Timestamp
    currency: str
    portfolio_name: str
    holdings: pd.DataFrame            # one row per holding, index = ticker
    classes: pd.DataFrame             # Equity / Fixed income sleeves
    benchmark: dict
    port_return: float
    bench_return: float
    active_return: float
    daily: pd.DataFrame               # cumulative returns and TRIs, index = date
    close: pd.DataFrame
    dist: pd.DataFrame
    tri: pd.DataFrame
    macro: pd.DataFrame
    decision: dict
    checks: dict
    start_value: float = 0.0
    end_value: float = 0.0
    flags: list[str] = field(default_factory=list)
    cfg: dict = field(default_factory=dict)

    @property
    def tickers(self) -> list[str]:
        return list(self.holdings.index)


def compute(edition_id: str, prior: "Results | None" = None) -> Results:
    pf = load_portfolio()
    ed = edition_cfg(pf, edition_id)
    hold = pd.DataFrame(pf["holdings"]).set_index("ticker")
    bm = pf["benchmark"]
    symbols = {t: r["symbol"] for t, r in hold.iterrows()} | {bm["ticker"]: bm["symbol"]}
    close, dist = load_prices(edition_id, list(symbols), symbols, ed["start"], ed["cutoff"])
    tri = total_return_index(close, dist)

    target = hold["weight"].astype(float)
    if prior is None:
        begin_w, carry = target.copy(), "portfolio set to target weights at inception."
    else:
        if prior.cutoff != pd.Timestamp(ed["start"]):
            raise ValueError("editions are not consecutive")
        begin_w = prior.holdings["end_w"].copy() if prior.decision["action"] == "Maintain" else target.copy()
        carry = ("prior month-end drifted weights, as the prior decision was Maintain." if prior.decision["action"] == "Maintain"
                 else "reset to target, as the prior decision was Rebalance.")

    ret_total = tri.iloc[-1] / tri.iloc[0] - 1
    ret_price = close.iloc[-1] / close.iloc[0] - 1
    dist_sum = dist.sum()
    h = hold[["name", "short", "asset_class", "exposure", "hedged", "rationale", "source", "symbol"]].copy()
    h["target_w"] = target
    h["begin_w"] = begin_w
    h["begin_px"], h["end_px"], h["dist"] = close.iloc[0][h.index], close.iloc[-1][h.index], dist_sum[h.index]
    h["price_ret"], h["total_ret"] = ret_price[h.index], ret_total[h.index]
    h["contrib"] = contributions(h["begin_w"], h["total_ret"])
    h["end_w"] = end_weights(h["begin_w"], h["total_ret"])
    h["drift"] = h["end_w"] - h["target_w"]
    h["begin_drift"] = h["begin_w"] - h["target_w"]

    port_ret = float(h["contrib"].sum())
    bench_ret = float(ret_total[bm["ticker"]])

    cls_target = pd.Series({"Equity": pf["equity_target"], "Fixed income": pf["fixed_income_target"]})
    g = h.groupby("asset_class")
    cl = pd.DataFrame({"target_w": cls_target, "begin_w": g["begin_w"].sum(), "contrib": g["contrib"].sum(), "end_w": g["end_w"].sum()})
    cl["sleeve_return"] = cl["contrib"] / cl["begin_w"]
    cl["drift"] = cl["end_w"] - cl["target_w"]
    cl = cl.loc[["Equity", "Fixed income"]]

    port_idx = (tri[h.index] * h["begin_w"]).sum(axis=1)  # buy-and-hold from beginning weights
    daily = pd.DataFrame({"portfolio": port_idx - 1, "benchmark": tri[bm["ticker"]] - 1})
    daily["active"] = daily["portfolio"] - daily["benchmark"]

    rb = pf["rebalance"]
    decision = rebalance_decision(h["end_w"], target, h["asset_class"], cls_target, rb["class_band_pp"], rb["holding_band_pp"])
    decision["cost_bps"] = rb["transaction_cost_bps"]
    decision["carry_note"] = carry

    checks = {
        "target_weights_sum": float(target.sum()),
        "begin_weights_sum": float(h["begin_w"].sum()),
        "end_weights_sum": float(h["end_w"].sum()),
        "contrib_vs_path_diff": float(abs(port_ret - daily["portfolio"].iloc[-1])),
        "class_contrib_vs_total_diff": float(abs(cl["contrib"].sum() - port_ret)),
        "tolerance": pf["reconciliation_tolerance"],
    }

    start_value = float(pf["start_value"]) if prior is None else prior.end_value
    macro_raw = load_macro(edition_id, [m["id"] for m in pf["macro_series"]])
    rows, flags = [], []
    for m in pf["macro_series"]:
        a0, a1 = asof(macro_raw[m["id"]], ed["start"]), asof(macro_raw[m["id"]], ed["cutoff"])
        change = (a1.value / a0.value - 1) if m["kind"] == "level" else (a1.value - a0.value) * 100
        note = ""
        for a, tag in ((a0, "start"), (a1, "end")):
            if a.stale_days:
                note += f"{tag} value is the {a.obs_date:%b %d} observation (no publication on {a.requested:%b %d}). "
        if note:
            flags.append(f"{m['label']}: {note.strip()}")
        rows.append({"id": m["id"], "label": m["label"], "unit": m["unit"], "dp": m["dp"], "kind": m["kind"],
                     "start_value": a0.value, "start_obs": a0.obs_date, "end_value": a1.value, "end_obs": a1.obs_date,
                     "change": change, "change_unit": "%" if m["kind"] == "level" else "bp", "note": note.strip()})
    macro = pd.DataFrame(rows).set_index("id")

    return Results(edition_id, ed["label"], pd.Timestamp(ed["start"]), pd.Timestamp(ed["cutoff"]), pf["currency"], pf["name"],
                   h, cl, bm, port_ret, bench_ret, port_ret - bench_ret, daily, close, dist, tri, macro, decision, checks,
                   start_value, start_value * (1 + port_ret), flags, ed)


def compute_all() -> dict[str, Results]:
    out, prior = {}, None
    for ed in load_portfolio()["editions"]:
        prior = out[ed["id"]] = compute(ed["id"], prior)
    return out
