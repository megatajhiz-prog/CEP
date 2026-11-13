"""Built-in demonstration plant (a mid-size manufacturing site), in English or Persian."""

from __future__ import annotations

from .estimators import boiler_water, cooling_tower_water, irrigation_water, process_water, sanitary_water
from .units import REFRIG_TON_TO_KW
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
CT_PARAMS = {"hours": 6000, "load": 0.7, "kw": 1407, "dt": 5.5, "mc": 300, "bc": 1200}
BOILER_PARAMS = {"hours": 7000, "load": 0.6, "steam": 4695, "fc": 200, "mc": 400, "bc": 2800}
PROCESS_PARAMS = {"units": 50_000, "g": 0.8, "r": 0.25, "p": 0.1}
SANITARY_PARAMS = {"employees": 250, "days": 300, "lpd": 80}
IRRIGATION_PARAMS = {"area": 4000, "depth": 600}


def demo_plant(lang: str = "en") -> Plant:
    n = _NAMES.get(lang, _NAMES["en"])
    ct = cooling_tower_water(hours_per_year=CT_PARAMS["hours"], tonnage=CT_PARAMS["kw"] / REFRIG_TON_TO_KW,
                             load_fraction=CT_PARAMS["load"], delta_t_c=CT_PARAMS["dt"],
                             makeup_conductivity=CT_PARAMS["mc"], blowdown_conductivity=CT_PARAMS["bc"])
    bo = boiler_water(hours_per_year=BOILER_PARAMS["hours"], load_fraction=BOILER_PARAMS["load"],
                      rated_steam_kg_per_h=BOILER_PARAMS["steam"], feedwater_conductivity=BOILER_PARAMS["fc"],
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

    plant = Plant(
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
    plant.ensure_products("محصول" if lang == "fa" else "Product")
    return plant


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
        name="کارخانهٔ نمونه" if fa else "Demo plant site", owner="شرکت نمونه" if fa else "Demo Co.",
        sector="صنایع غذایی" if fa else "Food and beverage", province="البرز" if fa else "Alborz",
        city="کرج" if fa else "Karaj", land_area_m2=60_000, commissioning_year=1392 if fa else 2013,
        shifts_per_day=2, calendar="jalali" if fa else "gregorian",
        areas=[Area("سالن تولید" if fa else "Production hall", "production"),
               Area("تأسیسات" if fa else "Utilities", "utility"),
               Area("اداری و رفاهی" if fa else "Administration", "services"),
               Area("فضای سبز" if fa else "Landscape", "landscape")],
        products=[Product("محصول الف" if fa else "Product A", n["unit"], per_year=30_000),
                  Product("محصول ب" if fa else "Product B", n["unit"], per_year=20_000)],
        meters=[Meter("کنتور چاه" if fa else "Well meter", f"source:{n['well']}", "flow", "m3", 1.0, "", "2026-03-10"),
                Meter("کنتور شهری" if fa else "City meter", f"source:{n['city']}", "flow", "m3", 1.0, "", "2026-03-10"),
                Meter("کنتور برق" if fa else "Power meter", "energy:el", "energy", "kwh", 0.5, "", "2025-11-02")])
    p.sync_production()
    p.profile.working_days = 300
    a_, b_ = p.site.products[0].name, p.site.products[1].name
    p.allocation = {n["process"]: {a_: 0.6, b_: 0.4}, n["ct"]: {a_: 0.5, b_: 0.5}, n["boiler"]: {a_: 0.6, b_: 0.4}}   # sanitary and landscape stay general
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
        rows = {f"production:{p.site.products[0].name}": prod * 0.6, f"production:{p.site.products[1].name}": prod * 0.4,
                f"source:{city}": city_m, f"source:{well}": well_m, f"outlet:{sewer}": sew_m,
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


# ------------------------------------------------------------------------------------------------- ORNL pilot 3
_ORNL = {
    "en": dict(plant="ORNL pilot 3: vinyl siding plant", unit="t", product="Vinyl siding",
               w1="Municipal water 1", w2="Municipal water 2", s1="Municipal sewer 1", s2="Municipal sewer 2 (third-party)",
               t_ct="Chemical treatment 1", t_ot="Chemical treatment 2", t_cl="Chlorine",
               vac="Process: vacuum pumps", quench="Process: quench tanks", wash="Process: wash bay",
               ct="Cooling tower for process", kitchen="Kitchen and restrooms", other="Other: process water loop",
               pump="Pump and motor", site="Vinyl siding plant (pilot training 3)", sector="Plastics",
               note=("Rebuilt from Malhotra et al. (2021), ORNL/TM-2021/1918, section 3.3, Figs. 11-13. Flows are the report's "
                     "percentages of plant intake, scaled to an assumed 400 000 m3/yr. Unit prices were solved from Fig. 13 "
                     "(cost contributions per m3; the report quotes them per thousand US gallons), and the pump energy from the same figure; the report does not print them. "
                     "Capital costs and savings in the plan are assumptions for illustration, not data from the report.")),
    "fa": dict(plant="نمونهٔ ORNL: کارخانهٔ سایدینگ وینیل", unit="تن", product="سایدینگ وینیل",
               w1="آب شهری ۱", w2="آب شهری ۲", s1="فاضلاب شهری ۱", s2="فاضلاب شهری ۲ (شخص ثالث)",
               t_ct="تصفیهٔ شیمیایی ۱", t_ot="تصفیهٔ شیمیایی ۲", t_cl="کلر",
               vac="فرایند: پمپ‌های خلأ", quench="فرایند: تانک‌های کوئنچ", wash="فرایند: محل شست‌وشو",
               ct="برج خنک‌کن فرایند", kitchen="آشپزخانه و سرویس‌ها", other="سایر: حلقهٔ آب فرایند",
               pump="پمپ و موتور", site="کارخانهٔ سایدینگ وینیل (آموزش پایلوت ۳)", sector="پلاستیک",
               note=("بازسازی از Malhotra و همکاران (۲۰۲۱)، ORNL/TM-2021/1918، بخش ۳٫۳ و شکل‌های ۱۱ تا ۱۳. جریان‌ها درصدهای گزارش "
                     "از آب ورودی کارخانه‌اند و در مقیاس فرضی ۴۰۰٬۰۰۰ مترمکعب در سال آمده‌اند. قیمت‌های واحد و انرژی پمپ‌ها از "
                     "شکل ۱۳ (سهم‌های هزینه بر مترمکعب؛ گزارش آن‌ها را بر هزار گالن آمریکا چاپ کرده) برعکس حساب شده‌اند، چون گزارش آن‌ها را چاپ نکرده است. هزینهٔ سرمایه‌گذاری "
                     "و صرفه‌جویی‌های طرح فرضی و فقط برای آموزش‌اند، نه داده‌ای از گزارش.")),
}


def ornl_pilot3(lang: str = "en") -> Plant:
    """The worked example of the ORNL Plant Water Profiler report (pilot training 3, a vinyl siding plant).

    Water volumes are the report's percentages of plant-level intake (Fig. 11); unit prices follow from the true-cost
    contributions of Fig. 13. With them the program reproduces the report: subsystem intake 101.7 %, evaporation 12.4 %,
    discharge 89.3 %, boundary imbalance 7.2 %, true cost 2.12 $/m3 (8.01 $/kGal in the report) = 1.45 x the direct cost."""
    from .model import Area, Product, Site

    n = _ORNL.get(lang, _ORNL["en"])
    kgal = 3.78541                                   # m3 per thousand US gallons (report prices are per kGal)
    u = 400_000 / 100.0                              # m3 for 1 % of plant-level intake (assumed scale)
    v = lambda pct: pct * u                          # noqa: E731
    pm = lambda price: price / kgal                  # noqa: E731  $/kGal -> $/m3
    el = 0.10
    sys_m3 = 101.73 * u                              # sum of subsystem intake, m3

    def kw(contribution: float) -> float:            # pump power whose energy cost is the report's $/kGal contribution
        return contribution / kgal * sys_m3 / el / 8000.0

    subs = [
        Subsystem(n["vac"], "process", intake={n["w1"]: v(55.4)}, recirculated=v(2.8), discharge={n["s1"]: v(55.4)}),
        Subsystem(n["quench"], "process", intake={n["w1"]: v(23.8)}, evaporation=v(1.2), discharge={n["s1"]: v(22.6)},
                  water_treatments={n["t_cl"]: 1.0}, pumps=[Pump(n["pump"], 8000, power_kw=kw(0.33), efficiency=1.0)]),
        Subsystem(n["wash"], "process", intake={n["w2"]: v(9.5)}, evaporation=v(0.93), discharge={n["s2"]: v(8.5)}),
        Subsystem(n["ct"], "cooling_tower", intake={n["w1"]: v(11.6)}, evaporation=v(9.6), discharge={n["s1"]: v(2.0)},
                  water_treatments={n["t_ct"]: 1.0}, pumps=[Pump(n["pump"], 8000, power_kw=kw(1.81), efficiency=1.0)]),
        Subsystem(n["kitchen"], "sanitary", intake={n["w2"]: v(1.16)}, evaporation=v(0.36), discharge={n["s2"]: v(0.8)}),
        Subsystem(n["other"], "process", intake={n["w1"]: v(0.27)}, evaporation=v(0.27), water_treatments={n["t_ot"]: 1.0}),
    ]
    production = sys_m3 / (0.33 * kgal / 0.45359237)  # tonnes per year, from 0.33 kGal per 1000 lb (= 2.75 m3/t)
    plant = Plant(
        name=n["plant"], currency="USD", production_per_year=production, production_unit=n["unit"],
        sources=[Source(n["w1"], pm(2.70), v(89.4)), Source(n["w2"], pm(8.00), v(10.6))],
        outlets=[Outlet(n["s1"], pm(2.46), v(79.7)), Outlet(n["s2"], pm(3.83), v(0.73))],
        treatments=[Treatment(n["t_ct"], pm(2.63)), Treatment(n["t_ot"], pm(3.77)), Treatment(n["t_cl"], pm(0.128))],
        subsystems=subs, costs=UnitCosts(electricity_per_kwh=el, fuel_per_kwh_thermal=0.04, heating_efficiency=0.8),
        plan=[PlanItem(34, n["wash"], 17.5, capex=6000, opex=0, life_years=10, rate_pct=10),      # low-flow nozzles
              PlanItem(6, n["quench"], 3.0, capex=8000, opex=200, life_years=10, rate_pct=10),    # level control of the tanks
              PlanItem(5, "", 8.0, capex=15000, opex=0, life_years=10, rate_pct=10)])            # leak repair (sizer area drips)
    plant.site = Site(name=n["site"], sector=n["sector"], note=n["note"], calendar="jalali" if lang == "fa" else "gregorian",
                      areas=[Area(n["site"], "production")], products=[Product(n["product"], n["unit"], per_year=production)])
    plant.sync_production()
    return plant


# ------------------------------------------------------------------------------------------------ wastewater and reuse
_WW = {
    "en": dict(plant="Tutorial: wastewater collection, treatment and reuse", well="Well", city="City water",
               sewer="Sewer", env="Surface water", proc="Process washing", ct="Cooling tower", boiler="Boiler",
               san="Offices and canteen", irr="Landscape", etp="Effluent treatment plant", ro="Reverse osmosis unit",
               pump="Reclaimed water pump", product="Product", site="Food plant (wastewater tutorial)", sector="Food and beverage",
               note=("Teaching example, invented numbers. Process, cooling tower, canteen and boiler wastewater is collected "
                     "(transfers to the effluent plant). The plant removes COD but almost no salt; part of its effluent feeds a "
                     "reverse osmosis unit whose permeate replaces fresh water in the process, the cooling tower and the boiler, "
                     "and part irrigates the landscape. The rest is discharged. The effluent plant is needed anyway for the "
                     "discharge permit, so only the reverse osmosis unit is charged to reuse.")),
    "fa": dict(plant="آموزش: جمع‌آوری، تصفیه و بازچرخانی پساب", well="چاه", city="آب شهری",
               sewer="فاضلاب شهری", env="آب سطحی", proc="شست‌وشوی فرایند", ct="برج خنک‌کن", boiler="بویلر",
               san="اداری و غذاخوری", irr="فضای سبز", etp="تصفیه‌خانهٔ پساب", ro="واحد اسمز معکوس",
               pump="پمپ آب بازیافتی", product="محصول", site="کارخانهٔ غذایی (آموزش پساب)", sector="صنایع غذایی",
               note=("مثال آموزشی با عددهای فرضی. پساب فرایند، برج خنک‌کن، غذاخوری و بویلر جمع‌آوری می‌شود (انتقال به "
                     "تصفیه‌خانه). تصفیه‌خانه COD را می‌گیرد ولی تقریباً نمک را نه؛ بخشی از پساب خروجی به واحد اسمز معکوس می‌رود "
                     "و آب تراوه جای آب تازه را در فرایند، برج خنک‌کن و بویلر می‌گیرد، بخشی هم فضای سبز را آبیاری می‌کند و بقیه "
                     "تخلیه می‌شود. تصفیه‌خانه برای پروانهٔ تخلیه به هر حال لازم است؛ پس فقط واحد اسمز معکوس به حساب بازچرخانی "
                     "گذاشته می‌شود.")),
}


def wastewater_demo(lang: str = "en") -> Plant:
    """Small food plant with a closed wastewater chain: generators -> effluent plant -> RO -> reuse (balanced, 114 000 m3/yr)."""
    from .model import Area, Product, Site, Transfer

    n = _WW.get(lang, _WW["en"])
    subs = [
        Subsystem(n["proc"], "process", intake={n["well"]: 70_000}, from_other=10_000, product=12_000, evaporation=3_000,
                  to_other=58_000, discharge={n["sewer"]: 7_000}),
        Subsystem(n["ct"], "cooling_tower", intake={n["city"]: 24_000}, from_other=6_000, evaporation=20_000,
                  to_other=7_000, discharge={n["sewer"]: 3_000}),
        Subsystem(n["boiler"], "boiler", intake={n["city"]: 7_000}, from_other=2_000, evaporation=6_500,
                  discharge={n["sewer"]: 2_500}),
        Subsystem(n["san"], "sanitary", intake={n["city"]: 8_000}, evaporation=500, to_other=7_500),
        Subsystem(n["irr"], "irrigation", intake={n["well"]: 5_000}, from_other=6_000, evaporation=11_000),
        Subsystem(n["etp"], "wwtp", from_other=72_500, product=1_500, evaporation=500, to_other=30_000,
                  discharge={n["env"]: 40_500},
                  params={"cod_in": 1800, "cod_out": 60, "tds_in": 1500, "tds_out": 1400, "cod_limit": 100, "tds_limit": 2000,
                          "capacity": 90_000, "opex_m3": 0.30, "capex": 250_000, "life": 15, "required": 1},
                  pumps=[Pump(n["pump"], 6000, power_kw=22.0)]),
        Subsystem(n["ro"], "wwtp", from_other=24_000, evaporation=500, to_other=18_000, discharge={n["sewer"]: 5_500},
                  params={"cod_in": 60, "cod_out": 5, "tds_in": 1400, "tds_out": 40, "capacity": 30_000,
                          "opex_m3": 0.45, "capex": 120_000, "life": 15}),
    ]
    links = [Transfer(n["proc"], n["etp"], 58_000), Transfer(n["ct"], n["etp"], 7_000), Transfer(n["san"], n["etp"], 7_500),
             Transfer(n["etp"], n["ro"], 24_000), Transfer(n["etp"], n["irr"], 6_000),
             Transfer(n["ro"], n["proc"], 10_000), Transfer(n["ro"], n["ct"], 6_000), Transfer(n["ro"], n["boiler"], 2_000)]
    plant = Plant(
        name=n["plant"], currency="USD", production_per_year=40_000, production_unit="t",
        sources=[Source(n["well"], 0.50, 75_000), Source(n["city"], 1.80, 39_000)],
        outlets=[Outlet(n["sewer"], 1.20, 18_000), Outlet(n["env"], 0.10, 40_500)],
        subsystems=subs, links=links, costs=UnitCosts(electricity_per_kwh=0.08, fuel_per_kwh_thermal=0.04, heating_efficiency=0.8))
    plant.site = Site(name=n["site"], sector=n["sector"], note=n["note"], calendar="jalali" if lang == "fa" else "gregorian",
                      areas=[Area(n["site"], "production")], products=[Product(n["product"], "t", per_year=40_000)])
    plant.sync_production()
    return plant


# ------------------------------------------------------------------------------------------------ water treatment chain
_WT = {
    "en": dict(plant="Tutorial: pre-treatment and demineralised water", well="Well", city="City water", sewer="Sewer",
               pre="Pre-treatment (clarifier + filters)", dm="Demineralised water unit (RO)", boiler="Boiler",
               proc="Process", ct="Cooling tower", site="Plant with a water treatment chain", sector="Chemicals", product="Product",
               note=("Teaching example, invented numbers. Raw water is first pre-treated (the back-wash is waste). Part of the "
                     "filtered water goes to a reverse-osmosis demineralised-water unit (the reject is waste); its permeate is the "
                     "boiler make-up and some process uses. The rest of the filtered water goes straight to the process and the "
                     "cooling tower. The page 'Water treatment' follows the cost of the water along the chain.")),
    "fa": dict(plant="آموزش: پیش‌تصفیه و تولید آب دمین", well="چاه", city="آب شهری", sewer="فاضلاب شهری",
               pre="پیش‌تصفیه (زلال‌ساز و فیلتر)", dm="واحد تولید آب دمین (اسمز معکوس)", boiler="بویلر",
               proc="فرایند", ct="برج خنک‌کن", site="کارخانه با زنجیرهٔ تصفیهٔ آب", sector="شیمیایی", product="محصول",
               note=("مثال آموزشی با عددهای فرضی. آب ورودی نخست پیش‌تصفیه می‌شود (شست‌وشوی معکوس فیلترها پساب است). بخشی از آب "
                     "فیلترشده به واحد آب دمین (اسمز معکوس) می‌رود (پساب غلیظ دور ریخته می‌شود) و تراوهٔ آن آب جبرانی بویلر و "
                     "برخی مصارف فرایند است. بقیهٔ آب فیلترشده مستقیم به فرایند و برج خنک‌کن می‌رود. صفحهٔ «تصفیهٔ آب» هزینهٔ آب را "
                     "در طول زنجیره دنبال می‌کند.")),
}


def water_treatment_demo(lang: str = "en") -> Plant:
    """Raw water -> pre-treatment -> RO demineralised water -> boiler make-up and process (balanced, 120 000 m3/yr)."""
    from .model import Area, Product, Site, Transfer

    n = _WT.get(lang, _WT["en"])
    subs = [
        Subsystem(n["pre"], "wtp", intake={n["well"]: 100_000, n["city"]: 20_000}, to_other=114_000,
                  discharge={n["sewer"]: 6_000},
                  params={"tds_in": 600, "tds_out": 580, "capacity": 150_000, "opex_m3": 0.06, "kwh_m3": 0.15,
                          "capex": 60_000, "life": 15, "min_yield": 90}),
        Subsystem(n["dm"], "wtp", from_other=40_000, to_other=30_000, discharge={n["sewer"]: 10_000},
                  params={"tds_in": 580, "tds_out": 8, "capacity": 50_000, "opex_m3": 0.35, "kwh_m3": 1.2,
                          "capex": 180_000, "life": 15, "min_yield": 70}),
        Subsystem(n["boiler"], "boiler", from_other=22_000, evaporation=18_000, discharge={n["sewer"]: 4_000}),
        Subsystem(n["proc"], "process", from_other=62_000, product=20_000, evaporation=5_000, discharge={n["sewer"]: 37_000}),
        Subsystem(n["ct"], "cooling_tower", from_other=20_000, evaporation=16_000, discharge={n["sewer"]: 4_000}),
    ]
    links = [Transfer(n["pre"], n["dm"], 40_000), Transfer(n["pre"], n["proc"], 54_000), Transfer(n["pre"], n["ct"], 20_000),
             Transfer(n["dm"], n["boiler"], 22_000), Transfer(n["dm"], n["proc"], 8_000)]
    plant = Plant(
        name=n["plant"], currency="USD", production_per_year=40_000, production_unit="t",
        sources=[Source(n["well"], 0.60, 100_000), Source(n["city"], 1.50, 20_000)],
        outlets=[Outlet(n["sewer"], 1.00, 61_000)],
        subsystems=subs, links=links, costs=UnitCosts(electricity_per_kwh=0.08, fuel_per_kwh_thermal=0.04, heating_efficiency=0.8))
    plant.site = Site(name=n["site"], sector=n["sector"], note=n["note"], calendar="jalali" if lang == "fa" else "gregorian",
                      areas=[Area(n["site"], "production")], products=[Product(n["product"], "t", per_year=40_000)])
    plant.sync_production()
    return plant
