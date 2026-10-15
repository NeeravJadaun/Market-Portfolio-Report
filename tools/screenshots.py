"""Render the real PDFs, slides and workbook sheets to PNG under docs/screenshots (needs soffice for pptx/xlsx)."""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

import pymupdf
from PIL import Image, ImageChops

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "screenshots"


def crop(path: Path, pad: int = 24) -> None:
    im = Image.open(path).convert("RGB")
    bbox = ImageChops.difference(im, Image.new("RGB", im.size, (255, 255, 255))).getbbox()
    if bbox:
        im = im.crop((max(bbox[0] - pad, 0), max(bbox[1] - pad, 0), min(bbox[2] + pad, im.width), min(bbox[3] + pad, im.height)))
    im.save(path)


def pdf_to_png(pdf: Path, stem: str, dpi: int, crop_pages: bool = False) -> None:
    for i, page in enumerate(pymupdf.open(pdf)):
        p = OUT / f"{stem}-{i + 1}.png"
        page.get_pixmap(dpi=dpi).save(p)
        if crop_pages:
            crop(p)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for ed in ("2026-08", "2026-09"):
        src = ROOT / "outputs" / ed
        pdf_to_png(src / f"Market-Portfolio-Report-{ed}.pdf", f"report-{ed}-page", 110)
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run([str(ROOT / "tools" / "render_office.sh"), tmp, str(src / f"Market-Portfolio-Deck-{ed}.pptx"), str(src / f"Market-Portfolio-Workbook-{ed}.xlsx")], check=True)
            pdf_to_png(Path(tmp) / f"Market-Portfolio-Deck-{ed}.pdf", f"deck-{ed}-slide", 110)
            names = ["overview", "holdings", "returns", "returns-daily", "contributions", "contributions-2", "assumptions", "sources"]
            wb = pymupdf.open(Path(tmp) / f"Market-Portfolio-Workbook-{ed}.pdf")
            keep = {0: "overview", 1: "holdings", 2: "returns"}
            for i, page in enumerate(wb):
                title = page.get_text().split("\n")[0].lower()
                tag = next((k for k in ("market & portfolio report workbook", "holdings", "returns", "contribution", "assumptions", "sources") if title.startswith(k)), None)
                if tag and tag != "returns" or (tag == "returns" and i == 2):
                    label = {"market & portfolio report workbook": "overview", "contribution": "contributions"}.get(tag, tag)
                    p = OUT / f"workbook-{ed}-{label}.png"
                    page.get_pixmap(dpi=200).save(p)
                    crop(p)
    print("screenshots in", OUT)


if __name__ == "__main__":
    sys.exit(main())
