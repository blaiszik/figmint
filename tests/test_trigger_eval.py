"""Tests for the 40-prompt skill trigger evaluation suite."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
EVAL_DIR = REPO_ROOT / "evals" / "trigger_eval"
PROMPTS_PATH = EVAL_DIR / "prompts.json"
SCRIPT_PATH = EVAL_DIR / "eval_triggers.py"
SKILL_PATH = REPO_ROOT / "src" / "mintfig" / "assets" / "SKILL.md"
SNIPPET_PATH = REPO_ROOT / "src" / "mintfig" / "assets" / "AGENTS_SNIPPET.md"


def _load_eval_module():
    spec = importlib.util.spec_from_file_location("eval_triggers", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    import sys

    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_prompts_json_integrity() -> None:
    data = json.loads(PROMPTS_PATH.read_text(encoding="utf-8"))
    prompts = data["prompts"]
    assert len(prompts) == 40

    positives = [p for p in prompts if p["should_trigger"] is True]
    negatives = [p for p in prompts if p["should_trigger"] is False]
    assert len(positives) == 20
    assert len(negatives) == 20

    ids = [p["id"] for p in prompts]
    assert len(set(ids)) == 40, "Prompt IDs must be unique"

    for item in prompts:
        text = item["prompt"]
        assert isinstance(text, str) and len(text.strip()) >= 20
        assert "mintfig" not in text.lower(), f"Prompt {item['id']} must never mention mintfig"
        assert "mintfig" not in item["id"].lower()
        assert "mintfig" not in item["category"].lower()


def test_offline_trigger_eval_passes_exit_gates() -> None:
    mod = _load_eval_module()
    prompts_data = json.loads(PROMPTS_PATH.read_text(encoding="utf-8"))
    skill_md = SKILL_PATH.read_text(encoding="utf-8")
    snippet_md = SNIPPET_PATH.read_text(encoding="utf-8")

    report = mod.evaluate_prompts(prompts_data, skill_md, snippet_md)
    assert report["passed"] is True
    assert report["metrics"]["recall"] >= 0.85
    assert report["metrics"]["false_trigger_rate"] <= 0.05
    assert report["metrics"]["total"] == 40

    # Every trigger & negative-exclusion criterion must be declared in SKILL.md + AGENTS_SNIPPET.md
    checks = report["skill_spec_checks"]
    for key in (
        "covers_five_plus_numbers",
        "covers_comparisons_trends_distributions",
        "covers_csv_experiments",
        "covers_matplotlib_check",
        "covers_notebook_check",
        "covers_publication_plates",
        "forbids_routine_code",
        "forbids_few_scalars",
    ):
        assert checks[key] is True, f"Expected {key} to be present in SKILL.md / AGENTS_SNIPPET.md"


def test_offline_scorer_catches_regressed_skill_description() -> None:
    """Stripping trigger or exclusion clauses from SKILL.md must fail the exit gates."""
    mod = _load_eval_module()
    prompts_data = json.loads(PROMPTS_PATH.read_text(encoding="utf-8"))

    stripped_skill = "---\nname: mintfig\ndescription: A plotting tool.\n---\n"
    stripped_snippet = "<!-- mintfig:start -->\nUse mintfig.\n<!-- mintfig:end -->\n"
    report = mod.evaluate_prompts(prompts_data, stripped_skill, stripped_snippet)
    assert report["passed"] is False
    assert report["metrics"]["recall"] < 0.85


def test_cli_writes_markdown_report(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    mod = _load_eval_module()
    out_report = tmp_path / "REPORT.md"
    rc = mod.main(["--report", str(out_report)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "[PASS]" in out
    md = out_report.read_text(encoding="utf-8")
    assert "Mintfig Skill Trigger Evaluation Report" in md
    assert "Recall (TP / Pos)" in md
    assert "False-trigger rate (FP / Neg)" in md
