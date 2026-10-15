"""Command line: python -m mpr build | fetch | check"""
from __future__ import annotations

import argparse
from pathlib import Path

from .config import OUTPUT_DIR


def build(only: list[str] | None = None) -> None:
    from .calc import compute_all
    from .charts import build_charts
    from .pdf import build_pdf
    from .workbook import build_workbook
    from .deck import build_deck

    results = compute_all()
    for eid, r in results.items():
        if only and eid not in only:
            continue
        out = OUTPUT_DIR / eid
        charts = build_charts(r, out / "charts")
        pdf = build_pdf(r, charts, out / f"Market-Portfolio-Report-{eid}.pdf")
        print("wrote", pdf)
        print("wrote", build_workbook(r, out / f"Market-Portfolio-Workbook-{eid}.xlsx"))
        print("wrote", build_deck(r, charts, out / f"Market-Portfolio-Deck-{eid}.pptx"))


def main() -> None:
    ap = argparse.ArgumentParser(prog="mpr")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="regenerate both editions from saved snapshots (offline)")
    b.add_argument("--edition", action="append")
    f = sub.add_parser("fetch", help="re-download public source snapshots (network)")
    f.add_argument("--edition", action="append")
    a = ap.parse_args()
    if a.cmd == "fetch":
        from .fetch import refresh
        refresh(a.edition)
    else:
        build(a.edition)


if __name__ == "__main__":
    main()
