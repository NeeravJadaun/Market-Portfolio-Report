"""Integration tests on the real saved snapshots for both editions."""
import hashlib
import json

import pandas as pd
import pytest

from mpr.config import SNAPSHOT_DIR, load_edition_text, load_portfolio

EDITIONS = ["2026-08", "2026-09"]


def test_two_consecutive_editions(results):
    a, b = results["2026-08"], results["2026-09"]
    assert b.start == a.cutoff
    assert (a.cutoff.month, b.cutoff.month) == (8, 9)
    assert b.start_value == pytest.approx(a.end_value)
    assert (b.holdings["begin_w"] - a.holdings["end_w"]).abs().max() < 1e-15  # August decision was Maintain


@pytest.mark.parametrize("eid", EDITIONS)
def test_weights_sum_to_one(results, eid):
    r = results[eid]
    tol = r.checks["tolerance"]
    for k in ("target_weights_sum", "begin_weights_sum", "end_weights_sum"):
        assert abs(r.checks[k] - 1) < tol
    assert abs(r.classes["end_w"].sum() - 1) < tol


@pytest.mark.parametrize("eid", EDITIONS)
def test_contributions_reconcile_within_documented_tolerance(results, eid):
    r = results[eid]
    assert r.checks["contrib_vs_path_diff"] <= r.checks["tolerance"]
    assert r.checks["class_contrib_vs_total_diff"] <= r.checks["tolerance"]
    assert r.holdings["contrib"].sum() == pytest.approx(r.port_return, abs=r.checks["tolerance"])
    assert r.active_return == pytest.approx(r.port_return - r.bench_return)


@pytest.mark.parametrize("eid", EDITIONS)
def test_dates_and_currency_aligned(results, eid):
    r = results[eid]
    pf = load_portfolio()
    assert r.close.index[0] == r.start and r.close.index[-1] == r.cutoff
    assert r.close.notna().all().all()
    assert list(r.close.columns) == r.tickers + [pf["benchmark"]["ticker"]]
    assert r.daily.index.equals(r.close.index) and r.currency == "CAD"
    assert (r.dist.iloc[0] == 0).all()  # start-date distributions belong to the prior edition


@pytest.mark.parametrize("eid", EDITIONS)
def test_snapshots_contain_nothing_after_cutoff(results, eid):
    from mpr.data import parse_yahoo

    cutoff = results[eid].cutoff
    for f in (SNAPSHOT_DIR / eid / "prices").glob("*.json"):
        close, _ = parse_yahoo(f.read_bytes())
        assert close.index.max() == cutoff
    for f in (SNAPSHOT_DIR / eid / "macro").glob("*.json"):
        obs = json.loads(f.read_text())["observations"]
        assert max(pd.Timestamp(o["d"]) for o in obs) <= cutoff


@pytest.mark.parametrize("eid", EDITIONS)
def test_manifest_hashes_and_dates(eid):
    man = json.loads((SNAPSHOT_DIR / "manifest.json").read_text())[eid]
    assert len(man["entries"]) >= 20
    for e in man["entries"]:
        assert e["url"].startswith("https://") and e["retrieved_at"].startswith("2026-")
        raw = (SNAPSHOT_DIR / eid / e["file"]).read_bytes()
        digest = e.get("sha256") or e["sha256_extract"]
        assert hashlib.sha256(raw.rstrip(b"\n") if e["kind"] == "document" else raw).hexdigest() == digest, e["id"]
        if e["kind"] == "document" and e["id"].startswith(("doc:boc_20", "doc:fed_20")):
            assert e["publication_date"] <= man["cutoff"]


@pytest.mark.parametrize("eid", EDITIONS)
def test_every_quoted_claim_exists_in_its_snapshot(eid):
    quotes = load_edition_text(eid)["quotes"]
    assert len(quotes) >= 6
    for sid, quote in quotes:
        text = (SNAPSHOT_DIR / eid / "docs" / f"{sid}.txt").read_text()
        assert quote in text, f"{sid}: {quote!r}"


@pytest.mark.parametrize("eid", EDITIONS)
def test_copy_direction_words_match_data(results, eid):
    from mpr.narrative import load_text

    load_text(results[eid])  # raises AssertionError if the copy's assumed signs disagree with the data


def test_stale_boc_series_are_flagged_not_filled(results):
    assert results["2026-08"].flags == []
    flags = results["2026-09"].flags
    assert len(flags) == 3 and all("Sep 29" in f for f in flags)
    m = results["2026-09"].macro
    assert m.loc["BD.CDN.10YR.DQ.YLD", "end_obs"] == pd.Timestamp("2026-09-29")
