"""Tests for Nature & Science publication press perfection features."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pytest
from matplotlib.colors import to_hex
from matplotlib.figure import Figure

matplotlib.use("Agg")

import mintfig as mint
from mintfig.annotations import direct_labels, place_labels, style_colorbar
from mintfig.bundle import BundleResult, bundle_figure, to_publication
from mintfig.palettes import PALETTES
from mintfig.plate import Plate
from mintfig.preflight import CheckResult, preflight_figure

PT_TO_MM = 25.4 / 72.0


def _check_by_rule(checks: list[CheckResult], rule: str) -> CheckResult:
    for check in checks:
        if check.rule == rule:
            return check
    raise AssertionError(f"Rule {rule!r} not found in {[c.rule for c in checks]}")


def _assert_zero_bbox_overlap(texts: list[matplotlib.text.Text], renderer: object) -> None:
    bboxes = [t.get_window_extent(renderer) for t in texts]
    for i in range(len(bboxes)):
        for j in range(i + 1, len(bboxes)):
            assert not bboxes[i].overlaps(bboxes[j]), (
                f"Overlapping placed labels: {texts[i].get_text()!r} ({bboxes[i]}) "
                f"vs {texts[j].get_text()!r} ({bboxes[j]})"
            )


class TestPlaceLabelsAndDirectLabels:
    def test_place_labels_resolves_crowded_cluster_deterministically_with_leaders(self) -> None:
        items = [
            (0.50, 0.50, "Sample A", "#C84B31"),
            (0.51, 0.505, "Sample B", "#2C5F8A"),
            (0.49, 0.495, "Sample C", "#1E8A78"),
            (0.505, 0.51, "Sample D", "#6E5A8A"),
            (0.50, 0.52, "Sample E", "#C98A2E"),
        ]

        def _run_once() -> tuple[list[tuple[float, float]], int, list[float]]:
            plate = Plate(journal="nature", width="single", height_mm=70.0, layout=(1, 1))
            ax = plate["a"]
            try:
                ax.scatter([p[0] for p in items], [p[1] for p in items], s=14, c=[p[3] for p in items])
                ax.set_xlim(0.0, 1.0)
                ax.set_ylim(0.0, 1.0)
                ax.set_xlabel("Order parameter")
                ax.set_ylabel("Susceptibility")

                texts = place_labels(ax, items, leader_lw=0.45, min_sep_pt=2.5)
                plate.fig.canvas.draw()
                renderer = plate.fig.canvas.get_renderer()

                assert len(texts) == len(items)
                _assert_zero_bbox_overlap(texts, renderer)

                leaders = [ln for ln in ax.lines if getattr(ln, "_mintfig_leader", False)]
                assert len(leaders) >= 2
                lws = [float(ln.get_linewidth()) for ln in leaders]
                assert all(lw == pytest.approx(0.45) for lw in lws)

                report = plate.preflight()
                assert _check_by_rule(report.checks, "text_overlaps").status == "pass"
                assert _check_by_rule(report.checks, "line_past_axis").status == "pass"

                positions = [(float(t.get_position()[0]), float(t.get_position()[1])) for t in texts]
                return positions, len(leaders), lws
            finally:
                plt.close(plate.fig)

        pos1, n1, _ = _run_once()
        pos2, n2, _ = _run_once()
        assert np.allclose(pos1, pos2, atol=1e-9)
        assert n1 == n2

    def test_direct_labels_separates_top_edge_exiting_and_crowded_curves(self) -> None:
        plate = Plate(journal="nature", width="single", height_mm=72.0, layout=(1, 1))
        ax = plate["a"]
        try:
            x = np.linspace(0.0, 10.0, 80)
            # Four steep curves exiting near the same top edge (panel d dome scenario)
            ax.plot(x, 0.25 * x**1.7, label="x = 0.08")
            ax.plot(x, 0.32 * x**1.7, label="x = 0.12")
            ax.plot(x, 0.41 * x**1.7, label="x = 0.16")
            ax.plot(x, 0.52 * x**1.7, label="x = 0.20")
            ax.set_xlim(0.0, 10.0)
            ax.set_ylim(0.0, 10.0)
            ax.set_xlabel("Temperature (K)")
            ax.set_ylabel("Resistivity (a.u.)")

            texts = direct_labels(ax)
            plate.fig.canvas.draw()
            renderer = plate.fig.canvas.get_renderer()

            assert len(texts) == 4
            _assert_zero_bbox_overlap(texts, renderer)
            leaders = [ln for ln in ax.lines if getattr(ln, "_mintfig_leader", False)]
            assert len(leaders) >= 1
            assert all(float(ln.get_linewidth()) == pytest.approx(0.45) for ln in leaders)

            report = plate.preflight()
            assert _check_by_rule(report.checks, "text_overlaps").status == "pass"
            assert _check_by_rule(report.checks, "line_past_axis").status == "pass"
        finally:
            plt.close(plate.fig)

    def test_direct_labels_draws_leaders_when_vertically_crowded_at_right_edge(self) -> None:
        plate = Plate(journal="nature", width="single", height_mm=70.0, layout=(1, 1))
        ax = plate["a"]
        try:
            x = np.linspace(0.0, 10.0, 40)
            for idx in range(5):
                ax.plot(x, 1.0 + 0.005 * idx + 0.05 * x, label=f"Series {idx + 1}")
            ax.set_xlabel("Time (s)")
            ax.set_ylabel("Response")

            texts = direct_labels(ax)
            plate.fig.canvas.draw()
            renderer = plate.fig.canvas.get_renderer()
            assert len(texts) == 5
            _assert_zero_bbox_overlap(texts, renderer)

            leaders = [ln for ln in ax.lines if getattr(ln, "_mintfig_leader", False)]
            assert len(leaders) >= 2
            assert _check_by_rule(plate.preflight().checks, "line_past_axis").status == "pass"
        finally:
            plt.close(plate.fig)


class TestColorbarHairlineBorder:
    def test_style_colorbar_sets_04pt_cbd2d9_hairline(self) -> None:
        plate = Plate(journal="nature", width="single", height_mm=70.0, layout=(1, 1))
        ax = plate["a"]
        try:
            data = np.linspace(0.0, 1.0, 64).reshape(8, 8)
            im = ax.imshow(data, cmap="mintfig_navy")
            cbar = plate.fig.colorbar(im, ax=ax)
            style_colorbar(cbar, label="Amplitude")

            assert cbar.outline.get_visible() is True
            assert float(cbar.outline.get_linewidth()) == pytest.approx(0.4)
            assert to_hex(cbar.outline.get_edgecolor()).upper() == "#CBD2D9"
            assert _check_by_rule(plate.preflight().checks, "hairline_strokes").status == "pass"
        finally:
            plt.close(plate.fig)


class TestCmykGamutPreflight:
    @pytest.mark.parametrize(
        ("neon_hex", "expected_hue"),
        [
            ("#00FF00", "electric green"),
            ("#00FFFF", "electric cyan"),
            ("#FF00FF", "electric magenta"),
            ("#0000FF", "electric blue"),
        ],
    )
    def test_flags_out_of_cmyk_gamut_neon_colors(self, neon_hex: str, expected_hue: str) -> None:
        plate = Plate(journal="nature", width="single", height_mm=65.0, layout=(1, 1))
        ax = plate["a"]
        try:
            ax.plot([0, 1, 2], [0, 1, 0.8], color=neon_hex, label="Neon curve")
            ax.set_xlabel("X")
            ax.set_ylabel("Y")
            report = preflight_figure(plate.fig, "nature")
            check = _check_by_rule(report.checks, "cmyk_gamut")
            assert check.status == "warn"
            assert neon_hex in check.message
            assert expected_hue in check.message
            assert check.fix_hint is not None and "palette=" in check.fix_hint
            # Warning-level rule must not cause strict failure by itself
            assert report.passed is True
        finally:
            plt.close(plate.fig)

    def test_flags_neon_bar_patch_and_scatter_marker(self) -> None:
        plate = Plate(journal="nature", width="double", height_mm=65.0, layout=(1, 2))
        try:
            plate["a"].bar([0, 1], [3, 5], color=["#2C5F8A", "#39FF14"])
            plate["a"].set_xlabel("Group")
            plate["a"].set_ylabel("Value")
            plate["b"].scatter([0, 1, 2], [1, 2, 1.5], color="#FF00CC", s=20)
            plate["b"].set_xlabel("X")
            plate["b"].set_ylabel("Y")
            report = preflight_figure(plate.fig, "nature")
            check = _check_by_rule(report.checks, "cmyk_gamut")
            assert check.status == "warn"
            assert set(check.panels) == {"a", "b"}
        finally:
            plt.close(plate.fig)

    @pytest.mark.parametrize("palette_name", list(PALETTES.keys()))
    def test_builtin_palettes_have_zero_cmyk_false_positives(self, palette_name: str) -> None:
        plate = Plate(
            journal="nature",
            width="double",
            height_mm=70.0,
            layout=(1, 1),
            palette=palette_name,
        )
        ax = plate["a"]
        try:
            x = np.linspace(0, 5, 20)
            for idx, col in enumerate(PALETTES[palette_name]):
                ax.plot(x, np.sin(x + idx * 0.4) + idx * 0.3, color=col)
            ax.set_xlabel("Time (s)")
            ax.set_ylabel("Signal")
            report = preflight_figure(plate.fig, "nature")
            check = _check_by_rule(report.checks, "cmyk_gamut")
            assert check.status == "pass", f"False positive on palette {palette_name!r}: {check.message}"
        finally:
            plt.close(plate.fig)


class TestSemanticSvgLayerGrouping:
    def test_svg_contains_hierarchical_semantic_gids_and_restores_state(self, tmp_path: Path) -> None:
        plate = Plate(journal="nature", width="double", height_mm=75.0, layout=(1, 2))
        try:
            x = np.linspace(0, 6, 40)
            (line_a,) = plate["a"].plot(x, np.sin(x), label="Sine")
            plate["a"].text(3.0, 0.5, "Peak")
            plate["a"].set_xlabel("Phase (rad)")
            plate["a"].set_ylabel("Amplitude")

            plate["b"].scatter(x[:15], np.cos(x[:15]), s=12)
            plate["b"].text(1.5, 0.0, "Node")
            plate["b"].set_xlabel("Phase (rad)")
            plate["b"].set_ylabel("Cosine")
            plate.label_panels()

            svg_path = plate.save(tmp_path / "layered.svg")
            # Temporary artist gids on data/annotations restored after save
            assert line_a.get_gid() is None
            # Plate axes and panel label gids persist cleanly
            assert plate["a"].get_gid() == "panel-a/axes"
            assert plate["b"].get_gid() == "panel-b/axes"
        finally:
            plt.close(plate.fig)

        root = ET.fromstring(svg_path.read_text(encoding="utf-8"))
        ids = {el.attrib["id"] for el in root.iter() if "id" in el.attrib}

        for panel in ("panel-a", "panel-b"):
            assert f"{panel}/axes" in ids
            assert f"{panel}/data" in ids
            assert f"{panel}/annotations" in ids
            assert f"{panel}/labels" in ids


class TestAutoCaptionAndToPublication:
    def test_bundle_figure_auto_drafts_caption_txt_with_errorbars_and_panels(self, tmp_path: Path) -> None:
        plate = Plate(journal="science", width="double", height_mm=75.0, layout=(1, 2))
        try:
            x = np.array([1.0, 2.0, 3.0, 4.0])
            plate["a"].errorbar(x, [1.2, 2.5, 3.1, 4.0], yerr=[0.2, 0.25, 0.3, 0.2], label="WT")
            plate["a"].set_title("Wild-type response")
            plate["a"].set_xlabel("Dose (mM)")
            plate["a"].set_ylabel("Activity (U/mg)")
            plate["a"].text(2.5, 1.0, "n = 12")

            plate["b"].plot(x, [1.0, 1.8, 2.2, 2.4], label="Mutant")
            plate["b"].set_title("Mutant kinetics")
            plate["b"].set_xlabel("Dose (mM)")
            plate["b"].set_ylabel("Rate (1/s)")
            plate.set_takeaway("Catalytic activity scales linearly with dose")
            plate.note_panel("a", "Wild-type activity across four doses")
            plate.label_panels()

            res = bundle_figure(plate, tmp_path / "sci_bundle", include_proof=False)
        finally:
            plt.close(plate.fig)

        assert res.caption_txt is not None and res.caption_txt.exists()
        cap = res.caption_txt.read_text(encoding="utf-8").strip()
        assert "Catalytic activity scales linearly with dose." in cap
        # Science uses uppercase panel letters in legends
        assert "A, Wild-type activity across four doses." in cap
        assert "B, Mutant kinetics" in cap
        assert "Error bars" in cap
        assert "n = 12" in cap
        assert cap in res.figure_tex.read_text(encoding="utf-8")
        assert res.to_dict()["caption_txt"] == str(res.caption_txt)

    def test_to_publication_exports_nature_double_bundle_and_exact_mediabox(self, tmp_path: Path) -> None:
        exp = mint.explain(
            "Checkout p99 jumped 4x after v2.3 deploy while search stayed flat",
            mint.compare(
                {"checkout": 1840, "search": 460, "auth": 310, "catalog": 280},
                title="Checkout dominates tail latency",
                label="p99 latency",
                unit="ms",
                highlight="checkout",
                error={"checkout": 140, "search": 35, "auth": 25, "catalog": 20},
                error_label="95% CI",
            ),
            mint.trend(
                [1, 2, 3, 4, 5, 6],
                {
                    "checkout": [520, 540, 560, 1100, 1520, 1840],
                    "search": [450, 460, 455, 465, 458, 460],
                },
                title="Regression began at week 4",
                label="p99 latency",
                unit="ms",
                x_label="Week",
                highlight="checkout",
            ),
            subtitle="Production API latency (n = 240 requests per bucket)",
            source="synthetic telemetry benchmark",
        )
        try:
            # 1. Return Figure when out_dir is None
            pub_fig = to_publication(exp, journal="nature", width="double")
            try:
                assert isinstance(pub_fig, Figure)
                w_mm = pub_fig.get_figwidth() * 25.4
                assert w_mm == pytest.approx(183.0, abs=0.2)
                # Chat headline banner should be stripped from printed journal figure
                fig_text_blob = " ".join(t.get_text() for t in pub_fig.texts)
                assert "Checkout p99 jumped 4x" not in fig_text_blob
            finally:
                plt.close(pub_fig)

            # 2. Export full journal bundle when out_dir is provided
            out_dir = tmp_path / "nature_pub"
            bundle = to_publication(exp, journal="nature", width="double", out_dir=out_dir)
            assert isinstance(bundle, BundleResult)
            assert bundle.figure_pdf.exists()
            assert bundle.figure_svg.exists()
            assert bundle.preview_png.exists()
            assert bundle.proof_png is not None and bundle.proof_png.exists()
            assert bundle.figure_tex.exists()
            assert bundle.caption_txt is not None and bundle.caption_txt.exists()
            assert bundle.report_json.exists()

            # Check caption.txt carries the chat takeaway + panel clauses + 95% CI + n
            cap = bundle.caption_txt.read_text(encoding="utf-8")
            assert "Checkout p99 jumped 4x" in cap
            assert "95% CI" in cap
            assert "240" in cap
            assert "a," in cap and "b," in cap

            # Verify SVG semantic layers exist in exported figure.svg
            svg_root = ET.fromstring(bundle.figure_svg.read_text(encoding="utf-8"))
            svg_ids = {el.attrib["id"] for el in svg_root.iter() if "id" in el.attrib}
            assert "panel-a/axes" in svg_ids
            assert "panel-b/axes" in svg_ids

            # Verify exact PDF MediaBox with pypdf if available
            pypdf = pytest.importorskip("pypdf")
            reader = pypdf.PdfReader(str(bundle.figure_pdf))
            box = reader.pages[0].mediabox
            assert float(box.width) * PT_TO_MM == pytest.approx(183.0, abs=0.2)
            assert float(box.height) * PT_TO_MM <= 170.5
        finally:
            plt.close(exp.fig)

    def test_pub_namespace_exports_place_labels_and_to_publication(self) -> None:
        assert mint.pub.place_labels is place_labels
        assert mint.pub.to_publication is to_publication
        assert "place_labels" in mint.pub.__all__
        assert "to_publication" in mint.pub.__all__
        assert "place_labels" not in mint.__all__
        assert "to_publication" not in mint.__all__
