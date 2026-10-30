# Mathematical formulation

Methodology: Malhotra et al., *Plant Water Profiler*, ORNL/TM-2021/1918. All
volumes are stored in **m³/year**; the report's US units are converted at the
boundary (1 US gal = 0.003785411784 m³, 1 lb = 0.45359237 kg, 1 refrigeration
ton = 3.516852842 kW). Every formula below is covered by a hand-calculation test
in `tests/test_engine.py`.

Notation per subsystem *x*: **I** intake (by source), **W** discharge (by outlet),
**E** evaporation / consumptive loss, **P** water leaving in product,
**R** internal recirculation, **R′in / R′out** water received from / sent to another
subsystem, **G** gross use, **M** makeup, **B** blowdown, **C** cycles of concentration.

## 1. Bottom-up estimators (`estimators.py`)

| Subsystem | Equations |
|---|---|
| Process | G = N·g, R = G·r, M = G − R, P = N·p |
| Cooling tower | G = 3 gpm/ton · tons · L · H · 60;  E = G · (e/100) · ΔT[°F]/10 (e = 0.85 %/10 °F);  C = B꜀/M꜀;  M = E / (1 − 1/C);  B = M − E;  R = G − M |
| Once-through cooling | I = G = W = F·H |
| Boiler | C = B꜀/F꜀;  S = BHP · 34.5 lb/h;  G = S / (1 − 1/C) · L · H;  M = (F꜀/M꜀) · G;  B = G / C;  E = M − B;  R = G − M |
| Sanitary | G = employees · days · litres per person-day |
| Landscaping | G = E = area · depth |

Conductivity ratios must give C > 1; boiler feedwater cannot be dirtier than
makeup. Violations raise `InputError` rather than returning a number.

## 2. Water balance (`balance.py`)

Subsystem unaccounted loss:

    L_x = (I_x + R′in) − (R′out + P_x + E_x + W_x)

Plant:

    L = ΣI − (ΣP + ΣE + ΣW)

Calibration compares ΣI with the metered / billed source water and ΣW with the
metered discharge. Plant closure error = metered intake − metered discharge − ΣE − ΣP.
A subsystem is flagged *unaccounted loss* (L > 2 % of inflow, typically leaks),
*excess outflow* (L < −2 %, inconsistent data) or *balanced*.
Inter-subsystem transfers must cancel across the plant; otherwise a warning is raised.

## 3. True cost of water (`cost.py`)

    $_x = Σ_s $_s·I_x,s + Σ_o $_o·W_x,o + Σ_t $_t·T_x,t + Σ_t′ $_t′·T′_x,t′ + $_elec·Elec_x + $_fuel·Fuel_x

* T_x,t = f_x,t · (I_x + R′in): water treated before use, f = fraction treated.
* T′_x,t′ = f_x,t′ · W_x: wastewater treated before discharge.
* Pump energy: kW · load · H / η, or V·A·pf·H/1000 (single phase) and ×√3 (three phase).
* Heat lost in discharge: Fuel = ρ·W·c_p·(T_ww − T_in) / 3600 / η_heating, zero when
  the wastewater is not warmer than the intake.

Reported: cost by component and subsystem, true-to-direct cost ratio
(direct = source water + discharge fees), true cost per m³ of intake, and shares of
water vs cost per subsystem. A subsystem is prioritised for *volume* (≥ 20 % of
intake), *cost* (cost share ≥ 1.25 × water share and ≥ 5 %), or *both*.

## 4. Savings (`savings.py`)

* Cooling tower: M′ = E / (1 − 1/C′); ΔM = M − M′; ΔB = B − B′ (B′ = M′ − E).
* Boiler: G′ = S/(1 − 1/C′)·L·H; M′ = (1 − r′)·G′; B′ = G′/C′.
* Leaks: saved = rate · hours · fraction fixed.
* Cost saving = ΔM·($_water + $_treatment) + ΔB·$_discharge; payback = capex / annual saving.

## 5. Data reconciliation (`reconcile.py`, an addition to the report)

Minimise Σ((x − x₀)/σ)² subject to A·x = b, where the constraints are: every
subsystem closes, inter-subsystem transfers cancel, and plant meters per source /
outlet are matched exactly. Closed form x = x₀ − S·Aᵀ(A·S·Aᵀ)⁺(A·x₀ − b) with
S = diag(σ²). Negative results are pinned at zero and the problem re-solved.
Flows with larger relative uncertainty move more.

## 6. Corrections to the printed report

| Report | This implementation |
|---|---|
| Signs in the L_x equation inconsistent | L_x = inflows − outflows, R cancels |
| Landscaping formula contains an extra D | G = 0.623·d·A (US) / area·depth (SI) |
| Heat-in-wastewater sign reversed | positive when wastewater is warmer than intake |
| Motor efficiency multiplied | divided (input power = shaft power / η) |

## 7. Not included

Industry-average comparison tables (EIO-LCA, STATCAN) are not in the report and
are not bundled. Drift loss in cooling towers is ignored, as in the report.
