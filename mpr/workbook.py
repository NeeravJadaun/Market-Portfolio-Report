"""Excel workbook. Inputs are blue; calculations are live formulas with cached values from the shared results."""
from __future__ import annotations

from pathlib import Path

import xlsxwriter
from xlsxwriter.utility import xl_col_to_name as colname, xl_rowcol_to_cell as cell

from . import theme as T
from .calc import Results
from .data import load_manifest
from .narrative import load_text, source_list

FN = T.FONT
PCT, PCT1, PP, NUM4, NUM2, MONEY = "+0.00%;-0.00%;0.00%", "0.0%", '+0.00" pp";-0.00" pp";0.00" pp"', "0.0000", "0.00", "#,##0"
RET = "+0.00%;-0.00%;0.00%"


def build_workbook(r: Results, out: Path) -> Path:
    txt = load_text(r)
    wb = xlsxwriter.Workbook(str(out))
    wb.set_properties({"title": f"Market & Portfolio Report workbook, {r.label}", "subject": T.LABEL, "author": T.LABEL,
                       "comments": f"{T.HYPO}. Not investment advice."})
    base = {"font_name": FN, "font_size": 10, "font_color": T.TEXT, "valign": "vcenter"}

    def F(**kw):
        return wb.add_format(base | kw)

    f = {
        "title": F(bold=True, font_size=16, font_color=T.NAVY), "sub": F(font_color=T.MUTED), "label": F(font_color=T.NAVY, bold=True),
        "hdr": F(bold=True, font_color="#FFFFFF", bg_color=T.NAVY, text_wrap=True, align="center", border=1, border_color=T.NAVY),
        "hdrl": F(bold=True, font_color="#FFFFFF", bg_color=T.NAVY, text_wrap=True, align="left", border=1, border_color=T.NAVY),
        "txt": F(bottom=1, bottom_color=T.BORDER), "wrap": F(text_wrap=True, valign="top", bottom=1, bottom_color=T.BORDER),
        "bold": F(bold=True, bottom=1, bottom_color=T.BORDER, bg_color=T.CANVAS),
        "date": F(num_format="yyyy-mm-dd", align="left", bottom=1, bottom_color=T.BORDER),
        "note": F(font_color=T.MUTED, italic=True, text_wrap=True, valign="top"),
        "ok": F(bold=True, font_color=T.NAVY, bottom=1, bottom_color=T.BORDER),
    }

    def num(fmt, inp=False, bold=False):
        return F(num_format=fmt, align="right", bottom=1, bottom_color=T.BORDER, font_color=T.BLUE if inp else T.TEXT,
                 bold=bold, bg_color=T.CANVAS if bold else T.SURFACE)

    def sheet(name, widths, tab=None):
        ws = wb.add_worksheet(name)
        ws.hide_gridlines(2)
        for i, w in enumerate(widths):
            ws.set_column(i, i, w)
        ws.set_tab_color(tab or T.NAVY)
        ws.set_landscape()
        ws.set_paper(1)
        if name != "Returns":
            ws.fit_to_pages(1, 0)
        return ws

    n = len(r.close)
    tick = list(r.holdings.index)
    bt = r.benchmark["ticker"]
    allt = tick + [bt]
    h = r.holdings
    nh = len(tick)

    ws_ov = sheet("Overview", [36, 20, 20, 20, 22, 22, 20, 4])
    ws_h = sheet("Holdings", [9, 52, 13, 42, 9, 11, 11, 13, 11, 13, 11, 12, 12, 52])
    ws_r = sheet("Returns", [44, 13, 13, 15, 13, 13, 3, 3, 3, 3, 13] + [14] * (8 * 3 + 3))
    ws_c = sheet("Contributions", [24, 14, 13, 13, 15, 16, 13, 13])
    ws_a = sheet("Assumptions", [38, 18, 12, 90])
    ws_s = sheet("Sources", [6, 14, 30, 48, 62, 26, 12, 40, 18])

    # ---------------------------------------------------------------- Assumptions (inputs)
    ws = ws_a
    ws.write(0, 0, "Assumptions and inputs", f["title"])
    ws.write(1, 0, f"{T.LABEL}. {T.HYPO}. Blue cells are inputs; every other number in the workbook is calculated from them.", f["sub"])
    for j, hd in enumerate(["Parameter", "Value", "Unit", "Note"]):
        ws.write(3, j, hd, f["hdrl"])
    rows = [
        ("Edition", r.label, "", "Monthly edition; information cut off at the close of the as-of date."),
        ("Start date (prior month-end close)", r.start.to_pydatetime(), "date", "Beginning prices and weights."),
        ("As-of date (cutoff close)", r.cutoff.to_pydatetime(), "date", "Last observation used. Nothing after this date is used."),
        ("Currency", r.currency, "", "All ETF proxies are CAD-listed, so returns are already in CAD."),
        ("Starting portfolio value", r.start_value, "CAD", "Hypothetical. First edition starts at C$100,000; later editions carry the prior ending value."),
        ("Equity target weight", float(r.classes.loc["Equity", "target_w"]), "weight", "Strategic target."),
        ("Fixed-income target weight", None, "weight", "Equals 1 minus the equity target."),
        ("Asset-class drift band", 2.0, "pp", "Rebalance if any sleeve is further than this from target at month-end."),
        ("Holding drift band", 1.5, "pp", "Rebalance if any holding is further than this from target at month-end."),
        ("Transaction cost", float(r.decision["cost_bps"]), "bps", "One-way cost applied to an illustrative reset. Zero: month returns exclude trading costs."),
        ("Reconciliation tolerance", float(r.checks["tolerance"]), "fraction", "Maximum allowed gap between summed contributions and the daily portfolio path."),
    ]
    from .config import load_portfolio

    rb = load_portfolio()["rebalance"]
    rows[7] = ("Asset-class drift band", rb["class_band_pp"], "pp", rows[7][3])
    rows[8] = ("Holding drift band", rb["holding_band_pp"], "pp", rows[8][3])
    for i, (k, v, u, note) in enumerate(rows):
        rr = 4 + i
        ws.write(rr, 0, k, f["txt"])
        if k == "Fixed-income target weight":
            ws.write_formula(rr, 1, "=1-B10", num(PCT1), float(r.classes.loc["Fixed income", "target_w"]))
        elif isinstance(v, str):
            ws.write(rr, 1, v, F(font_color=T.BLUE, align="right", bottom=1, bottom_color=T.BORDER))
        elif u == "date":
            ws.write_datetime(rr, 1, v, F(num_format="yyyy-mm-dd", font_color=T.BLUE, align="right", bottom=1, bottom_color=T.BORDER))
        else:
            fm = {"weight": PCT1, "CAD": "#,##0.00", "pp": "0.0", "bps": "0.0", "fraction": "0.0E+00"}[u]
            ws.write(rr, 1, v, num(fm, inp=True))
        ws.write(rr, 2, u, f["txt"])
        ws.write(rr, 3, note, f["txt"])
    for nm, rr in (("Start_Value", 8), ("Eq_Target", 9), ("FI_Target", 10), ("Class_Band", 11), ("Hold_Band", 12), ("Cost_bps", 13), ("Tol", 14)):
        wb.define_name(nm, f"=Assumptions!$B${rr}")
    ws.write(16, 0, "Method notes", f["label"])
    notes = [
        ("Return definition", "Total return from daily closes with distributions reinvested at the ex-date close. Price return (no distributions) is shown beside it. No withholding or income tax."),
        ("Fees and costs", "ETF prices are net of each fund's management expenses. Trading costs and taxes are excluded; the transaction-cost input above only prices an illustrative reset."),
        ("Currency", "XUU, XEF and XEC are CAD-listed and unhedged, so foreign-currency moves are already in their CAD returns; XHY is CAD-hedged. Bank of Canada USD/CAD is a daily average rate and is used only for commentary."),
        ("ETF proxies", "Seven liquid iShares ETFs stand in for asset-class exposures. The benchmark is a different issuer's 60/40 balanced fund, VBAL, which also reports net of fees."),
        ("Weights and contributions", "Contribution = beginning weight x total return, in percentage points of portfolio return. It is a contribution table, not formal performance attribution."),
        ("Rebalancing convention", rb["convention"]),
        ("Data quality", "No missing or stale observation is filled. " + (" ".join(r.flags) if r.flags else "No stale series in this edition.")),
        ("Carry-forward", r.decision["carry_note"]),
    ]
    for i, (k, v) in enumerate(notes):
        ws.write(17 + i, 0, k, f["wrap"])
        ws.merge_range(17 + i, 1, 17 + i, 3, v, f["wrap"])
        ws.set_row(17 + i, 44)
    ws.freeze_panes(4, 1)
    ws.autofilter(3, 0, 3 + len(rows), 3)

    # ---------------------------------------------------------------- Returns (daily inputs + TRI formulas + monthly summary)
    ws = ws_r
    ws.write(0, 0, "Returns", f["title"])
    ws.write(1, 0, f"{T.LABEL}. Daily closes and ex-date distributions (blue) come from the saved snapshots; total-return indexes and returns are formulas.", f["sub"])
    D0 = 10                      # first column of daily table (K)
    cC, cD, cT = D0 + 1, D0 + 1 + 8, D0 + 1 + 16    # closes, distributions, TRI blocks
    cP, cB, cA = D0 + 1 + 24, D0 + 1 + 25, D0 + 1 + 26
    r0 = 4                        # first data row (0-based) -> Excel row 5
    rl = r0 + n - 1
    ws.write(3, D0, "Date", f["hdr"])
    for k, t in enumerate(allt):
        ws.write(3, cC + k, f"{t} close", f["hdr"])
        ws.write(3, cD + k, f"{t} distribution", f["hdr"])
        ws.write(3, cT + k, f"{t} total-return index", f["hdr"])
    ws.write(3, cP, "Portfolio cumulative return", f["hdr"])
    ws.write(3, cB, "Benchmark cumulative return", f["hdr"])
    ws.write(3, cA, "Active (portfolio - benchmark)", f["hdr"])
    ws.set_row(3, 44)
    hold_start = {t: f"Holdings!$G${5 + i}" for i, t in enumerate(tick)}
    for i, d in enumerate(r.close.index):
        rr = r0 + i
        ws.write_datetime(rr, D0, d.to_pydatetime(), f["date"])
        for k, t in enumerate(allt):
            ws.write(rr, cC + k, float(r.close.loc[d, t]), num("0.0000", inp=True))
            ws.write(rr, cD + k, float(r.dist.loc[d, t]), num("0.0000", inp=True))
            if i == 0:
                ws.write(rr, cT + k, 1.0, num("0.000000"))
            else:
                ccell, dcell, pcell, tprev = cell(rr, cC + k), cell(rr, cD + k), cell(rr - 1, cC + k), cell(rr - 1, cT + k)
                ws.write_formula(rr, cT + k, f"={tprev}*({ccell}+{dcell})/{pcell}", num("0.000000"), float(r.tri.loc[d, t]))
        terms = "+".join(f"{hold_start[t]}*{cell(rr, cT + k)}" for k, t in enumerate(tick))
        ws.write_formula(rr, cP, f"={terms}-1", num(RET), float(r.daily.loc[d, "portfolio"]))
        ws.write_formula(rr, cB, f"={cell(rr, cT + nh)}-1", num(RET), float(r.daily.loc[d, "benchmark"]))
        ws.write_formula(rr, cA, f"={cell(rr, cP)}-{cell(rr, cB)}", num(RET), float(r.daily.loc[d, "active"]))
    ws.autofilter(3, D0, rl, cA)
    for j, hd in enumerate(["Series", "Start close", "End close", "Distributions in month", "Price return", "Total return"]):
        ws.write(3, j, hd, f["hdrl"] if j == 0 else f["hdr"])
    for k, t in enumerate(allt):
        rr = 4 + k
        ws.write(rr, 0, f"{t}  {h.loc[t, 'short']}" if t in tick else f"{t}  benchmark", f["txt"])
        c0, c1 = cell(r0, cC + k), cell(rl, cC + k)
        px0, px1 = float(r.close.iloc[0][t]), float(r.close.iloc[-1][t])
        ws.write_formula(rr, 1, f"={c0}", num("0.0000"), px0)
        ws.write_formula(rr, 2, f"={c1}", num("0.0000"), px1)
        ws.write_formula(rr, 3, f"=SUM({cell(r0, cD + k)}:{cell(rl, cD + k)})", num("0.0000"), float(r.dist[t].sum()))
        ws.write_formula(rr, 4, f"=C{rr + 1}/B{rr + 1}-1", num(RET), px1 / px0 - 1)
        ws.write_formula(rr, 5, f"={cell(rl, cT + k)}/{cell(r0, cT + k)}-1", num(RET), float(r.tri.iloc[-1][t] / r.tri.iloc[0][t] - 1))
    ws.write(4 + nh + 1, 0, "Hypothetical portfolio (sum of contributions)", f["bold"])
    for j in range(1, 5):
        ws.write(4 + nh + 1, j, "", f["bold"])
    ws.write_formula(4 + nh + 1, 5, "=Contributions!E14/100", num(RET, bold=True), r.port_return)
    ws.write(4 + nh + 2, 0, "Active return, portfolio minus benchmark (pp)", f["bold"])
    for j in range(1, 5):
        ws.write(4 + nh + 2, j, "", f["bold"])
    ws.write_formula(4 + nh + 2, 5, f"=(F{4 + nh + 2}-F{4 + nh + 1})*100", num(PP, bold=True), r.active_return * 100)
    ws.merge_range(4 + nh + 4, 0, 4 + nh + 4, 5, "Chart-ready: the daily table at right (Date, Portfolio and Benchmark cumulative return) feeds the Overview line chart. "
                   "Distributions are zero on the start date because they belong to the prior edition.", f["note"])
    ws.set_row(4 + nh + 4, 44)
    ws.freeze_panes(4, 1)

    # ---------------------------------------------------------------- Holdings
    ws = ws_h
    ws.write(0, 0, "Holdings and weights", f["title"])
    ws.write(1, 0, f"{T.LABEL}. {T.HYPO}. Blue = input weights; returns link to the Returns sheet.", f["sub"])
    hdrs = ["Ticker", "Fund", "Asset class", "Exposure", "Currency", "Target weight", "Start weight", "Start value (CAD)", "Total return",
            "End value (CAD)", "End weight", "Drift vs target", "Trade to target if reset", "Rationale"]
    for j, hd in enumerate(hdrs):
        ws.write(3, j, hd, f["hdrl"] if j in (0, 1, 2, 3, 13) else f["hdr"])
    ws.set_row(3, 32)
    for i, t in enumerate(tick):
        rr, x = 4 + i, h.loc[t]
        er = rr + 1
        ws.write(rr, 0, t, f["txt"]); ws.write(rr, 1, x["name"], f["txt"]); ws.write(rr, 2, x["asset_class"], f["txt"])
        ws.write(rr, 3, x["exposure"], f["txt"]); ws.write(rr, 4, "CAD", f["txt"])
        ws.write(rr, 5, float(x["target_w"]), num(PCT1, inp=True)); ws.write(rr, 6, float(x["begin_w"]), num(PCT1, inp=True))
        ws.write_formula(rr, 7, f"=Start_Value*G{er}", num(MONEY), r.start_value * x["begin_w"])
        ws.write_formula(rr, 8, f"=Returns!F{5 + i}", num(RET), float(x["total_ret"]))
        ws.write_formula(rr, 9, f"=H{er}*(1+I{er})", num(MONEY), r.start_value * x["begin_w"] * (1 + x["total_ret"]))
        ws.write_formula(rr, 10, f"=J{er}/J$14", num(PCT1), float(x["end_w"]))
        ws.write_formula(rr, 11, f"=(K{er}-F{er})*100", num(PP), float(x["drift"] * 100))
        ws.write_formula(rr, 12, f"=(F{er}-K{er})*100", num(PP), float(-x["drift"] * 100))
        ws.write(rr, 13, x["rationale"], f["wrap"])
        ws.set_row(rr, 30)
    c = r.classes
    for k, (key, lab) in enumerate((("Equity", "Equity sleeve"), ("Fixed income", "Fixed-income sleeve"))):
        rr = 11 + k
        er = rr + 1
        ws.write(rr, 0, "", f["bold"]); ws.write(rr, 1, lab, f["bold"]); ws.write(rr, 2, key, f["bold"])
        for j in (3, 4, 13):
            ws.write(rr, j, "", f["bold"])
        for col, fld in ((5, "target_w"), (6, "begin_w")):
            L = colname(col)
            ws.write_formula(rr, col, f'=SUMIF($C$5:$C$11,$C{er},{L}$5:{L}$11)', num(PCT1, bold=True), float(c.loc[key, fld]))
        ws.write_formula(rr, 7, f'=SUMIF($C$5:$C$11,$C{er},H$5:H$11)', num(MONEY, bold=True), r.start_value * float(c.loc[key, "begin_w"]))
        endv = r.start_value * float(c.loc[key, "begin_w"] + c.loc[key, "contrib"])
        ws.write_formula(rr, 8, f"=J{er}/H{er}-1", num(RET, bold=True), float(c.loc[key, "sleeve_return"]))
        ws.write_formula(rr, 9, f'=SUMIF($C$5:$C$11,$C{er},J$5:J$11)', num(MONEY, bold=True), endv)
        ws.write_formula(rr, 10, f'=SUMIF($C$5:$C$11,$C{er},K$5:K$11)', num(PCT1, bold=True), float(c.loc[key, "end_w"]))
        ws.write_formula(rr, 11, f"=(K{er}-F{er})*100", num(PP, bold=True), float(c.loc[key, "drift"] * 100))
        ws.write(rr, 12, "", f["bold"])
    ws.write(13, 0, "", f["bold"]); ws.write(13, 1, "Hypothetical portfolio", f["bold"]); ws.write(13, 2, "", f["bold"]); ws.write(13, 3, "", f["bold"]); ws.write(13, 4, "", f["bold"]); ws.write(13, 13, "", f["bold"])
    ws.write_formula(13, 5, "=SUM(F5:F11)", num(PCT1, bold=True), 1.0)
    ws.write_formula(13, 6, "=SUM(G5:G11)", num(PCT1, bold=True), float(h["begin_w"].sum()))
    ws.write_formula(13, 7, "=SUM(H5:H11)", num(MONEY, bold=True), r.start_value)
    ws.write_formula(13, 8, "=J14/H14-1", num(RET, bold=True), r.port_return)
    ws.write_formula(13, 9, "=SUM(J5:J11)", num(MONEY, bold=True), r.end_value)
    ws.write_formula(13, 10, "=SUM(K5:K11)", num(PCT1, bold=True), 1.0)
    ws.write(13, 11, "", f["bold"]); ws.write(13, 12, "", f["bold"])
    ws.write(14, 1, "Check: target, start and end weights each sum to 100%", f["txt"])
    ws.write_formula(14, 2, '=IF(AND(ABS(F14-1)<=Tol,ABS(G14-1)<=Tol,ABS(K14-1)<=Tol),"OK","CHECK")', f["ok"], "OK")
    ws.write(16, 0, "Benchmark", f["label"])
    ws.write(17, 0, bt, f["txt"]); ws.write(17, 1, r.benchmark["name"], f["txt"]); ws.write(17, 2, "Balanced", f["txt"]); ws.write(17, 3, "60/40 global balanced fund of index ETFs (CAD)", f["txt"]); ws.write(17, 4, "CAD", f["txt"])
    ws.write_formula(17, 8, f"=Returns!F{5 + nh}", num(RET), r.bench_return)
    ws.write(17, 13, r.benchmark["rationale"], f["wrap"])
    ws.set_row(17, 78)
    ws.write(19, 0, "Month-end maintain or rebalance test (illustrative)", f["label"])
    d = r.decision
    ws.write(20, 1, "Largest sleeve drift (pp)", f["txt"])
    ws.write_formula(20, 2, "=MAX(ABS(L12),ABS(L13))", num("0.00"), d["max_class_drift_pp"])
    ws.write(21, 1, "Largest holding drift (pp)", f["txt"])
    ws.write_formula(21, 2, "=MAX(ABS(MIN(L5:L11)),MAX(L5:L11))", num("0.00"), d["max_holding_drift_pp"])
    ws.write(22, 1, "Decision", f["txt"])
    ws.write_formula(22, 2, '=IF(OR(C21>Class_Band,C22>Hold_Band),"Rebalance","Maintain")', f["ok"], d["action"])
    ws.write(23, 1, "One-way turnover if reset to target", f["txt"])
    ws.write_formula(23, 2, "=SUMPRODUCT(ABS(M5:M11))/2/100", num("0.00%"), d["one_way_turnover"])
    ws.write(24, 1, "Illustrative reset cost at assumed bps (CAD)", f["txt"])
    ws.write_formula(24, 2, "=J14*C24*Cost_bps/10000", num("#,##0.00"), r.end_value * d["one_way_turnover"] * d["cost_bps"] / 1e4)
    ws.freeze_panes(4, 1)
    ws.autofilter(3, 0, 10, 13)

    # ---------------------------------------------------------------- Contributions
    ws = ws_c
    ws.write(0, 0, "Contribution to return", f["title"])
    ws.write(1, 0, "Contribution = beginning weight x total return, in percentage points of portfolio return. Not formal performance attribution.", f["sub"])
    for j, hd in enumerate(["Ticker", "Asset class", "Start weight", "Total return", "Contribution (pp)", "Share of portfolio return (signed)", "End weight", "Drift vs target"]):
        ws.write(3, j, hd, f["hdrl"] if j < 2 else f["hdr"])
    ws.set_row(3, 32)
    tot_pp = float(h["contrib"].sum() * 100)
    for i, t in enumerate(tick):
        rr, er, x = 4 + i, 5 + i, h.loc[t]
        ws.write(rr, 0, t, f["txt"]); ws.write(rr, 1, x["asset_class"], f["txt"])
        ws.write_formula(rr, 2, f"=Holdings!G{er}", num(PCT1), float(x["begin_w"]))
        ws.write_formula(rr, 3, f"=Holdings!I{er}", num(RET), float(x["total_ret"]))
        ws.write_formula(rr, 4, f"=C{er}*D{er}*100", num(PP), float(x["contrib"] * 100))
        ws.write_formula(rr, 5, f"=E{er}/E$14", num("0.0%"), float(x["contrib"] / h["contrib"].sum()))
        ws.write_formula(rr, 6, f"=Holdings!K{er}", num(PCT1), float(x["end_w"]))
        ws.write_formula(rr, 7, f"=Holdings!L{er}", num(PP), float(x["drift"] * 100))
    for k, (key, lab) in enumerate((("Equity", "Equity sleeve"), ("Fixed income", "Fixed-income sleeve"))):
        rr = 11 + k
        er = rr + 1
        ws.write(rr, 0, lab, f["bold"]); ws.write(rr, 1, key, f["bold"])
        ws.write_formula(rr, 2, f"=SUMIF($B$5:$B$11,$B{er},C$5:C$11)", num(PCT1, bold=True), float(c.loc[key, "begin_w"]))
        ws.write_formula(rr, 3, f"=E{er}/100/C{er}", num(RET, bold=True), float(c.loc[key, "sleeve_return"]))
        ws.write_formula(rr, 4, f"=SUMIF($B$5:$B$11,$B{er},E$5:E$11)", num(PP, bold=True), float(c.loc[key, "contrib"] * 100))
        ws.write_formula(rr, 5, f"=E{er}/E$14", num("0.0%", bold=True), float(c.loc[key, "contrib"] / h["contrib"].sum()))
        ws.write_formula(rr, 6, f"=SUMIF($B$5:$B$11,$B{er},G$5:G$11)", num(PCT1, bold=True), float(c.loc[key, "end_w"]))
        ws.write_formula(rr, 7, f"=(G{er}-{('Eq_Target' if key == 'Equity' else 'FI_Target')})*100", num(PP, bold=True), float(c.loc[key, "drift"] * 100))
    ws.write(13, 0, "Hypothetical portfolio", f["bold"]); ws.write(13, 1, "", f["bold"])
    ws.write_formula(13, 2, "=SUM(C5:C11)", num(PCT1, bold=True), 1.0)
    ws.write_formula(13, 3, "=E14/100", num(RET, bold=True), r.port_return)
    ws.write_formula(13, 4, "=SUM(E5:E11)", num(PP, bold=True), tot_pp)
    ws.write_formula(13, 5, "=SUM(F5:F11)", num("0.0%", bold=True), 1.0)
    ws.write_formula(13, 6, "=SUM(G5:G11)", num(PCT1, bold=True), 1.0)
    ws.write(13, 7, "", f["bold"])
    last = cell(rl, cP)
    ws.write(16, 0, "Reconciliation", f["label"])
    rec = [("Sum of contributions", "=E14/100", r.port_return, RET), ("Portfolio return from daily path", f"=Returns!{last}", float(r.daily['portfolio'].iloc[-1]), RET),
           ("Absolute difference", "=ABS(B18-B19)", r.checks["contrib_vs_path_diff"], "0.0E+00"), ("Tolerance", "=Tol", r.checks["tolerance"], "0.0E+00")]
    for i, (k, fm, v, nf) in enumerate(rec):
        ws.write(17 + i, 0, k, f["txt"])
        ws.write_formula(17 + i, 1, fm, num(nf), v)
    ws.write(21, 0, "Status", f["txt"])
    ws.write_formula(21, 1, '=IF(B20<=B21,"OK","CHECK")', f["ok"], "OK" if r.checks["contrib_vs_path_diff"] <= r.checks["tolerance"] else "CHECK")
    ws.write(23, 0, "Allocation drift by sleeve", f["label"])
    for j, hd in enumerate(["Sleeve", "Target", "Start", "End", "Drift (pp)", "Band (pp)", "Within band"]):
        ws.write(24, j, hd, f["hdrl"] if j == 0 else f["hdr"])
    for k, (key, lab, tg) in enumerate((("Equity", "Equity", "Eq_Target"), ("Fixed income", "Fixed income", "FI_Target"))):
        rr, src = 25 + k, 11 + k + 1
        ws.write(rr, 0, lab, f["txt"])
        ws.write_formula(rr, 1, f"={tg}", num(PCT1), float(c.loc[key, "target_w"]))
        ws.write_formula(rr, 2, f"=C{src}", num(PCT1), float(c.loc[key, "begin_w"]))
        ws.write_formula(rr, 3, f"=G{src}", num(PCT1), float(c.loc[key, "end_w"]))
        ws.write_formula(rr, 4, f"=(D{rr + 1}-B{rr + 1})*100", num(PP), float(c.loc[key, "drift"] * 100))
        ws.write_formula(rr, 5, "=Class_Band", num("0.0"), 2.0)
        ws.write_formula(rr, 6, f'=IF(ABS(E{rr + 1})<=F{rr + 1},"Yes","No")', f["txt"], "Yes" if abs(c.loc[key, "drift"] * 100) <= 2.0 else "No")
    ws.write(29, 0, "Chart-ready: contribution by holding (pp), in holdings order", f["label"])
    for j, hd in enumerate(["Ticker", "Asset class", "Contribution (pp)"]):
        ws.write(30, j, hd, f["hdrl"] if j < 2 else f["hdr"])
    for i, t in enumerate(tick):
        ws.write_formula(31 + i, 0, f"=A{5 + i}", f["txt"], t)
        ws.write_formula(31 + i, 1, f"=B{5 + i}", f["txt"], h.loc[t, "asset_class"])
        ws.write_formula(31 + i, 2, f"=E{5 + i}", num(PP), float(h.loc[t, "contrib"] * 100))
    ws.freeze_panes(4, 1)
    ws.autofilter(3, 0, 10, 7)

    # ---------------------------------------------------------------- Overview
    ws = ws_ov
    ws.write(0, 0, f"Market & Portfolio Report workbook: {r.label}", f["title"])
    ws.write(1, 0, f"{T.LABEL}. {T.HYPO}. As of the {r.cutoff:%B %-d, %Y} close, {r.currency}. Not investment advice.", f["sub"])
    for j, hd in enumerate(["Portfolio return", f"Benchmark ({bt}) return", "Difference (pp)", "Equity contribution (pp)", "Bond contribution (pp)", "Month-end decision"]):
        ws.write(3, j, hd, f["hdr"])
    kp = [("=Holdings!I14", r.port_return, RET), (f"=Returns!F{5 + nh}", r.bench_return, RET), (f"=Returns!F{4 + nh + 3}", r.active_return * 100, PP),
          ("=Contributions!E12", float(c.loc["Equity", "contrib"] * 100), PP), ("=Contributions!E13", float(c.loc["Fixed income", "contrib"] * 100), PP)]
    for j, (fm, v, nf) in enumerate(kp):
        ws.write_formula(4, j, fm, num(nf, bold=True), v)
    ws.write_formula(4, 5, "=Holdings!C23", F(bold=True, align="right", bottom=1, bottom_color=T.BORDER, bg_color=T.CANVAS), d["action"])
    ws.set_row(3, 32)
    ws.merge_range(6, 0, 6, 5, txt["headline"], F(bold=True, font_size=12, font_color=T.NAVY, text_wrap=True))
    ws.set_row(6, 24)
    ws.write(8, 0, "Rates and currency (Bank of Canada)", f["label"])
    for j, hd in enumerate(["Series", f"{r.start:%b %-d}", f"{r.cutoff:%b %-d}", "Change", "Unit", "Latest observation"]):
        ws.write(9, j, hd, f["hdrl"] if j == 0 else f["hdr"])
    for i, (sid, row) in enumerate(r.macro.iterrows()):
        rr = 10 + i
        ws.write(rr, 0, row["label"], f["txt"])
        ws.write(rr, 1, row["start_value"], num("0." + "0" * row["dp"], inp=True))
        ws.write(rr, 2, row["end_value"], num("0." + "0" * row["dp"], inp=True))
        if row["kind"] == "level":
            ws.write_formula(rr, 3, f"=C{rr + 1}/B{rr + 1}-1", num(RET), float(row["change"]))
        else:
            ws.write_formula(rr, 3, f"=(C{rr + 1}-B{rr + 1})*100", num('+0" bp";-0" bp";0" bp"'), float(row["change"]))
        ws.write(rr, 4, row["unit"], F(align="center", bottom=1, bottom_color=T.BORDER))
        ws.write_datetime(rr, 5, row["end_obs"].to_pydatetime(), f["date"])
    ws.merge_range(15, 0, 15, 5, "Chart order: portfolio solid navy, benchmark dashed slate; contribution bars in holdings order. Tables behind the charts are on Returns and Contributions.", f["note"])
    ws.set_row(15, 30)
    ln = wb.add_chart({"type": "line"})
    cats = ["Returns", r0, D0, rl, D0]
    ln.add_series({"name": "Hypothetical portfolio", "categories": cats, "values": ["Returns", r0, cP, rl, cP], "line": {"color": T.NAVY, "width": 2.5}})
    ln.add_series({"name": f"Benchmark ({bt})", "categories": cats, "values": ["Returns", r0, cB, rl, cB], "line": {"color": T.MUTED, "width": 2.0, "dash_type": "dash"}})
    ln.set_title({"name": "Cumulative total return, CAD", "name_font": {"name": FN, "size": 11, "color": T.TEXT}})
    ln.set_x_axis({"date_axis": True, "major_unit": 7, "major_unit_type": "days", "label_position": "low", "num_format": "mmm d", "num_font": {"name": FN, "size": 9}, "name": "Trading days", "name_font": {"name": FN, "size": 9}, "major_gridlines": {"visible": False}})
    ln.set_y_axis({"num_format": "0.0%", "num_font": {"name": FN, "size": 9}, "name": "Cumulative return", "name_font": {"name": FN, "size": 9}, "major_gridlines": {"visible": True, "line": {"color": T.GRID}}, "crossing": 0})
    ln.set_legend({"position": "bottom", "font": {"name": FN, "size": 9}})
    ln.set_size({"width": 560, "height": 300})
    ws.insert_chart("A18", ln)
    bar = wb.add_chart({"type": "bar"})
    bar.add_series({"name": "Contribution (pp)", "categories": ["Contributions", 31, 0, 30 + nh, 0], "values": ["Contributions", 31, 2, 30 + nh, 2],
                    "points": [{"fill": {"color": T.NAVY if a == "Equity" else T.BLUE}} for a in h["asset_class"]],
                    "data_labels": {"value": True, "num_format": '+0.00;-0.00', "font": {"name": FN, "size": 9}}, "gap": 60})
    bar.set_title({"name": "Contribution to return, pp (equity navy, fixed income blue)", "name_font": {"name": FN, "size": 11, "color": T.TEXT}})
    bar.set_y_axis({"reverse": True, "num_font": {"name": FN, "size": 9}, "label_position": "low"})
    span = float(h["contrib"].abs().max() * 100)
    bar.set_x_axis({"min": -round(span * 1.8 + 0.05, 1), "max": round(span * 1.8 + 0.05, 1), "num_format": "0.00", "num_font": {"name": FN, "size": 9}, "major_gridlines": {"visible": True, "line": {"color": T.GRID}}, "name": "Percentage points", "name_font": {"name": FN, "size": 9}})
    bar.set_legend({"none": True})
    bar.set_size({"width": 470, "height": 300})
    ws.insert_chart("D18", bar, {"x_offset": 60})
    ws.freeze_panes(4, 0)
    ws.autofilter(9, 0, 9 + len(r.macro), 5)
    ws.activate()

    # ---------------------------------------------------------------- Sources
    ws = ws_s
    ws.write(0, 0, "Sources and snapshots", f["title"])
    ws.write(1, 0, "Every input comes from a saved public snapshot (data/snapshots). Observation or publication date and retrieval date are shown. Facts are cited by [ref] in the report.", f["sub"])
    hd = ["Ref", "Kind", "Publisher", "Title / series", "URL requested", "Observation or publication", "Retrieved", "Snapshot file", "SHA-256 (first 12)"]
    for j, x in enumerate(hd):
        ws.write(3, j, x, f["hdrl"])
    man = load_manifest(r.edition_id)
    refs = {s["id"]: s for s in source_list(r)}
    rr = 4
    for s in source_list(r):
        if s["id"] in ("prices", "boc_valet", "funds"):
            continue
        e = next(e for e in man["entries"] if e["id"] == f"doc:{s['id']}")
        ws.write(rr, 0, s["n"], f["txt"]); ws.write(rr, 1, "Document", f["txt"]); ws.write(rr, 2, s["publisher"], f["txt"]); ws.write(rr, 3, s["title"], f["txt"])
        ws.write_url(rr, 4, e["url"], F(font_color=T.BLUE, underline=1, bottom=1, bottom_color=T.BORDER), e["url"])
        ws.write(rr, 5, s["date"], f["txt"]); ws.write(rr, 6, e["retrieved_at"][:10], f["txt"]); ws.write(rr, 7, f"data/snapshots/{r.edition_id}/{e['file']}", f["txt"])
        ws.write(rr, 8, e["sha256_extract"][:12], f["txt"])
        rr += 1
    ref_of = {"prices": refs["prices"]["n"], "boc_valet": refs["boc_valet"]["n"], "funds": refs["funds"]["n"]}
    for e in man["entries"]:
        kind = e["kind"]
        if kind == "document" and e["id"].split(":")[1] in refs:
            continue
        if kind == "prices":
            sym = e["id"].split(":")[1]
            ref, pub, ttl, obs = ref_of["prices"], "Yahoo Finance (chart API)", f"{sym}: daily close and ex-dividend events", f"{r.start:%Y-%m-%d} to {r.cutoff:%Y-%m-%d}"
        elif kind == "macro":
            sid = e["id"].split(":")[1]
            ref, pub, ttl, obs = ref_of["boc_valet"], "Bank of Canada Valet API", f"Series {sid}", f"to {r.cutoff:%Y-%m-%d}"
        else:
            ref, pub, ttl, obs = ref_of["funds"], "Issuer fund page", e["id"].split(":")[1], "Undated; objective text"
        ws.write(rr, 0, ref, f["txt"]); ws.write(rr, 1, kind.capitalize(), f["txt"]); ws.write(rr, 2, pub, f["txt"]); ws.write(rr, 3, ttl, f["txt"])
        ws.write_url(rr, 4, e["url"], F(font_color=T.BLUE, underline=1, bottom=1, bottom_color=T.BORDER), e["url"][:200])
        ws.write(rr, 5, obs, f["txt"]); ws.write(rr, 6, e["retrieved_at"][:10], f["txt"]); ws.write(rr, 7, f"data/snapshots/{r.edition_id}/{e['file']}", f["txt"])
        ws.write(rr, 8, (e.get("sha256") or e.get("sha256_extract"))[:12], f["txt"])
        rr += 1
    ws.write(rr + 1, 0, "Data-quality flags", f["label"])
    flags = r.flags or ["None: every series has an observation on the as-of date."]
    for i, fl in enumerate(flags):
        ws.write(rr + 2 + i, 0, fl, f["txt"])
    ws.write(rr + 3 + len(flags), 0, "Documents [3] and [4] were published before the cutoff. Fund pages and the FOMC calendar were retrieved after the cutoff and are used only for stable descriptions and a schedule fixed in advance.", f["note"])
    ws.freeze_panes(4, 0)
    ws.autofilter(3, 0, rr - 1, 8)
    wb.close()
    return out
