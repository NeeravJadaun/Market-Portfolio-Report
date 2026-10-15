"""Refresh source snapshots from public endpoints (no keys, no paid data).

Only this module touches the network. Builds read the saved snapshots, so
regenerating the editions is offline and reproducible. Each edition's price and
macro requests end at that edition's cutoff, so no snapshot contains later data.
"""
from __future__ import annotations

import hashlib
import html
import json
import re
import ssl
import urllib.request
from datetime import datetime, timedelta, timezone

import certifi

from .config import SNAPSHOT_DIR, load_portfolio, load_sources

UA = {"User-Agent": "Mozilla/5.0 (research-sample; educational)"}
CTX = ssl.create_default_context(cafile=certifi.where())
YAHOO = "https://query1.finance.yahoo.com/v8/finance/chart/{sym}?period1={p1}&period2={p2}&interval=1d&events=div%7Csplit"
VALET = "https://www.bankofcanada.ca/valet/observations/{sid}/json?start_date={s}&end_date={e}"


def _get(url: str, retries: int = 3) -> bytes:
    last = None
    for _ in range(retries):
        try:
            req = urllib.request.Request(url, headers=UA)
            return urllib.request.urlopen(req, timeout=40, context=CTX).read()
        except Exception as exc:  # noqa: BLE001 - retried then re-raised
            last = exc
    raise RuntimeError(f"fetch failed for {url}: {last}")


def _html_text(raw: bytes) -> str:
    t = raw.decode("utf-8", errors="ignore")
    t = re.sub(r"<script.*?</script>|<style.*?</style>", "", t, flags=re.S)
    t = re.sub(r"<[^>]+>", " ", t)
    return html.unescape(re.sub(r"\s+", " ", t)).strip()


def _extract(text: str, spec: dict) -> str:
    if "regex" in spec:
        found = []
        for rx in [spec["regex"]] if isinstance(spec["regex"], str) else spec["regex"]:
            m = re.search(rx, text)
            if not m:
                raise RuntimeError(f"expected text not found on page: {rx}")
            found.append(m.group(0))
        return " | ".join(found)
    start, end = spec["extract"]
    i = text.rfind(start) if start == "For release at" else text.find(start)
    j = text.find(end, i)
    if i < 0 or j < 0:
        raise RuntimeError(f"markers not found: {spec['extract']}")
    return text[i:j].strip()


def _epoch(d: str, plus_days: int = 0) -> int:
    dt = datetime.fromisoformat(d).replace(tzinfo=timezone.utc) + timedelta(days=plus_days)
    return int(dt.timestamp())


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def refresh(edition_ids: list[str] | None = None) -> None:
    pf, srcs = load_portfolio(), load_sources()
    editions = [e for e in pf["editions"] if not edition_ids or e["id"] in edition_ids]
    retrieved = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    manifest_path = SNAPSHOT_DIR / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    tickers = [h["symbol"] for h in pf["holdings"]] + [pf["benchmark"]["symbol"]]
    for ed in editions:
        d = SNAPSHOT_DIR / ed["id"]
        (d / "prices").mkdir(parents=True, exist_ok=True)
        (d / "macro").mkdir(exist_ok=True)
        (d / "docs").mkdir(exist_ok=True)
        entries = []
        p1 = _epoch(ed["start"], -12)
        p2 = _epoch(ed["cutoff"], 1)  # exclusive end: includes cutoff day, nothing later
        for sym in tickers:
            url = YAHOO.format(sym=sym, p1=p1, p2=p2)
            raw = _get(url)
            (d / "prices" / f"{sym}.json").write_bytes(raw)
            entries.append({"id": f"prices:{sym}", "file": f"prices/{sym}.json", "url": url, "kind": "prices",
                            "window": [ed["start"], ed["cutoff"]], "retrieved_at": retrieved, "sha256": _sha(raw)})
        for s in pf["macro_series"]:
            url = VALET.format(sid=s["id"], s=(datetime.fromisoformat(ed["start"]) - timedelta(days=10)).date(), e=ed["cutoff"])
            raw = _get(url)
            (d / "macro" / f"{s['id']}.json").write_bytes(raw)
            entries.append({"id": f"macro:{s['id']}", "file": f"macro/{s['id']}.json", "url": url, "kind": "macro",
                            "window": [ed["start"], ed["cutoff"]], "retrieved_at": retrieved, "sha256": _sha(raw)})
        for sid in _edition_doc_ids(ed["id"], srcs, pf):
            spec = srcs[sid]
            raw = _get(spec["url"])
            text = _extract(_html_text(raw), spec)
            (d / "docs" / f"{sid}.txt").write_text(text + "\n")
            entries.append({"id": f"doc:{sid}", "file": f"docs/{sid}.txt", "url": spec["url"], "kind": "document",
                            "publication_date": spec.get("publication_date"), "retrieved_at": retrieved,
                            "sha256_raw_page": _sha(raw), "sha256_extract": _sha(text.encode())})
        manifest[ed["id"]] = {"cutoff": ed["cutoff"], "entries": entries}
        print(f"{ed['id']}: {len(entries)} snapshots saved")
    manifest_path.write_text(json.dumps(manifest, indent=2))


def _edition_doc_ids(edition_id: str, srcs: dict, pf: dict) -> list[str]:
    from .config import load_edition_text

    ids = [s for s in load_edition_text(edition_id)["sources"] if srcs[s]["kind"] == "document"]
    ids += [h["source"] for h in pf["holdings"] + [pf["benchmark"]] if h["source"] not in ids]
    return ids
