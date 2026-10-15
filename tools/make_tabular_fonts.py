"""Derive 'Inter Tabular' from the stock Inter TTFs (SIL OFL 1.1).

Inter ships tabular figures as ``<glyph>.tf`` alternates behind the ``tnum``
feature. ReportLab, matplotlib and python-pptx cannot switch OpenType features,
so this remaps the cmap to the tabular glyphs and renames the family.

Usage: python tools/make_tabular_fonts.py <dir containing Inter-*.ttf> [out_dir]
"""
import sys
from pathlib import Path

from fontTools.ttLib import TTFont

STYLES = ["Regular", "Medium", "SemiBold", "Bold"]
FAMILY = "Inter Tabular"


def convert(src: Path, dst: Path, style: str) -> None:
    font = TTFont(src)
    glyphs = set(font.getGlyphOrder())
    for table in font["cmap"].tables:
        for code, name in list(table.cmap.items()):
            if f"{name}.tf" in glyphs:
                table.cmap[code] = f"{name}.tf"
    ps = f"InterTabular-{style}"
    for rec in font["name"].names:
        text = rec.toUnicode()
        if rec.nameID in (1, 16):
            rec.string = FAMILY if rec.nameID == 16 or style in ("Regular", "Bold") else f"{FAMILY} {style}"
        elif rec.nameID == 4:
            rec.string = f"{FAMILY} {style}"
        elif rec.nameID == 6:
            rec.string = ps
        elif rec.nameID == 3:
            rec.string = f"{ps};derived-from-Inter"
        elif rec.nameID in (7, 8, 9, 11, 12, 13, 14):
            continue
        elif "Inter" in text and rec.nameID in (2, 17):
            continue
    font["name"].names = [n for n in font["name"].names if n.nameID not in (21, 22)]  # drop WWS names that still say "Inter"
    font.save(dst)


if __name__ == "__main__":
    src_dir = Path(sys.argv[1])
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(__file__).resolve().parents[1] / "assets" / "fonts"
    out.mkdir(parents=True, exist_ok=True)
    for style in STYLES:
        convert(src_dir / f"Inter-{style}.ttf", out / f"InterTabular-{style}.ttf", style)
        print("wrote", out / f"InterTabular-{style}.ttf")
