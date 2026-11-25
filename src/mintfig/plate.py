"""Multi-panel physical-millimeter plate layout engine."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.figure import Figure

from . import export, style
from .specs import JournalSpec, get_spec, mm_to_in

if TYPE_CHECKING:
    from types import TracebackType

    from matplotlib.axes import Axes
    from matplotlib.text import Text

    from .bundle import BundleResult
    from .preflight import PreflightReport


def _grid_key(index: int, *, uppercase: bool) -> str:
    """Generate spreadsheet-style panel keys: a..z, aa.. (or A..Z, AA..)."""
    base = ord("A") if uppercase else ord("a")
    chars: list[str] = []
    n = index
    while True:
        chars.append(chr(base + (n % 26)))
        n = n // 26 - 1
        if n < 0:
            break
    return "".join(reversed(chars))


def _normalize_mosaic(
    layout: list[list[str]] | tuple[int, int],
    *,
    uppercase: bool,
) -> tuple[list[list[str]], int, int]:
    """Normalize a ``(nrows, ncols)`` tuple or mosaic list into a 2D mosaic."""
    if isinstance(layout, tuple):
        if len(layout) != 2:
            raise ValueError(f"Grid layout tuple must have 2 elements (nrows, ncols), got {layout!r}")
        nrows, ncols = int(layout[0]), int(layout[1])
        if nrows < 1 or ncols < 1:
            raise ValueError(f"Grid dimensions must be >= 1, got {layout!r}")
        mosaic: list[list[str]] = []
        idx = 0
        for _ in range(nrows):
            row: list[str] = []
            for _ in range(ncols):
                row.append(_grid_key(idx, uppercase=uppercase))
                idx += 1
            mosaic.append(row)
        return mosaic, nrows, ncols

    if not layout or not layout[0]:
        raise ValueError("Mosaic layout must be a non-empty 2D sequence of panel keys")
    mosaic = [list(row) for row in layout]
    return mosaic, len(mosaic), len(mosaic[0])


def _boxes_overlap(
    a: tuple[float, float, float, float],
    b: tuple[float, float, float, float],
    pad: float = 0.4,
) -> bool:
    """Return True if two (x0, y0, x1, y1) mm boxes intersect with optional padding."""
    return not (
        a[2] + pad <= b[0]
        or b[2] + pad <= a[0]
        or a[3] + pad <= b[1]
        or b[3] + pad <= a[1]
    )


def _lock_figure_size(fig: Figure, width_in: float, height_in: float) -> None:
    """Pin ``fig``'s size to exactly ``width_in`` x ``height_in`` inches.

    GUI backends (e.g. ``macosx``) open a window whose size is snapped to whole
    device pixels and feed that size back into the figure, so a 183.0 mm request
    can come back as 182.88 mm. ``forward=False`` updates the figure (and
    therefore every export) without asking the window to resize again.
    """
    cur_w, cur_h = (float(v) for v in fig.get_size_inches())
    if abs(cur_w - width_in) > 1e-12 or abs(cur_h - height_in) > 1e-12:
        fig.set_size_inches(width_in, height_in, forward=False)


def _rendered_text_extents(
    fig: Figure, renderer: Any
) -> list[tuple[Text, Any, Axes | None]]:
    """Return ``(text, window_extent, owner_axes)`` for every Text that is actually drawn.

    ``owner_axes`` is the axes the text decorates (tick labels do not carry a
    ``.axes`` reference themselves), or None for figure-level text.

    Excludes mintfig panel labels, empty or invisible text, text in hidden axes or
    legends, text clipped entirely outside its clip box, and tick labels of ticks
    outside the axis view interval (Matplotlib keeps those "visible" but never
    draws them).
    """
    from matplotlib.text import Text as _Text

    all_tick_ids: set[int] = set()
    active_tick_ids: set[int] = set()
    hidden_ids: set[int] = set()
    owner: dict[int, Axes] = {}
    for ax in fig.axes:
        for child in ax.findobj(match=_Text):
            owner[id(child)] = ax
        for axis in (ax.xaxis, ax.yaxis):
            axis_on = ax.get_visible() and axis.get_visible()
            if not axis_on:
                hidden_ids.add(id(axis.get_offset_text()))
            v0, v1 = axis.get_view_interval()
            lo, hi = min(v0, v1), max(v0, v1)
            eps = max(abs(hi - lo) * 1e-6, 1e-12)
            owner[id(axis.label)] = ax
            owner[id(axis.get_offset_text())] = ax
            for tick in list(axis.get_major_ticks()) + list(axis.get_minor_ticks()):
                all_tick_ids.update((id(tick.label1), id(tick.label2)))
                owner[id(tick.label1)] = ax
                owner[id(tick.label2)] = ax
                if not axis_on or not tick.get_visible():
                    continue
                loc = tick.get_loc()
                if loc is None or not np.isfinite(loc) or loc < lo - eps or loc > hi + eps:
                    continue
                active_tick_ids.update((id(tick.label1), id(tick.label2)))
    for leg in list(fig.legends) + [ax.get_legend() for ax in fig.axes]:
        if leg is not None and not leg.get_visible():
            hidden_ids.update(id(t) for t in [*leg.get_texts(), leg.get_title()])

    out: list[tuple[Text, Any, Axes | None]] = []
    seen: set[int] = set()
    for txt in fig.findobj(match=_Text):
        tid = id(txt)
        if tid in seen or tid in hidden_ids:
            continue
        seen.add(tid)
        if getattr(txt, "_mintfig_panel_label", False):
            continue
        if tid in all_tick_ids and tid not in active_tick_ids:
            continue
        if not txt.get_visible() or not txt.get_text().strip():
            continue
        if txt.axes is not None and not txt.axes.get_visible():
            continue
        try:
            bb = txt.get_window_extent(renderer)
        except (RuntimeError, ValueError):
            continue
        if bb is None or bb.width <= 0 or bb.height <= 0:
            continue
        if not np.all(np.isfinite([bb.x0, bb.y0, bb.x1, bb.y1])):
            continue
        if txt.get_clip_on():
            clip_box = txt.get_clip_box()
            if clip_box is not None and not bb.overlaps(clip_box):
                continue
        out.append((txt, bb, txt.axes or owner.get(tid)))
    return out


class Plate:
    """Physical-millimeter multi-panel figure plate locked to journal specifications.

    Manages exact mm canvas dimensions, constrained-layout spacing, case-insensitive
    panel access, aligned editorial panel labels, preflight checks, proof sheets,
    and locked-dimension export.
    """

    def __init__(
        self,
        journal: str | JournalSpec = "nature",
        width: str | float = "double",
        height_mm: float | None = None,
        *,
        aspect: float = 0.62,
        layout: list[list[str]] | tuple[int, int] = (1, 1),
        gap_mm: float | tuple[float, float] = 6.0,
        margin_mm: tuple[float, float, float, float] | None = None,
        width_ratios: Sequence[float] | None = None,
        height_ratios: Sequence[float] | None = None,
        palette: str | None = None,
    ) -> None:
        self.spec: JournalSpec = get_spec(journal)
        self.width_mm: float = float(self.spec.resolve_width_mm(width))
        self.height_mm: float = (
            float(height_mm) if height_mm is not None else round(self.width_mm * aspect, 1)
        )
        if self.height_mm <= 0:
            raise ValueError(f"height_mm must be positive, got {self.height_mm}")

        self.palette = palette
        self._prev_rc: dict[str, Any] = dict(mpl.rcParams)
        self._panel_label_artists: dict[str, Text] = {}
        self.takeaway: str | None = None
        self.takeaway_subtitle: str | None = None
        self.panel_notes: dict[str, str] = {}
        self.caption: str | None = None

        if isinstance(gap_mm, tuple):
            w_gap_mm, h_gap_mm = float(gap_mm[0]), float(gap_mm[1])
        else:
            w_gap_mm = h_gap_mm = float(gap_mm)

        mosaic, nrows, ncols = _normalize_mosaic(
            layout,
            uppercase=(self.spec.panel_label_case == "upper"),
        )

        gridspec_kw: dict[str, Any] = {}
        if width_ratios is not None:
            gridspec_kw["width_ratios"] = list(width_ratios)
        if height_ratios is not None:
            gridspec_kw["height_ratios"] = list(height_ratios)

        # Apply journal style so subsequent plotting calls on plate["a"] inherit exact
        # journal typography, linewidths, sans-serif mathtext, and editable PDF fonttype.
        style.apply(self.spec, palette=palette)

        with style.use(self.spec, palette=palette):
            self.fig: Figure = plt.figure(
                figsize=(mm_to_in(self.width_mm), mm_to_in(self.height_mm)),
                layout="constrained",
            )
            self.axes: dict[str, Axes] = self.fig.subplot_mosaic(
                mosaic,
                gridspec_kw=gridspec_kw if gridspec_kw else None,
            )
        self._lock_size()

        self._nrows: int = nrows
        self.panel_keys: list[str] = list(self.axes.keys())
        self._key_lookup: dict[str, str] = {k.lower(): k for k in self.panel_keys}

        # Tag figure and panel axes so preflight and bundle can attribute panels and journal.
        self.fig._mintfig_journal = self.spec.name  # type: ignore[attr-defined]
        self.fig._mintfig_plate = self  # type: ignore[attr-defined]
        for key, ax in self.axes.items():
            ax._mintfig_panel_key = key  # type: ignore[attr-defined]

        # Configure constrained_layout padding in physical mm without altering MediaBox.
        engine = self.fig.get_layout_engine()
        if engine is not None and hasattr(engine, "set"):
            # Split desired gap cleanly between outer/inner inch pads and fractional space.
            w_pad_mm = min(max(w_gap_mm * 0.42, 1.2), 2.8)
            h_pad_mm = min(max(h_gap_mm * 0.42, 1.2), 2.8)

            rem_w_mm = max(0.0, w_gap_mm - 2.0 * w_pad_mm)
            rem_h_mm = max(0.0, h_gap_mm - 2.0 * h_pad_mm)
            avg_col_mm = max(self.width_mm / max(ncols, 1), 10.0)
            avg_row_mm = max(self.height_mm / max(nrows, 1), 10.0)
            wspace = min(rem_w_mm / avg_col_mm, 0.25)
            hspace = min(rem_h_mm / avg_row_mm, 0.25)

            set_kw: dict[str, Any] = {
                "w_pad": mm_to_in(w_pad_mm),
                "h_pad": mm_to_in(h_pad_mm),
                "wspace": wspace,
                "hspace": hspace,
            }
            if margin_mm is not None:
                left_mm, right_mm, bottom_mm, top_mm = (float(v) for v in margin_mm)
                rect_l = left_mm / self.width_mm
                rect_b = bottom_mm / self.height_mm
                rect_w = 1.0 - (left_mm + right_mm) / self.width_mm
                rect_h = 1.0 - (bottom_mm + top_mm) / self.height_mm
                if rect_w <= 0.1 or rect_h <= 0.1:
                    raise ValueError(f"margin_mm={margin_mm} leaves insufficient drawable area")
                set_kw["rect"] = (rect_l, rect_b, rect_w, rect_h)
            engine.set(**set_kw)

    def __enter__(self) -> Plate:  # noqa: PYI034
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        mpl.rcParams.update(self._prev_rc)

    def _lock_size(self) -> None:
        """Re-assert the exact physical canvas size (guards against GUI pixel snapping)."""
        _lock_figure_size(self.fig, mm_to_in(self.width_mm), mm_to_in(self.height_mm))

    def _resolve_key(self, key: str) -> str:
        if key in self.axes:
            return key
        canonical = self._key_lookup.get(key.lower())
        if canonical is not None:
            return canonical
        raise KeyError(f"Unknown panel key {key!r}; available keys: {self.panel_keys}")

    def __getitem__(self, key: str) -> Axes:
        return self.axes[self._resolve_key(key)]

    def __contains__(self, key: object) -> bool:
        if not isinstance(key, str):
            return False
        return key in self.axes or key.lower() in self._key_lookup

    def __len__(self) -> int:
        return len(self.axes)

    def __iter__(self) -> Iterator[str]:
        return iter(self.panel_keys)

    def label_panels(
        self,
        *,
        dx_mm: float = -7.0,
        dy_mm: float = 1.5,
        case: Literal["auto", "lower", "upper"] = "auto",
        align_columns: bool = True,
        align_rows: bool = True,
        labels: dict[str, str] | None = None,
    ) -> dict[str, Text]:
        """Place bold upright panel labels aligned across columns and rows.

        Measures rendered axes tight bounding boxes (including tick labels,
        axis labels, and titles), automatically reserves top/left margin in
        constrained layout when needed so labels never clip, and ensures zero
        overlap with axis text.

        Each label's baseline sits ``dy_mm`` above its axes top. With
        ``align_rows`` every label in a grid row shares the highest baseline of
        that row, so a short fixed-aspect panel (e.g. ``imshow``) is labelled
        level with its tallest neighbour. A label is lifted only past its own
        row's text (a colliding title or top tick label); if the row above's
        text is in the way, the inter-row gap is widened instead. Calling this
        again replaces the previous labels and reproduces the same layout.
        """
        # Remove any previously placed labels before re-computing positions.
        for old_txt in self._panel_label_artists.values():
            try:
                old_txt.remove()
            except ValueError:
                pass
        self._panel_label_artists.clear()

        target_case = self.spec.panel_label_case if case == "auto" else case
        label_lookup = {k.lower(): v for k, v in labels.items()} if labels else {}

        resolved_labels: dict[str, str] = {}
        for key in self.panel_keys:
            if labels and key in labels:
                resolved_labels[key] = labels[key]
            elif key.lower() in label_lookup:
                resolved_labels[key] = label_lookup[key.lower()]
            else:
                resolved_labels[key] = key.upper() if target_case == "upper" else key.lower()

        # Approximate label physical footprint in mm.
        pt_to_mm = 25.4 / 72.0
        label_h_mm = self.spec.panel_label_pt * pt_to_mm * 1.15
        max_chars = max((len(v) for v in resolved_labels.values()), default=1)
        label_w_mm = self.spec.panel_label_pt * pt_to_mm * (0.78 * max(1, max_chars))

        # A text box in mm plus the bottom edge (mm) of the axes that owns it, or
        # None for figure-level text. The owner tells "text of the row above"
        # (which must not drag a label upward) apart from the panel's own text.
        TextBox = tuple[tuple[float, float, float, float], float | None]

        def _measure_geometry() -> tuple[dict[str, dict[str, Any]], list[TextBox]]:
            self._lock_size()
            # Constrained layout with fixed-aspect axes or colorbars may need a
            # second pass to settle after a fresh figure or an engine change;
            # measuring an unsettled layout makes repeated calls drift.
            def _axes_bounds() -> list[tuple[float, ...]]:
                return [tuple(a.get_position().bounds) for a in self.fig.axes]

            self.fig.canvas.draw()
            for _ in range(3):
                before = _axes_bounds()
                self.fig.canvas.draw()
                if _axes_bounds() == before:
                    break
            renderer = self.fig.canvas.get_renderer()
            fig_w_px = float(self.fig.bbox.width) or 1.0
            fig_h_px = float(self.fig.bbox.height) or 1.0
            px_to_mm_x = self.width_mm / fig_w_px
            px_to_mm_y = self.height_mm / fig_h_px

            geom: dict[str, dict[str, Any]] = {}
            for key in self.panel_keys:
                ax = self.axes[key]
                pos = ax.get_position()
                tight = ax.get_tightbbox(renderer)
                ss = ax.get_subplotspec()
                col_idx = int(ss.colspan.start) if ss is not None else 0
                row_idx = int(ss.rowspan.start) if ss is not None else 0

                ax_left_mm = pos.x0 * self.width_mm
                ax_right_mm = pos.x1 * self.width_mm
                ax_top_mm = pos.y1 * self.height_mm

                tight_left_mm = tight.x0 * px_to_mm_x if tight is not None else ax_left_mm
                tight_right_mm = tight.x1 * px_to_mm_x if tight is not None else ax_right_mm

                title_box: tuple[float, float, float, float] | None = None
                if ax.title.get_visible() and ax.title.get_text().strip():
                    tb = ax.title.get_window_extent(renderer)
                    title_box = (
                        tb.x0 * px_to_mm_x,
                        tb.y0 * px_to_mm_y,
                        tb.x1 * px_to_mm_x,
                        tb.y1 * px_to_mm_y,
                    )

                geom[key] = {
                    "col": col_idx,
                    "row": row_idx,
                    "ax_left": ax_left_mm,
                    "ax_right": ax_right_mm,
                    "ax_top": ax_top_mm,
                    "tight_left": min(ax_left_mm, tight_left_mm),
                    "tight_right": max(ax_right_mm, tight_right_mm),
                    "title_box": title_box,
                }

            # Only text that is actually rendered: Matplotlib keeps "visible" tick
            # labels for ticks outside the view limits (e.g. a 1.25 tick on a
            # [-1.1, 1.1] axis); they are never drawn and must not displace labels.
            text_boxes: list[TextBox] = []
            for _txt, bb, owner in _rendered_text_extents(self.fig, renderer):
                owner_bottom = (
                    owner.get_position().y0 * self.height_mm if owner is not None else None
                )
                text_boxes.append(
                    (
                        (
                            bb.x0 * px_to_mm_x,
                            bb.y0 * px_to_mm_y,
                            bb.x1 * px_to_mm_x,
                            bb.y1 * px_to_mm_y,
                        ),
                        owner_bottom,
                    )
                )
            return geom, text_boxes

        def _align_rows(geom: dict[str, dict[str, Any]], raw_y: dict[str, float]) -> None:
            # Every label in a grid row shares the highest label baseline of that
            # row, i.e. the tallest axes top (plus dy_mm) unless a title or tick
            # label lifted one of them.
            row_groups: dict[int, list[str]] = {}
            for key in self.panel_keys:
                row_groups.setdefault(geom[key]["row"], []).append(key)
            for keys in row_groups.values():
                row_y = max(raw_y[k] for k in keys)
                for k in keys:
                    raw_y[k] = row_y

        def _compute_positions(
            geom: dict[str, dict[str, Any]],
            text_boxes: list[TextBox],
            *,
            nudge_past_rows_above: bool = False,
        ) -> tuple[dict[str, tuple[float, float]], float]:
            """Return label positions (mm) and the extra inter-row gap (mm) still needed."""
            raw_x: dict[str, float] = {}
            raw_y: dict[str, float] = {}

            for key in self.panel_keys:
                g = geom[key]
                # Start outside the widest y-axis label or dx_mm left of the axes spine.
                if dx_mm < 0:
                    cand_x = min(g["ax_left"] + dx_mm, g["tight_left"])
                else:
                    cand_x = g["ax_left"] + dx_mm

                # Prevent drifting into an adjacent panel to the left (e.g., its colorbar).
                left_neighbors = [
                    og["tight_right"]
                    for ok, og in geom.items()
                    if ok != key and og["col"] < g["col"] and og["tight_right"] < g["ax_left"]
                ]
                if left_neighbors:
                    min_allowed_x = max(left_neighbors) + 1.5
                    cand_x = max(cand_x, min_allowed_x)

                raw_x[key] = cand_x
                raw_y[key] = g["ax_top"] + dy_mm

            # Align panels sharing the same grid column.
            if align_columns:
                col_groups: dict[int, list[str]] = {}
                for key in self.panel_keys:
                    col_groups.setdefault(geom[key]["col"], []).append(key)
                for keys in col_groups.values():
                    col_x = min(raw_x[k] for k in keys)
                    # Still respect left neighbor clearance across the whole column.
                    left_clear = []
                    col_idx = geom[keys[0]]["col"]
                    min_ax_left = min(geom[k]["ax_left"] for k in keys)
                    for og in geom.values():
                        if og["col"] < col_idx and og["tight_right"] < min_ax_left:
                            left_clear.append(og["tight_right"] + 1.5)
                    if left_clear:
                        col_x = max(col_x, max(left_clear))
                    for k in keys:
                        raw_x[k] = col_x

            # Check if any panel's title collides horizontally with its panel label;
            # if so, lift raw_y above the title.
            for key in self.panel_keys:
                tb = geom[key]["title_box"]
                if tb is not None:
                    lbox = (
                        raw_x[key],
                        raw_y[key],
                        raw_x[key] + label_w_mm,
                        raw_y[key] + label_h_mm,
                    )
                    if _boxes_overlap(lbox, tb, pad=0.8):
                        raw_y[key] = max(raw_y[key], tb[3] + 0.8)

            # Split obstacles: text owned by axes lying entirely above this panel
            # (the previous row's tick labels, xlabel, colorbar) is a ceiling. A
            # label is never pushed up through it; the row gap is widened instead.
            def _is_ceiling(key: str, owner_bottom: float | None) -> bool:
                return owner_bottom is not None and owner_bottom >= geom[key]["ax_top"] - 0.5

            obstacles: dict[str, list[tuple[float, float, float, float]]] = {}
            ceilings: dict[str, list[tuple[float, float, float, float]]] = {}
            for key in self.panel_keys:
                obstacles[key] = []
                ceilings[key] = []
                for box, owner_bottom in text_boxes:
                    if _is_ceiling(key, owner_bottom) and not nudge_past_rows_above:
                        ceilings[key].append(box)
                    else:
                        obstacles[key].append(box)

            if align_rows:
                _align_rows(geom, raw_y)

            # Nudge labels upward past colliding text (own top tick label, wide
            # title, ...), then re-align rows; repeat until stable.
            for _ in range(6):
                moved = False
                for key in self.panel_keys:
                    x_mm, y_mm = raw_x[key], raw_y[key]
                    for _ in range(8):
                        lbox = (x_mm, y_mm, x_mm + label_w_mm, y_mm + label_h_mm)
                        hits = [tb for tb in obstacles[key] if _boxes_overlap(lbox, tb, pad=0.5)]
                        if not hits:
                            break
                        y_mm = max(tb[3] for tb in hits) + 0.6
                    if y_mm > raw_y[key] + 1e-6:
                        moved = True
                        raw_y[key] = y_mm
                if align_rows:
                    _align_rows(geom, raw_y)
                if not moved:
                    break

            # How much more vertical room would every label need below its ceiling?
            gap_deficit = 0.0
            for key in self.panel_keys:
                x_mm, y_mm = raw_x[key], raw_y[key]
                for tb in ceilings[key]:
                    if tb[0] >= x_mm + label_w_mm + 0.5 or tb[2] + 0.5 <= x_mm:
                        continue
                    if tb[3] <= y_mm:
                        continue
                    gap_deficit = max(gap_deficit, y_mm + label_h_mm + 0.5 - tb[1])

            return {k: (raw_x[k], raw_y[k]) for k in self.panel_keys}, gap_deficit

        # Automatically reserve extra top/left margin (and inter-row gap) in
        # constrained_layout when needed so panel labels never clip outside the
        # exact physical canvas nor collide with the row above. Every engine
        # change is followed by a fresh measurement, so the final positions always
        # come from the geometry the labels are drawn on.
        engine = self.fig.get_layout_engine()
        can_adjust = engine is not None and hasattr(engine, "get") and hasattr(engine, "set")
        max_passes = 6
        for attempt in range(max_passes):
            geom, text_boxes = _measure_geometry()
            positions, gap_deficit_mm = _compute_positions(geom, text_boxes)

            min_x = min(pos[0] for pos in positions.values())
            max_top = max(pos[1] + label_h_mm for pos in positions.values())

            left_deficit_mm = max(0.0, 1.2 - min_x)
            top_deficit_mm = max(0.0, max_top - (self.height_mm - 1.2))

            needs_room = left_deficit_mm > 0.1 or top_deficit_mm > 0.1 or gap_deficit_mm > 0.1
            if not needs_room or not can_adjust or attempt == max_passes - 1:
                break

            params = engine.get()  # type: ignore[union-attr]
            set_kw: dict[str, Any] = {}
            if left_deficit_mm > 0.1 or top_deficit_mm > 0.1:
                cur_rect = list(params.get("rect", (0.0, 0.0, 1.0, 1.0)))
                add_left = (left_deficit_mm + 0.8) / self.width_mm if left_deficit_mm > 0.1 else 0.0
                add_top = (top_deficit_mm + 0.8) / self.height_mm if top_deficit_mm > 0.1 else 0.0
                new_left = min(cur_rect[0] + add_left, 0.25)
                new_width = max(cur_rect[2] - (new_left - cur_rect[0]), 0.5)
                new_height = max(cur_rect[3] - add_top, 0.5)
                new_rect = (new_left, cur_rect[1], new_width, new_height)
                if any(abs(a - b) > 1e-9 for a, b in zip(new_rect, cur_rect, strict=True)):
                    set_kw["rect"] = new_rect
            if gap_deficit_mm > 0.1 and self._nrows > 1:
                # Constrained layout separates rows by max(2*h_pad, hspace/nrows)
                # (figure fractions); widen that gap by the measured deficit.
                h_in = mm_to_in(self.height_mm)
                h_pad_frac = float(params.get("h_pad", 0.0) or 0.0) / h_in
                cur_hspace = float(params.get("hspace", 0.0) or 0.0)
                cur_gap = max(2.0 * h_pad_frac, cur_hspace / self._nrows)
                new_gap = min(cur_gap + (gap_deficit_mm + 0.6) / self.height_mm, 0.25)
                if new_gap > cur_gap + 1e-9:
                    set_kw["hspace"] = new_gap * self._nrows
            if not set_kw:
                break
            engine.set(**set_kw)  # type: ignore[union-attr]

        if gap_deficit_mm > 0.1:
            # The layout could not open enough room; avoiding overlap wins over
            # tight placement, so let labels climb past the row above as well.
            positions, _ = _compute_positions(geom, text_boxes, nudge_past_rows_above=True)

        # Final clamped placement inside safe canvas bounds.
        max_safe_x = max(1.0, self.width_mm - max(2.0, label_w_mm + 0.5))
        max_safe_y = max(1.0, self.height_mm - max(1.0, label_h_mm + 0.6))

        for key in self.panel_keys:
            x_mm, y_mm = positions[key]
            x_mm = min(max(x_mm, 1.0), max_safe_x)
            y_mm = min(max(y_mm, 1.0), max_safe_y)

            txt = self.fig.text(
                x_mm / self.width_mm,
                y_mm / self.height_mm,
                resolved_labels[key],
                ha="left",
                va="bottom",
                fontsize=self.spec.panel_label_pt,
                fontweight=self.spec.panel_label_weight,
                fontfamily="sans-serif",
                color="#000000",
            )
            txt._mintfig_panel_label = True  # type: ignore[attr-defined]
            self._panel_label_artists[key] = txt

        return dict(self._panel_label_artists)

    def save(
        self,
        path: str | Path,
        *,
        dpi: int | None = None,
        rasterize_above: int | None = 10_000,
        transparent: bool = False,
    ) -> Path:
        """Export this plate with exact physical dimensions and editable vector fonts."""
        self._lock_size()
        return export.save_figure(
            self.fig,
            path,
            spec=self.spec,
            dpi=dpi,
            rasterize_above=rasterize_above,
            transparent=transparent,
            lock_dimensions=True,
        )

    def preflight(self, *, strict: bool = False) -> PreflightReport:
        """Run automated journal compliance checks on this plate."""
        from . import preflight as _preflight

        self._lock_size()
        return _preflight.preflight_figure(self.fig, self.spec, strict=strict)

    def save_proof(self, path: str | Path, *, dpi: int = 220) -> PreflightReport:
        """Run preflight checks and render a visual CVD + compliance proof sheet PNG."""
        from . import proof as _proof

        report = self.preflight(strict=False)
        _proof.render_proof_sheet(self.fig, report, path, dpi=dpi)
        return report

    def set_takeaway(
        self,
        headline: str,
        *,
        subtitle: str | None = None,
        show: bool = False,
    ) -> Plate:
        """Attach a one-sentence human takeaway (and optionally render it as a figure header)."""
        self.takeaway = headline.strip()
        self.takeaway_subtitle = subtitle.strip() if subtitle else None
        if show and self.takeaway:
            header = self.takeaway if not self.takeaway_subtitle else f"{self.takeaway}\n{self.takeaway_subtitle}"
            txt = self.fig.suptitle(
                header,
                x=0.015,
                ha="left",
                fontsize=self.spec.panel_label_pt,
                fontweight="bold",
                color="#1A1D21",
            )
            txt._mintfig_panel_label = True  # type: ignore[attr-defined]
        return self

    def note_panel(self, key: str, note: str) -> Plate:
        """Record a concise one-line reading note for panel ``key`` (exported to ``figure.json``)."""
        canonical = self._resolve_key(key)
        self.panel_notes[canonical] = note.strip()
        return self

    def bundle(
        self,
        out_dir: str | Path,
        *,
        source_path: str | Path | None = None,
        source_code: str | None = None,
        caption: str | None = None,
        label: str = "fig:fig1",
        takeaway: str | None = None,
        panel_notes: dict[str, str] | None = None,
        include_proof: bool = True,
        preview_dpi: int = 300,
        rasterize_above: int | None = 10_000,
    ) -> BundleResult:
        """Export a complete submission-ready artifact bundle for this plate."""
        from . import bundle as _bundle

        self._lock_size()
        merged_notes = dict(self.panel_notes)
        if panel_notes:
            merged_notes.update(panel_notes)
        return _bundle.bundle_figure(
            self,
            out_dir,
            journal=self.spec,
            source_path=source_path,
            source_code=source_code,
            caption=caption if caption is not None else self.caption,
            label=label,
            takeaway=takeaway if takeaway is not None else self.takeaway,
            takeaway_subtitle=self.takeaway_subtitle,
            panel_notes=merged_notes or None,
            include_proof=include_proof,
            preview_dpi=preview_dpi,
            rasterize_above=rasterize_above,
        )


def figure(
    journal: str | JournalSpec = "nature",
    width: str | float = "single",
    height_mm: float | None = None,
    *,
    aspect: float = 0.72,
    palette: str | None = None,
) -> tuple[Figure, Axes]:
    """Quick single-panel helper with locked physical mm dimensions."""
    spec = get_spec(journal)
    w_mm = float(spec.resolve_width_mm(width))
    h_mm = float(height_mm) if height_mm is not None else round(w_mm * aspect, 1)
    if h_mm <= 0:
        raise ValueError(f"height_mm must be positive, got {h_mm}")

    style.apply(spec, palette=palette)
    with style.use(spec, palette=palette):
        fig, ax = plt.subplots(
            figsize=(mm_to_in(w_mm), mm_to_in(h_mm)),
            layout="constrained",
        )
    _lock_figure_size(fig, mm_to_in(w_mm), mm_to_in(h_mm))
    fig._mintfig_journal = spec.name  # type: ignore[attr-defined]
    return fig, ax
