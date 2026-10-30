import pytest

from waterprofiler import estimators as est
from waterprofiler.balance import subsystem_balance
from waterprofiler.estimate_apply import PARAMS, apply_estimate, estimate
from waterprofiler.model import Subsystem
from waterprofiler.numparse import fmt_float, parse_float


@pytest.mark.parametrize("text,expected", [
    ("12.5", 12.5), ("۱۲٫۵", 12.5), ("١٢٫٥", 12.5), ("1,234.5", 1234.5), ("۱٬۲۳۴", 1234.0),
    (" 7 ", 7.0), ("−3", -3.0), ("1e3", 1000.0), (None, None), ("", None), ("abc", None), (5, 5.0),
])
def test_parse_float(text, expected):
    assert parse_float(text) == expected


def test_fmt_roundtrip():
    for v in (0.1, 1234.5678, 1e-7, 123456789.0):
        assert parse_float(fmt_float(v)) == pytest.approx(v)
    assert fmt_float(None) == ""


CASES = {
    "process": dict(units=1000, g=2.0, r=0.2, p=0.1),
    "cooling_tower": dict(hours=6000, load=0.7, tons=400, dt=5.5, mc=300, bc=1200),
    "boiler": dict(hours=7000, load=0.6, bhp=300, fc=200, mc=400, bc=2800),
    "sanitary": dict(employees=100, days=250, lpd=80),
    "irrigation": dict(area=4000, depth=600),
}


@pytest.mark.parametrize("kind", list(CASES))
def test_applied_estimates_balance(kind):
    assert set(CASES[kind]) == set(PARAMS[kind])
    s = Subsystem("x")
    apply_estimate(s, kind, CASES[kind], "Src", "Out")
    b = subsystem_balance(s)
    assert abs(b.unknown_loss) < 1e-6 * max(1.0, b.inflow), (kind, b)
    assert s.params == CASES[kind]


def test_estimate_unknown_kind():
    with pytest.raises(est.InputError):
        estimate("other", {})
