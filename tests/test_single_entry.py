import pytest

from waterprofiler import timeseries as TS
from waterprofiler.estimate_apply import shared_params
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
