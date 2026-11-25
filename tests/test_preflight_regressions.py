"""Regression tests for preflight false positives, panel attribution, and rcParams leaks."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib
import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pytest

matplotlib.use("Agg")

import mintfig as mint
from mintfig.export import save_figure
from mintfig.plate import Plate
from mintfig.preflight import CheckResult, PreflightReport, preflight_figure, preflight_pdf
from mintfig.specs import get_spec, mm_to_in
from mintfig.style import use


def _check_by_rule(report: PreflightReport, rule: str) -> CheckResult:
    for check in report.checks:
        if check.rule == rule:
            return check
    raise AssertionError(f"Rule {rule!r} not found in {[c.rule for c in report.checks]}")


def _issue_by_rule(payload: dict, rule: str) -> dict:
    for issue in payload["issues"]:
        if issue["rule"] == rule:
            return issue
    raise AssertionError(f"Issue {rule!r} not found in {payload['issues']}")


class TestColormapFalsePositives:
    def test_solid_color_scatter_ignores_banned_default_cmap(self) -> None:
        with mpl.rc_context({"image.cmap": "jet"}):
            plate = Plate(journal="nature", width="single", height_mm=65.0, layout=(1, 1))
            plate["a"].scatter([0, 1, 2], [0, 1, 0.5], color="C0")
            try:
                check = _check_by_rule(preflight_figure(plate.fig, "nature"), "colormaps")
            finally:
                plt.close(plate.fig)
        assert check.status == "pass"
        assert "jet" not in check.message
        assert check.details["colormaps"] == []

    def test_solid_color_scatter_not_reported_as_viridis(self) -> None:
        plate = Plate(journal="nature", width="single", height_mm=65.0, layout=(1, 1))
        plate["a"].scatter([0, 1, 2], [0, 1, 0.5], color="C1")
        try:
            check = _check_by_rule(preflight_figure(plate.fig, "nature"), "colormaps")
        finally:
            plt.close(plate.fig)
        assert check.status == "pass"
        assert check.details["colormaps"] == []
        assert "viridis" not in check.message

    def test_rgb_image_ignores_banned_default_cmap(self) -> None:
        with mpl.rc_context({"image.cmap": "jet"}):
            plate = Plate(journal="nature", width="single", height_mm=65.0, layout=(1, 1))
            plate["a"].imshow(np.random.default_rng(0).random((8, 8, 3)))
            try:
                check = _check_by_rule(preflight_figure(plate.fig, "nature"), "colormaps")
            finally:
                plt.close(plate.fig)
        assert check.status == "pass"

    def test_colormapped_scatter_with_jet_still_fails(self) -> None:
        plate = Plate(journal="nature", width="single", height_mm=65.0, layout=(1, 1))
        plate["a"].scatter([0, 1, 2], [0, 1, 0.5], c=[0.1, 0.5, 0.9], cmap="jet")
        try:
            check = _check_by_rule(preflight_figure(plate.fig, "nature"), "colormaps")
        finally:
            plt.close(plate.fig)
        assert check.status == "fail"
        assert check.severity == "error"
        assert check.elements == ["jet"]

    def test_colorbar_from_bare_jet_mappable_still_fails(self) -> None:
        plate = Plate(journal="nature", width="single", height_mm=65.0, layout=(1, 1))
        plate["a"].plot([0, 1], [0, 1])
        sm = mpl.cm.ScalarMappable(norm=mpl.colors.Normalize(0, 1), cmap="jet")
        plate.fig.colorbar(sm, ax=plate["a"])
        try:
            check = _check_by_rule(preflight_figure(plate.fig, "nature"), "colormaps")
        finally:
            plt.close(plate.fig)
        assert check.status == "fail"
        assert "jet" in check.elements

    def test_pass_message_does_not_claim_perceptual_verification(self) -> None:
        plate = Plate(journal="nature", width="single", height_mm=65.0, layout=(1, 1))
        plate["a"].imshow(np.random.default_rng(0).random((8, 8)), cmap="viridis")
        try:
            check = _check_by_rule(preflight_figure(plate.fig, "nature"), "colormaps")
        finally:
            plt.close(plate.fig)
        assert check.status == "pass"
        assert "verified" not in check.message.lower()
        assert "viridis" in check.message
        assert "name check only" in check.message.lower()


class TestPanelAttribution:
    def test_font_sizes_reports_every_offending_panel(self) -> None:
        plate = Plate(journal="nature", width="double", height_mm=90.0, layout=(1, 3))
        for key in ("a", "b", "c"):
            plate[key].plot([0, 1], [0, 1])
        plate["a"].text(1, 0, "tinyA", fontsize=3)
        plate["c"].text(1, 0, "tinyC", fontsize=3)
        try:
            report = preflight_figure(plate.fig, "nature")
        finally:
            plt.close(plate.fig)

        check = _check_by_rule(report, "font_sizes")
        assert check.status == "fail"
        assert check.panel == "a"  # backward compatible: first offender
        assert check.panels == ["a", "c"]
        # elements stay unchanged (evals/run_eval.py matches them literally)
        assert check.elements == ["tinyA (3.0 pt)", "tinyC (3.0 pt)"]
        assert check.element_locations == [
            {"element": "tinyA (3.0 pt)", "panel": "a"},
            {"element": "tinyC (3.0 pt)", "panel": "c"},
        ]

        payload = json.loads(json.dumps(report.to_agent_dict()))
        assert payload["schema_version"] == "0.2"
        issue = _issue_by_rule(payload, "font_sizes")
        assert issue["panel"] == "a"
        assert issue["panels"] == ["a", "c"]
        assert issue["elements"] == ["tinyA (3.0 pt)", "tinyC (3.0 pt)"]
        assert {"rule", "severity", "panel", "elements", "message", "fix_hint"} <= set(issue)
        assert issue["element_locations"][1] == {"element": "tinyC (3.0 pt)", "panel": "c"}

        full = report.to_dict()
        fs = next(c for c in full["checks"] if c["rule"] == "font_sizes")
        assert fs["panels"] == ["a", "c"]
        assert "panels a, c" in report.summary()

    def test_passing_checks_have_empty_panels(self) -> None:
        plate = Plate(journal="nature", width="single", height_mm=65.0, layout=(1, 1))
        plate["a"].plot([0, 1], [0, 1])
        try:
            report = preflight_figure(plate.fig, "nature")
        finally:
            plt.close(plate.fig)
        for check in report.checks:
            if check.status == "pass":
                assert check.panels == []
                assert check.element_locations == []

    def test_colormaps_attributes_all_panels(self) -> None:
        plate = Plate(journal="nature", width="double", height_mm=90.0, layout=(1, 3))
        rng = np.random.default_rng(1)
        plate["a"].imshow(rng.random((8, 8)), cmap="jet")
        plate["b"].plot([0, 1], [0, 1])
        plate["c"].imshow(rng.random((8, 8)), cmap="jet")
        try:
            check = _check_by_rule(preflight_figure(plate.fig, "nature"), "colormaps")
        finally:
            plt.close(plate.fig)
        assert check.status == "fail"
        assert check.panel == "a"
        assert check.panels == ["a", "c"]
        assert check.elements == ["jet"]
        assert check.element_locations == [
            {"element": "jet", "panel": "a"},
            {"element": "jet", "panel": "c"},
        ]

    def test_hairline_strokes_attributes_all_panels(self) -> None:
        plate = Plate(journal="nature", width="double", height_mm=90.0, layout=(1, 3))
        plate["a"].plot([0, 1], [0, 1], linewidth=0.1, label="thinA")
        plate["b"].plot([0, 1], [0, 1])
        plate["c"].plot([0, 1], [1, 0], linewidth=0.1, label="thinC")
        try:
            check = _check_by_rule(preflight_figure(plate.fig, "nature"), "hairline_strokes")
        finally:
            plt.close(plate.fig)
        assert check.status == "warn"
        assert check.panels == ["a", "c"]
        locs = {loc["element"]: loc["panel"] for loc in check.element_locations}
        assert locs["Line2D(thinA) (0.1 pt)"] == "a"
        assert locs["Line2D(thinC) (0.1 pt)"] == "c"

    def test_text_overlaps_and_font_family_attribute_panels(self) -> None:
        plate = Plate(journal="nature", width="double", height_mm=90.0, layout=(1, 2))
        for key in ("a", "b"):
            plate[key].plot([0, 1], [0, 1])
        plate["b"].text(0.5, 0.5, "Alpha Label", ha="center", va="center")
        plate["b"].text(0.5, 0.5, "Beta Label", ha="center", va="center")
        plate["a"].set_title("Serif Title", fontfamily="DejaVu Serif")
        try:
            report = preflight_figure(plate.fig, "nature")
        finally:
            plt.close(plate.fig)

        overlap = _check_by_rule(report, "text_overlaps")
        assert overlap.status == "fail"
        assert overlap.panels == ["b"]
        assert overlap.elements[:2] == ["Alpha Label", "Beta Label"]
        assert all(loc["panel"] == "b" for loc in overlap.element_locations)

        family = _check_by_rule(report, "font_family")
        assert family.status == "warn"
        assert family.panels == ["a"]
        assert family.element_locations[0]["panel"] == "a"

    def test_canvas_clipping_attributes_panels(self) -> None:
        plate = Plate(journal="nature", width="double", height_mm=90.0, layout=(1, 2))
        for key in ("a", "b"):
            plate[key].plot([0, 1], [0, 1])
        runaway = plate["b"].text(
            1.6, 0.5, "Runaway note", transform=plate["b"].transAxes, clip_on=False
        )
        runaway.set_in_layout(False)  # keep constrained layout from making room for it
        try:
            check = _check_by_rule(preflight_figure(plate.fig, "nature"), "canvas_clipping")
        finally:
            plt.close(plate.fig)
        assert check.status == "fail"
        assert check.elements == ["Runaway note"]
        assert check.panels == ["b"]
        assert check.element_locations == [{"element": "Runaway note", "panel": "b"}]


class TestFontSizesReportsBothDirections:
    def test_too_small_and_too_large_reported_together(self) -> None:
        plate = Plate(journal="nature", width="double", height_mm=90.0, layout=(1, 2))
        for key in ("a", "b"):
            plate[key].plot([0, 1], [0, 1])
        plate["a"].text(0.2, 0.2, "tiny", fontsize=3)
        plate["b"].text(0.2, 0.8, "HUGE", fontsize=20)
        try:
            check = _check_by_rule(preflight_figure(plate.fig, "nature"), "font_sizes")
        finally:
            plt.close(plate.fig)
        assert check.status == "fail"
        assert check.severity == "error"
        assert "tiny (3.0 pt)" in check.elements
        assert "HUGE (20.0 pt)" in check.elements
        assert "below" in check.message and "above" in check.message
        assert [i["text"] for i in check.details["too_small"]] == ["tiny"]
        assert [i["text"] for i in check.details["too_large"]] == ["HUGE"]
        assert check.panel == "a"
        assert check.panels == ["a", "b"]
        assert check.fix_hint and "Increase" in check.fix_hint and "Reduce" in check.fix_hint

    def test_only_too_large_stays_warning(self) -> None:
        plate = Plate(journal="nature", width="single", height_mm=65.0, layout=(1, 1))
        plate["a"].plot([0, 1], [0, 1])
        plate["a"].text(0.2, 0.8, "HUGE", fontsize=20)
        try:
            check = _check_by_rule(preflight_figure(plate.fig, "nature"), "font_sizes")
        finally:
            plt.close(plate.fig)
        assert check.status == "warn"
        assert check.elements == ["HUGE (20.0 pt)"]
        assert check.details["too_small"] == []


_DEFAULT_FONT_RC = {"pdf.fonttype": 3, "svg.fonttype": "path"}


class TestVectorFontsLiveRcParams:
    def test_mintfig_tagged_figure_passes_after_rcparams_reset(self, tmp_path: Path) -> None:
        plate = Plate(journal="nature", width="single", height_mm=65.0, layout=(1, 1))
        plate["a"].plot([0, 1], [0, 1])
        try:
            with mpl.rc_context(_DEFAULT_FONT_RC):
                check = _check_by_rule(preflight_figure(plate.fig, "nature"), "vector_fonts")
                pdf_path = plate.save(tmp_path / "tagged.pdf")
        finally:
            plt.close(plate.fig)
        assert check.status == "pass"
        assert check.details["basis"] == "mintfig_export"
        assert check.details["authoritative"] is False
        # And the exported PDF really has no Type 3 fonts.
        assert _check_by_rule(preflight_pdf(pdf_path, "nature"), "vector_fonts").status == "pass"

    def test_fm_figure_tagged_passes(self) -> None:
        fig, ax = mint.figure(journal="nature", width="single", height_mm=60.0)
        ax.plot([0, 1], [0, 1])
        try:
            with mpl.rc_context(_DEFAULT_FONT_RC):
                check = _check_by_rule(preflight_figure(fig, "nature"), "vector_fonts")
        finally:
            plt.close(fig)
        assert check.status == "pass"

    def test_untagged_figure_after_use_context_warns_honestly(self, tmp_path: Path) -> None:
        # Mirrors evals/corpus/messy_11: built inside mint.use(), checked after exit.
        with use("nature"):
            fig, ax = plt.subplots(figsize=(mm_to_in(89.0), mm_to_in(58.0)), layout="constrained")
            ax.plot([0, 1], [0, 1])
        try:
            with mpl.rc_context(_DEFAULT_FONT_RC):
                check = _check_by_rule(preflight_figure(fig, "nature"), "vector_fonts")
                pdf_path = save_figure(fig, tmp_path / "untagged.pdf", spec=get_spec("nature"))
        finally:
            plt.close(fig)
        # Still a warning (a plain fig.savefig would emit Type 3), never an error...
        assert check.status == "warn"
        assert check.severity == "warning"
        assert check.details["basis"] == "current_rcparams"
        # ...and it says plainly that mintfig's exporters force Type 42.
        assert "plain fig.savefig" in check.message
        assert "mint.save_figure" in check.message
        assert check.fix_hint and "No plotting change needed" in check.fix_hint
        assert check.elements == ["pdf.fonttype=3 (expected 42)", "svg.fonttype='path' (expected 'none')"]
        assert _check_by_rule(preflight_pdf(pdf_path, "nature"), "vector_fonts").status == "pass"

    def test_plain_matplotlib_with_type3_still_warns(self) -> None:
        fig, ax = plt.subplots(figsize=(mm_to_in(89.0), mm_to_in(58.0)), layout="constrained")
        ax.plot([0, 1], [0, 1])
        try:
            with mpl.rc_context(_DEFAULT_FONT_RC):
                check = _check_by_rule(preflight_figure(fig, "nature"), "vector_fonts")
        finally:
            plt.close(fig)
        assert check.status == "warn"


class TestMathtextUsesArtistFontset:
    def test_cm_mathtext_flagged_after_context_exit(self) -> None:
        with mpl.rc_context({"mathtext.fontset": "cm"}):
            fig, ax = plt.subplots(figsize=(mm_to_in(89.0), mm_to_in(58.0)), layout="constrained")
            ax.set_xlabel(r"$\alpha$ rate")
        try:
            with mpl.rc_context({"mathtext.fontset": "dejavusans"}):
                check = _check_by_rule(preflight_figure(fig, "nature"), "font_family")
        finally:
            plt.close(fig)
        assert check.status == "warn"
        assert any("mathtext:cm" in e for e in check.elements)

    def test_sans_mathtext_not_flagged_when_global_is_cm(self) -> None:
        with use("nature"):
            fig, ax = plt.subplots(figsize=(mm_to_in(89.0), mm_to_in(58.0)), layout="constrained")
            ax.set_xlabel(r"$\alpha$ rate")
        try:
            with mpl.rc_context({"mathtext.fontset": "cm"}):
                check = _check_by_rule(preflight_figure(fig, "nature"), "font_family")
        finally:
            plt.close(fig)
        assert not any("mathtext" in e for e in check.elements)


@pytest.fixture(autouse=True)
def _close_all_figures():
    yield
    plt.close("all")


# --- Lines past the axis (gallery example 1: a 50% line ran on into the label gutter) ---


def _dose_axes():
    plate = mint.Plate(journal="nature", width="single", height_mm=64.0, layout=(1, 1))
    ax = plate["a"]
    x = np.logspace(-3, 2, 40)
    for name, ic50 in (("A", 0.02), ("B", 0.3)):
        ax.plot(x, 100 / (1 + (x / ic50)), label=name)
    ax.set_xscale("log")
    ax.set_xlim(7e-4, 1.4e2)
    ax.set_xlabel("Concentration (\N{GREEK SMALL LETTER MU}M)")
    ax.set_ylabel("Activity (%)")
    return plate, ax


def _rule(report, rule):
    return next(c for c in report.checks if c.rule == rule)


def test_direct_labels_bounds_a_full_width_reference_line():
    plate, ax = _dose_axes()
    ref = ax.axhline(50.0, linestyle="--", linewidth=0.5)
    mint.direct_labels(ax, expand_xlim=0.34)
    ax.spines["bottom"].set_bounds(7e-4, 1.4e2)
    xs = ref.get_xdata()
    assert np.isclose(min(xs), 7e-4) and np.isclose(max(xs), 1.4e2)
    assert _rule(plate.preflight(), "line_past_axis").status == "pass"


def test_reference_line_past_a_trimmed_axis_fails_preflight():
    plate, ax = _dose_axes()
    mint.direct_labels(ax, expand_xlim=0.34)
    ax.spines["bottom"].set_bounds(7e-4, 1.4e2)
    ax.axhline(50.0, linestyle="--", linewidth=0.5)  # drawn after: spans the label gutter
    result = _rule(plate.preflight(), "line_past_axis")
    assert result.status == "fail"
    assert result.details["offenders"][0]["edge"] == "right"
    assert "ax.hlines" in result.fix_hint
    with pytest.raises(ValueError, match="line_past_axis"):
        plate.preflight(strict=True)


def test_ordinary_axes_with_reference_lines_pass():
    plate = mint.Plate(journal="nature", width="single", height_mm=60.0, layout=(1, 1))
    ax = plate["a"]
    ax.plot([0, 1, 2], [1, 3, 2], label="a")
    ax.axhline(2.0, linestyle="--")
    ax.axvline(1.0, linestyle=":")
    ax.fill_between([0, 1, 2], [0.5, 2.5, 1.5], [1.5, 3.5, 2.5], alpha=0.2)
    ax.set_xlabel("x (s)")
    ax.set_ylabel("y (V)")
    assert _rule(plate.preflight(), "line_past_axis").status == "pass"


def test_unclipped_line_off_the_canvas_fails():
    plate = mint.Plate(journal="nature", width="single", height_mm=60.0, layout=(1, 1))
    ax = plate["a"]
    ax.plot([0, 1], [0, 1], label="a")
    ax.plot([0, 3], [0.5, 0.5], clip_on=False, label="runaway")
    ax.set_xlim(0, 1)
    ax.set_xlabel("x (s)")
    ax.set_ylabel("y (V)")
    result = _rule(plate.preflight(), "line_past_axis")
    assert result.status == "fail" and "runaway" in result.elements
