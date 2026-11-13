"""Excel import / export of plant input data.

``export_input_workbook`` writes every input of a plant into a workbook with one
sheet per table; ``write_template`` writes the same layout with a few example rows
and an instruction sheet. ``import_workbook`` reads such a workbook back into a
:class:`Plant`. Headers and codes may be Persian or English; the sheet *order*
is what identifies the tables, so renaming a sheet does not break the import.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from .i18n import Translator
from .model import Outlet, Plant, Pump, Source, Subsystem, Treatment, UnitCosts, _migrate_params
from .numparse import parse_float

KINDS = ["process", "cooling_tower", "boiler", "sanitary", "irrigation", "wwtp", "other"]
FLOWS = ["intake", "discharge", "evaporation", "product", "recirculated", "from_other", "to_other",
         "water_treatment", "wastewater_treatment"]
SINGLE = {"evaporation": "evaporation", "product": "product", "recirculated": "recirculated",
          "from_other": "from_other", "to_other": "to_other"}

SHEETS = ["plant", "sources", "outlets", "treatments", "subsystems", "flows", "pumps", "params"]
NAVY, WHITE = "0B3D78", "FFFFFF"


class ImportProblem(ValueError):
    """Raised for a workbook that cannot be read; the message is already localised."""


def _heads(t: Translator) -> Dict[str, List[str]]:
    return {
        "plant": [t("imp_field"), t("imp_value")],
        "sources": [t("col_name"), t("col_unit_cost"), t("col_metered")],
        "outlets": [t("col_name"), t("col_unit_cost"), t("col_metered")],
        "treatments": [t("col_name"), t("col_unit_cost"), t("col_wastewater")],
        "subsystems": [t("col_name"), t("kind"), t("t_in"), t("t_ww"), t("eq_unit")],
        "flows": [t("subsystem"), t("imp_flow"), t("imp_item"), t("imp_amount")],
        "pumps": [t("subsystem"), t("col_name"), t("pump_hours"), t("pump_kw"), t("pump_eff"),
                  t("pump_load"), t("pump_volts"), t("pump_amps"), t("pump_pf"), t("pump_phases")],
        "params": [t("subsystem"), t("imp_param"), t("imp_value")],
    }


def _plant_fields(t: Translator) -> List[Tuple[str, str]]:
    return [("name", t("plant_name")), ("currency", t("currency")), ("production", t("production")),
            ("production_unit", t("production_unit")), ("elec", t("elec_cost")), ("fuel", t("fuel_cost")),
            ("heat_eff", t("heat_eff"))]


# ----------------------------------------------------------------- writing
def _style_header(ws, ncols: int) -> None:
    fill = PatternFill("solid", fgColor=NAVY)
    for c in range(1, ncols + 1):
        cell = ws.cell(row=1, column=c)
        cell.font = Font(bold=True, color=WHITE)
        cell.fill = fill
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        ws.column_dimensions[get_column_letter(c)].width = 22
    ws.row_dimensions[1].height = 30
    ws.freeze_panes = "A2"


def _fill_sheets(wb: Workbook, plant: Plant, t: Translator, first_sheet_active: bool) -> None:
    heads = _heads(t)
    rtl = t.rtl
    sheets = {}
    for i, key in enumerate(SHEETS):
        ws = wb.active if (i == 0 and first_sheet_active) else wb.create_sheet()
        ws.title = t("imp_sheet_" + key)[:31]
        ws.append(heads[key])
        ws.sheet_view.rightToLeft = rtl
        sheets[key] = ws

    c = plant.costs
    vals = {"name": plant.name, "currency": plant.currency, "production": plant.production_per_year,
            "production_unit": plant.production_unit, "elec": c.electricity_per_kwh,
            "fuel": c.fuel_per_kwh_thermal, "heat_eff": c.heating_efficiency}
    for key, label in _plant_fields(t):
        sheets["plant"].append([label, vals[key]])
    for s in plant.sources:
        sheets["sources"].append([s.name, s.unit_cost, s.metered_m3])
    for o in plant.outlets:
        sheets["outlets"].append([o.name, o.unit_cost, o.metered_m3])
    for x in plant.treatments:
        sheets["treatments"].append([x.name, x.unit_cost, 1 if x.wastewater else 0])
    for s in plant.subsystems:
        sheets["subsystems"].append([s.name, s.kind, s.t_intake_c, s.t_wastewater_c, s.parent or None])
        if plant.has_children(s.name):         # a unit with equipment is the sum of them: its flows are not entered
            continue
        fl = sheets["flows"]
        for k, v in s.intake.items():
            fl.append([s.name, "intake", k, v])
        for k, v in s.discharge.items():
            fl.append([s.name, "discharge", k, v])
        for code, attr in SINGLE.items():
            v = getattr(s, attr)
            if v:
                fl.append([s.name, code, None, v])
        for k, v in s.water_treatments.items():
            fl.append([s.name, "water_treatment", k, v])
        for k, v in s.wastewater_treatments.items():
            fl.append([s.name, "wastewater_treatment", k, v])
        for p in s.pumps:
            kw = p.power_kw
            sheets["pumps"].append([s.name, p.name, p.hours_per_year, kw, p.efficiency, p.load_fraction,
                                    p.volts, p.amps, p.power_factor, p.phases])
        for k, v in s.params.items():
            sheets["params"].append([s.name, k, v])

    for key, ws in sheets.items():
        _style_header(ws, len(heads[key]))
    sheets["plant"].column_dimensions["A"].width = 34
    sheets["plant"].column_dimensions["B"].width = 30
    dv_kind = DataValidation(type="list", formula1='"' + ",".join(KINDS) + '"', allow_blank=True)
    sheets["subsystems"].add_data_validation(dv_kind)
    dv_kind.add("B2:B500")
    dv_flow = DataValidation(type="list", formula1='"' + ",".join(FLOWS) + '"', allow_blank=True)
    sheets["flows"].add_data_validation(dv_flow)
    dv_flow.add("B2:B2000")


def _instructions(wb: Workbook, t: Translator) -> None:
    ws = wb.create_sheet(t("imp_sheet_help"), 0)
    ws.sheet_view.rightToLeft = t.rtl
    ws.column_dimensions["A"].width = 110
    lines = [t("imp_help_title"), "", t("imp_help_1"), t("imp_help_2"), t("imp_help_3"), "",
             t("imp_help_kinds") + ": " + ", ".join(KINDS),
             t("imp_help_flows") + ": " + ", ".join(FLOWS), "", t("imp_help_units"), t("imp_help_names")]
    for i, line in enumerate(lines, 1):
        cell = ws.cell(row=i, column=1, value=line)
        cell.alignment = Alignment(wrap_text=True, vertical="top")
        if i == 1:
            cell.font = Font(bold=True, size=14, color=NAVY)


def export_input_workbook(plant: Plant, path: str, lang: str = "fa") -> None:
    t = Translator(lang)
    wb = Workbook()
    _fill_sheets(wb, plant, t, first_sheet_active=True)
    wb.save(path)


def write_template(path: str, lang: str = "fa") -> None:
    """Instruction sheet plus a tiny worked example the user overwrites."""
    t = Translator(lang)
    ex = Plant(name=t("imp_ex_plant"), currency="USD", production_per_year=1000.0, production_unit="t",
               sources=[Source(t("imp_ex_source"), 1.0, None)], outlets=[Outlet(t("imp_ex_outlet"), 1.0, None)],
               treatments=[Treatment(t("imp_ex_treat"), 0.3, False)],
               subsystems=[Subsystem(t("imp_ex_sub"), "process", intake={t("imp_ex_source"): 5000.0},
                                     discharge={t("imp_ex_outlet"): 4000.0}, evaporation=800.0, product=200.0,
                                     water_treatments={t("imp_ex_treat"): 1.0})],
               costs=UnitCosts(0.1, 0.03, 0.8))
    wb = Workbook()
    _fill_sheets(wb, ex, t, first_sheet_active=True)
    _instructions(wb, t)
    wb.save(path)


# ----------------------------------------------------------------- reading
def _label_map(t_fa: Translator, t_en: Translator, keys: List[str], prefix: str) -> Dict[str, str]:
    m: Dict[str, str] = {}
    for k in keys:
        m[k.lower()] = k
        for tr in (t_fa, t_en):
            m[tr(prefix + k).strip().lower()] = k
    return m


def _rows(ws) -> List[Tuple[int, list]]:
    out = []
    for r, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        if row is None or all(v is None or str(v).strip() == "" for v in row):
            continue
        out.append((r, list(row)))
    return out


def _text(v) -> str:
    return "" if v is None else str(v).strip()


def import_workbook(path: str, lang: str = "fa") -> Tuple[Plant, List[str]]:
    """Read ``path`` and return (plant, warnings). Raises :class:`ImportProblem`."""
    t = Translator(lang)
    t_fa, t_en = Translator("fa"), Translator("en")
    try:
        wb = load_workbook(path, data_only=True, read_only=False)
    except Exception as e:  # noqa: BLE001 - any unreadable file
        raise ImportProblem(t("imp_err_open", err=str(e))) from e

    sheets = [ws for ws in wb.worksheets if ws.title not in (t_fa("imp_sheet_help"), t_en("imp_sheet_help"))]
    if len(sheets) < len(SHEETS):
        raise ImportProblem(t("imp_err_sheets", n=len(SHEETS)))
    ws = dict(zip(SHEETS, sheets))
    warnings: List[str] = []

    def num(v, where: str, default: Optional[float] = None) -> Optional[float]:
        if v is None or _text(v) == "":
            return default
        x = parse_float(v)
        if x is None:
            warnings.append(t("imp_warn_number", where=where, value=_text(v)))
            return default
        return x

    # ---- plant
    fields = {}
    pf = {}
    for key, _ in _plant_fields(t):
        for tr in (t_fa, t_en):
            pf[dict(_plant_fields(tr))[key].strip().lower()] = key
    for r, row in _rows(ws["plant"]):
        k = pf.get(_text(row[0]).lower())
        if k:
            fields[k] = row[1] if len(row) > 1 else None
    plant = Plant(
        name=_text(fields.get("name")) or t("imp_ex_plant"),
        currency=_text(fields.get("currency")) or "IRR",
        production_per_year=num(fields.get("production"), "plant", 0.0) or 0.0,
        production_unit=_text(fields.get("production_unit")) or "t",
        costs=UnitCosts(num(fields.get("elec"), "plant", 0.0) or 0.0, num(fields.get("fuel"), "plant", 0.0) or 0.0,
                        num(fields.get("heat_eff"), "plant", 0.8) or 0.8),
    )

    plant.ensure_products("Product" if lang == "en" else "محصول")

    # ---- catalogues
    for r, row in _rows(ws["sources"]):
        if _text(row[0]):
            plant.sources.append(Source(_text(row[0]), num(row[1] if len(row) > 1 else None, f"{ws['sources'].title}!{r}", 0.0) or 0.0,
                                        num(row[2] if len(row) > 2 else None, f"{ws['sources'].title}!{r}")))
    for r, row in _rows(ws["outlets"]):
        if _text(row[0]):
            plant.outlets.append(Outlet(_text(row[0]), num(row[1] if len(row) > 1 else None, f"{ws['outlets'].title}!{r}", 0.0) or 0.0,
                                        num(row[2] if len(row) > 2 else None, f"{ws['outlets'].title}!{r}")))
    yes = {"1", "true", "yes", "y", "بله", "آری", "x", "✓"}
    for r, row in _rows(ws["treatments"]):
        if _text(row[0]):
            flag = _text(row[2] if len(row) > 2 else None).lower()
            plant.treatments.append(Treatment(_text(row[0]), num(row[1] if len(row) > 1 else None, f"{ws['treatments'].title}!{r}", 0.0) or 0.0,
                                              flag in yes or flag == "1.0"))

    # ---- subsystems
    kinds = _label_map(t_fa, t_en, KINDS, "kind_")
    subs: Dict[str, Subsystem] = {}
    for r, row in _rows(ws["subsystems"]):
        name = _text(row[0])
        if not name:
            continue
        kind = kinds.get(_text(row[1] if len(row) > 1 else None).lower())
        if kind is None:
            if _text(row[1] if len(row) > 1 else None):
                warnings.append(t("imp_warn_kind", name=name, value=_text(row[1])))
            kind = "other"
        s = Subsystem(name, kind, t_intake_c=num(row[2] if len(row) > 2 else None, f"{name}"),
                      t_wastewater_c=num(row[3] if len(row) > 3 else None, f"{name}"))
        par = _text(row[4] if len(row) > 4 else None)
        if par:
            s.parent = par
        subs[name] = s
        plant.subsystems.append(s)

    src_names = {s.name for s in plant.sources}
    out_names = {o.name for o in plant.outlets}
    tr_names = {x.name for x in plant.treatments}
    flows = _label_map(t_fa, t_en, FLOWS, "imp_flow_")
    for r, row in _rows(ws["flows"]):
        sname, fl, item = _text(row[0]), flows.get(_text(row[1] if len(row) > 1 else None).lower()), _text(row[2] if len(row) > 2 else None)
        where = f"{ws['flows'].title}!{r}"
        if sname not in subs:
            warnings.append(t("imp_warn_sub", where=where, name=sname))
            continue
        if fl is None:
            warnings.append(t("imp_warn_flow", where=where, value=_text(row[1] if len(row) > 1 else None)))
            continue
        v = num(row[3] if len(row) > 3 else None, where)
        if v is None:
            continue
        s = subs[sname]
        if fl in SINGLE:
            setattr(s, SINGLE[fl], v)
            continue
        target, known = {
            "intake": (s.intake, src_names), "discharge": (s.discharge, out_names),
            "water_treatment": (s.water_treatments, tr_names), "wastewater_treatment": (s.wastewater_treatments, tr_names),
        }[fl]
        if item not in known:
            warnings.append(t("imp_warn_item", where=where, name=item))
            continue
        target[item] = target.get(item, 0.0) + v

    # ---- pumps and parameters
    for r, row in _rows(ws["pumps"]):
        sname = _text(row[0])
        where = f"{ws['pumps'].title}!{r}"
        if sname not in subs:
            warnings.append(t("imp_warn_sub", where=where, name=sname))
            continue
        g = lambda i: row[i] if len(row) > i else None  # noqa: E731
        ph = num(g(9), where, 3.0)
        subs[sname].pumps.append(Pump(
            name=_text(g(1)) or "pump", hours_per_year=num(g(2), where, 0.0) or 0.0, power_kw=num(g(3), where),
            efficiency=num(g(4), where, 0.9) or 0.9, load_fraction=num(g(5), where, 1.0) if num(g(5), where, 1.0) is not None else 1.0,
            volts=num(g(6), where), amps=num(g(7), where), power_factor=num(g(8), where, 0.85) or 0.85,
            phases=1 if ph == 1 else 3))
    for r, row in _rows(ws["params"]):
        sname, key = _text(row[0]), _text(row[1] if len(row) > 1 else None)
        v = num(row[2] if len(row) > 2 else None, f"{ws['params'].title}!{r}")
        if sname in subs and key and v is not None:
            subs[sname].params[key] = v

    for sb in subs.values():
        sb.params = _migrate_params(sb.params)
    for note in plant.normalize_tree():
        warnings.append(note)
    plant.rollup()
    if not plant.subsystems:
        warnings.append(t("imp_warn_empty"))
    return plant, warnings
