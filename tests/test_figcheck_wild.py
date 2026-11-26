"""Wild-50 verification suite for ``mint.check``.

Validates the 50-figure Matplotlib & Seaborn-idiom corpus in
``evals/check_bench/corpus.py``:
- Clean false-positive rate < 2% (0 / 25 clean figures blocked)
- Defect catch rate > 90% (>= 23 / 25 defective figures blocked)
- Exact-rule recall > 90% (>= 23 / 25 defective figures report the expected rule)
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

BENCH_DIR = Path(__file__).resolve().parents[1] / "evals" / "check_bench"


def _load_module(name: str, filename: str) -> Any:
    path = BENCH_DIR / filename
    if str(BENCH_DIR) not in sys.path:
        sys.path.insert(0, str(BENCH_DIR))
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_CORPUS = _load_module("wild_check_bench_corpus", "corpus.py")
_RUNNER = _load_module("wild_check_bench_runner", "run_wild_eval.py")

WILD_50 = _CORPUS.WILD_50
CLEAN_CASES = tuple(c for c in WILD_50 if c.split == "clean")
DEFECTIVE_CASES = tuple(c for c in WILD_50 if c.split == "defective")


@pytest.fixture(scope="module")
def wild_eval() -> dict[str, Any]:
    """Run the Wild-50 corpus once per module for fast verification."""
    return _RUNNER.run_eval(WILD_50)


@pytest.fixture(scope="module")
def results_by_id(wild_eval: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {r["case_id"]: r for r in wild_eval["cases"]}


def test_wild_50_corpus_structure() -> None:
    assert len(WILD_50) == 50
    assert len(CLEAN_CASES) == 25
    assert len(DEFECTIVE_CASES) == 25
    ids = [c.case_id for c in WILD_50]
    assert len(ids) == len(set(ids)), "Duplicate case_id in WILD_50"
    assert all(c.expected_ship is True and not c.expected_rules for c in CLEAN_CASES)
    assert all(c.expected_ship is False and c.expected_rules for c in DEFECTIVE_CASES)


def test_wild_50_runs_fast(wild_eval: dict[str, Any]) -> None:
    assert wild_eval["elapsed_seconds"] < 15.0, (
        f"Wild-50 took {wild_eval['elapsed_seconds']}s (budget < 15s)"
    )


def test_clean_false_positive_rate_under_2_percent(wild_eval: dict[str, Any]) -> None:
    summary = wild_eval["summary"]
    fps = [r for r in wild_eval["cases"] if r["split"] == "clean" and not r["actual_ship"]]
    detail = "; ".join(
        f"{r['case_id']} -> {r['actual_rules']} (unmatched={r['unmatched_claim_numbers']})"
        for r in fps
    )
    assert summary["false_positive_rate"] < 0.02, (
        f"Clean FP rate {summary['false_positives']}/{summary['clean_total']} "
        f"({summary['false_positive_rate']*100:.1f}%) exceeds 2% target: {detail}"
    )


def test_defect_catch_rate_over_90_percent(wild_eval: dict[str, Any]) -> None:
    summary = wild_eval["summary"]
    missed = [r for r in wild_eval["cases"] if r["split"] == "defective" and r["actual_ship"]]
    detail = "; ".join(
        f"{r['case_id']} (expected {r['expected_rules']}, got {r['actual_rules']})"
        for r in missed
    )
    assert summary["defect_catch_rate"] > 0.90, (
        f"Defect catch rate {summary['defective_caught']}/{summary['defective_total']} "
        f"({summary['defect_catch_rate']*100:.1f}%) below 90% target: {detail}"
    )


def test_defect_exact_rule_recall_over_90_percent(wild_eval: dict[str, Any]) -> None:
    summary = wild_eval["summary"]
    missed = [
        r for r in wild_eval["cases"] if r["split"] == "defective" and not r["exact_rule_match"]
    ]
    detail = "; ".join(
        f"{r['case_id']} (expected {r['expected_rules']}, got {r['actual_rules']})"
        for r in missed
    )
    assert summary["exact_rule_recall"] > 0.90, (
        f"Exact-rule recall {summary['defective_exact_rule_match']}/{summary['defective_total']} "
        f"({summary['exact_rule_recall']*100:.1f}%) below 90% target: {detail}"
    )


@pytest.mark.parametrize("case", CLEAN_CASES, ids=[c.case_id for c in CLEAN_CASES])
def test_clean_case_ships(case: Any, results_by_id: dict[str, dict[str, Any]]) -> None:
    result = results_by_id[case.case_id]
    assert result["actual_ship"] is True, (
        f"{case.case_id} blocked unexpectedly: rules={result['actual_rules']}, "
        f"unmatched={result['unmatched_claim_numbers']}, issues={result['issues']}"
    )
