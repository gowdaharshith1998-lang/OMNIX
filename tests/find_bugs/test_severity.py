"""Deterministic severity scoring for find_bugs."""

from __future__ import annotations

from find_bugs import severity

_G = {
    "caller_counts": {"m.py::f": 3, "m.py::g": 0},
    "entry_reachable": {"m.py::f": True, "m.py::g": False},
}


def test_formula_public_entry() -> None:
    f = {
        "file": "m.py",
        "function": "f",
        "failures": [{}, {}],
    }
    s = severity.compute_severity(f, _G)
    # 3*2 + 5 + 2 + 1 = 14
    assert s == 14


def test_private_no_export_bonus() -> None:
    f = {
        "file": "m.py",
        "function": "_priv",
        "failures": [{}],
    }
    s = severity.compute_severity(f, _G)
    # 0*2 + 0 + 1 + 0 = 1
    assert s == 1


def test_higher_caller_higher_score() -> None:
    a = {
        "file": "a.py",
        "function": "f",
        "failures": [{}],
    }
    b = {
        "file": "a.py",
        "function": "f",
        "failures": [{}],
    }
    g1 = {
        "caller_counts": {"a.py::f": 10},
        "entry_reachable": {"a.py::f": False},
    }
    g2 = {
        "caller_counts": {"a.py::f": 0},
        "entry_reachable": {"a.py::f": False},
    }
    assert severity.compute_severity(a, g1) > severity.compute_severity(b, g2)


def test_reachable_higher() -> None:
    f = {"file": "a.py", "function": "f", "failures": [{}]}
    g1 = {
        "caller_counts": {"a.py::f": 0},
        "entry_reachable": {"a.py::f": True},
    }
    g2 = {
        "caller_counts": {"a.py::f": 0},
        "entry_reachable": {"a.py::f": False},
    }
    assert severity.compute_severity(f, g1) - severity.compute_severity(f, g2) == 5


def test_ranking_tiebreak() -> None:
    a = {
        "file": "a.py",
        "function": "b",
        "severity_score": 1,
    }
    c2 = {
        "file": "a.py",
        "function": "a",
        "severity_score": 1,
    }
    r = severity.rank_findings([a, c2])
    # same file, function "a" before "b" lexicographically
    assert r[0]["function"] == "a" and r[1]["function"] == "b"
