"""Independent hand-calculation checks of every formula in the engine."""

import math

import pytest

from waterprofiler import balance, cost, estimators as est, kpi, reconcile, savings
from waterprofiler.model import Outlet, Plant, Pump, Source, Subsystem, Treatment, UnitCosts
from waterprofiler.sample import demo_plant
from waterprofiler.units import GAL_TO_M3, LB_TO_KG

approx = lambda x, rel=1e-9: pytest.approx(x, rel=rel)


# ------------------------------------------------------------ estimators
def test_process():
    r = est.process_water(10_000, 2.0, recycled_fraction=0.25, consumed_in_product_per_unit_m3=0.3)
    assert r.gross == approx(20_000)
    assert r.recirc == approx(5_000)
    assert r.makeup == approx(15_000)
    assert r.product == approx(3_000)


def test_cooling_tower_hand_calc():
    # 400 tons, 70 % load, 6000 h, dT = 5.5 C = 9.9 F, COC = 1200/300 = 4
    r = est.cooling_tower_water(6000, 400, 0.7, 5.5, 300, 1200)
    g_gal = 3 * 400 * 0.7 * 6000 * 60
    e_gal = g_gal * 0.0085 * 9.9 / 10
    m_gal = e_gal / (1 - 1 / 4)
    assert r.gross == approx(g_gal * GAL_TO_M3)
    assert r.evap == approx(e_gal * GAL_TO_M3)
    assert r.makeup == approx(m_gal * GAL_TO_M3)
    assert r.blowdown == approx((m_gal - e_gal) * GAL_TO_M3)
    assert r.recirc == approx((g_gal - m_gal) * GAL_TO_M3)
    assert r.cycles == approx(4.0)
    # makeup = evaporation + blowdown
    assert r.makeup == approx(r.evap + r.blowdown)
    # blowdown/evaporation = 1/(C-1)
    assert r.blowdown / r.evap == approx(1 / 3)


def test_cooling_tower_rejects_bad_cycles():
    with pytest.raises(est.InputError):
        est.cooling_tower_water(6000, 400, 0.7, 5.5, 1200, 300)   # C < 1
    with pytest.raises(est.InputError):
        est.cooling_tower_water(6000, 400, 1.5, 5.5, 300, 1200)   # load > 1


def test_boiler_hand_calc():
    r = est.boiler_water(7000, 0.6, bhp=300, feedwater_conductivity=200,
                         makeup_conductivity=400, blowdown_conductivity=2800)
    s_kg_h = 300 * 34.5 * LB_TO_KG
    c = 2800 / 200
    g = s_kg_h / (1 - 1 / c) * 0.6 * 7000 / 1000
    assert r.cycles == approx(14.0)
    assert r.gross == approx(g)
    assert r.makeup == approx(0.5 * g)
    assert r.blowdown == approx(g / 14)
    assert r.evap == approx(r.makeup - r.blowdown)
    assert r.recirc == approx(g - r.makeup)
    # steam produced = G - B (all non-blowdown feedwater becomes steam)
    steam_m3 = s_kg_h * 0.6 * 7000 / 1000
    assert r.gross - r.blowdown == approx(steam_m3)


def test_boiler_rejects_feedwater_dirtier_than_makeup():
    with pytest.raises(est.InputError):
        est.boiler_water(7000, 0.6, bhp=300, feedwater_conductivity=500,
                         makeup_conductivity=400, blowdown_conductivity=2800)


def test_sanitary_and_irrigation():
    s = est.sanitary_water(100, 250, 80)
    assert s.gross == approx(100 * 250 * 80 / 1000)
    i = est.irrigation_water(1000, 600)
    assert i.gross == approx(600.0)
    assert i.evap == approx(600.0)
    # US-unit form agrees with the SI form
    sqft, inch = 10_000.0, 20.0
    us = est.irrigation_water_us(sqft, inch)
    si = est.irrigation_water(sqft * 0.09290304, inch * 25.4)
    assert us.gross == approx(si.gross, rel=2e-3)   # 0.623 is a rounded constant


def test_once_through():
    r = est.once_through_cooling(1000, 12)
    assert r.makeup == r.blowdown == r.gross == 12_000


# --------------------------------------------------------------- pumps
def test_pump_energy():
    assert Pump(power_kw=10, efficiency=0.8, hours_per_year=1000, load_fraction=0.5).kwh_per_year() == approx(6250)
    three = Pump(volts=400, amps=20, power_factor=0.85, phases=3, hours_per_year=1000).kwh_per_year()
    assert three == approx(400 * 20 * math.sqrt(3) * 0.85 / 1000 * 1000)
    one = Pump(volts=230, amps=10, power_factor=0.9, phases=1, hours_per_year=100).kwh_per_year()
    assert one == approx(230 * 10 * 0.9 / 1000 * 100)


# ------------------------------------------------------------- balance
def test_demo_balance_closes():
    p = demo_plant()
    b = balance.plant_balance(p)
    assert abs(b.unknown_loss) < 1e-6 * b.sum_intake
    assert all(s.status == "balanced" for s in b.subsystems)
    # meters were set to +3 %, -2 %, +2 % of the bottom-up sums
    assert b.source_side_imbalance is not None
    assert b.metered_intake > 0 and b.metered_discharge > 0


def test_unaccounted_loss_detected():
    s = Subsystem("Leaky", intake={"A": 1000.0}, discharge={"B": 700.0}, evaporation=100.0)
    sb = balance.subsystem_balance(s)
    assert sb.unknown_loss == approx(200.0)
    assert sb.status == "unaccounted loss"
    assert sb.unknown_loss_pct_of_inflow == approx(20.0)
    s2 = Subsystem("Over", intake={"A": 100.0}, discharge={"B": 300.0})
    assert balance.subsystem_balance(s2).status == "excess outflow"


def test_internal_transfers_cancel_in_plant_balance():
    a = Subsystem("A", intake={"S": 100.0}, to_other=40.0, discharge={"O": 60.0})
    b = Subsystem("B", from_other=40.0, discharge={"O": 40.0})
    p = Plant(sources=[Source("S")], outlets=[Outlet("O")], subsystems=[a, b])
    bal = balance.plant_balance(p)
    assert bal.unknown_loss == approx(0.0)
    assert not bal.warnings
    b.from_other = 10.0   # transfer mismatch must be flagged
    assert balance.plant_balance(p).warnings


def test_unknown_source_warning():
    p = Plant(sources=[], outlets=[], subsystems=[Subsystem("A", intake={"Ghost": 5.0})])
    assert any("Ghost" in w for w in balance.plant_balance(p).warnings)


# ---------------------------------------------------------------- cost
def test_cost_hand_calc():
    p = Plant(
        sources=[Source("City", 2.0)], outlets=[Outlet("Sewer", 3.0)],
        treatments=[Treatment("Soft", 0.5), Treatment("ETP", 1.0, wastewater=True)],
        costs=UnitCosts(electricity_per_kwh=0.1, fuel_per_kwh_thermal=0.05, heating_efficiency=0.8),
        subsystems=[Subsystem(
            "X", intake={"City": 1000.0}, discharge={"Sewer": 600.0}, evaporation=400.0,
            water_treatments={"Soft": 0.5}, wastewater_treatments={"ETP": 1.0},
            pumps=[Pump(power_kw=10, efficiency=1.0, hours_per_year=100)],
            t_intake_c=20, t_wastewater_c=40)],
    )
    c = cost.plant_cost(p)
    heat_kwh = 1000 * 600 * 4.186 * 20 / 3600 / 0.8
    sc = c.subsystems[0]
    assert sc.components["intake"] == approx(2000)
    assert sc.components["discharge"] == approx(1800)
    assert sc.components["water_treatment"] == approx(0.5 * 1000 * 0.5)
    assert sc.components["wastewater_treatment"] == approx(600)
    assert sc.components["pumping"] == approx(0.1 * 1000)
    assert sc.heat_kwh_thermal == approx(heat_kwh)
    assert sc.components["heat"] == approx(0.05 * heat_kwh)
    assert c.total == approx(sum(sc.components.values()))
    assert c.direct_billed_cost == approx(3800)
    assert c.true_to_direct_ratio == approx(c.total / 3800)
    assert c.true_cost_per_m3_intake == approx(c.total / 1000)


def test_heat_never_negative_when_wastewater_cooler():
    assert cost.heat_lost_kwh(100, 25, 20, 0.8) == 0.0
    assert cost.heat_lost_kwh(100, None, 30, 0.8) == 0.0


def test_demo_cost_has_true_cost_above_direct():
    p = demo_plant()
    c = cost.plant_cost(p)
    assert c.true_to_direct_ratio > 1.0
    assert sum(c.cost_share.values()) == approx(1.0)
    assert sum(c.water_share.values()) == approx(1.0)
    assert not c.warnings


def test_cost_unknown_treatment_warns():
    p = Plant(sources=[Source("S", 1)], outlets=[], subsystems=[
        Subsystem("X", intake={"S": 1.0}, water_treatments={"Nope": 1.0})])
    with pytest.raises(KeyError):
        cost.plant_cost(p)  # unknown treatment has no price: fail loudly rather than return 0


# ------------------------------------------------------------- savings
def test_cooling_tower_coc_savings():
    ct = est.cooling_tower_water(6000, 400, 0.7, 5.5, 300, 1200)   # C = 4
    r = savings.cooling_tower_coc(ct.evap, ct.makeup, new_cycles=6, water_unit_cost=1.0,
                                  discharge_unit_cost=2.0, treatment_unit_cost=0.5)
    m_new = ct.evap / (1 - 1 / 6)
    assert r.new_makeup == approx(m_new)
    assert r.makeup_savings == approx(ct.makeup - m_new)
    assert r.blowdown_savings == approx((ct.makeup - ct.evap) - (m_new - ct.evap))
    assert r.cost_savings == approx(r.makeup_savings * 1.5 + r.blowdown_savings * 2.0)
    # same makeup savings must equal the closed form E*(1/(C-1) - 1/(C'-1))
    assert r.makeup_savings == approx(ct.evap * (1 / 3 - 1 / 5))
    with pytest.raises(est.InputError):
        savings.cooling_tower_coc(1, 2, 1.0)


def test_boiler_savings_more_condensate_and_cycles():
    b = est.boiler_water(7000, 0.6, bhp=300, feedwater_conductivity=200,
                         makeup_conductivity=400, blowdown_conductivity=2800)
    r = savings.boiler_coc_and_condensate(b.makeup, 7000, 0.6, new_cycles=20, new_condensate_return_pct=70,
                                          bhp=300, baseline_blowdown_m3=b.blowdown)
    assert r.new_makeup < b.makeup and r.makeup_savings > 0
    assert r.blowdown_savings > 0
    with pytest.raises(est.InputError):
        savings.boiler_coc_and_condensate(1, 1, 1, 10, 120, bhp=1)


def test_leak_and_payback():
    r = savings.leak_repair(2.0, 8000, 0.5, water_unit_cost=1.0, discharge_unit_cost=2.0)
    assert r.makeup_savings == approx(8000.0)
    assert r.cost_savings == approx(8000 * 3.0)
    assert savings.simple_payback_years(24_000, 24_000) == approx(1.0)
    assert savings.simple_payback_years(1, 0) is None


# ------------------------------------------------------ KPI and ranking
def test_kpi_and_ranking_on_demo():
    p = demo_plant()
    b = balance.plant_balance(p)
    c = cost.plant_cost(p)
    k = kpi.plant_kpi(p, b, c)
    assert k.intake_per_unit == approx(b.sum_intake / 50_000)
    assert 0 < k.recirculation_ratio < 1
    assert k.unaccounted_fraction == approx(0.0, rel=0) or abs(k.unaccounted_fraction) < 1e-9
    ranked = kpi.rank_subsystems(c)
    assert ranked[0].cost >= ranked[-1].cost
    assert {r.priority for r in ranked} <= {"volume", "cost", "both", "low"}


# ------------------------------------------------------- reconciliation
def test_reconcile_closes_imbalance_and_conserves_mass():
    p = demo_plant()
    # corrupt two measurements
    p.subsystems[1].evaporation *= 1.25
    p.subsystems[0].discharge["Sewer"] *= 0.85
    before = balance.plant_balance(p)
    assert abs(before.unknown_loss) > 1.0
    r = reconcile.reconcile(p, use_meters=False)
    after = balance.plant_balance(r.plant)
    assert abs(after.unknown_loss) < 1e-6 * after.sum_intake
    assert all(abs(s.unknown_loss) < 1e-5 * max(1.0, s.inflow) for s in after.subsystems)
    assert r.residual_after < 1e-6 * max(1.0, r.residual_before)
    assert r.adjustments
    # original untouched
    assert balance.plant_balance(p).unknown_loss == approx(before.unknown_loss)


def test_reconcile_respects_trusted_measurement():
    p = demo_plant()
    p.subsystems[1].evaporation *= 1.25
    key = ("Cooling tower", "evaporation")
    r = reconcile.reconcile(p, use_meters=False, rel_sigma={key: 1e-6})
    ct = next(s for s in r.plant.subsystems if s.name == "Cooling tower")
    assert ct.evaporation == approx(p.subsystems[1].evaporation, rel=1e-4)


def test_reconcile_never_negative():
    a = Subsystem("A", intake={"S": 10.0}, discharge={"O": 100.0})
    p = Plant(sources=[Source("S")], outlets=[Outlet("O")], subsystems=[a])
    r = reconcile.reconcile(p, use_meters=False)
    s = r.plant.subsystems[0]
    assert s.intake["S"] >= 0 and s.discharge["O"] >= 0
    assert s.intake["S"] == approx(s.discharge["O"], rel=1e-6)


def test_reconcile_meters_hit_exact_totals():
    p = demo_plant()
    r = reconcile.reconcile(p, use_meters=True)
    b = balance.plant_balance(r.plant)
    assert b.source_side_imbalance == pytest.approx(0.0, abs=1e-3)
    assert b.discharge_side_imbalance == pytest.approx(0.0, abs=1e-3)


# ------------------------------------------------------- serialisation
def test_plant_roundtrip():
    p = demo_plant()
    q = Plant.from_dict(p.to_dict())
    assert q.to_dict() == p.to_dict()
    assert cost.plant_cost(q).total == approx(cost.plant_cost(p).total)


def test_persian_demo_matches_english_numbers():
    en, fa = demo_plant("en"), demo_plant("fa")
    assert [s.kind for s in en.subsystems] == [s.kind for s in fa.subsystems]
    assert cost.plant_cost(en).total == approx(cost.plant_cost(fa).total)
    assert abs(balance.plant_balance(fa).unknown_loss) < 1e-6 * balance.plant_balance(fa).sum_intake
    assert all(s.params for s in fa.subsystems)           # estimator inputs are kept for the savings tab


def test_reconcile_keeps_zero_flows_at_zero():
    p = demo_plant()
    p.subsystems[1].intake = {k: v * 1.1 for k, v in p.subsystems[1].intake.items()}   # unexplained extra makeup
    r = reconcile.reconcile(p)
    zero_before = {(s.name, f) for s in p.subsystems for f in ("from_other", "to_other", "product", "evaporation")
                   if getattr(s, f) == 0.0}
    assert zero_before
    for adj in r.adjustments:
        assert (adj.subsystem, adj.flow) not in zero_before
    for s in r.plant.subsystems:
        for f in ("from_other", "to_other", "product", "evaporation"):
            if (s.name, f) in zero_before:
                assert getattr(s, f) == 0.0
    assert not r.notes                                   # nothing needed pinning
    b = balance.plant_balance(r.plant)
    assert abs(b.unknown_loss) < 1e-6 * b.sum_intake
    assert b.source_side_imbalance == pytest.approx(0.0, abs=1e-3)
    ct = r.plant.subsystems[1]
    assert sum(ct.intake.values()) < sum(p.subsystems[1].intake.values())   # the extra water is taken back out of the cooling tower


def test_old_pump_file_with_horsepower_is_converted():
    from waterprofiler.model import _pump_from_dict
    p = _pump_from_dict({"name": "x", "power_hp": 10, "hours_per_year": 1000, "efficiency": 0.9})
    assert p.power_kw == approx(7.46) and p.kwh_per_year() == approx(10 * 0.746 / 0.9 * 1000)
