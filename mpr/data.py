"""Load and validate source snapshots. Missing or stale data raises or is flagged; nothing is filled."""
from __future__ import annotations

import json
from dataclasses import dataclass

import pandas as pd

from .config import SNAPSHOT_DIR


class DataError(ValueError):
    """Blocking data-quality problem (missing, misaligned or invalid observations)."""


def parse_yahoo(raw: bytes | str) -> tuple[pd.Series, pd.Series]:
    """Return (close, distributions) indexed by exchange-local calendar date."""
    res = json.loads(raw)["chart"]["result"][0]
    if res.get("events", {}).get("splits"):
        raise DataError(f"{res['meta']['symbol']}: split events present; closes are not comparable")
    if res["meta"].get("currency") != "CAD":
        raise DataError(f"{res['meta']['symbol']}: listing currency {res['meta'].get('currency')} is not CAD")

    def to_date(ts):
        return pd.to_datetime(ts, unit="s", utc=True).tz_convert("America/Toronto").tz_localize(None).normalize()

    close = pd.Series(res["indicators"]["quote"][0]["close"], index=pd.DatetimeIndex(to_date(res["timestamp"])), dtype="float64")
    divs = res.get("events", {}).get("dividends", {})
    dist = pd.Series({to_date(v["date"]): float(v["amount"]) for v in divs.values()}, dtype="float64").sort_index()
    return close, dist


def validate_prices(close: pd.DataFrame, dist: pd.DataFrame, start: str, cutoff: str) -> None:
    """Raise DataError unless the panel is complete, aligned, positive and ends exactly at the cutoff."""
    s, c = pd.Timestamp(start), pd.Timestamp(cutoff)
    if close.empty:
        raise DataError("no price data")
    if close.index.max() > c:
        raise DataError(f"observations after cutoff {cutoff}: {close.index.max().date()}")
    if s not in close.index:
        raise DataError(f"start date {start} missing from price panel")
    if close.index.max() != c:
        raise DataError(f"stale data: last observation {close.index.max().date()} but cutoff is {cutoff}")
    window = close.loc[s:c]
    gaps = window.columns[window.isna().any()]
    if len(gaps):
        bad = {t: [d.date().isoformat() for d in window.index[window[t].isna()]] for t in gaps}
        raise DataError(f"missing observations, not filled: {bad}")
    if (window <= 0).any().any():
        raise DataError("non-positive price observed")
    off = dist.index.difference(close.index)
    if len(off):
        raise DataError(f"distribution dates not on the trading calendar: {[d.date().isoformat() for d in off]}")


def load_prices(edition_id: str, tickers: list[str], symbols: dict[str, str], start: str, cutoff: str):
    """Return (close, dist) DataFrames for [start, cutoff], aligned on one trading calendar."""
    closes, dists = {}, {}
    for t in tickers:
        raw = (SNAPSHOT_DIR / edition_id / "prices" / f"{symbols[t]}.json").read_bytes()
        closes[t], dists[t] = parse_yahoo(raw)
    # outer join so a ticker missing a date shows as NaN and is rejected, never silently dropped
    close = pd.DataFrame(closes).sort_index()
    alldist = pd.DataFrame(dists).reindex(close.index)
    validate_prices(close, alldist.dropna(how="all"), start, cutoff)
    close = close.loc[start:cutoff]
    dist = alldist.loc[start:cutoff].fillna(0.0)  # zero means "no ex-date that day", not a filled gap
    dist.iloc[0] = 0.0  # the start date is the prior close; its distributions belong to the prior edition
    return close, dist


@dataclass(frozen=True)
class AsOf:
    value: float
    obs_date: pd.Timestamp
    requested: pd.Timestamp

    @property
    def stale_days(self) -> int:
        return (self.requested - self.obs_date).days


def asof(series: pd.Series, date: str) -> AsOf:
    """Latest observation on or before date; never extrapolates and never uses later data."""
    d = pd.Timestamp(date)
    s = series.dropna()
    s = s[s.index <= d]
    if s.empty:
        raise DataError(f"no observation on or before {date}")
    return AsOf(float(s.iloc[-1]), s.index[-1], d)


def load_macro(edition_id: str, series_ids: list[str]) -> dict[str, pd.Series]:
    out = {}
    for sid in series_ids:
        obs = json.loads((SNAPSHOT_DIR / edition_id / "macro" / f"{sid}.json").read_text())["observations"]
        out[sid] = pd.Series({pd.Timestamp(o["d"]): float(o[sid]["v"]) for o in obs if sid in o and o[sid].get("v") not in (None, "")}).sort_index()
    return out


def load_manifest(edition_id: str) -> dict:
    return json.loads((SNAPSHOT_DIR / "manifest.json").read_text())[edition_id]
