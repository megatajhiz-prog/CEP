"""Excel export of the full analysis (openpyxl)."""

from __future__ import annotations

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .analysis import Analysis
from .cost import COMPONENTS
from .i18n import Translator
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
    ws.title = t("tab_plant")[:31]
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

    # --- Warnings
    if a.warnings:
        ws = wb.create_sheet(t("warnings")[:31])
        ws.sheet_view.rightToLeft = rtl
        for i, w in enumerate(localize_all(a.warnings, lang), 1):
            ws.cell(row=i, column=1, value=w)
        _autowidth(ws)

    wb.save(path)
