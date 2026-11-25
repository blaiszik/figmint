"""Tests for JournalSpec, unit conversions, palettes, CVD simulation, and Matplotlib styling."""

from __future__ import annotations

import re

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pytest

matplotlib.use("Agg")

from mintfig.palettes import BANNED_COLORMAPS, PALETTES, get_palette, simulate_cvd
from mintfig.specs import JOURNALS, MM_PER_INCH, JournalSpec, get_spec, in_to_mm, mm_to_in
from mintfig.style import apply, rc_params, use

HEX_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


class TestUnitConversions:
    def test_constants_and_roundtrip(self) -> None:
        assert MM_PER_INCH == pytest.approx(25.4)
        assert mm_to_in(25.4) == pytest.approx(1.0)
        assert in_to_mm(1.0) == pytest.approx(25.4)
        for val_mm in (55.0, 89.0, 120.0, 183.0, 184.0):
            assert in_to_mm(mm_to_in(val_mm)) == pytest.approx(val_mm, abs=1e-9)


class TestJournalSpecs:
    def test_nature_spec(self) -> None:
        spec = get_spec("nature")
        assert isinstance(spec, JournalSpec)
        assert spec.name == "nature"
        assert spec.widths_mm["single"] == pytest.approx(89.0)
        assert spec.widths_mm["mid"] == pytest.approx(120.0)
        assert spec.widths_mm["1.5col"] == pytest.approx(120.0)
        assert spec.widths_mm["double"] == pytest.approx(183.0)
        assert spec.widths_mm["full"] == pytest.approx(183.0)
        assert spec.max_height_mm == pytest.approx(170.0)
        assert spec.max_page_height_mm == pytest.approx(247.0)
        assert spec.font_min_pt == pytest.approx(5.0)
        assert spec.font_max_pt == pytest.approx(7.0)
        assert spec.body_pt == pytest.approx(6.5)
        assert spec.tick_pt == pytest.approx(6.0)
        assert spec.legend_pt == pytest.approx(6.0)
        assert spec.panel_label_pt == pytest.approx(8.0)
        assert spec.panel_label_case == "lower"
        assert spec.default_palette == "nature"
        assert spec.dpi_photo == 300
        assert spec.dpi_combo == 500
        assert spec.dpi_line == 1000

    def test_science_spec(self) -> None:
        spec = get_spec("science")
        assert spec.name == "science"
        assert spec.widths_mm["single"] == pytest.approx(55.0)
        assert spec.widths_mm["double"] == pytest.approx(120.0)
        assert spec.widths_mm["2col"] == pytest.approx(120.0)
        assert spec.widths_mm["full"] == pytest.approx(184.0)
        assert spec.widths_mm["3col"] == pytest.approx(184.0)
        assert spec.max_height_mm == pytest.approx(180.0)
        assert spec.max_page_height_mm == pytest.approx(230.0)
        assert spec.font_min_pt == pytest.approx(6.0)
        assert spec.font_max_pt == pytest.approx(8.0)
        assert spec.body_pt == pytest.approx(7.0)
        assert spec.tick_pt == pytest.approx(6.0)
        assert spec.legend_pt == pytest.approx(6.5)
        assert spec.panel_label_pt == pytest.approx(8.5)
        assert spec.panel_label_case == "upper"
        assert spec.default_palette == "science"
        assert spec.dpi_photo == 300
        assert spec.dpi_combo == 600
        assert spec.dpi_line == 1200

    def test_science_advances_spec(self) -> None:
        spec = get_spec("science_advances")
        assert spec.name == "science_advances"
        assert spec.widths_mm["single"] == pytest.approx(84.0)
        assert spec.widths_mm["mid"] == pytest.approx(120.0)
        assert spec.widths_mm["double"] == pytest.approx(175.0)
        assert spec.widths_mm["full"] == pytest.approx(175.0)
        assert spec.panel_label_case == "upper"
        assert spec.font_min_pt == pytest.approx(6.0)
        assert spec.font_max_pt == pytest.approx(8.0)

    def test_get_spec_passthrough_and_errors(self) -> None:
        nature = JOURNALS["nature"]
        assert get_spec(nature) is nature
        with pytest.raises((KeyError, ValueError)):
            get_spec("nonexistent_journal")

    def test_resolve_width_mm(self) -> None:
        nature = get_spec("nature")
        assert nature.resolve_width_mm("single") == pytest.approx(89.0)
        assert nature.resolve_width_mm("double") == pytest.approx(183.0)
        assert nature.resolve_width_mm(105.5) == pytest.approx(105.5)
        with pytest.raises((KeyError, ValueError)):
            nature.resolve_width_mm("unknown_preset")
        with pytest.raises(ValueError):
            nature.resolve_width_mm(-10.0)
        with pytest.raises(ValueError):
            nature.resolve_width_mm(0.0)


class TestPalettesAndCVD:
    @pytest.mark.parametrize("name", ["nature", "science", "okabe_ito", "tol_bright", "tol_muted"])
    def test_palettes_valid_hex(self, name: str) -> None:
        assert name in PALETTES
        colors = get_palette(name)
        assert len(colors) >= 6
        for c in colors:
            assert HEX_RE.match(c), f"Invalid hex color {c!r} in palette {name!r}"

    def test_unknown_palette_raises(self) -> None:
        with pytest.raises((KeyError, ValueError)):
            get_palette("not_a_palette")

    def test_banned_colormaps(self) -> None:
        for bad in ("jet", "rainbow", "hsv"):
            assert bad in BANNED_COLORMAPS

    @pytest.mark.parametrize("kind", ["deuteranopia", "protanopia", "tritanopia", "grayscale"])
    def test_simulate_cvd_uint8_invariants(self, kind: str) -> None:
        rng = np.random.default_rng(123)
        img = rng.integers(0, 256, size=(24, 32, 3), dtype=np.uint8)
        out = simulate_cvd(img, kind)  # type: ignore[arg-type]
        assert out.shape == img.shape
        assert out.dtype == np.uint8
        assert int(out.min()) >= 0
        assert int(out.max()) <= 255

    @pytest.mark.parametrize("kind", ["deuteranopia", "protanopia", "tritanopia", "grayscale"])
    def test_simulate_cvd_float_invariants(self, kind: str) -> None:
        rng = np.random.default_rng(456)
        img = rng.random((16, 20, 3), dtype=np.float64)
        out = simulate_cvd(img, kind)  # type: ignore[arg-type]
        assert out.shape == img.shape
        assert np.issubdtype(out.dtype, np.floating)
        assert float(out.min()) >= 0.0 - 1e-9
        assert float(out.max()) <= 1.0 + 1e-9

    @pytest.mark.parametrize("kind", ["deuteranopia", "protanopia", "tritanopia", "grayscale"])
    def test_simulate_cvd_black_and_white_fixed_points(self, kind: str) -> None:
        bw = np.array([[[0, 0, 0], [255, 255, 255]]], dtype=np.uint8)
        out = simulate_cvd(bw, kind)  # type: ignore[arg-type]
        assert np.all(out[0, 0] <= 2)
        assert np.all(out[0, 1] >= 253)

    def test_simulate_cvd_grayscale_equal_channels(self) -> None:
        img = np.array([[[230, 75, 53], [0, 160, 135]]], dtype=np.uint8)
        gray = simulate_cvd(img, "grayscale")
        np.testing.assert_array_equal(gray[..., 0], gray[..., 1])
        np.testing.assert_array_equal(gray[..., 1], gray[..., 2])


class TestStyleRcParams:
    @pytest.mark.parametrize("journal", ["nature", "science", "science_advances"])
    def test_rc_params_enforces_publication_defaults(self, journal: str) -> None:
        spec = get_spec(journal)
        rc = rc_params(journal)
        assert rc["pdf.fonttype"] == 42
        assert rc["ps.fonttype"] == 42
        assert rc["svg.fonttype"] == "none"
        assert rc["font.family"] == "sans-serif"
        assert spec.font_family[0] in rc["font.sans-serif"]
        assert rc["mathtext.fontset"] in {"custom", "dejavusans", "stixsans"}
        assert rc["axes.spines.top"] is False
        assert rc["axes.spines.right"] is False
        assert rc["legend.frameon"] is False
        assert rc["xtick.direction"] == "out"
        assert rc["ytick.direction"] == "out"
        assert rc["axes.linewidth"] == pytest.approx(spec.axes_linewidth_pt)
        assert rc["lines.linewidth"] == pytest.approx(spec.data_linewidth_pt)
        assert rc["axes.labelsize"] == pytest.approx(spec.body_pt)
        assert rc["xtick.labelsize"] == pytest.approx(spec.tick_pt)
        assert rc["ytick.labelsize"] == pytest.approx(spec.tick_pt)

    def test_use_context_manager_restores_rcparams(self) -> None:
        original_top = plt.rcParams["axes.spines.top"]
        original_fonttype = plt.rcParams["pdf.fonttype"]
        plt.rcParams["axes.spines.top"] = True
        plt.rcParams["pdf.fonttype"] = 3
        try:
            with use("nature"):
                assert plt.rcParams["axes.spines.top"] is False
                assert plt.rcParams["pdf.fonttype"] == 42
                assert plt.rcParams["svg.fonttype"] == "none"
            assert plt.rcParams["axes.spines.top"] is True
            assert plt.rcParams["pdf.fonttype"] == 3
        finally:
            plt.rcParams["axes.spines.top"] = original_top
            plt.rcParams["pdf.fonttype"] = original_fonttype

    def test_apply_updates_global_rcparams(self) -> None:
        snapshot = plt.rcParams.copy()
        try:
            apply("science")
            assert plt.rcParams["pdf.fonttype"] == 42
            assert plt.rcParams["axes.spines.top"] is False
            assert plt.rcParams["axes.labelsize"] == pytest.approx(7.0)
        finally:
            plt.rcParams.update(snapshot)
