"""Paths and configuration loading."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "config"
SNAPSHOT_DIR = ROOT / "data" / "snapshots"
OUTPUT_DIR = ROOT / "outputs"
FONT_DIR = ROOT / "assets" / "fonts"


def load_portfolio() -> dict:
    return json.loads((CONFIG_DIR / "portfolio.json").read_text())


def load_sources() -> dict:
    return json.loads((CONFIG_DIR / "sources.json").read_text())


def load_edition_text(edition_id: str) -> dict:
    return json.loads((CONFIG_DIR / "editions" / f"{edition_id}.json").read_text())


def edition_cfg(portfolio: dict, edition_id: str) -> dict:
    for ed in portfolio["editions"]:
        if ed["id"] == edition_id:
            return ed
    raise KeyError(edition_id)
