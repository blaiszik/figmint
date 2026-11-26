"""figure-bench's delivery check: the agent's reply must carry the figure, with little prose."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import pytest

import mintfig as mint

BENCH = Path(__file__).resolve().parents[1] / "evals" / "figure_bench" / "bench.py"


def _load_bench():
    spec = importlib.util.spec_from_file_location("figure_bench", BENCH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


bench = _load_bench()


@pytest.fixture(scope="module")
def summary(tmp_path_factory: pytest.TempPathFactory) -> dict:
    work = tmp_path_factory.mktemp("work")
    fig = mint.explain(
        "Removing retrieval costs 8 points of accuracy",
        mint.compare({"full model": 82.0, "no retrieval": 74.0}, label="Accuracy", unit="%"),
        source="ablation runs",
    )
    cwd = Path.cwd()
    try:
        os.chdir(work)
        out = json.loads(json.dumps(fig.save("figure.png"), default=str))
    finally:
        os.chdir(cwd)
        plt.close(fig.fig)
    assert out["deliver"]["markdown"].endswith("(figure.png)")
    return out


def test_image_reply_passes(summary: dict) -> None:
    reply = (
        "Retrieval is worth 8 points; fine-tuning matters less.\n\n"
        f"{summary['deliver']['markdown']}\n\n*{summary['deliver']['caption']}*\n"
    )
    result = bench.check_reply(reply, summary)
    assert result["name"] == "reply_delivers_figure"
    assert result["status"] == "pass" and result["passed"] is True
    assert result["detail"].startswith("image figure.png;")
    # Any alt text, and ./ or <...> around the same path, still show the figure.
    assert bench.check_reply("Short.\n\n![my words](./figure.png)", summary)["passed"]
    assert bench.check_reply("Short.\n\n![my words](<figure.png>)", summary)["passed"]


def test_text_in_a_code_block_passes(summary: dict) -> None:
    reply = f"Retrieval is worth 8 points.\n\n```\n{summary['deliver']['text']}\n```\n"
    result = bench.check_reply(reply, summary)
    assert result["status"] == "pass", result["detail"]
    assert result["detail"].startswith("deliver.text in a code block")


def test_too_many_words_fails(summary: dict) -> None:
    prose = " ".join(["word"] * 61)
    result = bench.check_reply(f"{prose}\n\n{summary['deliver']['markdown']}\n", summary)
    assert result["status"] == "fail"
    assert result["detail"] == "61 words of prose (max 60)"
    # Words inside the image line and in code fences do not count.
    long_alt = f"![{' '.join(['alt'] * 80)}](figure.png)"
    fenced = "```python\n" + " ".join(["code"] * 80) + "\n```"
    assert bench.check_reply(f"One sentence.\n\n{long_alt}\n\n{fenced}\n", summary)["passed"]


def test_figure_missing_fails(summary: dict) -> None:
    result = bench.check_reply("Retrieval is worth 8 points. See figure.png.", summary)
    assert result["status"] == "fail"
    assert "no ![...](figure.png) image" in result["detail"]
    other = bench.check_reply("Short.\n\n![chart](other.png)", summary)
    assert other["status"] == "fail"
    # The text surface only counts inside a fence.
    unfenced = bench.check_reply(f"Short.\n\n{summary['deliver']['text']}", summary)
    assert unfenced["status"] == "fail"


def test_reply_absent_is_not_a_failure(summary: dict) -> None:
    result = bench.check_reply(None, summary)
    assert result["status"] == "not provided" and result["passed"] is None


def _old_run(run: Path, summary: dict) -> None:
    """A finished task in the layout ``submit`` writes, from before ``--reply`` existed."""
    meta = run / "01_ablation" / ".bench"
    meta.mkdir(parents=True)
    attempt = {"n": 1, "submitted": 1.0, "finished": 21.0, "render_s": 1.2, "passed": True,
               "checks": [{"name": "script_runs", "passed": True, "detail": ""}]}
    state = {"task": "01_ablation", "started": 0.0, "python": sys.executable, "attempts": [attempt]}
    (meta / "state.json").write_text(json.dumps(state))
    (meta / "attempt1_summary.json").write_text(json.dumps([summary]))


def test_grade_reports_delivery_and_still_grades_old_runs(summary: dict, tmp_path: Path) -> None:
    _old_run(tmp_path, summary)
    bench.main(["grade", "--run", str(tmp_path)])
    results = json.loads((tmp_path / "results.json").read_text())
    row = results["tasks_detail"][0]
    assert row["passed"] is True and row["delivery"] == "not provided"
    assert results["replies_provided"] == 0 and results["replies_deliver"] == 0
    md = (tmp_path / "results.md").read_text()
    assert "| Delivery |" in md and "| not provided |" in md

    state_path = tmp_path / "01_ablation" / ".bench" / "state.json"
    state = json.loads(state_path.read_text())
    reply = f"One sentence.\n\n{summary['deliver']['markdown']}\n"
    state["attempts"][0]["delivery"] = bench.check_reply(reply, summary)
    state_path.write_text(json.dumps(state))
    bench.main(["grade", "--run", str(tmp_path)])
    results = json.loads((tmp_path / "results.json").read_text())
    assert results["tasks_detail"][0]["delivery"] == "pass"
    assert results["replies_deliver"] == 1 and results["tasks_detail"][0]["failed_checks"] == []
