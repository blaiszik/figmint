"""mint.check: plain Matplotlib figures audited against their own data, at reading size."""

from __future__ import annotations

import datetime as dt
import importlib.util
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pytest

import mintfig as mint
from mintfig.cli import main as cli_main

VARIANTS = ["full model", "no retrieval", "no fine-tuning"]
ACC = [0.82, 0.74, 0.69]


@pytest.fixture(autouse=True)
def _defaults_and_close():
    """Matplotlib's own defaults: other tests may leave a journal style in rcParams."""
    with matplotlib.rc_context():
        matplotlib.rcdefaults()
        matplotlib.use("Agg")
        yield
    plt.close("all")


def _rules(report) -> set[str]:
    return {i["rule"] for i in report["issues"]}


def _bad_bars():
    fig, ax = plt.subplots(figsize=(12, 5))
    ax.bar(VARIANTS, ACC, yerr=[0.02, 0.03, 0.03])
    ax.set_ylim(0.6, 0.85)
    ax.set_title("Removing retrieval costs 12 points of accuracy")
    ax.set_ylabel("Test accuracy")
    return fig


def _good_bars():
    fig, ax = plt.subplots(figsize=(7, 3.6))
    ax.bar(VARIANTS, ACC, yerr=[0.02, 0.03, 0.03])
    ax.set_title("Removing retrieval costs 8 points of accuracy", loc="left", fontsize=15)
    ax.set_ylabel("Test accuracy (95% CI, 5 seeds)", fontsize=11)
    ax.tick_params(labelsize=11)
    fig.tight_layout()
    return fig


def test_bad_bar_chart_is_caught_with_concrete_fixes() -> None:
    report = mint.check(_bad_bars(), dpi=150)
    assert report["ship"] is False and report.ship is False
    assert {"text_too_small", "bar_baseline_nonzero", "interval_unlabelled",
            "claim_number_mismatch"} <= _rules(report)  # fmt: skip
    assert report["issues"][0]["rule"] == "bar_baseline_nonzero"  # errors first
    small = next(i for i in report["issues"] if i["rule"] == "text_too_small")
    assert "1800 px PNG is shown 700 px wide" in small["message"]
    assert "figsize width ≈ 4.7 in at dpi=150" in small["fix_hint"]
    number = report["claim"]["numbers"][0]
    assert number["text"] == "12 points" and number["found"] is False
    assert "no retrieval" in number["nearest"] and "8 points" in number["nearest"]
    assert report["display"]["png_px"] == [1800, 750]
    assert report["display"]["min_text_px"] < 11


def test_fixed_chart_ships_and_says_where_the_number_came_from() -> None:
    report = mint.check(_good_bars(), dpi=100)
    assert report["ship"] is True, report["issues"]
    assert report["issues"] == []
    number = report["claim"]["numbers"][0]
    assert number["found"] is True
    assert "full model vs no retrieval" in number["how"] and "8 points" in number["how"]
    panel = report["panels"][0]
    assert panel["values"]["bars"]["bars"] == pytest.approx(dict(zip(VARIANTS, ACC)))
    assert any("do not overlap" in f for f in panel["facts"])
    json.dumps(report)  # a plain, serialisable dict
    assert '"ship": true' in str(report)


def test_reading_width_changes_the_verdict() -> None:
    fig, ax = plt.subplots(figsize=(7, 3.6))
    ax.plot([0, 1, 2], [1, 3, 2])
    ax.set_title("Load peaks at 3", fontsize=12)
    ax.tick_params(labelsize=10)
    ax.set_xlabel("Day")
    ax.set_ylabel("Load (kW)")
    assert "text_too_small" not in _rules(mint.check(fig, dpi=100))
    narrow = mint.check(fig, dpi=100, width="narrow")
    assert "text_too_small" in _rules(narrow)
    assert narrow["display"]["shown_px"][0] == 450
    with pytest.raises(ValueError, match="width="):
        mint.check(fig, width="phone")


def test_accepts_axes_and_current_figure_and_refuses_explanations() -> None:
    fig = _good_bars()
    assert mint.check(fig.axes[0], dpi=100)["ship"] is True
    assert mint.check(dpi=100)["ship"] is True  # plt.gcf()
    exp = mint.explain("Full model leads by 8 points", mint.compare(dict(zip(VARIANTS, ACC))))
    with pytest.raises(TypeError, match="already carries its checks"):
        mint.check(exp)
    with pytest.raises(TypeError, match="Figure or Axes"):
        mint.check("figure.png")


def test_no_open_figure_is_a_clear_error() -> None:
    plt.close("all")
    with pytest.raises(TypeError, match="no open figure"):
        mint.check()


def test_crossing_claim_and_relative_change_on_lines() -> None:
    cycles = np.arange(0, 801, 20)
    base = 100 - 20 * cycles / 460
    better = 100 - 20 * cycles / 640
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(cycles, base, label="baseline")
    ax.plot(cycles, better, label="additive")
    ax.axhline(80, ls="--", color="0.5")
    ax.set_xlabel("Cycle")
    ax.set_ylabel("Capacity retention (%)")
    ax.legend()
    report = mint.check(fig, "Baseline cells reach 80% retention at cycle 460", dpi=100)
    numbers = {n["text"]: n for n in report["claim"]["numbers"]}
    assert numbers["80%"]["found"] and numbers["460"]["found"], numbers
    assert "crosses 80" in numbers["460"]["how"]
    assert any("crosses 80 near x=460" in f for f in report["panels"][0]["facts"])
    assert report["claim"]["source"] == "claim="
    drop = mint.check(fig, "Baseline retention falls 35% by cycle 800", dpi=100)
    assert drop["claim"]["numbers"][0]["found"] is True


def test_dates_on_the_x_axis_are_read_without_error() -> None:
    days = [dt.date(2026, 7, 1) + dt.timedelta(days=i) for i in range(30)]
    fig, ax = plt.subplots(figsize=(7, 3.5))
    ax.plot(days, np.linspace(120, 90, 30), label="weekday use")
    ax.set_title("Weekday use fell 25% after the retrofit")
    ax.set_ylabel("Energy (kWh)")
    report = mint.check(fig, dpi=100)
    assert report["claim"]["numbers"][0]["found"] is True
    assert report["panels"][0]["kind"] == "lines"


def test_grouped_bars_name_categories_and_series() -> None:
    langs = ["English", "Hindi", "Swahili"]
    before, after = [80, 62, 40], [84, 70, 57]
    x = np.arange(3)
    fig, ax = plt.subplots(figsize=(7, 3.6))
    ax.bar(x - 0.2, before, 0.4, label="v1")
    ax.bar(x + 0.2, after, 0.4, label="v2")
    ax.set_xticks(x, langs)
    ax.set_ylabel("Accuracy (%)")
    ax.legend()
    report = mint.check(fig, "Swahili gained 17 points, the most of any language", dpi=100)
    bars = report["panels"][0]["values"]["bars"]
    assert bars["v2"]["Swahili"] == 57 and bars["v1"]["English"] == 80
    number = report["claim"]["numbers"][0]
    assert number["found"] and "Swahili" in number["how"]


def test_scatter_correlation_and_hedged_claims() -> None:
    rng = np.random.default_rng(0)
    xs = rng.uniform(0, 10, 40)
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.scatter(xs, 2 * xs + rng.normal(0, 1, 40))
    ax.set_xlabel("Dose (mg)")
    ax.set_ylabel("Response (a.u.)")
    report = mint.check(fig, "Response rises about 30 units over the dose range", dpi=100)
    assert any("r = 0.9" in f for f in report["panels"][0]["facts"])
    assert report["claim"]["hedged"] is True
    assert "claim_number_mismatch" not in _rules(report)


def test_headline_is_the_largest_title_not_a_footnote() -> None:
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.bar(["a", "b"], [3, 6])
    ax.set_title("B doubles A", fontsize=14)
    fig.text(0.01, 0.01, "Note: 4 runs excluded (crash).", fontsize=9)
    assert mint.check(fig, dpi=100)["claim"]["text"] == "B doubles A"
    fig.suptitle("B is 2x A", fontsize=16)
    report = mint.check(fig, dpi=100)
    assert report["claim"]["text"] == "B is 2x A"
    assert report["claim"]["numbers"][0]["found"] is True


def test_headline_advisories() -> None:
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.bar(["a", "b"], [3, 6])
    ax.set_ylabel("Count")
    assert [a["rule"] for a in mint.check(fig, dpi=100)["advisories"]] == ["no_headline"]
    ax.set_title("Results by variant")
    report = mint.check(fig, dpi=100)
    assert [a["rule"] for a in report["advisories"]] == ["headline_states_no_number"]
    assert report["ship"] is True  # advice, never a blocker


def test_rainbow_colormap_is_an_error() -> None:
    fig, ax = plt.subplots(figsize=(6, 5))
    ax.imshow(np.arange(16.0).reshape(4, 4), cmap="jet")
    report = mint.check(fig, dpi=100)
    assert "rainbow_colormap" in _rules(report) and report["ship"] is False
    assert report["panels"][0]["values"]["image"]["max"] == 15.0


def test_framed_legend_over_a_line_is_not_struck() -> None:
    fig, ax = plt.subplots(figsize=(6, 4))
    for k in range(4):
        ax.plot([0, 1], [k / 4, k / 4 + 0.1], label=f"series {k}")
    ax.legend(loc="center")
    report = mint.check(fig, dpi=100)
    assert "text_struck_by_line" not in _rules(report)
    assert report["display"]["legends"] == 1


def test_gui_canvas_is_restored() -> None:
    from matplotlib.backend_bases import FigureCanvasBase

    fig = _good_bars()
    canvas = FigureCanvasBase(fig)
    assert mint.check(fig, dpi=100)["ship"] is True
    assert fig.canvas is canvas


def _load_neutral():
    path = Path(__file__).resolve().parents[1] / "evals" / "figure_bench" / "neutral.py"
    spec = importlib.util.spec_from_file_location("figure_bench_neutral_fc", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


NEUTRAL_TO_RULE = {
    "text_legible": "text_too_small", "no_text_overlap": "text_overlaps",
    "no_text_struck_by_lines": "text_struck_by_line", "text_well_formed": "text_malformed",
    "no_text_clipped": "text_clipped",
}  # fmt: skip


def _overlapping():
    fig, ax = plt.subplots(figsize=(4, 3))
    ax.text(0.5, 0.5, "first label", fontsize=20)
    ax.text(0.5, 0.5, "second label", fontsize=20)
    ax.text(0.5, 0.2, "Share of Share of 40%%")
    fig.text(0.98, 0.5, "runs off the right edge", fontsize=16)
    return fig


def _struck():
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.plot([0, 1], [0, 1])
    ax.text(0.5, 0.5, "on the line", ha="center", va="center", fontsize=12)
    return fig


@pytest.mark.parametrize("make, dpi", [(_bad_bars, 150), (_good_bars, 100), (_overlapping, 100),
                                       (_struck, 100)])
def test_text_checks_agree_with_the_figure_bench_audit(make, dpi, tmp_path: Path) -> None:
    """figure-bench's arm-neutral audit and mint.check measure text defects the same way."""
    neutral = _load_neutral()
    fig = make()
    png = tmp_path / "figure.png"
    fig.savefig(png, dpi=dpi)
    bench = {c["name"]: c["passed"] for c in
             neutral.neutral_checks(neutral.audit_saved_figure(fig, png, dpi=dpi, tight=False))}
    rules = _rules(mint.check(fig, dpi=dpi))
    for name, passed in bench.items():
        assert passed == (NEUTRAL_TO_RULE[name] not in rules), name


# --------------------------------------------------------------------------- CLI

BAD_SCRIPT = """
import matplotlib.pyplot as plt
fig, ax = plt.subplots(figsize=(12, 5))
ax.bar(["full model", "no retrieval"], [0.82, 0.74])
ax.set_ylim(0.6, 0.85)
ax.set_title("Removing retrieval costs 12 points")
fig.savefig("out.png", dpi=150)
fig.savefig("out.pdf")
plt.show()
"""

GOOD_SCRIPT = """
import matplotlib.pyplot as plt
fig, ax = plt.subplots(figsize=(7, 3.6))
ax.bar(["full model", "no retrieval"], [0.82, 0.74])
ax.set_title("Removing retrieval costs 8 points", fontsize=15)
ax.set_ylabel("Accuracy", fontsize=11)
ax.tick_params(labelsize=11)
fig.tight_layout()
fig.savefig("out.png", dpi=100)
"""


def _script(tmp_path: Path, body: str, name: str = "plot.py") -> Path:
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return path


def test_cli_check_script_exit_codes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli_main(["check", str(_script(tmp_path, GOOD_SCRIPT))]) == 0
    out = capsys.readouterr().out
    assert "out.png: SHIP" in out and "8 points: found" in out
    assert (tmp_path / "out.png").exists()  # ran from the script's own folder

    assert cli_main(["check", str(_script(tmp_path, BAD_SCRIPT, "bad.py")), "--json"]) == 1
    payload = json.loads(capsys.readouterr().out)
    (fig,) = payload["figures"]  # one figure, checked once although saved twice
    assert fig["path"] == "out.png" and fig["ship"] is False
    assert "bar_baseline_nonzero" in {i["rule"] for i in fig["issues"]}

    assert cli_main(["check", str(_script(tmp_path, BAD_SCRIPT, "bad.py")), "--claim",
                     "Removing retrieval costs 8 points", "--width", "slide"]) == 1
    out = capsys.readouterr().out
    assert "8 points: found" in out and "read at 1280 px" in out


def test_cli_check_script_failures(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli_main(["check", str(_script(tmp_path, "raise RuntimeError('boom')\n", "e.py"))]) == 2
    assert "SCRIPT ERROR" in capsys.readouterr().err
    assert cli_main(["check", str(_script(tmp_path, "x = 1\n", "none.py"))]) == 2
    assert "no figure" in capsys.readouterr().err
    assert cli_main(["check", str(tmp_path / "missing.py")]) == 2
    assert cli_main(["check", str(_script(tmp_path, GOOD_SCRIPT, "w.py")), "--width", "wide"]) == 2


def test_cli_checks_figures_left_open(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    body = GOOD_SCRIPT.replace('fig.savefig("out.png", dpi=100)\n', "")
    assert cli_main(["check", str(_script(tmp_path, body, "open.py"))]) in (0, 1)
    assert "figure:" in capsys.readouterr().out
    assert sys.argv  # restored
