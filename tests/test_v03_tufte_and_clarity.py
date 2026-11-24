"""Tests for Tufte primitives, direct_labels spine trim, Tufte clarity warnings, and skill rules."""

from __future__ import annotations

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pytest

matplotlib.use("Agg")

import figmint as fm
from figmint.plate import Plate
from figmint.preflight import CheckResult, preflight_figure
from figmint.skill import get_agents_snippet, get_skill_markdown


def _check_by_rule(checks: list[CheckResult], rule: str) -> CheckResult:
    for check in checks:
        if check.rule == rule:
            return check
    raise AssertionError(f"Rule {rule!r} not found in {[c.rule for c in checks]}")


class TestTuftePrimitives:
    def test_direct_labels_trims_bottom_spine_to_data_span(self) -> None:
        plate = Plate(journal="nature", width="single", height_mm=65.0, layout=(1, 1))
        ax = plate["a"]
        x = np.linspace(0.0, 10.0, 40)
        ax.plot(x, np.exp(-x / 3.0), label="Control")
        ax.plot(x, np.exp(-x / 6.0), ls="--", label="Treated")
        ax.set_xlabel("Time (h)")
        ax.set_ylabel("Signal")
        try:
            fm.direct_labels(ax, expand_xlim=0.35, trim_spine=True)
            bounds = ax.spines["bottom"].get_bounds()
            assert bounds is not None
            # Bottom spine must stop at data max (10.0), not stretch into the label gutter
            assert bounds[1] == pytest.approx(10.0, abs=0.05)
            assert ax.get_xlim()[1] > 11.0
        finally:
            plt.close(plate.fig)

    def test_range_frame_trims_spines_and_adds_rug(self) -> None:
        plate = Plate(journal="nature", width="single", height_mm=65.0, layout=(1, 1))
        ax = plate["a"]
        rng = np.random.default_rng(4)
        x = rng.uniform(2.0, 8.0, size=30)
        y = 1.5 * x + rng.normal(0.0, 0.4, size=30)
        ax.scatter(x, y, s=10)
        ax.set_xlabel("X")
        ax.set_ylabel("Y")
        try:
            fm.range_frame(ax, rug=True)
            bx = ax.spines["bottom"].get_bounds()
            by = ax.spines["left"].get_bounds()
            assert bx is not None and by is not None
            assert bx[0] == pytest.approx(float(x.min()), abs=1e-6)
            assert bx[1] == pytest.approx(float(x.max()), abs=1e-6)
            assert by[0] == pytest.approx(float(y.min()), abs=1e-6)
            assert by[1] == pytest.approx(float(y.max()), abs=1e-6)
            assert len(ax.collections) >= 3  # scatter + x rug + y rug
            assert plate.preflight().passed is True
        finally:
            plt.close(plate.fig)

    def test_ghost_context_draws_peer_curves_across_small_multiples(self) -> None:
        plate = Plate(journal="nature", width="double", height_mm=65.0, layout=(1, 3))
        x = np.linspace(0, 1, 25)
        panels = [
            (plate["a"], x, x**0.6),
            (plate["b"], x, x**1.2),
            (plate["c"], x, x**2.0),
        ]
        try:
            ghosts = fm.ghost_context(panels)
            # Each of 3 panels gets 2 peer ghost lines = 6 total
            assert len(ghosts) == 6
            for ax, px, py in panels:
                ax.plot(px, py, color="#C84B31", lw=1.2)
                ax.set_xlabel("Budget")
                ax.set_ylabel("Score")
            plate.label_panels()
            rep = plate.preflight()
            assert rep.passed is True
            assert rep.warnings == []
        finally:
            plt.close(plate.fig)

    def test_tufte_boxplot_slopegraph_and_sparkline_pass_preflight(self) -> None:
        plate = Plate(
            journal="neurips",
            width="full",
            height_mm=85.0,
            layout=[["a", "b"], ["c", "c"]],
            height_ratios=[1.4, 0.6],
            gap_mm=9.0,
        )
        rng = np.random.default_rng(9)
        try:
            fm.tufte_boxplot(
                plate["a"],
                [rng.normal(0.4, 0.1, 25), rng.normal(0.75, 0.12, 25)],
                labels=["Base", "RLVR"],
            )
            plate["a"].set_xlabel("Stage")
            plate["a"].set_ylabel("Score")

            fm.slopegraph(
                plate["b"],
                [40, 62, 74],
                [88, 81, 85],
                ["AIME", "GPQA", "MMLU"],
                left_label="Prior",
                right_label="Frontier",
                highlight="AIME",
                show_delta=True,
            )

            t = np.linspace(0, 100, 60)
            fm.sparkline(
                plate["c"],
                t,
                2.2 - 0.5 * (1 - np.exp(-t / 30.0)),
                label="Train loss",
                normal_band=(1.65, 1.80),
            )
            plate.label_panels()
            rep = plate.preflight()
            assert rep.passed is True
            assert rep.warnings == []
        finally:
            plt.close(plate.fig)


class TestTufteClarityWarnings:
    def test_bar_baseline_nonzero_warns_and_zero_baseline_passes(self) -> None:
        p_bad = Plate(journal="nature", width="single", height_mm=65.0, layout=(1, 1))
        p_bad["a"].bar(["A", "B", "C"], [82.0, 85.0, 89.0])
        p_bad["a"].set_ylim(80.0, 92.0)
        p_bad["a"].set_xlabel("Model")
        p_bad["a"].set_ylabel("Accuracy (%)")
        try:
            rep = preflight_figure(p_bad.fig, "nature")
            assert rep.passed is True  # clarity check is strictly warning
            chk = _check_by_rule(rep.checks, "bar_baseline_nonzero")
            assert chk.status == "warn"
            assert chk.severity == "warning"
            assert chk.panel == "a"
            assert chk.fix_hint and "set_ylim(bottom=0)" in chk.fix_hint
        finally:
            plt.close(p_bad.fig)

        p_ok = Plate(journal="nature", width="single", height_mm=65.0, layout=(1, 1))
        p_ok["a"].bar(["A", "B", "C"], [82.0, 85.0, 89.0])
        p_ok["a"].set_ylim(0.0, 100.0)
        p_ok["a"].set_xlabel("Model")
        p_ok["a"].set_ylabel("Accuracy (%)")
        try:
            rep = preflight_figure(p_ok.fig, "nature")
            assert _check_by_rule(rep.checks, "bar_baseline_nonzero").status == "pass"
        finally:
            plt.close(p_ok.fig)

    def test_chartjunk_hints_warns_on_boxed_legend_heavy_grid_and_spaghetti(self) -> None:
        plate = Plate(journal="nature", width="double", height_mm=75.0, layout=(1, 2))
        x = np.linspace(0, 1, 20)
        for i in range(6):
            plate["a"].plot(x, x * (i + 1) * 0.15, label=f"Series {i}")
        plate["a"].legend(frameon=True)
        plate["a"].set_xlabel("X")
        plate["a"].set_ylabel("Y")

        plate["b"].plot(x, np.sin(x))
        plate["b"].grid(True, linewidth=1.2, color="#666666")
        plate["b"].set_xlabel("X")
        plate["b"].set_ylabel("Y")
        try:
            rep = preflight_figure(plate.fig, "nature")
            assert rep.passed is True  # warnings only
            chk = _check_by_rule(rep.checks, "chartjunk_hints")
            assert chk.status == "warn"
            assert "a" in chk.panels
            assert "b" in chk.panels
            assert chk.details["boxed_legends"]
            assert chk.details["spaghetti_axes"]
            assert chk.details["heavy_grids"]
        finally:
            plt.close(plate.fig)

    def test_text_on_data_warns_when_annotation_sits_on_heavy_data_ink(self) -> None:
        plate = Plate(journal="nature", width="single", height_mm=65.0, layout=(1, 1))
        ax = plate["a"]
        # Dense dark horizontal band right through y=0.5 where text is placed
        x = np.linspace(0, 1, 80)
        for dy in np.linspace(-0.08, 0.08, 9):
            ax.plot(x, np.full_like(x, 0.5 + dy), color="#1A1D21", lw=2.0)
        ax.text(0.5, 0.5, "Buried Label", ha="center", va="center", fontsize=6.5)
        ax.set_ylim(0, 1)
        ax.set_xlabel("X")
        ax.set_ylabel("Y")
        try:
            rep = preflight_figure(plate.fig, "nature")
            assert rep.passed is True  # warning only
            chk = _check_by_rule(rep.checks, "text_on_data")
            assert chk.status == "warn"
            assert "Buried Label" in chk.elements
            assert chk.panel == "a"
        finally:
            plt.close(plate.fig)

    def test_borderless_white_legend_and_clean_annotation_do_not_false_positive(self) -> None:
        plate = Plate(journal="nature", width="single", height_mm=65.0, layout=(1, 1))
        ax = plate["a"]
        x = np.linspace(0, 1, 50)
        ax.plot(x, 0.2 * x + 0.1, color="#214D82", lw=1.1, label="Curve")
        # Borderless pure-white readability halo legend must NOT trigger boxed-legend warning
        leg = ax.legend(loc="upper left", frameon=True)
        leg.get_frame().set(facecolor="white", edgecolor="none", alpha=0.92)
        # Annotation in clear open whitespace must NOT trigger text_on_data
        ax.text(0.85, 0.85, "Clear Label", ha="right", va="top", fontsize=6.5)
        ax.set_ylim(0, 1)
        ax.set_xlabel("X")
        ax.set_ylabel("Y")
        try:
            rep = preflight_figure(plate.fig, "nature")
            assert rep.passed is True
            assert _check_by_rule(rep.checks, "chartjunk_hints").status == "pass"
            assert _check_by_rule(rep.checks, "text_on_data").status == "pass"
        finally:
            plt.close(plate.fig)

    def test_axis_off_hides_default_ticks_from_preflight(self) -> None:
        plate = Plate(journal="nature", width="single", height_mm=60.0, layout=(1, 1))
        ax = plate["a"]
        ax.set_axis_off()
        ax.text(0.5, 0.0, "Bottom Note", transform=ax.transAxes, ha="center", va="bottom", fontsize=6.5)
        try:
            rep = preflight_figure(plate.fig, "nature")
            assert rep.passed is True
            assert _check_by_rule(rep.checks, "text_overlaps").status == "pass"
            assert _check_by_rule(rep.checks, "canvas_clipping").status == "pass"
        finally:
            plt.close(plate.fig)

    def test_skill_assets_include_tufte_grammar(self) -> None:
        md = get_skill_markdown()
        assert "Tufte" in md
        assert "ghost_context" in md
        assert "slopegraph" in md
        assert "range_frame" in md
        snippet = get_agents_snippet()
        assert "Tufte" in snippet
        assert "bar_baseline_nonzero" in snippet


@pytest.fixture(autouse=True)
def _close_all() -> None:
    yield
    plt.close("all")
