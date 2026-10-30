"""Built-in demonstration plant (a mid-size manufacturing site)."""

from __future__ import annotations

from .estimators import boiler_water, cooling_tower_water, irrigation_water, process_water, sanitary_water
from .model import Outlet, Plant, Pump, Source, Subsystem, Treatment, UnitCosts


def demo_plant() -> Plant:
    ct = cooling_tower_water(hours_per_year=6000, tonnage=400, load_fraction=0.7, delta_t_c=5.5,
                             makeup_conductivity=300, blowdown_conductivity=1200)
    bo = boiler_water(hours_per_year=7000, load_fraction=0.6, bhp=300,
                      feedwater_conductivity=200, makeup_conductivity=400, blowdown_conductivity=2800)
    pr = process_water(units_per_year=50_000, water_use_per_unit_m3=0.8, recycled_fraction=0.25,
                       consumed_in_product_per_unit_m3=0.1)
    sa = sanitary_water(employees=250, days_per_year=300, litres_per_employee_day=80)
    ir = irrigation_water(area_m2=4000, depth_mm_per_year=600)

    well, city = "Well", "Municipal"
    ww, sewer = "Wastewater plant", "Sewer"

    subs = [
        Subsystem("Process", "process", intake={city: pr.makeup}, recirculated=pr.recirc,
                  product=pr.product, evaporation=0.0, discharge={sewer: pr.makeup - pr.product},
                  water_treatments={"Softening": 0.6}, wastewater_treatments={"Effluent treatment": 1.0},
                  pumps=[Pump("Process pumps", 6500, power_kw=45, efficiency=0.88, load_fraction=0.8)],
                  t_intake_c=18, t_wastewater_c=38),
        Subsystem("Cooling tower", "cooling_tower", intake={well: ct.makeup}, recirculated=ct.recirc,
                  evaporation=ct.evap, discharge={sewer: ct.blowdown},
                  water_treatments={"Cooling chemicals": 1.0},
                  pumps=[Pump("Cooling pumps", 6000, power_kw=75, efficiency=0.9, load_fraction=0.85)],
                  t_intake_c=20, t_wastewater_c=30),
        Subsystem("Boiler", "boiler", intake={city: bo.makeup}, recirculated=bo.recirc,
                  evaporation=bo.evap, discharge={sewer: bo.blowdown},
                  water_treatments={"Softening": 1.0, "RO": 0.5},
                  pumps=[Pump("Feedwater pumps", 7000, power_kw=22, efficiency=0.85, load_fraction=0.6)],
                  t_intake_c=18, t_wastewater_c=95),
        Subsystem("Sanitary", "sanitary", intake={city: sa.makeup}, discharge={sewer: sa.blowdown}),
        Subsystem("Landscaping", "irrigation", intake={well: ir.makeup}, evaporation=ir.evap),
    ]

    # Plant meters read slightly different from the bottom-up sums, as in practice.
    sum_city = sum(s.intake.get(city, 0.0) for s in subs)
    sum_well = sum(s.intake.get(well, 0.0) for s in subs)
    sum_sew = sum(s.discharge.get(sewer, 0.0) for s in subs)

    return Plant(
        name="Demo plant", currency="USD", production_per_year=50_000, production_unit="unit",
        sources=[Source(city, 1.40, round(sum_city * 1.03)), Source(well, 0.15, round(sum_well * 0.98))],
        outlets=[Outlet(sewer, 1.90, round(sum_sew * 1.02)), Outlet("Evaporation/none", 0.0)],
        treatments=[Treatment("Softening", 0.35), Treatment("RO", 1.10), Treatment("Cooling chemicals", 0.20),
                    Treatment("Effluent treatment", 0.60, wastewater=True)],
        subsystems=subs,
        costs=UnitCosts(electricity_per_kwh=0.11, fuel_per_kwh_thermal=0.035, heating_efficiency=0.80),
    )
