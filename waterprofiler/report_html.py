"""HTML report for the analysis. The GUI prints it to PDF via Qt (full Persian shaping/RTL)."""

from __future__ import annotations

from html import escape
from typing import Optional

from . import __version__, branding
from . import measures as _ms
from .analysis import Analysis
from .cost import COMPONENTS
from .i18n import Translator
from .messages import localize_all


def _n(v: Optional[float], d: int = 0) -> str:
    return "—" if v is None else f"{v:,.{d}f}"


def _pct(v: Optional[float]) -> str:
    return "—" if v is None else f"{100 * v:.1f}%"


def build_report_html(a: Analysis, lang: str = "fa", logo: Optional[str] = None) -> str:
    """``logo`` is an image source (URL or Qt resource name) for the report header; omit for none."""
    t = Translator(lang)
    d = "rtl" if t.rtl else "ltr"
    k, b, c = a.kpi, a.balance, a.cost
    cur = escape(a.plant.currency)

    kpi_rows = [
        (t("sum_intake") + " (m³)", _n(b.sum_intake)),
        (t("sum_discharge") + " (m³)", _n(b.sum_discharge)),
        (t("sum_evap") + " (m³)", _n(b.sum_evaporation)),
        (t("sum_product") + " (m³)", _n(b.sum_product)),
        (t("unknown_loss") + " (m³)", _n(b.unknown_loss)),
        (t("closure") + " %", "—" if b.closure_pct is None else f"{b.closure_pct:.1f}"),
        (t("direct_cost") + f" ({cur})", _n(c.direct_billed_cost)),
        (t("tab_cost") + f" ({cur})", _n(c.total)),
        (t("true_direct"), "—" if c.true_to_direct_ratio is None else f"{c.true_to_direct_ratio:.2f}"),
        (t("cost_per_m3") + f" ({cur})", _n(c.true_cost_per_m3_intake, 2)),
        (t("kpi_per_unit"), _n(k.intake_per_unit, 3)),
        (t("kpi_cost_unit") + f" ({cur})", _n(k.true_cost_per_unit, 2)),
        (t("kpi_recirc"), _pct(k.recirculation_ratio)),
        (t("kpi_consumptive"), _pct(k.consumptive_fraction)),
        (t("kpi_discharge"), _pct(k.discharge_fraction)),
        (t("kpi_unacc"), _pct(k.unaccounted_fraction)),
    ]

    img = f"<td width='130'><img src='{escape(logo)}' width='120'></td>" if logo else ""
    header = (f"<table width='100%' style='margin:0 0 6px 0'><tr>{img}<td>"
              f"<h1>{escape(branding.APP_NAME)}</h1>"
              f"<span class='small'>{escape(branding.COMPANY[lang])} — {escape(branding.TAGLINE[lang])}</span>"
              f"</td></tr></table>")
    parts = [f"""<html dir="{d}"><head><meta charset="utf-8"><style>
body {{ font-family: 'Vazirmatn','Tahoma','Segoe UI',sans-serif; font-size: 10pt; color:#1b1b1b; }}
h1 {{ color:#0B3D78; font-size:20pt; margin-bottom:2px; }}
h2 {{ color:#0B3D78; font-size:13pt; border-bottom:2px solid #0A74C8; margin-top:16px; }}
table {{ border-collapse:collapse; width:100%; margin-top:6px; }}
th {{ background:#0B3D78; color:#fff; padding:4px 6px; font-weight:bold; }}
td {{ border:1px solid #cfd8e3; padding:3px 6px; }}
td.n {{ text-align:right; direction:ltr; }}
.warn {{ color:#9c4a00; }}
.small {{ color:#666; font-size:8pt; }}
</style></head><body>
{header}
<p><b>{escape(a.plant.name)}</b> &nbsp;·&nbsp; {escape(t('production'))}: {_n(a.plant.production_per_year)} {escape(a.plant.production_unit)}</p>
<h2>{escape(t('kpi'))}</h2><table>"""]
    for lab, val in kpi_rows:
        parts.append(f"<tr><td>{escape(lab)}</td><td class='n'>{escape(val)}</td></tr>")
    parts.append("</table>")

    parts.append(f"<h2>{escape(t('tab_balance'))}</h2><table><tr>"
                 + "".join(f"<th>{escape(t(x))}</th>" for x in
                           ("subsystem", "inflow", "outflow", "unknown_loss", "loss_pct", "status"))
                 + "</tr>")
    for s in b.subsystems:
        parts.append(f"<tr><td>{escape(s.name)}</td><td class='n'>{_n(s.inflow)}</td><td class='n'>{_n(s.outflow)}</td>"
                     f"<td class='n'>{_n(s.unknown_loss)}</td><td class='n'>{s.unknown_loss_pct_of_inflow:.1f}</td>"
                     f"<td>{escape(t('st_' + s.status))}</td></tr>")
    parts.append("</table>")

    parts.append(f"<h2>{escape(t('tab_cost'))} ({cur})</h2><table><tr><th>{escape(t('subsystem'))}</th>"
                 + "".join(f"<th>{escape(t('comp_' + x))}</th>" for x in COMPONENTS)
                 + f"<th>{escape(t('total'))}</th><th>{escape(t('water_share'))}</th>"
                   f"<th>{escape(t('cost_share'))}</th><th>{escape(t('priority'))}</th></tr>")
    rank = {r.name: r for r in a.ranking}
    for sc in c.subsystems:
        r = rank[sc.name]
        parts.append(f"<tr><td>{escape(sc.name)}</td>"
                     + "".join(f"<td class='n'>{_n(sc.components[x])}</td>" for x in COMPONENTS)
                     + f"<td class='n'><b>{_n(sc.total)}</b></td><td class='n'>{_pct(r.intake_share)}</td>"
                       f"<td class='n'>{_pct(r.cost_share)}</td><td>{escape(t('pr_' + r.priority))}</td></tr>")
    parts.append("<tr><td><b>" + escape(t("total")) + "</b></td>"
                 + "".join(f"<td class='n'><b>{_n(c.by_component[x])}</b></td>" for x in COMPONENTS)
                 + f"<td class='n'><b>{_n(c.total)}</b></td><td></td><td></td><td></td></tr></table>")
    if a.plant.plan:
        res = _ms.evaluate_plan(a.plant)
        parts.append(f"<h2>{escape(t('sheet_plan'))}</h2><table><tr>"
                     + "".join(f"<th>{escape(t(x))}</th>" for x in ("ms_measure", "pl_target", "pl_pct", "pl_saved", "pl_val_col",
                                                                      "pl_capex", "pl_pay"))
                     + "</tr>")
        for ln in res.lines:
            pb = "—" if ln.payback is None else f"{ln.payback:.1f}"
            parts.append(f"<tr><td>{ln.measure.id}. {escape(ln.measure.name(lang))}</td>"
                         f"<td>{escape(ln.item.target or t('ms_plant_wide'))}</td><td class='n'>{ln.item.saving_pct:.1f}</td>"
                         f"<td class='n'>{_n(ln.saving)}</td><td class='n'>{_n(ln.annual_value)}</td>"
                         f"<td class='n'>{_n(ln.item.capex)}</td><td class='n'>{pb}</td></tr>")
        pt = "—" if res.payback is None else f"{res.payback:.1f}"
        parts.append(f"<tr><td><b>{escape(t('total'))}</b></td><td></td><td class='n'><b>{res.saving_pct:.1f}</b></td>"
                     f"<td class='n'><b>{_n(res.saving)}</b></td><td class='n'><b>{_n(res.annual_value)}</b></td>"
                     f"<td class='n'><b>{_n(res.capex)}</b></td><td class='n'><b>{pt}</b></td></tr></table>")
        parts.append(f"<p class='small'>{escape(t('ms_disclaimer'))}</p>")


    if a.warnings:
        parts.append(f"<h2 class='warn'>{escape(t('warnings'))}</h2><ul>"
                     + "".join(f"<li class='warn'>{escape(w)}</li>" for w in localize_all(a.warnings, lang)) + "</ul>")

    parts.append(f"<p class='small'>{escape(branding.APP_NAME)} {__version__} · {escape(branding.COMPANY[lang])} · ORNL/TM-2021/1918</p></body></html>")
    return "".join(parts)
