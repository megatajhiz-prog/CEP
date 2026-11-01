"""Built-in demonstration plant (a mid-size manufacturing site), in English or Persian."""

from __future__ import annotations

from .estimators import boiler_water, cooling_tower_water, irrigation_water, process_water, sanitary_water
from .model import Outlet, Plant, Pump, Source, Subsystem, Treatment, UnitCosts

_NAMES = {
    "en": {
        "plant": "Demo plant", "unit": "unit",
        "city": "Municipal", "well": "Well", "sewer": "Sewer", "none": "Evaporation/none",
        "soft": "Softening", "ro": "RO", "chem": "Cooling chemicals", "etp": "Effluent treatment",
        "process": "Process", "ct": "Cooling tower", "boiler": "Boiler", "sanitary": "Sanitary",
        "land": "Landscaping",
        "p_process": "Process pumps", "p_cool": "Cooling pumps", "p_feed": "Feedwater pumps",
    },
    "fa": {
        "plant": "کارخانهٔ نمونه", "unit": "واحد",
        "city": "شبکهٔ شهری", "well": "چاه", "sewer": "فاضلاب شهری", "none": "تبخیر/بدون تخلیه",
        "soft": "نرم‌سازی", "ro": "اسمز معکوس", "chem": "مواد شیمیایی خنک‌کن", "etp": "تصفیهٔ پساب",
        "process": "فرایند", "ct": "برج خنک‌کن", "boiler": "بویلر", "sanitary": "بهداشتی",
        "land": "فضای سبز",
        "p_process": "پمپ‌های فرایند", "p_cool": "پمپ‌های خنک‌کاری", "p_feed": "پمپ‌های آب تغذیه",
    },
}

# Estimator inputs, kept on the subsystems so 'Estimate from specifications' and the
# savings tab work on the demo exactly as on a user's own data.
CT_PARAMS = {"hours": 6000, "load": 0.7, "tons": 400, "dt": 5.5, "mc": 300, "bc": 1200}
BOILER_PARAMS = {"hours": 7000, "load": 0.6, "bhp": 300, "fc": 200, "mc": 400, "bc": 2800}
PROCESS_PARAMS = {"units": 50_000, "g": 0.8, "r": 0.25, "p": 0.1}
SANITARY_PARAMS = {"employees": 250, "days": 300, "lpd": 80}
IRRIGATION_PARAMS = {"area": 4000, "depth": 600}


def demo_plant(lang: str = "en") -> Plant:
    n = _NAMES.get(lang, _NAMES["en"])
    ct = cooling_tower_water(hours_per_year=CT_PARAMS["hours"], tonnage=CT_PARAMS["tons"],
                             load_fraction=CT_PARAMS["load"], delta_t_c=CT_PARAMS["dt"],
                             makeup_conductivity=CT_PARAMS["mc"], blowdown_conductivity=CT_PARAMS["bc"])
    bo = boiler_water(hours_per_year=BOILER_PARAMS["hours"], load_fraction=BOILER_PARAMS["load"],
                      bhp=BOILER_PARAMS["bhp"], feedwater_conductivity=BOILER_PARAMS["fc"],
                      makeup_conductivity=BOILER_PARAMS["mc"], blowdown_conductivity=BOILER_PARAMS["bc"])
    pr = process_water(units_per_year=PROCESS_PARAMS["units"], water_use_per_unit_m3=PROCESS_PARAMS["g"],
                       recycled_fraction=PROCESS_PARAMS["r"], consumed_in_product_per_unit_m3=PROCESS_PARAMS["p"])
    sa = sanitary_water(employees=SANITARY_PARAMS["employees"], days_per_year=SANITARY_PARAMS["days"],
                        litres_per_employee_day=SANITARY_PARAMS["lpd"])
    ir = irrigation_water(area_m2=IRRIGATION_PARAMS["area"], depth_mm_per_year=IRRIGATION_PARAMS["depth"])

    well, city, sewer = n["well"], n["city"], n["sewer"]

    subs = [
        Subsystem(n["process"], "process", intake={city: pr.makeup}, recirculated=pr.recirc,
                  product=pr.product, evaporation=0.0, discharge={sewer: pr.makeup - pr.product},
                  water_treatments={n["soft"]: 0.6}, wastewater_treatments={n["etp"]: 1.0},
                  pumps=[Pump(n["p_process"], 6500, power_kw=45, efficiency=0.88, load_fraction=0.8)],
                  t_intake_c=18, t_wastewater_c=38, params=dict(PROCESS_PARAMS)),
        Subsystem(n["ct"], "cooling_tower", intake={well: ct.makeup}, recirculated=ct.recirc,
                  evaporation=ct.evap, discharge={sewer: ct.blowdown},
                  water_treatments={n["chem"]: 1.0},
                  pumps=[Pump(n["p_cool"], 6000, power_kw=75, efficiency=0.9, load_fraction=0.85)],
                  t_intake_c=20, t_wastewater_c=30, params=dict(CT_PARAMS)),
        Subsystem(n["boiler"], "boiler", intake={city: bo.makeup}, recirculated=bo.recirc,
                  evaporation=bo.evap, discharge={sewer: bo.blowdown},
                  water_treatments={n["soft"]: 1.0, n["ro"]: 0.5},
                  pumps=[Pump(n["p_feed"], 7000, power_kw=22, efficiency=0.85, load_fraction=0.6)],
                  t_intake_c=18, t_wastewater_c=95, params=dict(BOILER_PARAMS)),
        Subsystem(n["sanitary"], "sanitary", intake={city: sa.makeup}, discharge={sewer: sa.blowdown},
                  params=dict(SANITARY_PARAMS)),
        Subsystem(n["land"], "irrigation", intake={well: ir.makeup}, evaporation=ir.evap,
                  params=dict(IRRIGATION_PARAMS)),
    ]

    # Plant meters read slightly different from the bottom-up sums, as in practice.
    sum_city = sum(s.intake.get(city, 0.0) for s in subs)
    sum_well = sum(s.intake.get(well, 0.0) for s in subs)
    sum_sew = sum(s.discharge.get(sewer, 0.0) for s in subs)

    return Plant(
        name=n["plant"], currency="USD", production_per_year=50_000, production_unit=n["unit"],
        sources=[Source(city, 1.40, round(sum_city * 1.03)), Source(well, 0.15, round(sum_well * 0.98))],
        outlets=[Outlet(sewer, 1.90, round(sum_sew * 1.02)), Outlet(n["none"], 0.0)],
        treatments=[Treatment(n["soft"], 0.35), Treatment(n["ro"], 1.10), Treatment(n["chem"], 0.20),
                    Treatment(n["etp"], 0.60, wastewater=True)],
        subsystems=subs,
        costs=UnitCosts(electricity_per_kwh=0.11, fuel_per_kwh_thermal=0.035, heating_efficiency=0.80),
    )
