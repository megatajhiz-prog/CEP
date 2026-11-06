"""Built-in demonstration plant (a mid-size manufacturing site), in English or Persian."""

from __future__ import annotations

from .estimators import boiler_water, cooling_tower_water, irrigation_water, process_water, sanitary_water
from .model import Outlet, PlanItem, Plant, Pump, Source, Subsystem, Treatment, UnitCosts

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
        plan=[
            PlanItem(11, n["ct"], 12.0, capex=5000, opex=300, life_years=15, rate_pct=10),    # raise cycles of concentration
            PlanItem(23, n["boiler"], 25.0, capex=12000, opex=500, life_years=15, rate_pct=10),  # condensate return
            PlanItem(5, "", 5.0, capex=3000, opex=0, life_years=10, rate_pct=10),               # leak repair, plant-wide
            PlanItem(33, n["process"], 15.0, capex=20000, opex=1500, life_years=15, rate_pct=10),  # filter and reuse process water
        ],
    )


def demo_with_history(lang: str = "en") -> Plant:
    """The demo plant plus site data and 19 months (Jalali 1404-01 .. 1405-07) of monthly time series.

    Deterministic, seasonal (summer cooling load) and with one leak episode, so that the time-series page, the
    time-based indicators and the anomaly finder have something to show. Not real measurements."""
    import math

    from . import jcalendar as cal
    from . import timeseries as TS
    from .model import Area, Meter, Product, Site

    p = demo_plant(lang)
    n = _NAMES.get(lang, _NAMES["en"])
    fa = lang == "fa"
    p.site = Site(
        owner="شرکت نمونه" if fa else "Demo Co.",
        sector="صنایع غذایی" if fa else "Food and beverage", province="البرز" if fa else "Alborz",
        city="کرج" if fa else "Karaj", land_area_m2=60_000, commissioning_year=1392 if fa else 2013,
        shifts_per_day=2, operating_days=300, calendar="jalali" if fa else "gregorian",
        areas=[Area("سالن تولید" if fa else "Production hall", "production"),
               Area("تأسیسات" if fa else "Utilities", "utility"),
               Area("اداری و رفاهی" if fa else "Administration", "services"),
               Area("فضای سبز" if fa else "Landscape", "landscape")],
        products=[Product("محصول الف" if fa else "Product A", n["unit"]), Product("محصول ب" if fa else "Product B", n["unit"])],
        meters=[Meter("کنتور چاه" if fa else "Well meter", f"source:{n['well']}", "flow", "m3", 1.0, "", "2026-03-10"),
                Meter("کنتور شهری" if fa else "City meter", f"source:{n['city']}", "flow", "m3", 1.0, "", "2026-03-10"),
                Meter("کنتور برق" if fa else "Power meter", "energy:el", "energy", "kwh", 0.5, "", "2025-11-02")])
    for s in p.subsystems:
        s.area = {n["process"]: p.site.areas[0].name, n["ct"]: p.site.areas[1].name, n["boiler"]: p.site.areas[1].name,
                  n["sanitary"]: p.site.areas[2].name, n["land"]: p.site.areas[3].name}.get(s.name, "")
    months = cal.slices(cal.make_date("jalali", 1404, 1, 1), cal.make_date("jalali", 1405, 7, 30), "month", "jalali", lang)
    city, well, sewer = n["city"], n["well"], n["sewer"]
    sub = {s.name: s for s in p.subsystems}
    for i, m in enumerate(months):
        frac = m.days / 365.0
        season = math.cos(2 * math.pi * (m.start.timetuple().tm_yday - 200) / 365.0)       # peak in July
        prod = p.production_per_year * frac * (1.0 + 0.06 * math.sin(i * 1.7))
        leak = 1.0 + (0.60 if i in (12, 13, 14) else 0.0)                                   # a leak episode
        city_m = sum(sub[x].intake.get(city, 0.0) for x in sub) * frac * (prod / (p.production_per_year * frac)) * leak
        well_m = sum(sub[x].intake.get(well, 0.0) for x in sub) * frac * (1.0 + 0.30 * season)
        sew_m = sum(sub[x].discharge.get(sewer, 0.0) for x in sub) * frac * (prod / (p.production_per_year * frac))
        rows = {"production": prod, f"source:{city}": city_m, f"source:{well}": well_m, f"outlet:{sewer}": sew_m,
                f"sub:{n['ct']}:intake": sub[n["ct"]].total_intake * frac * (1.0 + 0.30 * season),
                f"sub:{n['process']}:intake": sub[n["process"]].total_intake * frac * (prod / (p.production_per_year * frac)),
                "loss:measured": 0.02 * (city_m + well_m) * (3.5 if i in (12, 13, 14) else 1.0),
                f"sub:{n['process']}:production": prod * 0.72,
                f"price:source:{city}": 1.40 * (1.25 if i >= 12 else 1.0),          # tariff rise in month 13
                f"price:source:{well}": 0.15 * (1.10 if i >= 12 else 1.0),
                f"price:outlet:{sewer}": 1.90 * (1.15 if i >= 12 else 1.0),
                "energy:el": 90_000.0 * (1.0 + 0.15 * season) + 6_000.0 * math.sin(i),
                "env:temp": 17.0 + 16.0 * season, "site:employees": 250.0 + (i % 4)}
        for k, v in rows.items():
            TS.put(p, k, m.start, m.end, round(v, 2))
    return p
