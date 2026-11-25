"""Regression tests for Plate.label_panels placement and exact physical canvas size."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pytest
from pypdf import PdfReader

matplotlib.use("Agg")

from mintfig import plate as plate_mod
from mintfig.plate import Plate, figure
from mintfig.specs import mm_to_in

PT_TO_MM = 25.4 / 72.0
DY_TOL_MM = 0.3
X = np.linspace(0, 10, 100)


@pytest.fixture(autouse=True)
def _isolate_mpl() -> Iterator[None]:
    saved = dict(matplotlib.rcParams)
    yield
    plt.close("all")
    matplotlib.rcParams.update(saved)


def _label_geometry(p: Plate) -> dict[str, dict[str, float]]:
    """Return per-panel label y, axes top, dy and dx in mm (after a fresh draw)."""
    p.fig.canvas.draw()
    out: dict[str, dict[str, float]] = {}
    for key, txt in p._panel_label_artists.items():
        pos = p[key].get_position()
        x, y = txt.get_position()
        top = pos.y1 * p.height_mm
        out[key] = {
            "x": x * p.width_mm,
            "y": y * p.height_mm,
            "top": top,
            "dy": y * p.height_mm - top,
            "dx": x * p.width_mm - pos.x0 * p.width_mm,
        }
    return out


def _assert_preflight_layout_clean(p: Plate) -> None:
    report = p.preflight()
    by_rule = {c.rule: c for c in report.checks}
    for rule in ("text_overlaps", "canvas_clipping"):
        assert rule in by_rule, f"preflight no longer runs {rule}"
        assert by_rule[rule].status not in {"fail", "warn"}, by_rule[rule].message


def _plain_1x3() -> Plate:
    p = Plate("nature", "double", height_mm=90, layout=(1, 3))
    for k in "abc":
        p[k].plot(X, np.sin(X))
    return p


def _imshow_1x3() -> Plate:
    p = Plate("nature", "double", height_mm=90, layout=(1, 3))
    for k in "ab":
        p[k].plot(X, np.sin(X))
    im = p["c"].imshow(np.random.default_rng(0).normal(size=(8, 8)))
    p.fig.colorbar(im, ax=p["c"])
    return p


def _titled_2x2() -> Plate:
    p = Plate("nature", "double", height_mm=120, layout=[["a", "b"], ["c", "d"]])
    for k in "abcd":
        p[k].plot(X, np.sin(X))
        p[k].set_ylabel("Signal (a.u.)")
    p["b"].set_title("A title on b only")
    return p


def _ceiling_2x2() -> Plate:
    # A very wide first x tick label on the top row hangs into the gap exactly
    # where the bottom-row labels go; the gap must open, not the labels climb.
    p = Plate("nature", "double", height_mm=90, layout=[["a", "b"], ["c", "d"]], gap_mm=2)
    for k in "abcd":
        p[k].plot(X, np.sin(X))
        p[k].set_xlim(0, 10)
    for k in "ab":
        p[k].set_xticks([0, 5, 10], ["−1000000000000", "5", "10"])
    return p


LAYOUTS: dict[str, Callable[[], Plate]] = {
    "plain_1x3": _plain_1x3,
    "imshow_colorbar_1x3": _imshow_1x3,
    "titled_2x2": _titled_2x2,
    "ceiling_2x2": _ceiling_2x2,
}


class TestLabelHeight:
    def test_plain_row_labels_sit_dy_above_axes_top(self) -> None:
        p = _plain_1x3()
        p.label_panels()
        g = _label_geometry(p)
        for key in "abc":
            assert g[key]["dy"] == pytest.approx(1.5, abs=DY_TOL_MM), key
            assert g[key]["dx"] == pytest.approx(-7.0, abs=DY_TOL_MM), key
        assert g["a"]["y"] == pytest.approx(g["b"]["y"], abs=1e-6)
        assert g["a"]["y"] == pytest.approx(g["c"]["y"], abs=1e-6)

    @pytest.mark.parametrize("dy_mm", [0.8, 2.5])
    def test_custom_dy_is_honoured(self, dy_mm: float) -> None:
        p = _plain_1x3()
        p.label_panels(dy_mm=dy_mm)
        g = _label_geometry(p)
        for key in "abc":
            assert g[key]["dy"] == pytest.approx(dy_mm, abs=DY_TOL_MM), key

    def test_out_of_view_tick_labels_are_not_obstacles(self) -> None:
        # sin(x) autoscale puts a 1.25 major tick just outside the view; its label is
        # "visible" but never drawn and previously pushed every label up ~5 mm.
        p = _plain_1x3()
        p.fig.canvas.draw()
        renderer = p.fig.canvas.get_renderer()
        texts = {t.get_text() for t, _bb, _ax in plate_mod._rendered_text_extents(p.fig, renderer)}
        _lo, hi = p["a"].get_ylim()
        assert hi < 1.25
        assert "1.25" not in texts
        assert "1.00" in texts

    def test_fixed_aspect_panel_aligns_with_tallest_axes_in_row(self) -> None:
        p = _imshow_1x3()
        p.label_panels()
        g = _label_geometry(p)
        # Tall line plots: label dy_mm above their own top.
        assert g["a"]["dy"] == pytest.approx(1.5, abs=DY_TOL_MM)
        assert g["b"]["dy"] == pytest.approx(1.5, abs=DY_TOL_MM)
        # Short equal-aspect image: shares the row baseline set by the tallest axes.
        assert g["c"]["top"] < g["a"]["top"] - 5.0
        assert g["c"]["y"] == pytest.approx(g["a"]["y"], abs=1e-6)
        assert g["c"]["y"] == pytest.approx(max(v["top"] for v in g.values()) + 1.5, abs=DY_TOL_MM)

    def test_lower_row_not_dragged_by_text_of_row_above(self) -> None:
        p = _titled_2x2()
        p.label_panels()
        g = _label_geometry(p)
        for key in "abcd":
            assert g[key]["dy"] == pytest.approx(1.5, abs=DY_TOL_MM), key
        assert g["a"]["y"] == pytest.approx(g["b"]["y"], abs=1e-6)
        assert g["c"]["y"] == pytest.approx(g["d"]["y"], abs=1e-6)
        assert g["a"]["x"] == pytest.approx(g["c"]["x"], abs=1e-6)

    def test_row_gap_opens_when_label_would_hit_row_above(self) -> None:
        p = _ceiling_2x2()
        hspace_before = p.fig.get_layout_engine().get()["hspace"]
        p.label_panels()
        g = _label_geometry(p)
        for key in "abcd":
            assert g[key]["dy"] == pytest.approx(1.5, abs=DY_TOL_MM), key
        assert p.fig.get_layout_engine().get()["hspace"] > hspace_before

    def test_label_lifts_clear_of_colliding_title_and_row_follows(self) -> None:
        p = Plate("nature", "single", height_mm=60, layout=(1, 2))
        for k in "ab":
            p[k].plot(X, np.sin(X))
        # Title anchored left of the spine, i.e. right where the label sits.
        p["a"].set_title("Title over the label", x=-0.25, ha="left")
        p.label_panels()
        g = _label_geometry(p)
        p.fig.canvas.draw()
        title_bb = p["a"].title.get_window_extent(p.fig.canvas.get_renderer())
        title_top_mm = title_bb.y1 * p.height_mm / p.fig.bbox.height
        title_left_mm = title_bb.x0 * p.width_mm / p.fig.bbox.width
        # Sanity: the title really reaches back over the label's x position.
        assert title_left_mm < g["a"]["x"] + 2.0
        assert g["a"]["y"] >= title_top_mm + 0.5
        assert g["a"]["y"] == pytest.approx(g["b"]["y"], abs=1e-6)
        _assert_preflight_layout_clean(p)


class TestLabelInvariants:
    @pytest.mark.parametrize("name", sorted(LAYOUTS))
    def test_preflight_overlap_and_clipping_clean(self, name: str) -> None:
        p = LAYOUTS[name]()
        p.label_panels()
        _assert_preflight_layout_clean(p)

    @pytest.mark.parametrize("name", sorted(LAYOUTS))
    def test_label_panels_is_idempotent(self, name: str) -> None:
        p = LAYOUTS[name]()
        n_texts_before = len(p.fig.texts)

        def snapshot() -> tuple[Any, ...]:
            p.fig.canvas.draw()
            params = p.fig.get_layout_engine().get()
            labels = [float(v) for t in p._panel_label_artists.values() for v in t.get_position()]
            axes = [float(v) for k in p.panel_keys for v in p[k].get_position().bounds]
            return labels, axes, [float(v) for v in params["rect"]], float(params["hspace"])

        p.label_panels()
        first = snapshot()
        for _ in range(2):
            p.label_panels()
            again = snapshot()
            assert again[0] == pytest.approx(first[0], abs=1e-9)
            assert again[1] == pytest.approx(first[1], abs=1e-9)
            assert again[2] == pytest.approx(first[2], abs=1e-12)
            assert again[3] == pytest.approx(first[3], abs=1e-12)
        labels = [t for t in p.fig.texts if getattr(t, "_mintfig_panel_label", False)]
        assert len(labels) == len(p.panel_keys)
        assert len(p.fig.texts) == n_texts_before + len(p.panel_keys)


def _snap_to_pixels(fig: Any, dpi: float = 150.0) -> None:
    """Mimic a GUI window manager rounding the canvas to whole pixels."""
    w, h = fig.get_size_inches()
    fig.set_size_inches(int(w * dpi) / dpi, int(h * dpi) / dpi, forward=False)


class TestExactCanvasSize:
    def test_plate_and_figure_sizes_exact_after_construction(self) -> None:
        p = Plate("nature", "double", height_mm=90.0, layout=(1, 3))
        assert tuple(p.fig.get_size_inches()) == (mm_to_in(183.0), mm_to_in(90.0))
        fig, _ax = figure("nature", "single", height_mm=65.0)
        assert tuple(fig.get_size_inches()) == (mm_to_in(89.0), mm_to_in(65.0))

    def test_size_survives_gui_pixel_snapping(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        real_figure = plt.figure
        real_subplots = plt.subplots

        def snapping_figure(*args: Any, **kwargs: Any) -> Any:
            fig = real_figure(*args, **kwargs)
            _snap_to_pixels(fig)
            return fig

        def snapping_subplots(*args: Any, **kwargs: Any) -> Any:
            fig, ax = real_subplots(*args, **kwargs)
            _snap_to_pixels(fig)
            return fig, ax

        monkeypatch.setattr(plate_mod.plt, "figure", snapping_figure)
        monkeypatch.setattr(plate_mod.plt, "subplots", snapping_subplots)

        p = Plate("nature", "double", height_mm=90.0, layout=(1, 3))
        assert tuple(p.fig.get_size_inches()) == (mm_to_in(183.0), mm_to_in(90.0))
        fig, _ax = figure("nature", "single", height_mm=65.0)
        assert tuple(fig.get_size_inches()) == (mm_to_in(89.0), mm_to_in(65.0))

        # A later resize event (window shown / event loop) is undone before export.
        for k in "abc":
            p[k].plot(X, np.sin(X))
        _snap_to_pixels(p.fig)
        p.label_panels()
        assert tuple(p.fig.get_size_inches()) == (mm_to_in(183.0), mm_to_in(90.0))
        _snap_to_pixels(p.fig)
        out = p.save(tmp_path / "snapped.pdf")
        box = PdfReader(str(out)).pages[0].mediabox
        assert float(box.width) * PT_TO_MM == pytest.approx(183.0, abs=0.01)
        assert float(box.height) * PT_TO_MM == pytest.approx(90.0, abs=0.01)
