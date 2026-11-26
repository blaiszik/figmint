"""Tests for mintfig v0.3: cell/pnas/neurips/screen specs, layout_collapse, clarity warnings, and figure.json."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pytest
from pypdf import PdfReader

matplotlib.use("Agg")

import mintfig as mint
from mintfig.cli import main as cli_main
from mintfig.plate import Plate
from mintfig.preflight import CheckResult, preflight_figure
from mintfig.runner import run_script
from mintfig.specs import JournalSpec, get_spec
from mintfig.style import rc_params

PT_TO_MM = 25.4 / 72.0


def _check_by_rule(checks: list[CheckResult], rule: str) -> CheckResult:
    for check in checks:
        if check.rule == rule:
            return check
    raise AssertionError(f"Rule {rule!r} not found in {[c.rule for c in checks]}")


class TestNewJournalAndScreenSpecs:
    @pytest.mark.parametrize(
        ("journal", "preset", "expected_mm", "panel_case"),
        [
            ("cell", "single", 85.0, "upper"),
            ("cell", "mid", 114.0, "upper"),
            ("cell", "double", 174.0, "upper"),
            ("pnas", "single", 87.0, "upper"),
            ("pnas", "mid", 114.0, "upper"),
            ("pnas", "double", 178.0, "upper"),
            ("neurips", "half", 67.0, "lower"),
            ("neurips", "mid", 111.8, "lower"),
            ("neurips", "full", 139.7, "lower"),
            ("screen", "chat", 140.0, "lower"),
            ("screen", "wide", 180.0, "lower"),
            ("screen", "slide", 240.0, "lower"),
        ],
    )
    def test_new_specs_dimensions_and_export(
        self,
        tmp_path: Path,
        journal: str,
        preset: str,
        expected_mm: float,
        panel_case: str,
    ) -> None:
        spec = get_spec(journal)
        assert spec.resolve_width_mm(preset) == pytest.approx(expected_mm)
        assert spec.panel_label_case == panel_case
        if journal != "screen":
            assert spec.source_url.startswith("https://")
            assert spec.spec_version
            assert spec.last_verified

        plate = Plate(journal=journal, width=preset, height_mm=65.0, layout=(1, 1))
        plate["a"].plot([0, 1, 2], [0, 1, 0.5])
        plate["a"].set_xlabel("Input")
        plate["a"].set_ylabel("Output")
        plate.label_panels()
        try:
            report = plate.preflight()
            assert report.passed is True
            pdf_path = plate.save(tmp_path / f"{journal}_{preset}.pdf")
        finally:
            plt.close(plate.fig)

        box = PdfReader(str(pdf_path)).pages[0].mediabox
        assert float(box.width) * PT_TO_MM == pytest.approx(expected_mm, abs=0.15)
        assert float(box.height) * PT_TO_MM == pytest.approx(65.0, abs=0.15)

    def test_custom_spec_does_not_inherit_version_claim(self) -> None:
        custom = JournalSpec(
            name="custom_lab",
            display_name="Custom Lab",
            widths_mm={"single": 90.0},
            max_height_mm=150.0,
            max_page_height_mm=200.0,
            font_family=("Helvetica", "Arial"),
            font_min_pt=6.0,
            font_max_pt=8.0,
            body_pt=7.0,
            tick_pt=6.0,
            legend_pt=6.0,
            panel_label_pt=8.0,
            panel_label_case="lower",
        )
        assert custom.spec_version == ""
        assert custom.last_verified == ""
        assert custom.source_url == ""

    def test_cli_specs_json_lists_all_seven_targets(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        rc = cli_main(["specs", "--json"])
        payload = json.loads(capsys.readouterr().out)
        assert rc == 0
        for name in ("nature", "science", "science_advances", "cell", "pnas", "neurips", "screen"):
            assert name in payload


class TestHandoffDeterministicFixes:
    def test_collapsed_constrained_layout_fails_preflight(self) -> None:
        # Incompatible mosaic row splits + tight vertical budget forces constrained_layout
        # to emit a collapse warning or zero-size axes.
        plate = Plate(
            journal="nature",
            width="single",
            height_mm=24.0,
            layout=[
                ["a", "a", "a", "a", "a", "b", "b", "b", "b", "b", "b", "b"],
                ["c", "c", "c", "c", "d", "d", "d", "d", "e", "e", "e", "e"],
            ],
            gap_mm=12.0,
        )
        for key in ("a", "b", "c", "d", "e"):
            plate[key].plot([0, 1], [0, 1])
            plate[key].set_xlabel("Very long horizontal axis label (units)")
            plate[key].set_ylabel("Very long vertical axis label (units)")
        try:
            report = preflight_figure(plate.fig, "nature")
            chk = _check_by_rule(report.checks, "layout_collapse")
            assert chk.status == "fail"
            assert chk.severity == "error"
            assert chk.fix_hint
            assert report.passed is False
        finally:
            plt.close(plate.fig)

    def test_zero_size_axes_fails_layout_collapse(self) -> None:
        plate = Plate(journal="nature", width="single", height_mm=65.0, layout=(1, 1))
        plate["a"].plot([0, 1], [0, 1])
        plate["a"].set_xlabel("X")
        plate["a"].set_ylabel("Y")
        # Add a degenerate zero-height axes
        plate.fig.add_axes((0.1, 0.5, 0.2, 0.0001))
        try:
            report = preflight_figure(plate.fig, "nature")
            chk = _check_by_rule(report.checks, "layout_collapse")
            assert chk.status == "fail"
            assert chk.severity == "error"
        finally:
            plt.close(plate.fig)

    def test_italic_variables_default_in_style(self) -> None:
        assert rc_params("nature")["mathtext.default"] == "it"
        assert rc_params("neurips")["mathtext.default"] == "it"

    def test_scalebar_renders_upright_micro_sign(self) -> None:
        plate = Plate(journal="nature", width="single", height_mm=65.0, layout=(1, 1))
        ax = plate["a"]
        try:
            ax.imshow(np.zeros((32, 32)), cmap="magma")
            _, txt_default = mint.pub.scalebar(ax, 50)
            _, txt_unicode = mint.pub.scalebar(ax, 25, unit="µm", location="upper left")
            assert r"$\mathrm{\mu}$" in txt_default.get_text()
            assert r"$\mathrm{\mu}$" in txt_unicode.get_text()
            assert "µ" not in txt_unicode.get_text()
        finally:
            plt.close(plate.fig)

    def test_runner_reads_caption_takeaway_and_writes_figure_json(
        self, tmp_path: Path
    ) -> None:
        script = tmp_path / "captioned.py"
        script.write_text(
            "import numpy as np\n"
            "import mintfig as mint\n"
            "CAPTION = 'Synthetic scaling loss across four compute orders.'\n"
            "LABEL = 'fig:scaling'\n"
            "TAKEAWAY = 'Validation loss follows a power law with compute.'\n"
            "PANEL_NOTES = {'a': 'Loss decays smoothly with FLOPs.'}\n"
            "def build():\n"
            "    p = mint.Plate(journal='neurips', width='full', height_mm=70.0)\n"
            "    x = np.linspace(1, 10, 40)\n"
            "    p['a'].plot(x, x**-0.5, label='Frontier')\n"
            "    p['a'].set_xlabel('Compute (FLOPs)')\n"
            "    p['a'].set_ylabel('Validation loss')\n"
            "    p.label_panels()\n"
            "    return p\n",
            encoding="utf-8",
        )
        out_dir = tmp_path / "out"
        res = run_script(script, journal="neurips", bundle_dir=out_dir)
        assert res.ok is True
        assert res.bundle is not None
        assert res.bundle.figure_json is not None and res.bundle.figure_json.exists()

        tex = res.bundle.figure_tex.read_text(encoding="utf-8")
        assert "Synthetic scaling loss across four compute orders." in tex
        assert r"\label{fig:scaling}" in tex

        sidecar = json.loads(res.bundle.figure_json.read_text(encoding="utf-8"))
        assert sidecar["journal"] == "neurips"
        assert sidecar["takeaway"] == "Validation loss follows a power law with compute."
        assert sidecar["caption"] == "Synthetic scaling loss across four compute orders."
        assert sidecar["reproduce_sha256"] and len(sidecar["reproduce_sha256"]) == 64
        assert sidecar["panels"][0]["key"] == "a"
        assert sidecar["panels"][0]["note"] == "Loss decays smoothly with FLOPs."
        assert sidecar["panels"][0]["series"] == ["Frontier"]


class TestClarityWarningTierAndMessageHelpers:
    def test_color_separation_warns_on_red_green_solid_lines_and_passes_with_linestyle(
        self,
    ) -> None:
        # Science default red (#EE0000) and green (#008B45) collapse in grayscale & CVD
        p_bad = Plate(journal="science", width="double", height_mm=70.0, layout=(1, 1))
        x = np.linspace(0, 1, 20)
        p_bad["A"].plot(x, x, color="#EE0000", ls="-", label="Treatment")
        p_bad["A"].plot(x, 1 - x, color="#008B45", ls="-", label="Control")
        p_bad["A"].set_xlabel("Time (s)")
        p_bad["A"].set_ylabel("Response")
        try:
            rep = preflight_figure(p_bad.fig, "science")
            # Clarity tier is strictly a warning, never an error
            assert rep.passed is True
            chk = _check_by_rule(rep.checks, "color_separation")
            assert chk.status == "warn"
            assert chk.severity == "warning"
            assert chk.panel == "A"
            assert chk.fix_hint and "linestyle" in chk.fix_hint
        finally:
            plt.close(p_bad.fig)

        # Adding a distinct linestyle resolves the clarity warning
        p_ok = Plate(journal="science", width="double", height_mm=70.0, layout=(1, 1))
        p_ok["A"].plot(x, x, color="#EE0000", ls="-", label="Treatment")
        p_ok["A"].plot(x, 1 - x, color="#008B45", ls="--", label="Control")
        p_ok["A"].set_xlabel("Time (s)")
        p_ok["A"].set_ylabel("Response")
        try:
            rep = preflight_figure(p_ok.fig, "science")
            assert _check_by_rule(rep.checks, "color_separation").status == "pass"
        finally:
            plt.close(p_ok.fig)

    def test_clarity_metadata_warns_missing_colorbar_and_unlabeled_axes(self) -> None:
        plate = Plate(journal="nature", width="double", height_mm=80.0, layout=(1, 2))
        rng = np.random.default_rng(0)
        plate["a"].imshow(rng.random((12, 12)), cmap="viridis")
        plate["b"].plot([0, 1, 2], [0, 1, 0.5])
        try:
            rep = preflight_figure(plate.fig, "nature")
            assert rep.passed is True  # warnings only
            chk = _check_by_rule(rep.checks, "clarity_metadata")
            assert chk.status == "warn"
            assert chk.severity == "warning"
            assert "a" in chk.panels
            assert "b" in chk.panels
            assert chk.fix_hint
        finally:
            plt.close(plate.fig)

    def test_emphasize_and_takeaway_helpers(self, tmp_path: Path) -> None:
        plate = Plate(journal="screen", width="chat", height_mm=80.0, layout=(1, 1))
        x = np.linspace(0, 5, 30)
        l_bg = plate["a"].plot(x, np.sin(x), label="Baseline")[0]
        l_fg = plate["a"].plot(x, np.cos(x), label="Frontier")[0]
        plate["a"].set_xlabel("Step")
        plate["a"].set_ylabel("Score")
        focused = mint.pub.emphasize(plate["a"], keep="Frontier", focus_lw=1.6)
        plate.set_takeaway("Frontier surpasses baseline across all steps.", show=True)
        plate.note_panel("a", "Cosine curve dominates baseline.")
        try:
            assert focused == [l_fg]
            assert l_fg.get_linewidth() == pytest.approx(1.6)
            assert l_bg.get_alpha() == pytest.approx(0.45)
            rep = plate.preflight()
            assert rep.passed is True
            res = plate.bundle(tmp_path / "screen_bundle", include_proof=False)
            sidecar = json.loads(res.figure_json.read_text(encoding="utf-8"))  # type: ignore[union-attr]
            assert sidecar["takeaway"] == "Frontier surpasses baseline across all steps."
            assert sidecar["panels"][0]["note"] == "Cosine curve dominates baseline."
        finally:
            plt.close(plate.fig)


@pytest.fixture(autouse=True)
def _close_all() -> None:
    yield
    plt.close("all")
