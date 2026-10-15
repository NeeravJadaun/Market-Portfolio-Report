"""Palette, fonts and number formats shared by every output."""
from __future__ import annotations

from matplotlib import font_manager

from .config import FONT_DIR

CANVAS, SURFACE, TEXT, MUTED, BORDER = "#F8FAFC", "#FFFFFF", "#0F172A", "#475569", "#E2E8F0"
NAVY, BLUE = "#15324F", "#1D4ED8"
GRID = "#E2E8F0"
FONT = "Inter Tabular"
FONT_FILES = {"Regular": "InterTabular-Regular.ttf", "Medium": "InterTabular-Medium.ttf",
              "SemiBold": "InterTabular-SemiBold.ttf", "Bold": "InterTabular-Bold.ttf"}
MINUS = "\u2212"
NBSP = "\u00a0"
LABEL = "Independent educational research sample"
HYPO = "Hypothetical portfolio"


def register_matplotlib_fonts() -> None:
    for f in FONT_FILES.values():
        font_manager.fontManager.addfont(str(FONT_DIR / f))


def register_reportlab_fonts() -> None:
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.lib.fonts import addMapping

    for style, f in FONT_FILES.items():
        pdfmetrics.registerFont(TTFont(f"Inter-{style}", str(FONT_DIR / f)))
    addMapping("Inter", 0, 0, "Inter-Regular")
    addMapping("Inter", 1, 0, "Inter-Bold")
    addMapping("Inter", 0, 1, "Inter-Regular")
    addMapping("Inter", 1, 1, "Inter-Bold")


# ---- number formats: one definition for text, charts, tables, deck -------------------------------
def pct(x: float, dp: int = 2, sign: bool = True) -> str:
    s = f"{abs(x) * 100:.{dp}f}%"
    if round(x * 100, dp) == 0:
        return f"{0:.{dp}f}%"
    return (MINUS if x < 0 else ("+" if sign else "")) + s


def pp(x: float, dp: int = 2) -> str:
    """Percentage points; x is a fraction (0.0013 -> +0.13 pp)."""
    v = round(x * 100, dp)
    return (f"{0:.{dp}f}{NBSP}pp" if v == 0 else (MINUS if v < 0 else "+") + f"{abs(v):.{dp}f}{NBSP}pp")


def wt(x: float, dp: int = 1) -> str:
    return f"{x * 100:.{dp}f}%"


def bp(x: float) -> str:
    v = round(x)
    return f"0{NBSP}bp" if v == 0 else (MINUS if v < 0 else "+") + f"{abs(v):.0f}{NBSP}bp"


def money(x: float, dp: int = 0) -> str:
    return f"C${x:,.{dp}f}"


def num(x: float, dp: int) -> str:
    return f"{x:.{dp}f}"
