"""Tests for Plate layout, panel labeling, scientific annotations, PDF dimensions, and hybrid export."""

from __future__ import annotations

from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pytest
from pypdf import PdfReader

matplotlib.use("Agg")

from figmint.annotations import (
    despine,
    direct_labels,
    scalebar,
    sig_bracket,
    style_colorbar,
    zoom_inset,
)
from figmint.export import rasterize_heavy, save_figure
from figmint.plate import Plate, figure
from figmint.specs import get_spec

PT_TO_MM = 25.4 / 72.0


def _collect_pdf_fonts(reader: PdfReader) -> list[dict[str, str]]:
    """Collect all font dictionaries referenced across pages (including nested XObjects)."""
    fonts: list[dict[str, str]] = []
    seen: set[int] = set()

    def _walk_resources(res_obj: object) -> None:
        if res_obj is None:
            return
        res = res_obj.get_object() if hasattr(res_obj, "get_object") else res_obj
        if not isinstance(res, dict):
            return
        font_dict = res.get("/Font")
        if font_dict is not None:
            font_dict = font_dict.get_object() if hasattr(font_dict, "get_object") else font_dict
            if isinstance(font_dict, dict):
                for name, fref in font_dict.items():
                    fobj = fref.get_object() if hasattr(fref, "get_object") else fref
                    obj_id = id(fobj)
                    if obj_id in seen:
                        continue
                    seen.add(obj_id)
                    fonts.append(
                        {
                            "name": str(name),
                            "subtype": str(fobj.get("/Subtype", "")),
                            "basefont": str(fobj.get("/BaseFont", "")),
                        }
                    )
        xobjects = res.get("/XObject")
        if xobjects is not None:
            xobjects = xobjects.get_object() if hasattr(xobjects, "get_object") else xobjects
            if isinstance(xobjects, dict):
                for xobj_ref in xobjects.values():
                    xobj = xobj_ref.get_object() if hasattr(xobj_ref, "get_object") else xobj_ref
                    if isinstance(xobj, dict) and "/Resources" in xobj:
                        _walk_resources(xobj["/Resources"])

    for page in reader.pages:
        _walk_resources(page.get("/Resources"))
    return fonts


class TestPdfMediaBoxAndFonts:
    @pytest.mark.parametrize(
        ("journal", "width_preset", "expected_mm"),
        [
            ("nature", "single", 89.0),
            ("nature", "mid", 120.0),
            ("nature", "double", 183.0),
            ("science", "single", 55.0),
            ("science", "double", 120.0),
            ("science", "full", 184.0),
        ],
    )
    def test_exact_pdf_mediabox_and_zero_type3_fonts(
        self,
        tmp_path: Path,
        journal: str,
        width_preset: str,
        expected_mm: float,
    ) -> None:
        height_mm = 70.0
        plate = Plate(journal=journal, width=width_preset, height_mm=height_mm, layout=(1, 1))
        ax = plate["a"]
        x = np.linspace(0, 10, 50)
        ax.plot(x, np.sin(x))
        ax.set_xlabel(r"Time ($\mu\mathrm{s}$)")
        ax.set_ylabel(r"Signal ($10^{-3}$)")
        plate.label_panels()

        pdf_path = tmp_path / f"{journal}_{width_preset}.pdf"
        out = plate.save(pdf_path)
        plt.close(plate.fig)

        assert out.exists()
        reader = PdfReader(str(out))
        assert len(reader.pages) == 1
        box = reader.pages[0].mediabox
        w_mm = float(box.width) * PT_TO_MM
        h_mm = float(box.height) * PT_TO_MM
        assert w_mm == pytest.approx(expected_mm, abs=0.15)
        assert h_mm == pytest.approx(height_mm, abs=0.15)

        fonts = _collect_pdf_fonts(reader)
        assert len(fonts) >= 1, "Expected embedded vector fonts in exported PDF"
        type3 = [f for f in fonts if f["subtype"] == "/Type3"]
        assert type3 == [], f"Found forbidden Type 3 fonts: {type3}"

    def test_single_figure_helper_locks_dimensions(self, tmp_path: Path) -> None:
        fig, ax = figure(journal="nature", width="single", height_mm=65.0)
        ax.plot([0, 1, 2], [0, 1, 0.5])
        ax.set_xlabel("X")
        ax.set_ylabel("Y")
        pdf_path = save_figure(fig, tmp_path / "single_helper.pdf", spec=get_spec("nature"))
        plt.close(fig)

        reader = PdfReader(str(pdf_path))
        box = reader.pages[0].mediabox
        assert float(box.width) * PT_TO_MM == pytest.approx(89.0, abs=0.15)
        assert float(box.height) * PT_TO_MM == pytest.approx(65.0, abs=0.15)


class TestPlateLayoutAndPanelLabels:
    def test_grid_layout_nature_lowercase_and_case_insensitive_indexing(self) -> None:
        plate = Plate(journal="nature", width="double", height_mm=110.0, layout=(2, 2))
        try:
            assert plate.panel_keys == ["a", "b", "c", "d"]
            assert plate["a"] is plate["A"]
            assert plate["d"] is plate["D"]
            for key in plate.panel_keys:
                ax = plate[key]
                ax.plot([0, 1, 2], [0, 2, 1])
                ax.set_xlabel("x")
                ax.set_ylabel("y")
            labels = plate.label_panels()
            assert [labels[k].get_text() for k in plate.panel_keys] == ["a", "b", "c", "d"]
            for txt in labels.values():
                assert getattr(txt, "_figmint_panel_label", False) is True
                assert txt.get_fontweight() in {"bold", 700}
                assert txt.get_fontsize() == pytest.approx(8.0)

            # Column alignment: a & c share X; b & d share X.
            assert labels["a"].get_position()[0] == pytest.approx(
                labels["c"].get_position()[0], abs=1e-4
            )
            assert labels["b"].get_position()[0] == pytest.approx(
                labels["d"].get_position()[0], abs=1e-4
            )
            # Row alignment: a & b share Y; c & d share Y.
            assert labels["a"].get_position()[1] == pytest.approx(
                labels["b"].get_position()[1], abs=1e-4
            )
            assert labels["c"].get_position()[1] == pytest.approx(
                labels["d"].get_position()[1], abs=1e-4
            )
        finally:
            plt.close(plate.fig)

    def test_mosaic_layout_science_uppercase_labels(self) -> None:
        plate = Plate(
            journal="science",
            width="full",
            height_mm=110.0,
            layout=[["a", "b"], ["a", "c"]],
        )
        try:
            assert plate["a"] is plate["A"]
            assert plate["b"] is plate["B"]
            assert plate["c"] is plate["C"]
            for k in plate.panel_keys:
                plate[k].plot([0, 1], [0, 1])
                plate[k].set_xlabel("X")
                plate[k].set_ylabel("Y")
            labels = plate.label_panels()
            texts = [labels[k].get_text() for k in plate.panel_keys]
            assert texts == ["A", "B", "C"]
            for txt in labels.values():
                assert getattr(txt, "_figmint_panel_label", False) is True
                assert txt.get_fontsize() == pytest.approx(8.5)
        finally:
            plt.close(plate.fig)


class TestAnnotations:
    def test_sig_bracket_auto_stacking_no_overlap(self) -> None:
        plate = Plate(journal="nature", width="single", height_mm=75.0, layout=(1, 1))
        ax = plate["a"]
        try:
            ax.bar([0, 1, 2], [3.0, 4.2, 5.1])
            ax.set_ylim(0, 6.0)
            y_before = ax.get_ylim()[1]

            sig_bracket(ax, 0, 1, p=0.0014)
            sig_bracket(ax, 0, 2, p=0.00002)
            sig_bracket(ax, 1, 2, p=0.03, label="stars")

            plate.fig.canvas.draw()
            renderer = plate.fig.canvas.get_renderer()

            # ylim should expand to keep brackets inside the plot area
            assert ax.get_ylim()[1] > y_before

            # Check that all 3 bracket texts have non-overlapping bounding boxes
            bracket_texts = [t for t in ax.texts if t.get_text().strip()]
            assert len(bracket_texts) == 3
            rendered_labels = [t.get_text() for t in bracket_texts]
            assert any("0.0014" in s for s in rendered_labels)
            assert any("0.0001" in s for s in rendered_labels)
            assert any("*" in s for s in rendered_labels)

            bboxes = [t.get_window_extent(renderer) for t in bracket_texts]
            for i in range(len(bboxes)):
                for j in range(i + 1, len(bboxes)):
                    assert not bboxes[i].overlaps(bboxes[j]), (
                        f"Stacked sig_bracket labels overlapped: {rendered_labels[i]!r} vs {rendered_labels[j]!r}"
                    )
        finally:
            plt.close(plate.fig)

    def test_scalebar_and_style_colorbar(self) -> None:
        plate = Plate(journal="nature", width="single", height_mm=75.0, layout=(1, 1))
        ax = plate["a"]
        try:
            rng = np.random.default_rng(7)
            im = ax.imshow(rng.random((64, 64)), cmap="viridis")
            scalebar(ax, length=20.0, unit="µm", pixel_size=1.0, location="lower right")
            cbar = plate.fig.colorbar(im, ax=ax)
            style_colorbar(cbar, label="Intensity (a.u.)")
            plate.fig.canvas.draw()

            # Scalebar should place at least one text containing µm and a line/patch
            all_texts = [t.get_text() for t in ax.texts] + [
                child.get_text()
                for artist in ax.artists
                for child in getattr(artist, "get_children", list)()
                if hasattr(child, "get_text")
            ]
            # Recursively check anchored offsetbox texts too if used
            def _extract_texts(artist: object) -> list[str]:
                found: list[str] = []
                if hasattr(artist, "get_text"):
                    found.append(str(artist.get_text()))
                if hasattr(artist, "get_children"):
                    for ch in artist.get_children():
                        found.extend(_extract_texts(ch))
                return found

            for art in list(ax.artists) + list(ax.texts):
                all_texts.extend(_extract_texts(art))
            assert any("20" in s and "m" in s for s in all_texts)
        finally:
            plt.close(plate.fig)

    def test_direct_labels_separates_close_curves(self) -> None:
        plate = Plate(journal="nature", width="single", height_mm=70.0, layout=(1, 1))
        ax = plate["a"]
        try:
            x = np.linspace(0, 10, 50)
            ax.plot(x, 1.00 + 0.02 * x, label="Control")
            ax.plot(x, 1.01 + 0.02 * x, label="Treatment A")
            ax.plot(x, 1.02 + 0.02 * x, label="Treatment B")
            x_max_before = ax.get_xlim()[1]

            labels = direct_labels(ax)
            plate.fig.canvas.draw()
            renderer = plate.fig.canvas.get_renderer()

            assert ax.get_xlim()[1] > x_max_before
            label_texts = list(labels) if labels is not None else list(ax.texts)
            assert len(label_texts) == 3

            bboxes = [t.get_window_extent(renderer) for t in label_texts]
            for i in range(len(bboxes)):
                for j in range(i + 1, len(bboxes)):
                    assert not bboxes[i].overlaps(bboxes[j]), (
                        f"direct_labels collided: {label_texts[i].get_text()!r} vs {label_texts[j].get_text()!r}"
                    )
        finally:
            plt.close(plate.fig)

    def test_zoom_inset_and_despine(self) -> None:
        plate = Plate(journal="nature", width="single", height_mm=70.0, layout=(1, 1))
        ax = plate["a"]
        try:
            x = np.linspace(0, 10, 100)
            ax.plot(x, np.exp(-x))
            axins = zoom_inset(ax, bounds=(0.45, 0.45, 0.48, 0.45), xlim=(0.0, 2.0), ylim=(0.1, 1.0))
            axins.plot(x, np.exp(-x))
            despine(ax, top=True, right=True)
            plate.fig.canvas.draw()

            assert axins.get_xlim() == pytest.approx((0.0, 2.0))
            assert axins.get_ylim() == pytest.approx((0.1, 1.0))
            assert ax.spines["top"].get_visible() is False
            assert ax.spines["right"].get_visible() is False
        finally:
            plt.close(plate.fig)


class TestHybridRasterizationExport:
    def test_rasterize_heavy_keeps_50k_scatter_pdf_compact_and_vector_text(
        self, tmp_path: Path
    ) -> None:
        rng = np.random.default_rng(42)
        n_pts = 50_000
        x = rng.normal(0.0, 1.0, size=n_pts)
        y = rng.normal(0.0, 1.0, size=n_pts)

        plate = Plate(journal="nature", width="single", height_mm=80.0, layout=(1, 1))
        ax = plate["a"]
        scatter = ax.scatter(x, y, s=1.5, alpha=0.35, linewidths=0)
        ax.set_xlabel("UMAP 1")
        ax.set_ylabel("UMAP 2")
        plate.label_panels()

        count = rasterize_heavy(plate.fig, threshold=10_000)
        assert count >= 1
        assert scatter.get_rasterized() is True
        # Axes spines and text must stay vector (not rasterized)
        assert ax.spines["left"].get_rasterized() is False
        assert ax.xaxis.label.get_rasterized() is False

        pdf_path = plate.save(tmp_path / "dense_50k.pdf", rasterize_above=10_000)
        plt.close(plate.fig)

        size_bytes = pdf_path.stat().st_size
        assert size_bytes < 1_500_000, f"PDF too large ({size_bytes} bytes >= 1.5 MB)"

        reader = PdfReader(str(pdf_path))
        fonts = _collect_pdf_fonts(reader)
        assert len(fonts) >= 1, "Vector fonts missing from hybrid PDF"
        assert [f for f in fonts if f["subtype"] == "/Type3"] == []
