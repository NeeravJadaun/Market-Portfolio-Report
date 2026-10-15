"""Fill edition copy from the shared results object so every number in prose comes from `Results`."""
from __future__ import annotations

import re

import pandas as pd

from . import theme as T
from .calc import Results
from .config import SNAPSHOT_DIR, load_edition_text, load_sources

REF_ORDER = ["prices", "boc_valet", "boc_doc", "fed_doc", "fomc_calendar", "funds"]


def values(r: Results) -> dict[str, str]:
    h, m, c = r.holdings, r.macro, r.classes
    v: dict[str, str] = {
        "port": T.pct(r.port_return), "port_abs": T.pct(abs(r.port_return), sign=False), "bench": T.pct(r.bench_return),
        "active": T.pp(r.active_return), "eq_sleeve": T.pct(c.loc["Equity", "sleeve_return"]),
        "fi_sleeve": T.pct(c.loc["Fixed income", "sleeve_return"]), "eq_contrib": T.pp(c.loc["Equity", "contrib"]),
        "fi_contrib": T.pp(c.loc["Fixed income", "contrib"]), "fi_contrib_abs": T.pp(abs(c.loc["Fixed income", "contrib"])).lstrip("+"), "eq_end_w": T.wt(c.loc["Equity", "end_w"]),
        "fi_end_w": T.wt(c.loc["Fixed income", "end_w"]), "eq_drift": T.pp(c.loc["Equity", "drift"]),
        "fi_share": f"{c.loc['Fixed income', 'contrib'] / r.port_return * 100:.0f}%",
        "max_hold_drift": f"{r.decision['max_holding_drift_pp']:.2f}{T.NBSP}pp", "max_class_drift": f"{r.decision['max_class_drift_pp']:.2f}{T.NBSP}pp",
        "turnover": T.wt(r.decision["one_way_turnover"], 2), "bench_name": r.benchmark["name"],
        "foreign_w": T.wt(h.loc[["XUU", "XEF", "XEC"], "begin_w"].sum()),
        "policy": f"{m.loc['V39079', 'end_value']:.2f}",
        "cutoff": f"{r.cutoff:%B %-d, %Y}", "month": r.label, "start_label": f"{r.start:%B %-d}",
    }
    from .config import load_portfolio
    rb = load_portfolio()["rebalance"]
    v["class_band"], v["hold_band"] = f"{rb['class_band_pp']:.1f}{T.NBSP}pp", f"{rb['holding_band_pp']:.1f}{T.NBSP}pp"
    for t in h.index:
        v[f"ret_{t}"], v[f"pr_{t}"], v[f"contrib_{t}"] = T.pct(h.loc[t, "total_ret"]), T.pct(h.loc[t, "price_ret"]), T.pp(h.loc[t, "contrib"])
    fx = m.loc["FXUSDCAD"]
    v.update(fx_abs=T.pct(abs(fx.change), sign=False), fx0=f"{fx.start_value:.4f}", fx1=f"{fx.end_value:.4f}", fx_chg=T.pct(fx.change))
    implied = (1 + h.loc["XUU", "total_ret"]) * fx.start_value / fx.end_value - 1
    v["fx_implied"], v["fx_drag"] = T.pct(implied), T.pp(h.loc["XUU", "total_ret"] - implied)
    for key, sid in (("y2", "BD.CDN.2YR.DQ.YLD"), ("y10", "BD.CDN.10YR.DQ.YLD")):
        v[f"{key}_0"], v[f"{key}_1"], v[f"{key}_chg"] = f"{m.loc[sid, 'start_value']:.2f}", f"{m.loc[sid, 'end_value']:.2f}", T.bp(m.loc[sid, "change"])
    v["macro_asof"] = f"{m.loc['BD.CDN.10YR.DQ.YLD', 'end_obs']:%b %-d}"
    return v


class Strict(dict):
    def __missing__(self, k):  # a typo in copy must fail the build, not print a blank
        raise KeyError(f"unknown placeholder {{{k}}}")


def fill(obj, v):
    if isinstance(obj, str):
        return obj.format_map(Strict(v))
    if isinstance(obj, list):
        return [fill(o, v) for o in obj]
    if isinstance(obj, dict):
        return {k: fill(o, v) for k, o in obj.items()}
    return obj


def doc_refs(edition_id: str) -> dict[str, int]:
    """Map source id -> reference number [n] in this edition, following REF_ORDER."""
    ids = load_edition_text(edition_id)["sources"]
    kinds = {"prices": "prices", "boc_valet": "boc_valet", "fomc_calendar": "fomc_calendar"}
    out, n = {}, 0
    for slot in REF_ORDER:
        if slot == "funds":
            n += 1
            out["funds"] = n
            continue
        for s in ids:
            hit = kinds.get(s) == slot or (slot == "boc_doc" and s.startswith("boc_20")) or (slot == "fed_doc" and s.startswith("fed_20"))
            if hit:
                n += 1
                out[s] = n
    return out


def load_text(r: Results) -> dict:
    raw = load_edition_text(r.edition_id)
    v = values(r)
    text = fill({k: x for k, x in raw.items() if k not in ("sources", "quotes", "expects")}, v)
    refs = doc_refs(r.edition_id)
    # [prices] style tokens inside copy become [n]
    def sub(o):
        if isinstance(o, str):
            return re.sub(r"\[(\w+)\]", lambda m: f"[{refs[m.group(1)]}]" if m.group(1) in refs else m.group(0), o)
        if isinstance(o, list):
            return [sub(x) for x in o]
        if isinstance(o, dict):
            return {k: sub(x) for k, x in o.items()}
        return o
    text = sub(text)
    text["_values"], text["_refs"] = v, refs
    check_expectations(r, raw.get("expects", {}))
    return text


def check_expectations(r: Results, expects: dict) -> None:
    """Direction words in the copy were written for specific signs; fail the build if data disagree."""
    probes = {"port_return": r.port_return, "active_return": r.active_return, "eq_contrib": r.classes.loc["Equity", "contrib"],
              "fi_contrib": r.classes.loc["Fixed income", "contrib"], "fx_change": r.macro.loc["FXUSDCAD", "change"],
              "y2_change": r.macro.loc["BD.CDN.2YR.DQ.YLD", "change"], "y10_change": r.macro.loc["BD.CDN.10YR.DQ.YLD", "change"],
              "decision": r.decision["action"]}
    probes |= {f"ret_{t}": r.holdings.loc[t, "total_ret"] for t in r.holdings.index}
    for k, want in expects.items():
        got = probes[k]
        ok = (got == want) if isinstance(want, str) and k == "decision" else (got > 0 if want == "pos" else got < 0)
        if not ok:
            raise AssertionError(f"{r.edition_id}: copy assumes {k} is {want}, data say {got}")


def source_list(r: Results) -> list[dict]:
    """Numbered references: publisher, short title, URL, observation or publication date."""
    srcs = load_sources()
    out = []
    short = {"prices": "ETF closes and distributions", "boc_valet": "FX, yields, overnight target",
             "fomc_calendar": "FOMC meeting calendar"}
    for sid, n in sorted(doc_refs(r.edition_id).items(), key=lambda kv: kv[1]):
        if sid == "funds":
            out.append({"n": n, "id": sid, "publisher": "BlackRock and Vanguard Canada", "title": "fund pages (index objectives only)",
                        "url": "blackrock.com/ca/investors/en/products/ ; vanguard.ca/en/product/etf/asset-allocation/9578/", "date": ""})
            continue
        s = srcs[sid]
        if sid == "prices":
            date = f"{r.start:%b %-d} to {r.cutoff:%b %-d}"
        elif sid == "boc_valet":
            date = f"to {r.cutoff:%b %-d}" + (f", latest {values(r)['macro_asof']}" if r.flags else "")
        elif sid == "fomc_calendar":
            date = "schedule"
        else:
            date = pd.Timestamp(s["publication_date"]).strftime("%b %-d, %Y")
        title = short.get(sid) or ("rate announcement" if sid.startswith("boc") else "FOMC statement")
        pub = s["publisher"].replace(" (chart API)", "").replace(" Valet API", " Valet") if sid != "fomc_calendar" else "Federal Reserve"
        out.append({"n": n, "id": sid, "publisher": pub, "title": title, "url": s["url"].replace("https://www.", "").replace("https://", ""), "date": date})
    return out


def snapshot_text(edition_id: str, source_id: str) -> str:
    return (SNAPSHOT_DIR / edition_id / "docs" / f"{source_id}.txt").read_text()


def retrieval_dates(r: Results) -> list[str]:
    from .data import load_manifest

    return sorted({e["retrieved_at"][:10] for e in load_manifest(r.edition_id)["entries"]})
