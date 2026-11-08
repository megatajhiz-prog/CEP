import pytest

from waterprofiler import timeseries as TS
from waterprofiler.estimate_apply import shared_params
from waterprofiler.balance import plant_balance
from waterprofiler.sample import demo_plant, demo_with_history


def test_no_series_nothing_driven():
    p = demo_plant("en")
    assert TS.driven(p) == {} and TS.sync(p) == 0


def test_series_drive_the_model_and_sync_is_idempotent():
    p = demo_with_history("en")
    d = TS.driven(p)
    assert "production_per_year" in d and "profile:employees" in d
    assert any(k.startswith("source:") and k.endswith(":metered") for k in d)
    assert TS.sync(p) > 0
    assert TS.sync(p) == 0                                   # second run changes nothing
    assert p.profile.employees == pytest.approx(251.5, rel=0.05)
    first_src = next(k for k in d if k.endswith(":metered") and k.startswith("source:"))
    assert p.source(first_src.split(":")[1]).metered_m3 > 0


def test_manual_edit_of_a_driven_field_is_undone_by_sync_but_free_fields_stay():
    p = demo_with_history("en")
    TS.sync(p)
    keep = p.profile.permit_m3 = 123456.0                    # no series for it: stays editable and untouched
    p.production_per_year = 1.0
    TS.sync(p)
    assert p.production_per_year > 1.0 and p.profile.permit_m3 == keep


def test_removing_the_series_frees_the_fields():
    p = demo_with_history("en")
    assert TS.driven(p)
    p.series.clear()
    assert TS.driven(p) == {} and TS.sync(p) == 0


def test_shared_estimator_inputs_come_from_the_profile():
    p = demo_plant("en")
    assert shared_params(p, "sanitary") == {} and shared_params(p, "irrigation") == {}
    p.profile.employees, p.profile.working_days, p.profile.green_area_m2 = 120, 280, 5000
    assert shared_params(p, "sanitary") == {"employees": 120, "days": 280}
    assert shared_params(p, "irrigation") == {"area": 5000}
    assert shared_params(p, "boiler") == {}


def test_reconcile_keeps_series_driven_flows_and_closes_the_balance():
    from waterprofiler import reconcile as R
    from waterprofiler.balance import plant_balance
    p = demo_with_history("en")
    TS.sync(p)
    sig = R.measured_sigma(p)
    assert sig and all(v < 1e-3 for v in sig.values())
    q = R.reconcile(p, rel_sigma=sig).plant
    TS.sync(q)                                               # what the application does on the next collect
    assert abs(plant_balance(q).unknown_loss) < 1e-3 * plant_balance(q).sum_intake


def test_reconcile_of_migrated_demo_balances_and_survives_sync():
    from waterprofiler import reconcile as R
    from waterprofiler import timeseries as TS
    from waterprofiler.balance import plant_balance
    from waterprofiler.sample import demo_plant
    p = demo_plant("en")
    TS.migrate_static(p)
    TS.sync(p)
    res = R.reconcile(p, default_rel_sigma=0.1, rel_sigma=R.measured_sigma(p))
    q = res.plant
    assert TS.absorb_model(q) == 0
    TS.sync(q)
    b = plant_balance(q)
    assert abs(b.unknown_loss) < 1e-3 * b.sum_intake
