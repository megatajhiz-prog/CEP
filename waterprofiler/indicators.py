"""Supply and consumption indicators of the plant water system.

Everything here is derived from the plant model (flows, costs, pumps, plan) and from the optional
``Plant.profile`` inputs. An indicator whose inputs are missing has ``value = None`` and lists the missing
profile fields in ``needs``; nothing is ever guessed.

Notation (all volumes in m3 per year): I intake from sources, R internal recirculation, R'in transfer received
from another subsystem, W discharge, E evaporation, P water leaving in product, L unaccounted loss
(L = sum(I) - sum(W) - sum(E) - sum(P)), Q production in product units.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence

from .analysis import Analysis, analyse
from .cost import COMPONENTS
from .measures import evaluate_plan
from .model import Plant

GROUPS = ("supply", "use", "waste", "cost", "quality", "target", "plan", "time")

# unit codes, rendered by the GUI: "m3", "pct", "x", "kwh", "kwh_m3", "cur", "cur_m3", "cur_unit", "kg", "kg_m3",
# "lpd", "mm", "days", "m3_unit", "m3_mcur", "m3_t", "m3_m2", "cur_m3day", "pp", "years", "kg_unit"

# profile fields that count towards "completeness"
PROFILE_FIELDS = (
    "employees", "working_days", "building_area_m2", "green_area_m2", "revenue", "value_added", "production_cost",
    "steam_t", "storage_m3", "outage_hours", "network_km", "connections", "pressure_m", "ef_el",
    "ef_th", "cod_raw", "cod_out", "tds_intake", "tds_discharge", "target_intake_per_unit", "target_recirc_pct",
    "target_loss_pct",
)


@dataclass
class Indicator:
    id: str
    group: str
    unit: str
    value: Optional[float] = None
    needs: List[str] = field(default_factory=list)       # missing profile fields
    reason: str = ""                                    # "" | "inputs" | "data" (too little data) | "series" (no time series)
    approx: bool = False


@dataclass
class SubIndicators:
    name: str
    kind: str
    values: Dict[str, Optional[float]]


@dataclass
class IndicatorSet:
    items: List[Indicator]
    subsystems: List[SubIndicators]
    completeness: float                                  # share of profile fields entered
    computable: float                                    # share of indicators that have a value

    def get(self, ind_id: str) -> Indicator:
        for i in self.items:
            if i.id == ind_id:
                return i
        raise KeyError(ind_id)

    def by_group(self, group: str) -> List[Indicator]:
        return [i for i in self.items if i.group == group]


def _div(a: float, b: float) -> Optional[float]:
    return a / b if b and b > 0 else None


def compute(plant: Plant, a: Optional[Analysis] = None) -> IndicatorSet:
    a = a or analyse(plant)
    b, c, k = a.balance, a.cost, a.kpi
    pf = plant.profile
    plant.rollup()
    subs = plant.leaves()                    # totals over the nodes that carry data
    intake = b.sum_intake
    disch = b.sum_discharge
    ev, prod_w, loss = b.sum_evaporation, b.sum_product, b.unknown_loss
    recirc = sum(s.recirculated for s in subs)
    rin = sum(s.from_other for s in subs)
    gross = intake + recirc + rin
    units = plant.production_per_year or 0.0
    el_kwh = sum(sc.electricity_kwh for sc in c.subsystems)
    th_kwh = sum(sc.heat_kwh_thermal for sc in c.subsystems)
    out: List[Indicator] = []

    def add(ind_id: str, group: str, unit: str, value: Optional[float] = None, needs: Sequence[str] = (),
            approx: bool = False) -> None:
        missing = [n for n in needs if not getattr(pf, n, 0)]
        if missing:
            out.append(Indicator(ind_id, group, unit, None, missing, "inputs", approx))
        elif value is None:
            out.append(Indicator(ind_id, group, unit, None, [], "data", approx))
        else:
            out.append(Indicator(ind_id, group, unit, float(value), [], "", approx))

    # ------------------------------------------------------------------ supply
    by_src = b.intake_by_source
    shares = {n: v / intake for n, v in by_src.items()} if intake > 0 else {}
    add("sup_intake", "supply", "m3", intake)
    add("sup_largest_share", "supply", "pct", 100 * max(shares.values()) if shares else None)
    add("sup_hhi", "supply", "x", sum(v * v for v in shares.values()) if shares else None)
    alt = {s.name for s in plant.sources if s.alternative}
    add("sup_alt_share", "supply", "pct", 100 * sum(by_src.get(n, 0.0) for n in alt) / intake if intake > 0 else None)
    add("sup_avg_cost", "supply", "cur_m3", c.by_component["intake"] / intake if intake > 0 else None)
    metered = {s.name for s in plant.sources if s.metered_m3 is not None}
    add("sup_meter_cover", "supply", "pct", 100 * sum(by_src.get(n, 0.0) for n in metered) / intake if intake > 0 else None)
    # The plant permit is the sum of the limits of the sources whose limit the user switched on; without any, no indicator.
    lim = {s.name: s.permit_m3 for s in plant.sources if s.permit_on and s.permit_m3 > 0}
    if lim:
        add("sup_permit_use", "supply", "pct", 100.0 * sum(by_src.get(n, 0.0) for n in lim) / sum(lim.values()))
    else:
        out.append(Indicator("sup_permit_use", "supply", "pct", None, [], "permit"))
    add("sup_storage_days", "supply", "days", _div(pf.storage_m3, intake / 365.0) if intake > 0 else None, ("storage_m3",))
    add("sup_availability", "supply", "pct", 100 * (1 - pf.outage_hours / 8760.0), ("outage_hours",))
    add("sup_pump_kwh", "supply", "kwh", el_kwh if el_kwh > 0 else None)
    add("sup_pump_specific", "supply", "kwh_m3", el_kwh / intake if el_kwh > 0 and intake > 0 else None)
    uarl = None
    if pf.network_km > 0 and pf.connections > 0 and pf.pressure_m > 0:
        # IWA unavoidable annual real losses: (18 Lm + 0.8 Nc) * P litres/day, no private pipework
        uarl = (18.0 * pf.network_km + 0.8 * pf.connections) * pf.pressure_m * 365.0 / 1000.0
    add("sup_ili", "supply", "x", loss / uarl if uarl and loss >= 0 else None,
        ("network_km", "connections", "pressure_m"), approx=True)

    # --------------------------------------------------------------------- use
    add("use_gross", "use", "m3", gross)
    add("use_reuse_factor", "use", "x", _div(gross, intake))
    add("use_recirc_ratio", "use", "pct", _pct100(k.recirculation_ratio))
    add("use_internal_share", "use", "pct", _pct(recirc, gross))
    add("use_transfer_share", "use", "pct", _pct(rin, gross))
    add("use_consumption", "use", "m3", intake - disch)
    add("use_consumptive_fraction", "use", "pct", _pct100(k.consumptive_fraction))
    add("use_evap_share", "use", "pct", _pct(ev, intake))
    add("use_product_share", "use", "pct", _pct(prod_w, intake))
    add("use_loss_m3", "use", "m3", loss)
    add("use_loss_fraction", "use", "pct", _pct100(k.unaccounted_fraction))
    add("use_per_unit", "use", "m3_unit", _div(intake, units))
    add("use_gross_per_unit", "use", "m3_unit", _div(gross, units))
    add("use_consumption_per_unit", "use", "m3_unit", _div(intake - disch, units))
    san = [s for s in subs if s.kind == "sanitary"]
    emp = pf.employees or max([s.params.get("employees", 0.0) for s in san] or [0.0])
    days = pf.working_days or max([s.params.get("days", 0.0) for s in san] or [0.0])
    san_in = sum(s.total_intake for s in san)
    add("use_lpd", "use", "lpd", 1000.0 * san_in / (emp * days) if san and emp > 0 and days > 0 else None)
    add("use_per_building", "use", "m3_m2", _div(intake, pf.building_area_m2), ("building_area_m2",))
    irr_in = sum(s.total_intake for s in subs if s.kind == "irrigation")
    add("use_irrigation_depth", "use", "mm", _div(1000.0 * irr_in, pf.green_area_m2) if irr_in > 0 else None,
        ("green_area_m2",))
    add("use_per_revenue", "use", "m3_mcur", _div(intake, pf.revenue / 1e6) if intake > 0 else None, ("revenue",))
    add("use_productivity", "use", "cur_m3", _div(pf.value_added, intake), ("value_added",))
    boil_in = sum(s.total_intake for s in subs if s.kind == "boiler")
    add("use_water_per_steam", "use", "m3_t", _div(boil_in, pf.steam_t) if boil_in > 0 else None, ("steam_t",))

    # ------------------------------------------------------------- wastewater
    add("ww_total", "waste", "m3", disch)
    add("ww_fraction", "waste", "pct", _pct100(k.discharge_fraction))
    add("ww_per_unit", "waste", "m3_unit", _div(disch, units))
    treated = sum(min(1.0, sum(s.wastewater_treatments.values())) * s.total_discharge for s in subs)
    add("ww_treated_share", "waste", "pct", _pct(treated, disch))
    dout = b.discharge_by_outlet
    add("ww_largest_outlet", "waste", "pct", 100 * max(dout.values()) / disch if dout and disch > 0 else None)
    add("ww_avg_cost", "waste", "cur_m3", c.by_component["discharge"] / disch if disch > 0 else None)
    add("ww_cod_raw_load", "waste", "kg", pf.cod_raw * disch / 1000.0, ("cod_raw",))
    add("ww_cod_out_load", "waste", "kg", pf.cod_out * disch / 1000.0, ("cod_out",))
    add("ww_cod_removal", "waste", "pct", 100 * (1 - pf.cod_out / pf.cod_raw) if pf.cod_raw > 0 else None,
        ("cod_raw", "cod_out"))
    add("ww_tds_load", "waste", "kg", (pf.tds_discharge * disch - pf.tds_intake * intake) / 1000.0,
        ("tds_intake", "tds_discharge"))
    add("ww_tds_factor", "waste", "x", _div(pf.tds_discharge, pf.tds_intake), ("tds_intake", "tds_discharge"))
    add("ww_cod_per_unit", "waste", "kg_unit", _div(pf.cod_out * disch / 1000.0, units), ("cod_out",))

    # ------------------------------------------------------------ cost / energy
    total = c.total
    add("cost_total", "cost", "cur", total)
    add("cost_per_m3", "cost", "cur_m3", c.true_cost_per_m3_intake)
    add("cost_per_unit", "cost", "cur_unit", k.true_cost_per_unit)
    add("cost_true_to_direct", "cost", "x", c.true_to_direct_ratio)
    for comp in COMPONENTS:
        add("cost_share_" + comp, "cost", "pct", _pct(c.by_component[comp], total))
    add("cost_of_production", "cost", "pct", _pct(total, pf.production_cost), ("production_cost",))
    add("cost_of_revenue", "cost", "pct", _pct(total, pf.revenue), ("revenue",))
    add("cost_energy_share", "cost", "pct", _pct(c.by_component["pumping"] + c.by_component["heat"], total))
    add("en_heat_kwh", "cost", "kwh", th_kwh if th_kwh > 0 else None)
    add("en_heat_per_m3", "cost", "kwh_m3", th_kwh / intake if th_kwh > 0 and intake > 0 else None)
    add("en_total_kwh", "cost", "kwh", el_kwh + th_kwh if el_kwh + th_kwh > 0 else None)
    co2 = None
    if (pf.ef_el > 0 or el_kwh == 0) and (pf.ef_th > 0 or th_kwh == 0) and el_kwh + th_kwh > 0:
        co2 = el_kwh * pf.ef_el + th_kwh * pf.ef_th
    need_ef = tuple(n for n, kwh in (("ef_el", el_kwh), ("ef_th", th_kwh)) if kwh > 0)
    add("en_co2", "cost", "kg", co2, need_ef)
    add("en_co2_per_m3", "cost", "kg_m3", _div(co2, intake) if co2 is not None else None, need_ef)

    # ------------------------------------------------------------ data quality
    add("q_closure", "quality", "pct", b.closure_pct)
    add("q_source_gap", "quality", "pct",
        100 * b.source_side_imbalance / b.metered_intake if b.source_side_imbalance is not None and b.metered_intake else None)
    add("q_discharge_gap", "quality", "pct",
        100 * b.discharge_side_imbalance / b.metered_discharge
        if b.discharge_side_imbalance is not None and b.metered_discharge else None)
    out_metered = {o.name for o in plant.outlets if o.metered_m3 is not None}
    add("q_outlet_meter_cover", "quality", "pct",
        100 * sum(dout.get(n, 0.0) for n in out_metered) / disch if disch > 0 else None)
    add("q_balanced_share", "quality", "pct",
        100 * sum(1 for s in b.subsystems if s.status == "balanced") / len(b.subsystems) if b.subsystems else None)
    entered = sum(1 for n in PROFILE_FIELDS if getattr(pf, n, 0) > 0)
    add("q_completeness", "quality", "pct", 100.0 * entered / len(PROFILE_FIELDS))

    # ------------------------------------------------------------------ targets
    add("tg_intake_unit", "target", "m3_unit", k.intake_per_unit - pf.target_intake_per_unit
        if k.intake_per_unit is not None else None, ("target_intake_per_unit",))
    add("tg_intake_unit_pct", "target", "pct", 100 * (k.intake_per_unit / pf.target_intake_per_unit - 1)
        if k.intake_per_unit is not None and pf.target_intake_per_unit > 0 else None, ("target_intake_per_unit",))
    add("tg_recirc", "target", "pp", 100 * k.recirculation_ratio - pf.target_recirc_pct
        if k.recirculation_ratio is not None else None, ("target_recirc_pct",))
    add("tg_loss", "target", "pp", 100 * k.unaccounted_fraction - pf.target_loss_pct
        if k.unaccounted_fraction is not None else None, ("target_loss_pct",))

    # --------------------------------------------------------------------- plan
    pr = evaluate_plan(plant) if plant.plan else None
    have = pr is not None and bool(pr.lines)
    add("pl_saving", "plan", "m3", pr.saving if have else None)
    add("pl_saving_pct", "plan", "pct", pr.saving_pct if have else None)
    after = intake - pr.saving if have else None
    add("pl_intake_after", "plan", "m3", after)
    add("pl_unit_after", "plan", "m3_unit", _div(after, units) if after is not None else None)
    add("pl_value", "plan", "cur", pr.annual_value if have else None)
    add("pl_capex", "plan", "cur", pr.capex if have and pr.capex > 0 else None)
    add("pl_capex_per_daily", "plan", "cur_m3day", pr.capex / (pr.saving / 365.0) if have and pr.saving > 0 and pr.capex > 0 else None)
    add("pl_payback", "plan", "years", pr.payback if have else None)

    # -------------------------------------------------------------- time series
    from . import timeseries as _ts
    for i_id, i_unit, i_val, i_reason in _ts.time_indicators(plant):
        if i_val is None:
            out.append(Indicator(i_id, "time", i_unit, None, [], i_reason or "series"))
        else:
            out.append(Indicator(i_id, "time", i_unit, float(i_val)))

    # ---------------------------------------------------------- per subsystem
    bal = {x.name: x for x in b.subsystems}
    cst = {x.name: x for x in c.subsystems}
    sub_rows: List[SubIndicators] = []
    bal, cst = b.nodes or bal, c.nodes or cst
    for s in plant.ordered():
        bx, cx = bal.get(s.name), cst.get(s.name)
        inflow = s.total_intake + s.from_other
        gross_x = inflow + s.recirculated
        q = pf.sub_production.get(s.name, 0.0)
        v: Dict[str, Optional[float]] = {
            "intake": s.total_intake,
            "intake_share": 100 * c.water_share.get(s.name, 0.0),
            "cost_share": 100 * c.cost_share.get(s.name, 0.0),
            "cost_per_m3": cx.per_m3_intake if cx else None,
            "loss_pct": 100 * bx.unknown_loss_pct_of_inflow if bx else None,
            "consumptive": _pct(s.evaporation + s.product, inflow),
            "discharge": _pct(s.total_discharge, inflow),
            "reuse": _pct(s.from_other, inflow),
            "recirc": _pct(s.recirculated, gross_x),
            "per_unit": _div(s.total_intake, q) if q > 0 else None,
            "cycles": None, "blowdown": None, "lpd": None,
        }
        if s.kind in ("cooling_tower", "boiler"):
            mc, bc = s.params.get("mc", 0.0), s.params.get("bc", 0.0)
            v["cycles"] = bc / mc if mc > 0 and bc > 0 else None
            v["blowdown"] = _pct(s.total_discharge, s.total_intake)
        if s.kind == "sanitary":
            e_, d_ = pf.employees or s.params.get("employees", 0.0), pf.working_days or s.params.get("days", 0.0)
            v["lpd"] = 1000.0 * s.total_intake / (e_ * d_) if e_ > 0 and d_ > 0 else None
        sub_rows.append(SubIndicators(s.name, s.kind, v))

    done = sum(1 for i in out if i.value is not None)
    return IndicatorSet(out, sub_rows, 100.0 * entered / len(PROFILE_FIELDS), 100.0 * done / len(out))


def _pct(a: float, b: float) -> Optional[float]:
    return 100.0 * a / b if b and b > 0 else None


def _pct100(frac: Optional[float]) -> Optional[float]:
    return None if frac is None else 100.0 * frac
