import pytest

from waterprofiler import estimators as est
from waterprofiler import savings as sv
from waterprofiler.balance import plant_balance
from waterprofiler.messages import localize
from waterprofiler.model import Plant, Subsystem
from waterprofiler.sample import demo_plant


def _msg(fn):
    with pytest.raises(est.InputError) as e:
        fn()
    return str(e.value)


def test_known_engine_errors_have_persian_text():
    cases = [
        lambda: est.cooling_tower_water(6000, 100, 1.5, 5, 300, 1200),
        lambda: est.cooling_tower_water(-1, 100, 0.5, 5, 300, 1200),
        lambda: est.cooling_tower_water(6000, 100, 0.5, 5, 300, 200),
        lambda: est.cooling_tower_water(6000, 100, 0.5, 5, 0, 1200),
        lambda: est.boiler_water(7000, 0.6, 500, 400, 2800, bhp=100),
        lambda: est.boiler_water(7000, 0.6, 200, 400, 2800),
        lambda: sv.cooling_tower_coc(1000, 2000, 1.0, 1, 1, 0),
    ]
    for fn in cases:
        m = _msg(fn)
        fa = localize(m, "fa")
        assert fa != m, m
        assert not any("a" <= ch.lower() <= "z" for ch in fa.replace("BHP", "").replace("kg/h", "")), fa
        assert localize(m, "en") == m


def test_balance_warnings_localized():
    p = demo_plant("en")
    p.subsystems[0].intake["Ghost"] = 5.0
    p.subsystems[1].to_other = 100.0
    ws = plant_balance(p).warnings
    assert len(ws) == 2
    assert all(localize(w, "fa") != w for w in ws)


def test_unknown_text_is_untouched():
    assert localize("something else", "fa") == "something else"
