"""change() slopegraph form for fm.explain."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

import numpy as np
from matplotlib.axes import Axes
from matplotlib.transforms import Bbox

from ..annotations import _relax_positions_pt
from .core import (
    _MARGIN_MM,
    MAX_CHANGE_ITEMS,
    MAX_COMPARE_ITEMS,
    PT_TO_MM,
    ExplainError,
    Panel,
    _bare_axes,
    _base_spec,
    _Ctx,
    _diff_with_unit,
    _formatter,
    _guarded,
    _is_strict,
    _Measure,
    _named_values,
    _names,
    _plain,
    _record_adjustment,
    _relative_text,
    _signed,
    _Sizes,
    _with_unit,
)

# --------------------------------------------------------------------------- #
# change (slopegraph)
# --------------------------------------------------------------------------- #


#: Narrowest slopegraph plot (mm at scale 1) before change() wraps or drops labels.
_CHANGE_PLOT_MM = 14.0
#: Width (pt at scale 1) a wrapped item name may take under its value in change().
_CHANGE_NAME_PT = 70.0


@_guarded("change")
def change(
    before: Mapping[str, float] | str,
    after: Mapping[str, float] | str,
    *,
    data: Any = None,
    name: str | None = None,
    labels: Sequence[str] = ("Before", "After"),
    title: str | None = None,
    label: str | None = None,
    unit: str | None = None,
    highlight: str | Sequence[str] | None = None,
    fmt: str | None = None,
) -> Panel:
    """What moved between two states? A slopegraph: one line per item, steepness is the change.

    ``before`` and ``after`` map the same item names to values on one scale,
    or name two columns in ``data=`` (with ``name=`` for the item column).
    """
    if data is not None:
        from .._tabular import resolve_change_table

        if labels == ("Before", "After") and isinstance(before, str) and isinstance(after, str):
            labels = (before, after)
        before, after = resolve_change_table(
            data,
            before_col=before,
            after_col=after,
            name_col=name,
        )
    elif name is not None:
        raise ExplainError(
            "change(name=...) requires data= with row-shaped records or a DataFrame.",
            fix_hint='Pass data=rows, e.g. fm.change("v1", "v2", data=rows, name="item").',
        )
    left = _named_values(before, "change(before)")
    right = _named_values(after, "change(after)")
    if set(left) != set(right):
        missing = sorted(set(left) ^ set(right))
        shared = [nm for nm in left if nm in right]
        if not _is_strict() and shared:
            left = {nm: left[nm] for nm in shared}
            right = {nm: right[nm] for nm in shared}
            _record_adjustment(f"change(): dropped unmatched item(s) {missing[:6]!r}")
        else:
            raise ExplainError(
                f"change() needs the same items before and after; unmatched: {missing[:6]!r}.",
                fix_hint="Drop items that lack one of the two values, and say so in `note`.",
            )
    if isinstance(labels, (str, bytes)) or len(labels) != 2:
        raise ExplainError(
            "change(labels) needs exactly two names.", fix_hint='e.g. ("2024", "2025").'
        )
    labels = (str(labels[0]), str(labels[1]))
    names = sorted(right, key=lambda nm: right[nm], reverse=True)
    if len(names) > MAX_CHANGE_ITEMS:
        if not _is_strict():
            req_hl = (
                [highlight]
                if isinstance(highlight, str)
                else ([str(h) for h in highlight] if highlight is not None else [])
            )
            keep = [nm for nm in req_hl if nm in right]
            for nm in sorted(names, key=lambda k: abs(right[k] - left[k]), reverse=True):
                if len(keep) >= MAX_CHANGE_ITEMS:
                    break
                if nm not in keep:
                    keep.append(nm)
            keep_set = set(keep)
            left = {nm: left[nm] for nm in names if nm in keep_set}
            right = {nm: right[nm] for nm in names if nm in keep_set}
            _record_adjustment(f"change(): trimmed {len(names)} items to top {len(keep)} movers")
            names = sorted(right, key=lambda nm: right[nm], reverse=True)
        else:
            raise ExplainError(
                f"change() got {len(names)} items; a slopegraph tangles beyond {MAX_CHANGE_ITEMS}.",
                fix_hint=f"change() takes at most {MAX_CHANGE_ITEMS} items: keep the items the "
                f"takeaway is about, or use compare() on the differences (up to {MAX_COMPARE_ITEMS} "
                "items, baseline= for a reference).",
                rule="too_many_items",
            )
    hl = _names(highlight, names)
    fmt_fn = _formatter([*left.values(), *right.values()], fmt, unit=unit)
    deltas = {nm: right[nm] - left[nm] for nm in names}
    delta_fmt = _formatter(list(deltas.values()), fmt, unit=unit)

    def _delta_text(name: str) -> str:
        return _signed(delta_fmt(deltas[name]))

    points = unit is not None and unit.strip().startswith("%")

    def _moved(name: str) -> str:
        """"+768 ms, +59%"; in points for "%" units ("+5 points"); no percent across zero."""
        shown = _diff_with_unit(_delta_text(name), unit)
        rel = None if points else _relative_text(right[name], left[name], None)
        return f"{shown}, {rel}" if rel else shown

    def _from_to(name: str) -> str:
        # The unit on both values or on neither: "$0.479 → $0.377", "945 ms → 1,379 ms".
        return (
            f"{_with_unit(fmt_fn(left[name]), unit)} \N{RIGHTWARDS ARROW} "
            f"{_with_unit(fmt_fn(right[name]), unit)}"
        )

    biggest = max(names, key=lambda nm: abs(deltas[nm]))
    ups = sum(1 for d in deltas.values() if d > 0)
    downs = sum(1 for d in deltas.values() if d < 0)
    facts = [
        f"largest change: {biggest} {_from_to(biggest)} ({_moved(biggest)})",
        f"{ups} up, {downs} down, {len(names) - ups - downs} unchanged",
    ]
    for item in hl:
        if item != biggest:
            facts.append(f"{item}: {_from_to(item)} ({_moved(item)})")
    # Alt text: the largest change and every highlighted item's.
    alt_facts = [facts[0], *facts[2:]]
    rest = [nm for nm in names if nm not in hl and nm != biggest]
    if rest:
        # One line for the items the takeaway does not name: "the other 4 changed by
        # −2.1% to +2.9%" (points for "%" units; absolute when a percent is meaningless).
        rels = [None if points else _relative_text(right[nm], left[nm], None) for nm in rest]
        if not points and all(rels):
            pct = sorted(rest, key=lambda nm: (right[nm] - left[nm]) / abs(left[nm]))
            lo_t = _relative_text(right[pct[0]], left[pct[0]], None)
            hi_t = _relative_text(right[pct[-1]], left[pct[-1]], None)
        else:
            by = sorted(rest, key=lambda nm: deltas[nm])
            lo_t = _diff_with_unit(_delta_text(by[0]), unit)
            hi_t = _diff_with_unit(_delta_text(by[-1]), unit)
        who = "the other item" if len(rest) == 1 else f"the other {len(rest)}"
        span = lo_t if len(rest) == 1 or lo_t == hi_t else f"{lo_t} to {hi_t}"
        facts.append(f"{who} changed by {span}")

    def _right_text(name: str, level: int, measure: _Measure, sizes: _Sizes) -> str:
        """The label at the line's end. Level 0: "45.4  math (+16.8)" on one line; from
        level 1 the name goes under "45.4  (+16.8)", wrapped onto two lines if long."""
        head = fmt_fn(right[name])
        if level == 0:
            return f"{head}  {name} ({_delta_text(name)})"
        head = f"{head}  ({_delta_text(name)})"
        budget = max(measure.width_pt(head, sizes.small), 0.6 * _CHANGE_NAME_PT * sizes.scale)
        lines = measure.wrap(name, budget, sizes.small)
        if len(lines) > 2:
            lines = [lines[0], " ".join(lines[1:])]
        return "\n".join([head, *lines])

    def _layout(cell_width_mm: float, measure: _Measure, sizes: _Sizes) -> tuple[int, float]:
        """How the labels fit a cell this wide: the first level whose plot keeps its
        minimum width (level 2 also drops the left-hand values), and the points needed."""
        weight = "bold"  # measure as the widest weight drawn
        cell_pt = min(cell_width_mm, 92.0) * sizes.scale / PT_TO_MM
        heads = [measure.width_pt(t, sizes.small, "bold") for t in labels]
        plot_pt = max(_CHANGE_PLOT_MM * sizes.scale / PT_TO_MM, 0.5 * sum(heads) + 6.0)
        left_pt = max(measure.width_pt(fmt_fn(left[nm]), sizes.small, weight) for nm in names)
        need = 0.0
        for level in (0, 1, 2):
            right_pt = max(
                measure.width_pt(line, sizes.small, weight)
                for nm in names
                for line in _right_text(nm, level, measure, sizes).split("\n")
            )
            need = (0.0 if level == 2 else left_pt + 6.0) + plot_pt + 6.0 + right_pt + 4.0
            if need <= cell_pt:
                return level, need
        return 3, need

    def _label_lines(cell_width_mm: float, measure: _Measure, sizes: _Sizes) -> int:
        level, _need = _layout(cell_width_mm, measure, sizes)
        if level == 0:
            return 1
        return max(
            len(_right_text(nm, min(level, 2), measure, sizes).split("\n")) for nm in names
        )

    def _height(w: float, measure: _Measure, sizes: _Sizes, tight: bool) -> float:
        lines = _label_lines(w, measure, sizes)
        if lines == 1:
            return max(30.0, 4.6 * len(names) + 10.0) if tight else max(38.0, 4.6 * len(names) + 12.0)
        # Multi-line labels stack: each needs its lines of small text.
        per = lines * 1.22 * sizes.small / sizes.scale * PT_TO_MM + 0.6
        return max(30.0 if tight else 38.0, per * len(names) + (10.0 if tight else 12.0))

    def _draw(ctx: _Ctx, ax: Axes) -> Callable[[], None]:
        sz = ctx.sizes
        theme = ctx.theme
        level, need_pt = _layout(ctx.cell_width_mm, ctx.measure, sz)
        if level == 3:
            content_pt = (ctx.fig.bbox.width * ctx.pt_per_px) - 2 * _MARGIN_MM * sz.scale / PT_TO_MM
            share = need_pt / content_pt
            if share <= 1 / 3:
                needs, example = "a third of the width", '[["a", "a", "b"]]'
            elif share <= 1 / 2:
                needs, example = "half the width", '[["a", "b"]]'
            elif share <= 2 / 3:
                needs, example = "two thirds of the width", '[["a", "b", "b"]]'
            else:
                needs, example = "the full width", '[["a"], ["b"]]'
            raise ExplainError(
                f"change() labels need at least {needs} ({need_pt * PT_TO_MM:.0f} mm, "
                f"{100 * share:.0f}% of the figure) even with names wrapped and the left-hand "
                "values dropped.",
                fix_hint=f"Give the slopegraph at least {needs}, e.g. layout={example} with it "
                "as panel b, or shorten the item names."
                + (" No width fits: shorten the item names." if share > 1 else ""),
                rule="panel_too_small",
            )
        lines = _label_lines(ctx.cell_width_mm, ctx.measure, sz)
        accent = {name: col for name, col in ctx.colors.items() if name in names}
        focus_mode = bool(hl or accent)
        effects = ctx.line_effects()
        _bare_axes(ax)
        ax.xaxis.set_visible(False)
        ax.yaxis.set_visible(False)
        values = [*left.values(), *right.values()]
        lo, hi = min(values), max(values)
        span = (hi - lo) or abs(hi) or 1.0
        ax.set_xlim(0.0, 1.0)
        ax.set_ylim(lo - 0.05 * span, hi + 0.05 * span)
        rail_col = theme.grid if theme.grid_style != "none" else theme.context_line
        ax.vlines([0.0, 1.0], lo, hi, color=rail_col, linewidth=0.7, zorder=1)
        for x_at, text, color in ((0.0, labels[0], theme.muted), (1.0, labels[1], theme.ink)):
            ax.annotate(
                _plain(text, theme),
                (x_at, 1.0),
                xycoords=("data", "axes fraction"),
                xytext=(0.0, 5.0),
                textcoords="offset points",
                ha="center",
                va="bottom",
                fontsize=sz.small,
                fontweight="bold",
                color=color,
                annotation_clip=False,
            )
        left_notes, right_notes = [], []
        for item in names:
            focus = item in accent
            col = accent.get(item, theme.axis if not focus_mode else theme.context_line)
            line_kw: dict[str, Any] = {
                "color": col,
                "linewidth": (
                    (theme.line_lw + 0.1 if focus else theme.context_line_lw + 0.1) * sz.scale
                ),
                "marker": "o",
                "markersize": (3.6 if focus else 3.0) * sz.scale,
                "markerfacecolor": col,
                "markeredgecolor": theme.background,
                "markeredgewidth": 0.6,
                "zorder": 4 if focus else 2,
                "clip_on": False,
                "label": "_slope",
                "solid_capstyle": theme.line_capstyle,
            }
            if effects is not None:
                line_kw["path_effects"] = effects
            ax.plot([0.0, 1.0], [left[item], right[item]], **line_kw)
            text_color = ctx.text_color(col) if focus else theme.ink
            weight = "bold" if focus else "normal"
            if level < 2:
                left_notes.append(
                    ax.annotate(
                        _plain(fmt_fn(left[item]), theme),
                        (0.0, left[item]),
                        xytext=(-6.0, 0.0),
                        textcoords="offset points",
                        ha="right",
                        va="center",
                        fontsize=sz.small,
                        color=text_color if focus else theme.muted,
                        fontweight=weight,
                        annotation_clip=False,
                    )
                )
            right_note = ax.annotate(
                _plain(_right_text(item, level, ctx.measure, sz), theme),
                (1.0, right[item]),
                xytext=(6.0, 0.0),
                textcoords="offset points",
                ha="left",
                va="center",
                fontsize=sz.small,
                color=text_color,
                fontweight=weight,
                annotation_clip=False,
            )
            right_note.set_linespacing(1.05)
            right_notes.append(right_note)

        def _finish() -> None:
            renderer = ctx.fig.canvas.get_renderer()
            box = ax.get_window_extent(renderer)
            k = ctx.pt_per_px
            for notes, x_at, source, dx, rows in (
                (left_notes, 0.0, left, -6.0, 1),
                (right_notes, 1.0, right, 6.0, lines),
            ):
                if not notes:
                    continue
                ys = np.array([ax.transData.transform((x_at, source[nm]))[1] * k for nm in names])
                # A wrapped label's first line (its value) sits level with the line's end.
                half = 0.5 * (rows - 1) * sz.small * 1.1
                placed = _relax_positions_pt(
                    ys - half,
                    sz.small * (1.22 + 1.1 * (rows - 1)),
                    box.y0 * k + half,
                    box.y1 * k - half,
                )
                for note, y0, y1 in zip(notes, ys, placed, strict=True):
                    note.set_position((dx, float(y1 - y0)))

        return _finish

    def _narrow(ctx: _Ctx, ax: Axes, rect: Bbox) -> list[tuple[Axes, Bbox]]:
        """A slopegraph reads by steepness, so it never spans a full-width row."""
        limit = 92.0 * ctx.sizes.scale * float(ctx.fig.dpi) / 25.4
        return [(ax, Bbox.from_extents(rect.x0, rect.y0, min(rect.x1, rect.x0 + limit), rect.y1))]

    return Panel(
        kind="change",
        alt_facts=alt_facts,
        title=title,
        label=label,
        unit=unit,
        spec=_base_spec(
            title,
            label,
            unit,
            before=dict(left),
            after=dict(right),
            labels=list(labels),
            highlight=hl or None,
            fmt=fmt,
        ),
        facts=facts,
        describe=f"Slopegraph of {label or 'values'} for {len(names)} items, {labels[0]} to {labels[1]}",
        _height_mm=lambda w, m, sizes, _t: _height(w, m, sizes, tight=False),
        _min_height_mm=lambda w, m, sizes, _t: _height(w, m, sizes, tight=True),
        _frames=_narrow,
        _draw=_draw,
        color_items=tuple(names),
        color_focus=tuple(hl),
        color_mode="highlight" if hl else "uniform",
        uses_default=False,  # without highlight every slope is the same neutral grey
    )
