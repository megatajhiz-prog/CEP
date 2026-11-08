from datetime import date

import pytest

from waterprofiler import jcalendar as cal
from waterprofiler import timeseries as T
from waterprofiler import validation as V
from waterprofiler.sample import demo_with_history


def months(p, y=2025, first=4):
    return cal.slices(date(y, first, 1), date(y, 12, 31), "month", "gregorian", "en")


def test_bad_values():
    assert V.bad_value("source:A", -1.0) and V.bad_value("source:A", 0.0) is None
    assert V.bad_value("pump:S:P:load", 1.2) and V.bad_value("pump:S:P:load", 0.8) is None
    assert V.bad_value("pump:S:P:hours", 800.0, days=30) and V.bad_value("pump:S:P:hours", 700.0, days=30) is None
    assert V.bad_value("sub:S:t_in", 120.0) and V.bad_value("sub:S:t_in", 18.0) is None
    assert V.bad_value("env:temp", -5.0) is None            # winter temperatures may be negative
    assert V.bad_value("source:A", None) is None


def test_gaps_negative_and_balance_are_reported():
    p = demo_with_history("en")
    sl = months(p, 2025)
    assert not [i for i in V.check(p, sl) if i.level == "error"]
    key = next(k for k, v in p.series.items() if k.startswith("source:") and len(v) > 3)
    pts = p.series[key]
    gone = pts.pop(5)                                        # one month disappears from the middle
    assert V.gaps(p, key) and any(i.key == key and "empty" in i.en for i in V.check(p, sl))
    pts.insert(5, gone)
    T.put(p, key, date(2025, 3, 1), date(2025, 3, 31), -10.0)
    errs = [i for i in V.check(p, sl) if i.level == "error"]
    assert errs and errs[0].key == key and errs[0].text("fa") != errs[0].text("en")


def test_period_balance_warning_and_completeness():
    p = demo_with_history("en")
    sub = p.subsystems[0].name
    T.put(p, f"sub:{sub}:intake", date(2025, 6, 1), date(2025, 6, 30), 100.0)
    T.put(p, f"sub:{sub}:discharge", date(2025, 6, 1), date(2025, 6, 30), 900.0)
    issues = V.check(p, months(p))
    assert any(i.key == f"sub:{sub}:discharge" and "exceeds" in i.en for i in issues)
    comp = V.completeness(p, months(p))
    assert comp and all(len(c[1]) == 9 for c in comp)
    assert any(all(c[1]) for c in comp)
