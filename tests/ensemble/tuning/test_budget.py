"""Run budgets are counted in new runs, per session and method, before a run starts.

A budget checked after the run would let a burst of parallel calls overshoot
it; one shared across methods would let a cheap method starve an expensive
one. Both halves of the comparison between the deterministic pipeline and
free orchestration use the same caps: 12 parameter sets per method, which is
12 runs for an exact method and 12 x (1 + 4) for one that calibrates K.
"""

from __future__ import annotations

import threading

import pytest

from omicsclaw.ensemble.tuning.budget import BudgetExceeded, RunBudget, caps, parse_budget


def test_caps_follow_the_k_control_kind():
    assert caps({"leiden": "calibrate", "spagcn": "exact", "cellcharter": "exact"}) == {
        "leiden": 60, "spagcn": 12, "cellcharter": 12,
    }
    with pytest.raises(ValueError):
        caps({"x": "other"})


@pytest.mark.parametrize(
    "text, parsed",
    [
        ("", None),
        ("  ", None),
        ("40", 40),
        ("leiden:60,louvain:60,spagcn:12", {"leiden": 60, "louvain": 60, "spagcn": 12}),
        (" leiden : 5 , ", {"leiden": 5}),
    ],
)
def test_parse(text, parsed):
    assert parse_budget(text) == parsed


@pytest.mark.parametrize("text", ["leiden", "leiden:x", "leiden:-1", ":3", "leiden:1,leiden:2", "-2"])
def test_parse_refuses_malformed_budgets(text):
    with pytest.raises(ValueError):
        parse_budget(text)


def test_each_method_has_its_own_account_per_session():
    budget = RunBudget({"leiden": 2, "spagcn": 1})
    budget.reserve("s1", "leiden")
    budget.reserve("s1", "leiden")
    with pytest.raises(BudgetExceeded) as raised:
        budget.reserve("s1", "leiden")
    assert (raised.value.used, raised.value.cap) == (2, 2)
    budget.reserve("s1", "spagcn")
    budget.reserve("s2", "leiden")
    budget.reserve("s1", "graphst")
    assert budget.snapshot("s1") == {"leiden": 2, "spagcn": 1, "graphst": 1}


def test_a_total_budget_counts_every_method():
    budget = RunBudget(3)
    budget.reserve("s", "a", 2)
    with pytest.raises(BudgetExceeded):
        budget.reserve("s", "b", 2)
    budget.reserve("s", "b")
    assert budget.total("s") == 3


def test_concurrent_reservations_never_overshoot():
    budget = RunBudget({"m": 10})
    granted = []
    refused = []

    def worker():
        try:
            budget.reserve("s", "m")
            granted.append(1)
        except BudgetExceeded:
            refused.append(1)

    threads = [threading.Thread(target=worker) for _ in range(40)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(granted) == 10 and len(refused) == 30


def test_no_limit():
    budget = RunBudget(None)
    for _ in range(100):
        budget.reserve("s", "m")
    assert budget.used("s", "m") == 100 and not budget.limited
