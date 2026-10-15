"""Two-page research PDF (ReportLab). Fonts are embedded as TrueType subsets."""
from __future__ import annotations

import re
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import BaseDocTemplate, Frame, Image, PageBreak, PageTemplate, Paragraph, Spacer, Table, TableStyle

from . import theme as T
from .calc import Results
from .charts import CONTRIB_SIZE, PERF_SIZE
from .narrative import load_text, retrieval_dates, source_list

T.register_reportlab_fonts()
C = {k: colors.HexColor(v) for k, v in dict(canvas=T.CANVAS, surface=T.SURFACE, text=T.TEXT, muted=T.MUTED, border=T.BORDER, navy=T.NAVY, blue=T.BLUE).items()}
PAGE_W, PAGE_H = letter
MX, TOP, BOT = 36, 52, 48
W = PAGE_W - 2 * MX


def mk_table(data, **kw) -> Table:
    """Table whose default font is the embedded one (ReportLab otherwise references unembedded Helvetica)."""
    tb = Table(data, **kw)
    tb.setStyle(TableStyle([("FONTNAME", (0, 0), (-1, -1), "Inter-Regular")]))
    return tb


def S(name, **kw) -> ParagraphStyle:
    base = dict(fontName="Inter-Regular", fontSize=10.5, leading=13.6, textColor=C["text"], alignment=TA_LEFT, bulletFontName="Inter-Regular", bulletFontSize=10.5)
    return ParagraphStyle(name, **(base | kw))


ST = {
    "title": S("title", fontName="Inter-Bold", fontSize=21, leading=25, textColor=C["navy"]),
    "sub": S("sub", fontSize=10.5, leading=13.6, textColor=C["muted"]),
    "h2": S("h2", fontName="Inter-SemiBold", fontSize=11.5, leading=14, textColor=C["navy"], spaceBefore=5, spaceAfter=1.5),
    "headline": S("headline", fontName="Inter-SemiBold", fontSize=12.5, leading=16, textColor=C["navy"], spaceAfter=3),
    "body": S("body"),
    "bullet": S("bullet", leftIndent=11, bulletIndent=0, spaceAfter=1.5),
    "small": S("small", fontSize=9, leading=11.4, textColor=C["muted"]),
    "src": S("src", fontSize=9, leading=11.2, textColor=C["text"], spaceAfter=1.6),
    "cell": S("cell", fontSize=9.5, leading=11.5),
    "cellr": S("cellr", fontSize=9.5, leading=11.5, alignment=2),
    "kpi_v": S("kpi_v", fontName="Inter-Bold", fontSize=16, leading=19, textColor=C["navy"]),
    "kpi_l": S("kpi_l", fontSize=9, leading=11, textColor=C["muted"]),
}


def md(text: str) -> str:
    """Escape, then restore [n] reference styling and <b> run-in labels."""
    t = escape(text)
    t = re.sub(r"((?:\[\d\])+)", lambda m: f'<font color="{T.BLUE}">{m.group(1)}</font>', t)
    return t


def P(text, style="body", **kw):
    return Paragraph(md(text) if not kw.get("raw") else text, ST[style])


def labelled(label: str, text: str, style="body"):
    return Paragraph(f'<font name="Inter-SemiBold" color="{T.NAVY}">{label}</font> {md(text)}', ST[style])


def tbl(rows, widths, header=True, bold_rows=(), shade_rows=(), align_right_from=1, line_above=()):
    data = []
    for i, row in enumerate(rows):
        out = []
        for j, cell in enumerate(row):
            if isinstance(cell, str):
                st = ParagraphStyle("c", parent=ST["cellr" if j >= align_right_from else "cell"],
                                    fontName="Inter-SemiBold" if (i == 0 and header) or i in bold_rows else "Inter-Regular",
                                    textColor=C["muted"] if (i == 0 and header) else C["text"])
                out.append(Paragraph(escape(cell), st))
            else:
                out.append(cell)
        data.append(out)
    t = mk_table(data, colWidths=widths, repeatRows=0)
    cmds = [("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 1.4), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.4),
            ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
            ("LINEBELOW", (0, 0), (-1, -1), 0.5, C["border"]), ("LINEABOVE", (0, 0), (-1, 0), 0.9, C["navy"])]
    if header:
        cmds.append(("LINEBELOW", (0, 0), (-1, 0), 0.9, C["navy"]))
    for i in shade_rows:
        cmds.append(("BACKGROUND", (0, i), (-1, i), C["canvas"]))
    for i in line_above:
        cmds.append(("LINEABOVE", (0, i), (-1, i), 0.9, C["navy"]))
    t.setStyle(TableStyle(cmds))
    return t


def kpi_strip(r: Results):
    c = r.classes
    cells = [(T.pct(r.port_return), "Hypothetical portfolio"), (T.pct(r.bench_return), f"Benchmark ({r.benchmark['ticker']})"),
             (T.pp(r.active_return), "Difference"), (T.pp(c.loc["Equity", "contrib"]), "Equity contribution"),
             (T.pp(c.loc["Fixed income", "contrib"]), "Bond contribution")]
    row = [[Paragraph(v, ST["kpi_v"]), Paragraph(escape(l), ST["kpi_l"])] for v, l in cells]
    t = mk_table([[ [p[0], p[1]] for p in row ]], colWidths=[W / 5] * 5)
    t.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.75, C["border"]), ("INNERGRID", (0, 0), (-1, -1), 0.5, C["border"]),
                           ("BACKGROUND", (0, 0), (-1, -1), C["surface"]), ("TOPPADDING", (0, 0), (-1, -1), 5),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 5), ("LEFTPADDING", (0, 0), (-1, -1), 8), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    return t


def overview_tables(r: Results):
    h = r.holdings
    seg = [["Segment (ETF proxy)", "Total", "Price"]]
    for t, row in h.iterrows():
        seg.append([f"{row['short']} ({t})", T.pct(row["total_ret"]), T.pct(row["price_ret"])])
    bt = r.benchmark["ticker"]
    seg.append([f"Benchmark ({bt})", T.pct(r.bench_return), T.pct(r.close[bt].iloc[-1] / r.close[bt].iloc[0] - 1)])
    rw = 272
    left = tbl(seg, [W - rw - 14 - 96, 48, 48], shade_rows=(len(seg) - 1,))
    rates = [["Rates, currency", f"{r.start:%b %-d}", f"{r.cutoff:%b %-d}", "Change", "As of"]]
    names = {"FXUSDCAD": "USD/CAD", "BD.CDN.2YR.DQ.YLD": "Canada 2-yr (%)", "BD.CDN.10YR.DQ.YLD": "Canada 10-yr (%)", "V39079": "BoC overnight (%)"}
    for sid, row in r.macro.iterrows():
        chg = T.pct(row["change"]) if row["kind"] == "level" else T.bp(row["change"])
        rates.append([names[sid], f"{row['start_value']:.{row['dp']}f}", f"{row['end_value']:.{row['dp']}f}", chg, f"{row['end_obs']:%b %-d}"])
    right = tbl(rates, [96, 42, 42, 50, 42])
    outer = mk_table([[left, right]], colWidths=[W - rw, rw])
    outer.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (0, 0), 14), ("RIGHTPADDING", (1, 0), (1, 0), 0), ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
    return outer


def holdings_table(r: Results):
    h, c = r.holdings, r.classes
    rows = [["Holding", "Start weight", "Price return", "Total return", "Contribution", "End weight", "Drift"]]
    dash = "—"
    for t, x in h.iterrows():
        rows.append([f"{t}  {x['short']}", T.wt(x["begin_w"]), T.pct(x["price_ret"]), T.pct(x["total_ret"]), T.pp(x["contrib"]), T.wt(x["end_w"]), T.pp(x["drift"])])
    for k, lab in (("Equity", "Equity sleeve"), ("Fixed income", "Fixed-income sleeve")):
        rows.append([lab, T.wt(c.loc[k, "begin_w"]), dash, T.pct(c.loc[k, "sleeve_return"]), T.pp(c.loc[k, "contrib"]), T.wt(c.loc[k, "end_w"]), T.pp(c.loc[k, "drift"])])
    rows.append(["Hypothetical portfolio", T.wt(h["begin_w"].sum()), dash, T.pct(r.port_return), T.pp(h["contrib"].sum()), T.wt(h["end_w"].sum()), dash])
    bt = r.benchmark["ticker"]
    rows.append([f"Benchmark ({bt})", dash, T.pct(r.close[bt].iloc[-1] / r.close[bt].iloc[0] - 1), T.pct(r.bench_return), dash, dash, dash])
    n = len(h)
    return tbl(rows, [W - 6 * 63 - 4, 63, 63, 63, 66, 60, 63 + 4 - 0], bold_rows=(n + 1, n + 2, n + 3), shade_rows=(n + 1, n + 2), line_above=(n + 3,))


def wrap_url(url: str, width: int = 42) -> str:
    """Break URLs after slashes so none splits mid-word; several URLs (separated by ' ; ') go on separate lines."""
    lines: list[str] = []
    for one in url.split(" ; "):
        cur = ""
        parts = one.split("/")
        for i, seg in enumerate(parts):
            piece = seg + ("/" if i < len(parts) - 1 else "")
            if cur and len(cur) + len(piece) > width:
                lines.append(cur)
                cur = ""
            cur += piece
        lines.append(cur)
    return "<br/>".join(escape(x.strip()) for x in lines if x.strip())


def src_block(r: Results):
    out = []
    for s in source_list(r):
        url = s["url"].split(" ;")[0]
        shown = wrap_url(s["url"])
        link = f'<link href="https://{url}" color="{T.BLUE}">{shown}</link>' if s["id"] != "funds" else shown
        out.append(Paragraph(f'<font color="{T.BLUE}">[{s["n"]}]</font> {escape(s["publisher"])}, {escape(s["title"])}{", " + escape(s["date"]) if s["date"] else ""}. {link}', ST["src"]))
    half = (len(out) + 1) // 2
    tb = mk_table([[out[:half], out[half:]]], colWidths=[W / 2, W / 2])
    tb.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (0, 0), 10),
                            ("RIGHTPADDING", (1, 0), (1, 0), 0), ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
    return [tb]


def bullets(items):
    return [Paragraph(md(i), ST["bullet"], bulletText="•") for i in items]


def monitor_block(items):
    return [Paragraph(f'<font name="Inter-SemiBold">{escape(a)}.</font> {md(b)}', ST["bullet"], bulletText="•") for a, b in items]


def page_decor(r: Results):
    def draw(canvas, doc):
        canvas.saveState()
        canvas.setFont("Inter-SemiBold", 9)
        canvas.setFillColor(C["navy"])
        canvas.drawString(MX, PAGE_H - 34, T.LABEL.upper())
        canvas.setFont("Inter-Regular", 9)
        canvas.setFillColor(C["muted"])
        canvas.drawRightString(PAGE_W - MX, PAGE_H - 34, f"Market & Portfolio Report  |  {r.label}")
        canvas.setStrokeColor(C["border"])
        canvas.setLineWidth(0.75)
        canvas.line(MX, PAGE_H - 41, PAGE_W - MX, PAGE_H - 41)
        canvas.line(MX, 40, PAGE_W - MX, 40)
        canvas.setFont("Inter-Regular", 9)
        canvas.drawString(MX, 28, f"{T.HYPO}. Not investment advice. Returns are total returns in {r.currency}, before taxes and trading costs.")
        canvas.drawRightString(PAGE_W - MX, 28, f"Page {doc.page} of 2")
        canvas.restoreState()
    return draw


def build_pdf(r: Results, charts: dict[str, Path], out: Path) -> Path:
    txt = load_text(r)
    v = txt["_values"]
    doc = BaseDocTemplate(str(out), pagesize=letter, leftMargin=MX, rightMargin=MX, topMargin=TOP, bottomMargin=BOT,
                          title=f"Market & Portfolio Report, {r.label}", author=T.LABEL, initialFontName="Inter-Regular", initialFontSize=10.5, initialLeading=13.6,
                          subject="Hypothetical portfolio versus benchmark; independent educational research sample", creator="mpr")
    frame = Frame(MX, BOT, W, PAGE_H - TOP - BOT, leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0, id="body")
    doc.addPageTemplates([PageTemplate(id="p", frames=[frame], onPage=page_decor(r))])
    perf_h = W * PERF_SIZE[1] / PERF_SIZE[0]
    pr = txt["_refs"]["prices"]
    s: list = []
    # ---- page 1
    s += [P(f"{r.label} Market & Portfolio Report", "title"),
          P(f"As of the {r.cutoff:%B %-d, %Y} close  |  {r.currency}  |  {T.HYPO} (60/40) vs {r.benchmark['ticker']} benchmark", "sub"),
          Spacer(1, 6), kpi_strip(r), Spacer(1, 5),
          Image(str(charts["performance"]), width=W, height=perf_h),
          P(f"Cumulative total return since the {r.start:%b %-d} close, daily. Source: [{pr}]. Facts are cited; interpretation is labelled.", "small"),
          Spacer(1, 3), Paragraph(md(txt["headline"]), ST["headline"]),
          labelled("Facts.", txt["takeaway_fact"]), Spacer(1, 2), labelled("Interpretation.", txt["takeaway_view"]),
          P("Market overview", "h2"), overview_tables(r), Spacer(1, 2), P(txt["overview_note"], "small"),
          P(txt["theme_title"], "h2")]
    s += bullets(txt["theme_evidence"])
    s += [Spacer(1, 1), labelled("Interpretation.", txt["theme_view"]), PageBreak()]
    # ---- page 2
    cw = CONTRIB_SIZE[0] * 72
    left = [Image(str(charts["contributions"]), width=cw, height=cw * CONTRIB_SIZE[1] / CONTRIB_SIZE[0]),
]
    right = [P("Equity implications", "h2"), P(txt["equity_view"]), P("Fixed-income implications", "h2"), P(txt["fi_view"])]
    two = mk_table([[left, right]], colWidths=[cw + 14, W - cw - 14])
    two.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (0, 0), 14), ("RIGHTPADDING", (1, 0), (1, 0), 0), ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
    colw = (W - 18) / 2
    lcol = [P("Maintain or rebalance (illustrative)", "h2"), P(txt["rebalance"]), Spacer(1, 3), labelled("Counterargument.", txt["counter"])]
    rcol = [P("Downside risks", "h2")] + bullets(txt["risks"]) + [P("What to monitor", "h2")] + monitor_block(txt["monitor"])
    grid = mk_table([[lcol, rcol]], colWidths=[colw + 18, colw])
    grid.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (0, 0), 18), ("RIGHTPADDING", (1, 0), (1, 0), 0), ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
    rd = ", ".join(retrieval_dates(r))
    br = txt["_refs"]
    boc_n = next(v for k, v in br.items() if k.startswith("boc_20"))
    fed_n = next(v for k, v in br.items() if k.startswith("fed_20"))
    s += [P("Portfolio and benchmark detail", "h2"), holdings_table(r), Spacer(1, 2),
          P(f"Start weights: {r.decision['carry_note']} Price return excludes distributions. [{pr}]", "small"),
          Spacer(1, 2), two, grid,
          P("Method and sources", "h2"), P(txt["methodology"] + f" Sources retrieved {rd}; [{boc_n}] and [{fed_n}] were published before the cutoff.", "small"), Spacer(1, 2)] + src_block(r)
    doc.build(s)
    return out
