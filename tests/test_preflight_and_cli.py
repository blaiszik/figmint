"""Tests for preflight compliance checks, proof sheet generation, and the CLI."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pytest
from PIL import Image

matplotlib.use("Agg")

from figmint.cli import main as cli_main
from figmint.export import save_figure
from figmint.plate import Plate
from figmint.preflight import CheckResult, PreflightReport, preflight_figure, preflight_pdf
from figmint.proof import render_proof_sheet
from figmint.specs import get_spec, mm_to_in
from figmint.style import use


def _check_by_rule(report: PreflightReport, rule: str) -> CheckResult:
    for check in report.checks:
        if check.rule == rule:
            return check
    raise AssertionError(f"Rule {rule!r} not found in {[c.rule for c in report.checks]}")


def _build_clean_plate(journal: str = "nature", width: str = "double") -> Plate:
    plate = Plate(journal=journal, width=width, height_mm=95.0, layout=(1, 2))
    x = np.linspace(0.0, 10.0, 60)
    plate["a"].plot(x, np.sin(x), label="Curve A")
    plate["a"].set_xlabel("Time (min)")
    plate["a"].set_ylabel("Signal (a.u.)")
    plate["b"].plot(x, np.cos(x), label="Curve B")
    plate["b"].set_xlabel("Time (min)")
    plate["b"].set_ylabel("Response (a.u.)")
    plate.label_panels()
    return plate


class TestPreflightCleanPass:
    def test_clean_plate_passes_figure_and_pdf_preflight(self, tmp_path: Path) -> None:
        plate = _build_clean_plate("nature", "double")
        try:
            fig_report = plate.preflight(strict=True)
            assert isinstance(fig_report, PreflightReport)
            assert fig_report.passed is True
            assert fig_report.failures == []
            assert "PASS" in fig_report.summary()
            data = fig_report.to_dict()
            assert data["journal"] == "nature"
            assert isinstance(data["checks"], list)

            pdf_path = plate.save(tmp_path / "clean_nature.pdf")
        finally:
            plt.close(plate.fig)

        pdf_report = preflight_pdf(pdf_path, "nature")
        assert pdf_report.passed is True
        assert pdf_report.failures == []
        assert pdf_report.width_mm == pytest.approx(183.0, abs=0.2)


class TestPreflightIntentionalViolations:
    def test_wrong_column_width_fails_figure_and_pdf(self, tmp_path: Path) -> None:
        plate = Plate(journal="nature", width=140.0, height_mm=80.0, layout=(1, 1))
        plate["a"].plot([0, 1], [0, 1])
        plate["a"].set_xlabel("X")
        plate["a"].set_ylabel("Y")
        try:
            report = preflight_figure(plate.fig, "nature")
            assert report.passed is False
            dim_check = _check_by_rule(report, "dimensions")
            assert dim_check.status == "fail"

            with pytest.raises(ValueError):
                preflight_figure(plate.fig, "nature", strict=True)

            pdf_path = plate.save(tmp_path / "bad_width.pdf")
        finally:
            plt.close(plate.fig)

        pdf_report = preflight_pdf(pdf_path, "nature")
        assert pdf_report.passed is False
        assert _check_by_rule(pdf_report, "dimensions").status == "fail"

    def test_tiny_font_size_fails(self) -> None:
        plate = Plate(journal="nature", width="single", height_mm=65.0, layout=(1, 1))
        ax = plate["a"]
        ax.plot([0, 1], [0, 1])
        ax.text(0.5, 0.5, "microscopic", fontsize=3.5)
        try:
            report = preflight_figure(plate.fig, "nature")
            assert report.passed is False
            assert _check_by_rule(report, "font_sizes").status == "fail"
        finally:
            plt.close(plate.fig)

    def test_banned_jet_colormap_fails(self) -> None:
        plate = Plate(journal="nature", width="single", height_mm=65.0, layout=(1, 1))
        ax = plate["a"]
        rng = np.random.default_rng(0)
        ax.imshow(rng.random((16, 16)), cmap="jet")
        try:
            report = preflight_figure(plate.fig, "nature")
            assert report.passed is False
            assert _check_by_rule(report, "colormaps").status == "fail"
        finally:
            plt.close(plate.fig)

    def test_hairline_stroke_flagged(self) -> None:
        plate = Plate(journal="nature", width="single", height_mm=65.0, layout=(1, 1))
        ax = plate["a"]
        ax.plot([0, 1, 2], [0, 1, 0.5], linewidth=0.1)
        try:
            report = preflight_figure(plate.fig, "nature")
            stroke_check = _check_by_rule(report, "hairline_strokes")
            assert stroke_check.status in {"fail", "warn"}
        finally:
            plt.close(plate.fig)

    def test_colliding_text_labels_fail(self) -> None:
        plate = Plate(journal="nature", width="single", height_mm=65.0, layout=(1, 1))
        ax = plate["a"]
        ax.plot([0, 1], [0, 1])
        ax.text(0.5, 0.5, "Alpha Label", ha="center", va="center")
        ax.text(0.5, 0.5, "Beta Label", ha="center", va="center")
        try:
            report = preflight_figure(plate.fig, "nature")
            assert report.passed is False
            overlap_check = _check_by_rule(report, "text_overlaps")
            assert overlap_check.status == "fail"
        finally:
            plt.close(plate.fig)

    def test_clipped_out_of_bounds_text_flagged(self) -> None:
        plate = Plate(journal="nature", width="single", height_mm=65.0, layout=(1, 1))
        ax = plate["a"]
        ax.plot([0, 1], [0, 1])
        # Deliberately place unclipped text outside the right figure edge
        plate.fig.text(1.03, 0.5, "Clipped outside canvas", clip_on=False)
        try:
            report = preflight_figure(plate.fig, "nature")
            clip_check = _check_by_rule(report, "canvas_clipping")
            assert clip_check.status in {"fail", "warn"}
        finally:
            plt.close(plate.fig)

    def test_serif_font_flagged(self) -> None:
        with use("nature"):
            fig, ax = plt.subplots(figsize=(mm_to_in(89.0), mm_to_in(65.0)), layout="constrained")
            ax.plot([0, 1], [0, 1])
            ax.set_title("Serif Title", fontfamily="DejaVu Serif")
            try:
                report = preflight_figure(fig, "nature")
                fam_check = _check_by_rule(report, "font_family")
                assert fam_check.status in {"fail", "warn"}
            finally:
                plt.close(fig)


class TestProofSheet:
    def test_render_proof_sheet_creates_valid_high_res_png(self, tmp_path: Path) -> None:
        plate = _build_clean_plate("nature", "single")
        out_png = tmp_path / "proof_sheet.png"
        try:
            report = plate.preflight()
            returned = render_proof_sheet(plate.fig, report, out_png, dpi=180)
        finally:
            plt.close(plate.fig)

        assert returned == out_png
        assert out_png.exists()
        assert out_png.stat().st_size > 20_000

        with Image.open(out_png) as img:
            assert img.format == "PNG"
            w, h = img.size
            assert w >= 800
            assert h >= 600
            assert img.mode in {"RGB", "RGBA"}


class TestCLI:
    def test_cli_check_pass_and_fail_and_json(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # 1. Compliant Nature PDF
        good_plate = _build_clean_plate("nature", "single")
        good_pdf = good_plate.save(tmp_path / "good.pdf")
        plt.close(good_plate.fig)

        rc_good = cli_main(["check", str(good_pdf), "--journal", "nature"])
        captured_good = capsys.readouterr()
        assert rc_good == 0
        assert "PASS" in captured_good.out

        # JSON output check
        rc_json = cli_main(["check", str(good_pdf), "--journal", "nature", "--json"])
        captured_json = capsys.readouterr()
        assert rc_json == 0
        payload = json.loads(captured_json.out)
        assert payload["journal"] == "nature"
        assert "checks" in payload

        # 2. Non-compliant Nature PDF (wrong width 140 mm)
        with use("nature"):
            bad_fig, bad_ax = plt.subplots(figsize=(mm_to_in(140.0), mm_to_in(70.0)))
            bad_ax.plot([0, 1], [0, 1])
            bad_pdf = save_figure(bad_fig, tmp_path / "bad.pdf", spec=get_spec("nature"))
            plt.close(bad_fig)

        rc_bad = cli_main(["check", str(bad_pdf), "--journal", "nature"])
        captured_bad = capsys.readouterr()
        assert rc_bad == 1
        assert "FAIL" in captured_bad.out

    def test_cli_specs_command(self, capsys: pytest.CaptureFixture[str]) -> None:
        rc_all = cli_main(["specs"])
        out_all = capsys.readouterr().out
        assert rc_all == 0
        assert "nature" in out_all.lower()
        assert "science" in out_all.lower()
        assert "89" in out_all

        rc_one = cli_main(["specs", "--journal", "science"])
        out_one = capsys.readouterr().out
        assert rc_one == 0
        assert "55" in out_one
        assert "184" in out_one

    def test_cli_entry_point_subprocess(self, tmp_path: Path) -> None:
        figmint_bin = Path(sys.executable).parent / "figmint"
        cmd = [str(figmint_bin), "specs"] if figmint_bin.exists() else [sys.executable, "-m", "figmint.cli", "specs"]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        assert proc.returncode == 0
        assert "89" in proc.stdout
