"""Matplotlib figures. One drawing function per chart; PDF and deck call it with different sizes."""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402

from . import theme as T  # noqa: E402
from .calc import Results  # noqa: E402

T.register_matplotlib_fonts()


def _style(fs: float) -> None:
    plt.rcParams.update({
        "font.family": T.FONT, "font.size": fs, "axes.edgecolor": T.BORDER, "axes.labelcolor": T.MUTED,
        "xtick.color": T.MUTED, "ytick.color": T.MUTED, "text.color": T.TEXT, "axes.titleweight": "bold",
        "axes.spines.top": False, "axes.spines.right": False, "axes.unicode_minus": True,
        "figure.facecolor": T.SURFACE, "axes.facecolor": T.SURFACE, "savefig.facecolor": T.SURFACE,
    })


def _fmt_pct(v, _pos=None):
    return T.pct(v, 1)


PERF_SIZE, CONTRIB_SIZE = (7.5, 2.05), (3.35, 1.9)


def performance_chart(r: Results, path: Path, size=PERF_SIZE, fs: float = 8.5, dpi: int = 300) -> Path:
    """Cumulative total return since the prior month-end: portfolio navy solid, benchmark slate dashed."""
    _style(fs)
    fig, ax = plt.subplots(figsize=size)
    d = r.daily
    ax.axhline(0, color=T.MUTED, lw=0.8, zorder=1)
    ax.plot(d.index, d["portfolio"], color=T.NAVY, lw=2.2, ls="-", label="Hypothetical portfolio", zorder=3)
    ax.plot(d.index, d["benchmark"], color=T.MUTED, lw=1.8, ls=(0, (5, 3)), label=f"Benchmark ({r.benchmark['ticker']})", zorder=2)
    ax.grid(axis="y", color=T.GRID, lw=0.7)
    ax.set_axisbelow(True)
    ax.yaxis.set_major_formatter(FuncFormatter(_fmt_pct))
    ax.xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=mdates.MO))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %-d"))
    ax.set_xticks([x for x in ax.get_xticks() if x <= mdates.date2num(d.index[-1])])
    ax.set_xlim(d.index[0], d.index[-1] + (d.index[-1] - d.index[0]) * 0.17)
    ax.set_ylabel("Cumulative total return, CAD")
    ax.set_xlabel(f"Trading days, {r.start:%b %-d} close to {r.cutoff:%b %-d} close, {r.cutoff:%Y}")
    lo, hi_v = min(0.0, d[["portfolio", "benchmark"]].min().min()), d[["portfolio", "benchmark"]].max().max()
    rng = (hi_v - lo) or 0.01
    ax.set_ylim(lo - rng * 0.06, hi_v + rng * 0.30)
    yr = ax.get_ylim()[1] - ax.get_ylim()[0]
    last = d.iloc[-1]
    hi, lw = ("portfolio", "benchmark") if last["portfolio"] >= last["benchmark"] else ("benchmark", "portfolio")
    gap = 0.15 * yr
    ypos = {hi: last[hi], lw: last[lw]}
    if ypos[hi] - ypos[lw] < gap:
        mid = (ypos[hi] + ypos[lw]) / 2
        ypos = {hi: mid + gap / 2, lw: mid - gap / 2}
    for key, col, lab in (("portfolio", T.NAVY, "Portfolio"), ("benchmark", T.MUTED, "Benchmark")):
        ax.annotate(f"{lab} {T.pct(last[key])}", (d.index[-1], last[key]), xytext=(d.index[-1] + (d.index[-1] - d.index[0]) * 0.02, ypos[key]),
                    color=col, fontweight="bold", va="center", ha="left", fontsize=fs)
    ax.legend(loc="upper left", frameon=False, ncol=2, handlelength=2.6, borderaxespad=0.2)
    fig.tight_layout(pad=0.4)
    fig.savefig(path, dpi=dpi)
    plt.close(fig)
    return path


def contribution_chart(r: Results, path: Path, size=CONTRIB_SIZE, fs: float = 8.5, dpi: int = 300) -> Path:
    """Horizontal contribution bars (weight x return, pp) in holdings order, zero baseline, values labelled."""
    _style(fs)
    h = r.holdings
    fig, ax = plt.subplots(figsize=size)
    rows, y = [], 0  # (y, ticker or None, group label)
    for grp, color in (("Equity", T.NAVY), ("Fixed income", T.BLUE)):
        rows.append((y, None, grp, color))
        y += 1
        for t in h.index[h["asset_class"] == grp]:
            rows.append((y, t, grp, color))
            y += 1
    top = y - 1
    vals = [h.loc[t, "contrib"] * 100 for _, t, _, _ in rows if t]
    span = max(abs(v) for v in vals) or 0.1
    ax.axvline(0, color=T.TEXT, lw=0.9, zorder=4)
    ticks, labels = [], []
    for yy, tk, grp, color in rows:
        ypos = top - yy
        ticks.append(ypos)
        if tk is None:
            labels.append(grp)
            continue
        v = h.loc[tk, "contrib"] * 100
        ax.barh(ypos, v, color=color, height=0.62, zorder=3)
        ax.text(v + (span * 0.06 if v >= 0 else -span * 0.06), ypos, T.pp(v / 100).replace(T.NBSP + "pp", ""), va="center",
                ha="left" if v >= 0 else "right", fontsize=fs, color=T.TEXT)
        labels.append(tk)
    ax.set_yticks(ticks)
    ax.set_yticklabels(labels)
    for lab, (yy, tk, grp, color) in zip(ax.get_yticklabels(), rows):
        lab.set_fontweight("bold")
        lab.set_color(color if tk is None else T.MUTED)
    ax.set_ylim(-0.6, top + 0.6)
    ax.grid(axis="x", color=T.GRID, lw=0.7)
    ax.set_axisbelow(True)
    ax.set_xlim(-span * 1.6 if min(vals) < 0 else -span * 0.15, span * 1.6)
    ax.set_xlabel("Contribution to portfolio return, pp (CAD)")
    ax.spines["left"].set_visible(False)
    ax.tick_params(axis="y", length=0)
    fig.tight_layout(pad=0.4)
    fig.savefig(path, dpi=dpi)
    plt.close(fig)
    return path


def build_charts(r: Results, out_dir: Path) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    return {
        "performance": performance_chart(r, out_dir / "performance.png"),
        "contributions": contribution_chart(r, out_dir / "contributions.png"),
        "performance_slide": performance_chart(r, out_dir / "performance_slide.png", size=(7.6, 4.3), fs=13),
        "contributions_slide": contribution_chart(r, out_dir / "contributions_slide.png", size=(6.0, 4.3), fs=13),
    }
