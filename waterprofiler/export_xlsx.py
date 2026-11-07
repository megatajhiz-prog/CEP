"""Excel export of the full analysis (openpyxl)."""

from __future__ import annotations

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .analysis import Analysis
from .cost import COMPONENTS
from . import complex as CX
from .i18n import Translator
from . import measures as _ms
from .messages import localize_all

HEAD_FILL = PatternFill("solid", fgColor="0B3D78")
HEAD_FONT = Font(bold=True, color="FFFFFF")


def _header(ws, row, labels):
    for j, lab in enumerate(labels, 1):
        c = ws.cell(row=row, column=j, value=lab)
        c.fill, c.font = HEAD_FILL, HEAD_FONT
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)


def _autowidth(ws):
    for col in ws.columns:
        width = max((len(str(c.value)) if c.value is not None else 0) for c in col)
        ws.column_dimensions[get_column_letter(col[0].column)].width = min(max(12, width + 2), 60)


def export_xlsx(a: Analysis, path: str, lang: str = "fa") -> None:
    t = Translator(lang)
    wb = Workbook()
    rtl = t.rtl

    # --- Summary
    ws = wb.active
    ws.title = t("sheet_summary")[:31]
    ws.sheet_view.rightToLeft = rtl
    k, p = a.kpi, a.plant
    rows = [
        (t("plant_name"), p.name),
        (t("currency"), p.currency),
        (t("production"), p.production_per_year),
        (t("sum_intake"), a.balance.sum_intake),
        (t("sum_discharge"), a.balance.sum_discharge),
        (t("sum_evap"), a.balance.sum_evaporation),
        (t("sum_product"), a.balance.sum_product),
        (t("unknown_loss"), a.balance.unknown_loss),
        (t("metered_intake"), a.balance.metered_intake),
        (t("metered_discharge"), a.balance.metered_discharge),
        (t("closure") + " %", a.balance.closure_pct),
        (t("direct_cost"), a.cost.direct_billed_cost),
        (t("total") + " " + t("tab_cost"), a.cost.total),
        (t("true_direct"), a.cost.true_to_direct_ratio),
        (t("cost_per_m3"), a.cost.true_cost_per_m3_intake),
        (t("kpi_per_unit"), k.intake_per_unit),
        (t("kpi_cost_unit"), k.true_cost_per_unit),
        (t("kpi_recirc"), k.recirculation_ratio),
        (t("kpi_consumptive"), k.consumptive_fraction),
        (t("kpi_discharge"), k.discharge_fraction),
        (t("kpi_unacc"), k.unaccounted_fraction),
    ]
    _header(ws, 1, ["", ""])
    for i, (lab, val) in enumerate(rows, 2):
        ws.cell(row=i, column=1, value=lab)
        c = ws.cell(row=i, column=2, value=val)
        if isinstance(val, float):
            c.number_format = "#,##0.00"
    _autowidth(ws)

    # --- Industrial complex: details, areas, products, meters
    ws = wb.create_sheet(t("sheet_complex")[:31])
    ws.sheet_view.rightToLeft = rtl
    r = 1
    _header(ws, r, [t("cx_info"), ""])
    for key, val in CX.info_rows(p):
        r += 1
        ws.cell(row=r, column=1, value=t(key))
        ws.cell(row=r, column=2, value=val)
    r += 2
    _header(ws, r, [t("site_area"), t("site_kind"), t("site_nsubs"), t("site_intake"), t("site_discharge"),
                    t("site_evap"), t("site_product"), t("site_share")])
    for x in CX.area_rows(p):
        r += 1
        vals = [x.name or t("cx_unassigned"), t("site_ak_" + x.kind) if x.kind else "", len(x.subsystems),
                x.intake, x.discharge, x.evaporation, x.product, x.share]
        for j, v in enumerate(vals, 1):
            c = ws.cell(row=r, column=j, value=v)
            if isinstance(v, float):
                c.number_format = "#,##0.0"
    if p.site.products:
        r += 2
        _header(ws, r, [t("cx_products"), t("production_unit")])
        for pr in p.site.products:
            r += 1
            ws.cell(row=r, column=1, value=pr.name)
            ws.cell(row=r, column=2, value=p.production_unit)
    if p.site.meters:
        r += 2
        _header(ws, r, [t("cx_meters"), t("site_tag"), t("site_munit"), t("site_acc"), t("site_calibrated"), ""])
        for m in CX.meter_rows(p):
            r += 1
            for j, v in enumerate([m.name, m.tag, m.unit, m.accuracy_pct or None, m.calibrated,
                                   t("cx_due") if m.due else t("cx_ok")], 1):
                ws.cell(row=r, column=j, value=v)
    _autowidth(ws)

    # --- Balance
    ws = wb.create_sheet(t("tab_balance")[:31])
    ws.sheet_view.rightToLeft = rtl
    _header(ws, 1, [t("subsystem"), t("inflow"), t("outflow"), t("unknown_loss"), t("loss_pct"), t("status")])
    for i, s in enumerate(a.balance.subsystems, 2):
        for j, v in enumerate([s.name, s.inflow, s.outflow, s.unknown_loss,
                               s.unknown_loss_pct_of_inflow, t("st_" + s.status)], 1):
            c = ws.cell(row=i, column=j, value=v)
            if isinstance(v, float):
                c.number_format = "#,##0.00"
    _autowidth(ws)

    # --- Cost
    ws = wb.create_sheet(t("tab_cost")[:31])
    ws.sheet_view.rightToLeft = rtl
    _header(ws, 1, [t("subsystem")] + [t("comp_" + c) for c in COMPONENTS]
            + [t("total"), t("cost_per_m3"), t("water_share"), t("cost_share"), t("priority")])
    rank = {r.name: r for r in a.ranking}
    for i, sc in enumerate(a.cost.subsystems, 2):
        r = rank[sc.name]
        vals = [sc.name] + [sc.components[c] for c in COMPONENTS] + [
            sc.total, sc.per_m3_intake, r.intake_share, r.cost_share, t("pr_" + r.priority)]
        for j, v in enumerate(vals, 1):
            c = ws.cell(row=i, column=j, value=v)
            if isinstance(v, float):
                c.number_format = "0.0%" if j in (len(vals) - 2, len(vals) - 1) else "#,##0.00"
    n = len(a.cost.subsystems) + 2
    ws.cell(row=n, column=1, value=t("total")).font = Font(bold=True)
    for j, comp in enumerate(COMPONENTS, 2):
        col = get_column_letter(j)
        c = ws.cell(row=n, column=j, value=f"=SUM({col}2:{col}{n - 1})")
        c.number_format, c.font = "#,##0.00", Font(bold=True)
    col = get_column_letter(len(COMPONENTS) + 2)
    c = ws.cell(row=n, column=len(COMPONENTS) + 2, value=f"=SUM({col}2:{col}{n - 1})")
    c.number_format, c.font = "#,##0.00", Font(bold=True)
    _autowidth(ws)

    # --- Flows by subsystem
    ws = wb.create_sheet(t("tab_subsystems")[:31])
    ws.sheet_view.rightToLeft = rtl
    _header(ws, 1, [t("subsystem"), t("kind"), t("intake"), t("recirculated"), t("from_other"), t("to_other"),
                    t("product"), t("evaporation"), t("discharge")])
    for i, s in enumerate(p.subsystems, 2):
        vals = [s.name, t("kind_" + s.kind) if s.kind in
                ("process", "cooling_tower", "boiler", "sanitary", "irrigation", "other") else s.kind,
                s.total_intake, s.recirculated, s.from_other, s.to_other, s.product, s.evaporation,
                s.total_discharge]
        for j, v in enumerate(vals, 1):
            c = ws.cell(row=i, column=j, value=v)
            if isinstance(v, float):
                c.number_format = "#,##0.00"
    _autowidth(ws)

    # --- Saving plan
    if p.plan:
        res = _ms.evaluate_plan(p)
        ws = wb.create_sheet(t("sheet_plan")[:31])
        ws.sheet_view.rightToLeft = rtl
        _header(ws, 1, [t("ms_measure"), t("pl_target"), t("pl_pct"), t("pl_capex"), t("pl_opex"), t("pl_life"),
                        t("pl_rate"), t("pl_saved"), t("pl_val_col"), t("pl_i1"), t("pl_i2"), t("pl_lcc"), t("pl_pay")])
        for i, ln in enumerate(res.lines, 2):
            it = ln.item
            vals = [f"{ln.measure.id}. {ln.measure.name(lang)}", it.target or t("ms_plant_wide"), it.saving_pct,
                    it.capex, it.opex, it.life_years, it.rate_pct, ln.saving, ln.annual_value, ln.i1, ln.i2, ln.lcc,
                    ln.payback]
            for j, v in enumerate(vals, 1):
                c = ws.cell(row=i, column=j, value=v)
                if isinstance(v, float):
                    c.number_format = "#,##0.00"
        n = len(res.lines) + 3
        ws.cell(row=n, column=1, value=t("pl_saving") + " (m³)").font = Font(bold=True)
        ws.cell(row=n, column=2, value=res.saving).number_format = "#,##0"
        ws.cell(row=n + 1, column=1, value=t("pl_value")).font = Font(bold=True)
        ws.cell(row=n + 1, column=2, value=res.annual_value).number_format = "#,##0"
        ws.cell(row=n + 2, column=1, value=t("pl_capex")).font = Font(bold=True)
        ws.cell(row=n + 2, column=2, value=res.capex).number_format = "#,##0"
        _autowidth(ws)

    # --- Economic evaluation (one summary sheet + the yearly cash flows of every measure)
    if p.plan:
        from . import economics as _ec
        items = _ec.evaluate_plan_economics(p)
        ws = wb.create_sheet(t("sheet_econ")[:31])
        ws.sheet_view.rightToLeft = rtl
        _header(ws, 1, [t("ms_measure"), t("ec_saving_col"), t("ec_price"), t("ec_capex"), t("ec_opex"), t("ec_life"),
                        t("ec_rate"), t("ec_npv"), t("ec_irr"), t("ec_spb"), t("ec_dpb"), t("ec_bcr"), t("ec_lcow"),
                        t("ec_verdict")])
        for i, ie in enumerate(items, 2):
            m = _ms.get(ie.item.measure_id)
            r = ie.result
            if r is None:
                ws.cell(row=i, column=1, value=f"{m.id}. {m.name(lang)}")
                continue
            q = r.inputs
            vals = [f"{m.id}. {m.name(lang)}", q.saving_m3, q.price, q.capex, q.opex, q.life, q.rate_pct, r.npv, r.irr,
                    r.payback, r.dpayback, r.bcr, r.lcow, t("ec_v_short_" + r.verdict)]
            for j, v in enumerate(vals, 1):
                c = ws.cell(row=i, column=j, value=v)
                if isinstance(v, float):
                    c.number_format = "#,##0.00"
        row = len(items) + 4
        for ie in items:
            r = ie.result
            if r is None:
                continue
            m = _ms.get(ie.item.measure_id)
            ws.cell(row=row, column=1, value=f"{m.id}. {m.name(lang)}").font = Font(bold=True)
            row += 1
            _header(ws, row, [t("ec_year"), t("ec_vol"), t("ec_benefit"), t("ec_cost"), t("ec_net"), t("ec_cum"), t("ec_dcum")])
            for y in r.years:
                row += 1
                for j, v in enumerate([y, r.volume[y], r.benefit[y], r.cost[y], r.net[y], r.cum[y], r.dcum[y]], 1):
                    c = ws.cell(row=row, column=j, value=v)
                    if j > 1:
                        c.number_format = "#,##0"
            row += 2
        _autowidth(ws)

    # --- Indicators (all of them; the ones without inputs list what is missing)
    from . import indicators as _ik
    from .indicator_text import GROUP_TITLE, PROFILE_LABEL, SUB_COLS, TEXT, UNITS, format_value, unit_label
    ires = _ik.compute(p, a)
    ws = wb.create_sheet(t("sheet_ind")[:31])
    ws.sheet_view.rightToLeft = rtl
    _header(ws, 1, [t("in_col_name"), t("in_col_value"), t("in_col_unit"), t("in_col_formula"), t("in_col_note")])
    row = 1
    for g in _ik.GROUPS:
        row += 1
        ws.cell(row=row, column=1, value=GROUP_TITLE[g][0 if lang == "fa" else 1]).font = Font(bold=True)
        for ind in ires.by_group(g):
            row += 1
            tx = TEXT[ind.id]
            ws.cell(row=row, column=1, value=tx[0] if lang == "fa" else tx[1])
            c = ws.cell(row=row, column=2, value=ind.value)
            if ind.value is not None:
                c.number_format = "#,##0" if UNITS[ind.unit][2] == 0 else "#,##0." + "0" * UNITS[ind.unit][2]
            ws.cell(row=row, column=3, value=unit_label(ind.unit, lang, p.currency, p.production_unit))
            ws.cell(row=row, column=4, value=tx[2])
            if ind.reason == "inputs":
                note = t("in_needs", x=", ".join(PROFILE_LABEL[n][0 if lang == "fa" else 1] for n in ind.needs))
            elif ind.reason == "data":
                note = t("in_nodata")
            else:
                note = tx[3] if lang == "fa" else tx[4]
            ws.cell(row=row, column=5, value=note)
    row += 2
    ws.cell(row=row, column=1, value=t("in_sub_title")).font = Font(bold=True)
    row += 1
    _header(ws, row, [t("subsystem")] + [(c[1] if lang == "fa" else c[2]) for c in SUB_COLS])
    for sr in ires.subsystems:
        row += 1
        ws.cell(row=row, column=1, value=sr.name)
        for j, (key, _fa, _en, u) in enumerate(SUB_COLS, 2):
            v = sr.values.get(key)
            c = ws.cell(row=row, column=j, value=v)
            if v is not None:
                c.number_format = "#,##0.00"
    _autowidth(ws)

    # --- Warnings
    if a.warnings:
        ws = wb.create_sheet(t("warnings")[:31])
        ws.sheet_view.rightToLeft = rtl
        for i, w in enumerate(localize_all(a.warnings, lang), 1):
            ws.cell(row=i, column=1, value=w)
        _autowidth(ws)

    wb.save(path)
