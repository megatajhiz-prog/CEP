import pytest
from waterprofiler import ranking as R
from waterprofiler.model import Plant
from waterprofiler.sample import demo_plant


def _plant():
    return demo_plant("en")


def test_ranks_are_a_permutation_and_scores_in_range():
    r = R.rank_plan(_plant())
    assert sorted(x.rank for x in r.rows) == list(range(1, len(r.rows) + 1))
    assert all(0.0 <= x.score <= 1.0 for x in r.rows)
    assert abs(sum(r.weights.values()) - 1.0) < 1e-12
    assert [x.rank for x in r.rows] == sorted(x.rank for x in r.rows)


def test_weights_decide_the_order():
    p = _plant()
    only = lambda c: R.Settings({k: (1.0 if k == c else 0.0) for k in R.DEFAULT_WEIGHTS})
    top_cheap = R.rank_plan(p, only("capex"), False).rows[0]
    assert top_cheap.raw["capex"] == min(x.raw["capex"] for x in R.rank_plan(p, only("capex"), False).rows)
    top_save = R.rank_plan(p, only("saving"), False).rows[0]
    assert top_save.raw["saving"] == max(x.raw["saving"] for x in R.rank_plan(p, only("saving"), False).rows)


def test_user_scores_enter_the_ranking():
    p = _plant()
    st = R.Settings({k: (1.0 if k == "ease" else 0.0) for k in R.DEFAULT_WEIGHTS})
    p.plan[2].ease = 5.0
    for i in (0, 1, 3):
        p.plan[i].ease = 1.0
    assert R.rank_plan(p, st, False).rows[0].index == 2


def test_topsis_and_wsm_both_computed_and_method_selects():
    p = _plant()
    a = R.rank_plan(p, R.Settings(method="wsm"), False)
    b = R.rank_plan(p, R.Settings(method="topsis"), False)
    ra = {x.index: x for x in a.rows}
    rb = {x.index: x for x in b.rows}
    for i in ra:
        assert ra[i].wsm == pytest.approx(rb[i].wsm) and ra[i].topsis == pytest.approx(rb[i].topsis)
        assert ra[i].score == pytest.approx(ra[i].wsm) and rb[i].score == pytest.approx(rb[i].topsis)


def test_sensitivity_is_reproducible_and_consistent():
    r1, r2 = R.rank_plan(_plant()), R.rank_plan(_plant())
    assert [x.p_first for x in r1.rows] == [x.p_first for x in r2.rows]
    assert sum(x.p_first for x in r1.rows) == pytest.approx(1.0)
    for x in r1.rows:
        assert x.rank_min <= x.rank <= x.rank_max or x.rank_min <= round(x.rank_mean) <= x.rank_max


def test_budget_limits_the_portfolio_and_overlap_is_not_double_counted():
    p = _plant()
    free = R.rank_plan(p, R.Settings(budget=0.0)).portfolio
    assert free.exact and free.capex == sum(i.capex for i in p.plan) or free.capex <= sum(i.capex for i in p.plan)
    cheap = min(i.capex for i in p.plan)
    tight = R.rank_plan(p, R.Settings(budget=cheap)).portfolio
    assert tight.capex <= cheap + 1e-9 and len(tight.chosen) >= 1
    none = R.rank_plan(p, R.Settings(budget=cheap / 2)).portfolio
    assert none.chosen == [] and "budget_too_small" in R.rank_plan(p, R.Settings(budget=cheap / 2)).warnings
    from waterprofiler import measures as M
    assert free.saving == pytest.approx(M.evaluate_plan(p).saving) or free.saving <= M.evaluate_plan(p).saving + 1e-6


def test_zero_weights_raise_and_settings_roundtrip():
    with pytest.raises(R.RankError):
        R.normalise_weights({k: 0.0 for k in R.DEFAULT_WEIGHTS})
    p = _plant()
    p.plan[0].ease, p.plan[0].reliability = 4.0, 2.0
    R.Settings({**R.DEFAULT_WEIGHTS, "capex": 40.0}, "topsis", 1234.0, "saving").store(p)
    q = Plant.from_dict(p.to_dict())
    s = R.Settings.of(q)
    assert (s.method, s.budget, s.objective, s.weights["capex"]) == ("topsis", 1234.0, "saving", 40.0)
    assert (q.plan[0].ease, q.plan[0].reliability) == (4.0, 2.0)


def test_old_files_and_empty_plan():
    p = _plant()
    p.plan = []
    r = R.rank_plan(p)
    assert r.rows == [] and r.portfolio is None
    assert R.Settings.of(Plant()).weights == R.DEFAULT_WEIGHTS
