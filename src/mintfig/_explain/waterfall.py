"""waterfall() attribution / bridge form for mint.explain.

Answers: "How do individual gains and losses add up from start to finish?"
Draws horizontal floating bars connected by subtle vertical bridge connectors,
with optional starting anchor and final total bar grounded at zero.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np
from matplotlib.axes import Axes

from .._tabular import resolve_named_table
from ..themes import MINTFIG_THEME, Theme
from .core import (
    PT_TO_MM,
    ExplainError,
    Panel,
    _bare_axes,
    _base_spec,
    _Ctx,
    _diff_with_unit,
    _formatter,
    _guarded,
    _inline_unit,
    _is_number,
    _is_strict,
    _issue,
    _jsonable,
    _Measure,
    _named_values,
    _names,
    _plain,
    _record_adjustment,
    _reference_line,
    _signed,
    _Sizes,
    _to_float,
    _with_unit,
)

MAX_WATERFALL_STEPS = 14
COMFORTABLE_WATERFALL_STEPS = 10


def _parse_start(start: object) -> tuple[str, float] | None:
    if start is None:
        return None
    if _is_number(start):
        return ("Start", _to_float(start, "waterfall(start)"))
    if (
        isinstance(start, Sequence)
        and not isinstance(start, (str, bytes))
        and len(start) == 2
        and isinstance(start[0], str)
    ):
        return (start[0].strip() or "Start", _to_float(start[1], "waterfall(start)"))
    raise ExplainError(
        f"waterfall(start={start!r}) must be a number or (label, number).",
        fix_hint='Pass start=69.0 or start=("Base model", 69.0).',
    )


@_guarded("waterfall")
def waterfall(
    steps: Mapping[str, float] | Sequence[tuple[str, float]] | Sequence[Mapping[str, Any]],
    *,
    name: str | None = None,
    value: str | None = None,
    start: float | tuple[str, float] | None = None,
    total_label: str = "Total",
    show_total: bool = True,
    title: str | None = None,
    label: str | None = None,
    unit: str | None = None,
    highlight: str | Sequence[str] | None = None,
    reference: float | tuple[float, str] | None = None,
    fmt: str | None = None,
) -> Panel:
    """How do individual gains and losses add up from start to finish?

    ``steps`` maps step names to signed deltas (a dict, Series, or row-shaped
    data with ``name=`` and ``value=``). Optional ``start=`` anchors the bridge
    at a starting value (e.g. ``start=("Base", 69.0)``); ``show_total=True``
    adds a final anchored bar labelled ``total_label`` showing the cumulative sum.
    """
    tabular = resolve_named_table(
        steps,
        "waterfall(steps)",
        name=name,
        value=value,
        form="waterfall",
    )
    if tabular is not None:
        steps = tabular[0]
    data = _named_values(steps, "waterfall(steps)")
    step_names = list(data)
    if not step_names:
        raise ExplainError("waterfall(steps) is empty.", fix_hint="Pass at least one step.")

    start_anchor = _parse_start(start)
    ref = _reference_line(reference, "waterfall(reference)")

    # Limit handling: in lenient mode, fold smallest steps into "Other (k)" so the total stays exact!
    if len(step_names) > MAX_WATERFALL_STEPS:
        if not _is_strict():
            req_hl = (
                [highlight]
                if isinstance(highlight, str)
                else ([str(h) for h in highlight] if highlight is not None else [])
            )
            must_keep = [nm for nm in req_hl if nm in data]
            by_mag = sorted(step_names, key=lambda nm: abs(data[nm]), reverse=True)
            keep_limit = MAX_WATERFALL_STEPS - 1
            chosen = list(dict.fromkeys(must_keep))
            for nm in by_mag:
                if len(chosen) >= keep_limit:
                    break
                if nm not in chosen:
                    chosen.append(nm)
            chosen_set = set(chosen)
            folded = [nm for nm in step_names if nm not in chosen_set]
            folded_sum = sum(data[nm] for nm in folded)
            new_data = {nm: data[nm] for nm in step_names if nm in chosen_set}
            new_data[f"Other ({len(folded)})"] = folded_sum
            _record_adjustment(
                f"waterfall(): folded {len(folded)} smaller step(s) into Other ({len(folded)})"
            )
            data = new_data
            step_names = list(data)
        else:
            raise ExplainError(
                f"waterfall() got {len(step_names)} steps; more than {MAX_WATERFALL_STEPS} "
                "cannot be read in one bridge.",
                fix_hint=f"Keep at most {MAX_WATERFALL_STEPS} steps (fold minor contributions into 'Other').",
                rule="too_many_items",
            )

    hl = _names(highlight, step_names, "waterfall(highlight)")

    issues: list[dict[str, Any]] = []
    if len(step_names) > COMFORTABLE_WATERFALL_STEPS:
        issues.append(
            _issue(
                "many_items",
                "warning",
                f"{len(step_names)} waterfall steps is a long bridge for one glance.",
                "Group minor contributions into one 'Other' step.",
            )
        )

    # Build ordered bar entries: (row_label, x_start, x_end, kind_tag, delta_val)
    # kind_tag in {"start", "pos", "neg", "zero", "total"}
    entries: list[tuple[str, float, float, str, float]] = []
    running = 0.0
    if start_anchor is not None:
        s_label, s_val = start_anchor
        entries.append((s_label, 0.0, s_val, "start", s_val))
        running = s_val
    for nm in step_names:
        delta = data[nm]
        nxt = running + delta
        tag = "pos" if delta > 0 else ("neg" if delta < 0 else "zero")
        entries.append((nm, running, nxt, tag, delta))
        running = nxt
    final_total = running
    if show_total:
        t_lbl = str(total_label).strip() or "Total"
        entries.append((t_lbl, 0.0, final_total, "total", final_total))

    all_levels = [0.0, *[e[1] for e in entries], *[e[2] for e in entries]]
    all_deltas = [abs(data[nm]) for nm in step_names]
    level_fmt = _formatter(all_levels, fmt, unit=unit)
    delta_fmt = _formatter(all_deltas or [0.0], fmt, unit=unit)
    inline_u = _inline_unit(unit)

    def _lvl(v: float) -> str:
        return _with_unit(level_fmt(v), unit)

    def _dlt(v: float) -> str:
        return _diff_with_unit(_signed(delta_fmt(v)), unit)

    # Compute facts
    net_delta = sum(data[nm] for nm in step_names)
    facts: list[str] = []
    if start_anchor is not None:
        facts.append(
            f"{start_anchor[0]} {_lvl(start_anchor[1])} \N{RIGHTWARDS ARROW} "
            f"{total_label} {_lvl(final_total)} (net {_dlt(net_delta)})"
        )
    else:
        facts.append(f"net {total_label.lower()}: {_lvl(final_total)} across {len(step_names)} steps")

    pos_steps = [nm for nm in step_names if data[nm] > 0]
    neg_steps = [nm for nm in step_names if data[nm] < 0]
    if pos_steps:
        best_pos = max(pos_steps, key=lambda nm: data[nm])
        facts.append(f"largest positive driver: {best_pos} ({_dlt(data[best_pos])})")
    if neg_steps:
        worst_neg = min(neg_steps, key=lambda nm: data[nm])
        facts.append(f"largest negative drag: {worst_neg} ({_dlt(data[worst_neg])})")

    cum_after: dict[str, float] = {}
    cur = start_anchor[1] if start_anchor is not None else 0.0
    for nm in step_names:
        cur += data[nm]
        cum_after[nm] = cur
    for item in hl:
        facts.append(f"{item}: {_dlt(data[item])} (cumulative {_lvl(cum_after[item])})")
    if ref is not None:
        gap = final_total - ref[0]
        ref_nm = f" ({ref[1]})" if ref[1] else ""
        facts.append(
            f"{total_label} vs reference {_lvl(ref[0])}{ref_nm}: {_dlt(gap)}"
        )

    n_rows = len(entries)
    row_labels = [e[0] for e in entries]
    hl_set = set(hl)

    def _wrapped(
        cell_width_mm: float,
        measure: _Measure,
        sizes: _Sizes,
        theme: Theme = MINTFIG_THEME,
    ) -> list[str]:
        cell_pt = cell_width_mm * sizes.scale / PT_TO_MM
        out: list[str] = []
        for idx, nm in enumerate(row_labels):
            tag = entries[idx][3]
            weight = "bold" if (nm in hl_set or tag in {"start", "total"}) else "normal"
            lines = measure.wrap(nm, 0.36 * cell_pt, sizes.body, weight)
            if len(lines) > 2:
                lines = [lines[0], " ".join(lines[1:])]
            out.append("\n".join(lines))
        return out

    def _pitch(wrapped: list[str], tight: bool = False) -> float:
        lines = max(nm.count("\n") + 1 for nm in wrapped)
        if tight:
            return {1: 4.8, 2: 7.4}.get(lines, 9.5)
        return {1: 5.5, 2: 8.4}.get(lines, 10.5)

    def _draw(ctx: _Ctx, ax: Axes) -> None:
        sz = ctx.sizes
        theme = ctx.theme
        y = np.arange(n_rows, dtype=float)
        bar_h = min(theme.bar_height, 0.64)

        pos_col = theme.series_colors[2] if len(theme.series_colors) > 2 else theme.series_colors[0]
        neg_col = theme.series_colors[1] if len(theme.series_colors) > 1 else theme.accent_colors[0]
        focus_mode = bool(hl_set)

        lo = float(min(*all_levels, ref[0] if ref else 0.0))
        hi = float(max(*all_levels, ref[0] if ref else 0.0))
        span = (hi - lo) or abs(hi) or 1.0
        pad_r = 0.22 * span
        pad_l = 0.14 * span if lo < 0 else 0.0
        ax.set_xlim(lo - pad_l, hi + pad_r)
        ax.set_ylim(n_rows - 0.5, -0.5)
        _bare_axes(ax)
        ax.xaxis.set_visible(False)

        # Draw bars + collect bridge connector x positions
        bridge_xs: list[float] = []
        bridge_y0: list[float] = []
        bridge_y1: list[float] = []
        value_notes: list[tuple[Any, float]] = []

        for idx, (nm, x0, x1, tag, delta) in enumerate(entries):
            if tag in {"start", "total"}:
                col = theme.ink
                alpha = 0.92
            elif nm in hl_set:
                col = ctx.colors.get(nm, pos_col if tag == "pos" else neg_col)
                alpha = 1.0
            else:
                col = pos_col if tag == "pos" else (neg_col if tag == "neg" else theme.muted)
                alpha = 0.42 if focus_mode else 0.88

            left = min(x0, x1)
            width = abs(x1 - x0)
            if width <= 1e-12:
                # Zero-delta step: crisp vertical tick mark
                ax.vlines(
                    [x0],
                    [idx - bar_h * 0.45],
                    [idx + bar_h * 0.45],
                    color=theme.muted,
                    linewidth=1.4 * sz.scale,
                    zorder=3,
                )
            else:
                ax.barh(
                    [idx],
                    [width],
                    left=[left],
                    height=bar_h,
                    color=col,
                    alpha=alpha,
                    edgecolor="none",
                    zorder=2,
                )

            # Vertical bridge connector from this bar's ending cumulative level to next row
            if idx < n_rows - 1:
                bridge_x = x1
                bridge_xs.append(bridge_x)
                bridge_y0.append(idx + bar_h * 0.5)
                bridge_y1.append(idx + 1 - bar_h * 0.5)

            # Value / delta label
            if tag in {"start", "total"}:
                txt = _with_unit(level_fmt(delta), unit) if (idx == 0 or inline_u or tag == "total") else level_fmt(delta)
            else:
                signed_txt = _signed(delta_fmt(delta))
                txt = _with_unit(signed_txt, unit) if inline_u else signed_txt

            anchor_x = max(x0, x1)
            is_bold = nm in hl_set or tag == "total"
            lbl_col = (
                theme.ink
                if (is_bold or tag == "start" or not focus_mode)
                else theme.muted
            )
            note = ax.annotate(
                _plain(txt, theme),
                (anchor_x, idx),
                xytext=(5.0, 0.0),
                textcoords="offset points",
                ha="left",
                va="center",
                fontsize=sz.small,
                fontweight="bold" if is_bold else "normal",
                color=lbl_col,
                annotation_clip=False,
            )
            value_notes.append((note, min(x0, x1)))

        if bridge_xs:
            ax.vlines(
                bridge_xs,
                bridge_y0,
                bridge_y1,
                color=theme.axis,
                linewidth=0.65 * sz.scale,
                linestyle=(0, (2, 2)),
                zorder=1,
            )

        ax.vlines(
            [0.0],
            [-0.45],
            [n_rows - 0.55],
            color=theme.zero_line,
            linewidth=theme.zero_line_lw,
            zorder=3,
        )

        if ref is not None:
            ax.axvline(
                ref[0],
                color=theme.ink,
                linewidth=0.7,
                linestyle=(0, (3, 2)),
                zorder=4,
            )
            if ref[1]:
                ax.annotate(
                    _plain(ref[1], theme),
                    (ref[0], 1.0),
                    xycoords=("data", "axes fraction"),
                    xytext=(0.0, 2.5),
                    textcoords="offset points",
                    ha="center",
                    va="bottom",
                    fontsize=sz.small,
                    color=theme.muted,
                    annotation_clip=False,
                )

        shown_names = _wrapped(ctx.cell_width_mm, ctx.measure, sz, theme)
        ax.set_yticks(y, [_plain(nm, theme) for nm in shown_names])
        ax.tick_params(axis="y", length=0, labelsize=sz.body, labelcolor=theme.ink, pad=5)
        for tick, (nm, _x0, _x1, tag, _d) in zip(ax.get_yticklabels(), entries, strict=True):
            tick.set_linespacing(1.05)
            if nm in hl_set or tag in {"start", "total"}:
                tick.set_fontweight("bold")
            elif focus_mode:
                tick.set_color(theme.muted)

        if ref is None:
            return None
        ref_x = ref[0]

        def _clear_reference() -> None:
            renderer = ctx.fig.canvas.get_renderer()
            k = ctx.pt_per_px
            cell = ax.get_tightbbox(renderer)
            frame = ax.get_window_extent(renderer)
            right_limit = max(frame.x1, cell.x1 if cell is not None else frame.x1)
            line_px = float(ax.transData.transform((ref_x, 0.0))[0])
            gap = 3.0 / k
            for note, left_anchor in value_notes:
                box = note.get_window_extent(renderer)
                if not (box.x0 - 1 <= line_px <= box.x1 + 1):
                    continue
                dx, dy = note.xyann
                shift = (line_px + gap - box.x0) * k
                note.set_position((dx + shift, dy))
                moved = note.get_window_extent(renderer)
                if moved.x1 <= right_limit + 1:
                    continue
                note.xy = (left_anchor, note.xy[1])
                note.set_horizontalalignment("right")
                note.set_position((-5.0, dy))

        return _clear_reference

    spec = _base_spec(
        title,
        label,
        unit,
        steps={nm: _jsonable(data[nm]) for nm in step_names},
        start=_jsonable(start_anchor) if start_anchor is not None else None,
        total_label=total_label if total_label != "Total" else None,
        show_total=show_total if not show_total else None,
        highlight=hl or None,
        reference=list(ref) if ref else None,
        fmt=fmt,
    )
    describe = (
        f"Waterfall bridge of {label or 'values'}"
        + (f" ({unit})" if unit else "")
        + f" across {len(step_names)} steps"
        + (f" from {start_anchor[0]} to {total_label}" if start_anchor else f" to {total_label}")
    )
    return Panel(
        kind="waterfall",
        title=title,
        label=label,
        unit=unit,
        spec=spec,
        facts=facts,
        describe=describe,
        issues=issues,
        _height_mm=lambda w, m, s, t: n_rows * _pitch(_wrapped(w, m, s, t))
        + (4.5 if ref and ref[1] else 1.5),
        _min_height_mm=lambda w, m, s, t: n_rows * _pitch(_wrapped(w, m, s, t), tight=True)
        + (4.0 if ref and ref[1] else 1.0),
        _draw=_draw,
        color_items=tuple(step_names),
        color_focus=tuple(hl),
        color_mode="highlight" if hl else "none",
        alt_facts=facts[: min(3, len(facts))],
    )
