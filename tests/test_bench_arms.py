"""figure-bench's Matplotlib arm and the arm-neutral audit both arms are scored by."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pytest

HERE = Path(__file__).resolve().parents[1] / "evals" / "figure_bench"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


bench = _load("figure_bench", HERE / "bench.py")
neutral = _load("figure_bench_neutral", HERE / "neutral.py")


def _audit(fig, tmp_path: Path, dpi: float = 100.0, tight: bool = False) -> dict:
    png = tmp_path / "figure.png"
    fig.savefig(png, dpi=dpi, bbox_inches="tight" if tight else None)
    try:
        return neutral.audit_saved_figure(fig, png, dpi=dpi, tight=tight)
    finally:
        plt.close(fig)


def _checks(audit: dict) -> dict[str, bool]:
    return {c["name"]: c["passed"] for c in neutral.neutral_checks(audit)}


def test_small_default_figure_is_clean(tmp_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(6.4, 4.8))
    ax.plot([0, 1, 2], [1, 3, 2])
    ax.set_title("Load peaks at 3 on day 1")
    audit = _audit(fig, tmp_path)
    assert audit["png_px"] == [640, 480]
    assert audit["display_width_px"] == 640  # narrower than the chat column: shown at its own size
    assert audit["min_text_px"] == pytest.approx(10 * 100 / 72, abs=0.1)
    assert all(_checks(audit).values())
    assert audit["headlines"] == ["Load peaks at 3 on day 1"]


def test_wide_figure_text_is_measured_at_display_width(tmp_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(12, 4.5))
    ax.plot([0, 1], [0, 1])
    audit = _audit(fig, tmp_path, dpi=150)
    # 10 pt at 150 dpi in an 1800 px PNG shown 700 px wide.
    assert audit["min_text_px"] == pytest.approx(10 * 150 / 72 * 700 / 1800, abs=0.1)
    assert _checks(audit)["text_legible"] is False


def test_overlap_clip_and_malformed_text_are_flagged(tmp_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(4, 3))
    ax.text(0.5, 0.5, "first label", fontsize=20)
    ax.text(0.5, 0.5, "second label", fontsize=20)
    ax.text(0.5, 0.2, "Share of Share of 40%%")
    fig.text(0.98, 0.5, "runs off the right edge", fontsize=16)
    checks = _checks(_audit(fig, tmp_path))
    assert checks["no_text_overlap"] is False
    assert checks["no_text_clipped"] is False
    assert checks["text_well_formed"] is False


def test_tight_bbox_is_not_clipping(tmp_path: Path) -> None:
    fig, _ax = plt.subplots(figsize=(4, 3))
    fig.text(0.98, 0.5, "runs off the right edge", fontsize=16)
    assert _checks(_audit(fig, tmp_path, tight=True))["no_text_clipped"] is True


def test_framed_legend_text_is_not_struck_by_lines_under_it(tmp_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(4, 3))
    for k in range(4):
        ax.plot([0, 1], [k / 4, k / 4 + 0.1], label=f"series {k}")
    ax.legend(loc="center")
    audit = _audit(fig, tmp_path)
    assert audit["legends"] == 1
    assert _checks(audit)["no_text_struck_by_lines"] is True


def test_uncertainty_words() -> None:
    for text in ("mean ± s.d.", "95% CI", "5 seeds", "n = 12", "replicates"):
        assert neutral.UNCERTAINTY_WORDS.search(text), text
    assert not neutral.UNCERTAINTY_WORDS.search("Accuracy by variant")


def _run_matplotlib_task(tmp_path: Path, script: str, reply: str) -> tuple[Path, dict]:
    run = tmp_path / "run"
    bench.main(["start", "01_ablation", "--run", str(run), "--arm", "matplotlib",
                "--python", sys.executable])
    work = run / "01_ablation"
    (tmp_path / "fig.py").write_text(script, encoding="utf-8")
    (tmp_path / "reply.md").write_text(reply, encoding="utf-8")
    bench.main(["submit", "01_ablation", str(tmp_path / "fig.py"), "--run", str(run),
                "--reply", str(tmp_path / "reply.md")])
    state = json.loads((work / ".bench" / "state.json").read_text())
    return run, state


CLEAN_SCRIPT = """
import matplotlib.pyplot as plt
fig, ax = plt.subplots(figsize=(6, 4))
ax.barh(["no reranker", "full model"], [80.5, 82.1])
ax.set_title("The reranker buys 1.6 points (5 seeds)")
fig.tight_layout()
fig.savefig("figure.png", dpi=100)
"""


def test_matplotlib_arm_end_to_end(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    run, state = _run_matplotlib_task(
        tmp_path, CLEAN_SCRIPT, "The reranker buys 1.6 points.\n\n![Ablation](figure.png)\n")
    out = capsys.readouterr().out
    assert "ONE figure made with Matplotlib" in out and "SKILL.md" not in out
    attempt = state["attempts"][0]
    assert state["arm"] == "matplotlib"
    assert attempt["passed"] is True, attempt["checks"]
    assert attempt["delivery"]["status"] == "pass"
    assert attempt["audit"]["headlines"] == ["The reranker buys 1.6 points (5 seeds)"]

    bench.main(["grade", "--run", str(run)])
    results = json.loads((run / "results.json").read_text())
    row = results["tasks_detail"][0]
    assert results["arm"] == "matplotlib"
    assert row["neutral"]["first"]["headline_correct"] is True  # 1.6 is in the answer key
    assert row["neutral"]["first"]["reply_correct"] is True
    assert row["neutral"]["first"]["uncertainty_named"] is True  # 01_ablation has seeds
    assert results["neutral"]["first"]["clean"] == "1/1"

    out_md = tmp_path / "compare.md"
    bench.main(["compare", str(run), str(run), "--out", str(out_md)])
    table = out_md.read_text()
    assert "| No layout or text defect (all five below) | 1/1 | 1/1 |" in table


def test_matplotlib_arm_rejects_mintfig(tmp_path: Path) -> None:
    script = "import mintfig\n" + CLEAN_SCRIPT
    _, state = _run_matplotlib_task(tmp_path, script, "![x](figure.png)\n")
    checks = {c["name"]: c["passed"] for c in state["attempts"][0]["checks"]}
    assert checks["no_mintfig"] is False
    assert state["attempts"][0]["passed"] is False


TINY_SCRIPT = """
import matplotlib.pyplot as plt
fig, ax = plt.subplots(figsize=(14, 5))
ax.plot([0, 1], [0, 1], label="a")
ax.legend()
fig.savefig("figure.png", dpi=150)
"""


def test_plain_arm_hides_defects_and_stops_once_saved(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run = tmp_path / "run"
    bench.main(["start", "02_ab_latency", "--run", str(run), "--arm", "matplotlib-plain",
                "--python", sys.executable])
    rules = capsys.readouterr().out
    assert "700 px" in rules and "11 px" not in rules  # told display width & surface, not defect checks
    (tmp_path / "fig.py").write_text(TINY_SCRIPT, encoding="utf-8")
    bench.main(["submit", "02_ab_latency", str(tmp_path / "fig.py"), "--run", str(run)])
    out = capsys.readouterr().out
    assert "text_legible" not in out and "Task complete" in out
    state = json.loads((run / "02_ab_latency" / ".bench" / "state.json").read_text())
    attempt = state["attempts"][0]
    assert attempt["done"] is True and attempt["passed"] is False  # graded on the hidden gate
    with pytest.raises(SystemExit):
        bench.main(["submit", "02_ab_latency", str(tmp_path / "fig.py"), "--run", str(run)])


def test_readers_prepare_and_score(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    run, _ = _run_matplotlib_task(tmp_path, CLEAN_SCRIPT, "![x](figure.png)\n")
    readers = tmp_path / "readers"
    bench.main(["readers-prepare", str(run), "--out", str(readers)])
    key = json.loads((readers / "key.json").read_text())
    (fid, item), = key.items()
    batch = readers / item["batch"]
    assert (batch / fid / "figure.png").exists()
    assert "reranker" in (batch / fid / "question.md").read_text()
    assert "key.json" not in (batch / "README.md").read_text()
    (batch / "answers.json").write_text(json.dumps({fid: {"answer": "1.6 points", "where": "title"}}))
    bench.main(["readers-score", str(readers)])
    rows = json.loads((run / "readers.json").read_text())
    assert rows["01_ablation"]["correct"] is True
    bench.main(["grade", "--run", str(run)])
    bench.main(["compare", str(run)])
    assert "| Reader answers the task's question correctly | 1/1 |" in capsys.readouterr().out


@pytest.fixture(autouse=True)
def _close_all():
    yield
    plt.close("all")


def test_reader_copies_carry_no_embedded_takeaway(tmp_path: Path) -> None:
    import mintfig as mint

    src = tmp_path / "fig.png"
    mint.explain("Removing retrieval costs 8 points",
                 mint.compare({"full": 82.0, "no retrieval": 74.0}, label="Accuracy", unit="%")).save(src)
    assert b"mintfig:takeaway" in src.read_bytes()
    dst = tmp_path / "copy.png"
    bench.strip_png_text(src, dst)
    assert b"mintfig:" not in dst.read_bytes()
    assert neutral.png_size(dst) == neutral.png_size(src)
    assert plt.imread(dst).shape == plt.imread(src).shape
