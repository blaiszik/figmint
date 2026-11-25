"""Grouped multi-series compare panel for multi-benchmark / multi-model comparisons."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np
from matplotlib.axes import Axes
from matplotlib.patches import Rectangle
from matplotlib.ticker import FuncFormatter, MaxNLocator

from ..themes import Theme
from .core import (
    MAX_COLORED_SERIES,
    PT_TO_MM,
    ExplainError,
    Panel,
    _bare_axes,
    _base_spec,
    _baseline_name,
    _Ctx,
    _diff_with_unit,
    _formatter,
    _inline_unit,
    _is_strict,
    _jsonable,
    _Measure,
    _names,
    _narrow_log_ticks,
    _plain,
    _record_adjustment,
    _reference_line,
    _signed,
    _Sizes,
    _tick_label,
    _to_float,
    _with_unit,
)

MAX_GROUPED_COMPARE_ITEMS = 12
MAX_GROUPED_COMPARE_SERIES = 6


def is_nested_compare(values: object) -> bool:
    """True when ``values`` is a non-empty mapping of ``{category: {series: num}}``."""
    if not isinstance(values, Mapping) or not values:
        return False
    first = next(iter(values.values()))
    return isinstance(first, Mapping)


def build_grouped_compare(
    nested: Mapping[str, Mapping[str, Any]],
    *,
    title: str | None = None,
    label: str | None = None,
    unit: str | None = None,
    highlight: str | Sequence[str] | None = None,
    baseline: str | None = None,
    sort: bool | str = False,
    zero: bool = True,
    reference: float | tuple[float, str] | None = None,
    log: bool = False,
    fmt: str | None = None,
) -> Panel:
    """Multi-benchmark / multi-series grouped comparison (horizontal bars or Cleveland dots)."""
    categories: list[str] = []
    series_names: list[str] = []
    grid: dict[str, dict[str, float | None]] = {}

    for raw_cat, raw_series in nested.items():
        if not isinstance(raw_series, Mapping):
            raise ExplainError(
                f"compare(values[{raw_cat!r}]) must be a dict of series -> number.",
                fix_hint='Pass {category: {series: number}} uniformly for grouped compare().',
            )
        cat = str(raw_cat)
        categories.append(cat)
        bucket: dict[str, float | None] = {}
        for raw_s, raw_v in raw_series.items():
            ser = str(raw_s)
            if ser not in series_names:
                series_names.append(ser)
            if raw_v is None or (isinstance(raw_v, float) and math.isnan(raw_v)):
                bucket[ser] = None
            else:
                bucket[ser] = _to_float(raw_v, f"compare(values[{cat!r}][{ser!r}])")
        grid[cat] = bucket

    if not categories:
        raise ExplainError("compare(values) is empty.", fix_hint="Pass at least one category.")
    if not series_names:
        raise ExplainError("compare(values) has no series.", fix_hint="Pass at least one series.")

    if len(categories) > MAX_GROUPED_COMPARE_ITEMS:
        if not _is_strict():
            orig_c = len(categories)
            categories = categories[:MAX_GROUPED_COMPARE_ITEMS]
            grid = {c: grid[c] for c in categories}
            _record_adjustment(
                f"compare(): trimmed {orig_c} grouped categories to first {len(categories)}"
            )
        else:
            raise ExplainError(
                f"Grouped compare() got {len(categories)} categories; beyond "
                f"{MAX_GROUPED_COMPARE_ITEMS} a grouped bar chart gets cramped.",
                fix_hint=f"Keep at most {MAX_GROUPED_COMPARE_ITEMS} categories, or use fm.matrix() / fm.table().",
                rule="too_many_items",
            )

    hl = _names(highlight, series_names, "compare(highlight)")
    base = _baseline_name(baseline, series_names, hl, "compare")

    if len(series_names) > MAX_GROUPED_COMPARE_SERIES:
        if not _is_strict():
            must = list(dict.fromkeys([*hl, *([base] if base else [])]))
            kept = list(must)
            for s in series_names:
                if len(kept) >= MAX_GROUPED_COMPARE_SERIES:
                    break
                if s not in kept:
                    kept.append(s)
            orig_s = len(series_names)
            series_names = [s for s in series_names if s in kept]
            _record_adjustment(f"compare(): trimmed {orig_s} series to {len(series_names)}")
        else:
            raise ExplainError(
                f"Grouped compare() got {len(series_names)} series; beyond "
                f"{MAX_GROUPED_COMPARE_SERIES} series a grouped chart cannot be read.",
                fix_hint=f"Keep at most {MAX_GROUPED_COMPARE_SERIES} series (≤{MAX_COLORED_SERIES} coloured), or use fm.table().",
                rule="too_many_series",
            )

    if len(series_names) > MAX_COLORED_SERIES and not hl:
        if not _is_strict():
            kept = series_names[:MAX_COLORED_SERIES]
            if base and base not in kept:
                kept[-1] = base
            orig_s = len(series_names)
            series_names = kept
            _record_adjustment(
                f"compare(): trimmed {orig_s} unhighlighted series to {MAX_COLORED_SERIES}"
            )
        else:
            raise ExplainError(
                f"Grouped compare() has {len(series_names)} series; more than {MAX_COLORED_SERIES} "
                "colours cannot be told apart.",
                fix_hint=f"Pass highlight= for 1-3 focal series (others turn grey), or keep at most {MAX_COLORED_SERIES} series.",
                rule="too_many_series",
            )

    ref = _reference_line(reference, "compare(reference)")
    all_vals = [
        v for c in categories for s in series_names if (v := grid[c].get(s)) is not None
    ]
    if not all_vals:
        raise ExplainError("compare(values) has no finite values.", fix_hint="Pass numbers.")
    if log and min([*all_vals, *([ref[0]] if ref else [])]) <= 0:
        raise ExplainError(
            "compare(log=True) needs strictly positive values.",
            fix_hint="Drop log=True or remove non-positive values.",
        )

    # Optional sort of categories by focal series (first highlight, else first series)
    if sort in (True, "desc", "asc"):
        focal = hl[0] if hl else series_names[0]
        reverse = sort != "asc"
        categories.sort(
            key=lambda c: (
                grid[c].get(focal) is None,
                -(grid[c].get(focal) or 0.0) if reverse else (grid[c].get(focal) or 0.0),
            )
        )

    dots = (not zero) or log
    fmt_fn = _formatter(all_vals, fmt, unit=unit, log=log)
    inline_u = _inline_unit(unit)

    def _u(v: float) -> str:
        return _with_unit(fmt_fn(v), unit)

    # Order series visually: highlighted first, then remaining (baseline stays in order or after focus)
    ordered_series = list(series_names)
    if hl:
        ordered_series = [*hl, *[s for s in series_names if s not in hl]]

    # Compute facts
    facts: list[str] = [
        f"{len(categories)} categories \N{MULTIPLICATION SIGN} {len(ordered_series)} series"
    ]
    wins: dict[str, int] = {s: 0 for s in ordered_series}
    lower_better = sort == "asc"
    for cat in categories:
        present = [(s, grid[cat][s]) for s in ordered_series if grid[cat].get(s) is not None]
        if not present:
            continue
        ranked = sorted(present, key=lambda kv: kv[1], reverse=not lower_better)  # type: ignore[arg-type,return-value]
        leader_s, leader_v = ranked[0]
        wins[leader_s] += 1
        if len(ranked) >= 2:
            second_s, second_v = ranked[1]
            facts.append(
                f"{cat}: leader {leader_s} ({_u(leader_v)}) vs {second_s} ({_u(second_v)})"
            )
        else:
            facts.append(f"{cat}: {leader_s} ({_u(leader_v)})")

    top_winner = max(ordered_series, key=lambda s: wins[s])
    facts.insert(1, f"{top_winner} leads {wins[top_winner]} of {len(categories)} categories")

    if base is not None:
        targets = hl or [s for s in ordered_series if s != base][:2]
        for tgt in targets:
            deltas = [
                grid[c][tgt] - grid[c][base]  # type: ignore[operator]
                for c in categories
                if grid[c].get(tgt) is not None and grid[c].get(base) is not None
            ]
            if deltas:
                d_fmt = _formatter(deltas, fmt, unit=unit)
                avg_d = float(np.mean(deltas))
                lo_d, hi_d = min(deltas), max(deltas)
                facts.append(
                    f"{tgt} vs {base}: mean {_diff_with_unit(_signed(d_fmt(avg_d)), unit)} "
                    f"(range {_diff_with_unit(_signed(d_fmt(lo_d)), unit)} to "
                    f"{_diff_with_unit(_signed(d_fmt(hi_d)), unit)})"
                )

    n_cats = len(categories)
    n_ser = len(ordered_series)
    diverging = min(all_vals) < 0 < max(all_vals)

    def _height_mm(cell_w_mm: float, measure: _Measure, sizes: _Sizes, theme: Theme) -> float:
        bar_pitch = (3.7 if n_ser >= 3 else 4.3) * sizes.scale
        cluster_gap = 4.2 * sizes.scale
        header_mm = 7.0 * sizes.scale
        axis_mm = 5.5 * sizes.scale if (dots or log) else 1.5 * sizes.scale
        return header_mm + n_cats * (n_ser * bar_pitch + cluster_gap) + axis_mm

    def _min_height_mm(cell_w_mm: float, measure: _Measure, sizes: _Sizes, theme: Theme) -> float:
        bar_pitch = 3.2 * sizes.scale
        cluster_gap = 3.2 * sizes.scale
        return 6.0 * sizes.scale + n_cats * (n_ser * bar_pitch + cluster_gap) + 2.0 * sizes.scale

    def _draw(ctx: _Ctx, ax: Axes) -> None:
        sz = ctx.sizes
        theme = ctx.theme
        accent = {s: col for s, col in ctx.colors.items() if s in ordered_series and s != base}

        def _scolor(s: str) -> str:
            if s == base:
                return ctx.colors.get(s, theme.ink)
            if hl:
                return accent.get(s, theme.context_fill)
            return ctx.colors.get(s, theme.series_colors[ordered_series.index(s) % len(theme.series_colors)])

        scolors = {s: _scolor(s) for s in ordered_series}

        # Geometry: each category occupies a vertical cluster centered at c_idx * step
        bar_h = 0.72
        group_gap = 0.95
        cluster_step = n_ser + group_gap
        centers = np.arange(n_cats, dtype=float) * cluster_step
        offsets = (np.arange(n_ser, dtype=float) - (n_ser - 1) / 2.0) * 0.96

        _bare_axes(ax)
        top_y = -0.5 * n_ser - 1.35  # room at top for inline series key strip
        bot_y = (n_cats - 1) * cluster_step + 0.5 * n_ser + 0.45
        ax.set_ylim(bot_y, top_y)

        if dots:
            lo_v = float(min([*all_vals, *([ref[0]] if ref else [])]))
            hi_v = float(max([*all_vals, *([ref[0]] if ref else [])]))
            if log:
                ax.set_xscale("log")
                lims = _narrow_log_ticks(ax.xaxis, lo_v, hi_v, theme.minus_sign, extend=False, data_hi=hi_v)
                ax.set_xlim(*lims)
            else:
                span = (hi_v - lo_v) or abs(hi_v) or 1.0
                ax.set_xlim(lo_v - 0.08 * span, hi_v + 0.14 * span)
            if theme.grid_style != "none" and theme.grid_lw > 0:
                ax.grid(axis="x", color=theme.grid, linestyle=theme.grid_style, linewidth=theme.grid_lw)
            ax.set_axisbelow(True)
            for s_idx, s in enumerate(ordered_series):
                ys_s = []
                xs_s = []
                for c_idx, cat in enumerate(categories):
                    v = grid[cat].get(s)
                    if v is not None:
                        ys_s.append(centers[c_idx] + offsets[s_idx])
                        xs_s.append(v)
                if xs_s:
                    focus = (not hl) or (s in hl) or (s == base)
                    ax.scatter(
                        xs_s,
                        ys_s,
                        s=((4.5 if focus else 3.4) * sz.scale) ** 2,
                        color=scolors[s],
                        edgecolor=theme.background,
                        linewidth=0.5,
                        zorder=4 if focus else 3,
                    )
            if not log:
                minus = theme.minus_sign
                ax.xaxis.set_major_locator(MaxNLocator(nbins=4, steps=[1, 2, 2.5, 5, 10]))
                ax.xaxis.set_major_formatter(
                    FuncFormatter(lambda v, _p, m=minus, a=ax.xaxis: _tick_label(v, m, a))
                )
            ax.tick_params(axis="x", length=0, labelsize=sz.small, labelcolor=theme.muted, pad=3)
        else:
            lo_v = float(min(0.0, *all_vals, *([ref[0]] if ref else [])))
            hi_v = float(max(0.0, *all_vals, *([ref[0]] if ref else [])))
            span = (hi_v - lo_v) or 1.0
            ax.set_xlim(lo_v - (0.04 * span if diverging else 0.0), hi_v + 0.18 * span)
            for s_idx, s in enumerate(ordered_series):
                ys_s = []
                vs_s = []
                for c_idx, cat in enumerate(categories):
                    v = grid[cat].get(s)
                    if v is not None:
                        ys_s.append(centers[c_idx] + offsets[s_idx])
                        vs_s.append(v)
                if vs_s:
                    ax.barh(
                        ys_s,
                        vs_s,
                        height=bar_h,
                        color=scolors[s],
                        edgecolor="none",
                        zorder=2,
                    )
            ax.vlines(
                0.0,
                -0.5 * n_ser - 0.25,
                bot_y - 0.1,
                color=theme.zero_line,
                linewidth=theme.zero_line_lw,
                zorder=3,
            )
            ax.xaxis.set_visible(False)

        # Direct value labels at the end of every bar / dot
        first_val_done = False
        for c_idx, cat in enumerate(categories):
            for s_idx, s in enumerate(ordered_series):
                v = grid[cat].get(s)
                if v is None:
                    continue
                yi = centers[c_idx] + offsets[s_idx]
                txt = fmt_fn(v)
                if inline_u and not first_val_done:
                    txt = _with_unit(txt, unit)
                    first_val_done = True
                is_hl_s = s in hl
                anchor_x = v if (dots or v >= 0) else 0.0
                ax.annotate(
                    _plain(txt, theme),
                    (anchor_x, yi),
                    xytext=(4.5, 0.0),
                    textcoords="offset points",
                    ha="left",
                    va="center",
                    fontsize=sz.foot,
                    fontweight="bold" if is_hl_s else "normal",
                    color=theme.ink if (is_hl_s or not hl or s == base) else theme.muted,
                    annotation_clip=False,
                )

        # Subtle horizontal separator between benchmark clusters (LineCollection -> never trips struck check)
        if n_cats > 1:
            sep_ys = [centers[i] + 0.5 * cluster_step for i in range(n_cats - 1)]
            x0, x1 = ax.get_xlim()
            ax.hlines(sep_ys, x0, x1, color=theme.grid, linewidth=0.4 * sz.scale, zorder=1)

        if ref is not None:
            ax.axvline(ref[0], color=theme.ink, linewidth=0.7, linestyle=(0, (3, 2)), zorder=4)
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

        # Category names on y axis
        ax.set_yticks(centers, [_plain(c, theme) for c in categories])
        ax.tick_params(axis="y", length=0, labelsize=sz.body, labelcolor=theme.ink, pad=6)

        # Inline colour-coded series strip at top of axes (no boxed legend!)
        key_y = top_y + 0.48
        x0, x1 = ax.get_xlim()
        # Use axes-fraction x coordinates so linear & log x axes work identically!
        cell_w_pt = max(ctx.cell_width_mm * 0.65 / PT_TO_MM, 80.0)
        cursor_frac = 0.0
        swatch_w = 0.024
        gap_frac = 0.045
        for s in ordered_series:
            is_focus = (not hl) or (s in hl) or (s == base)
            weight = "bold" if s in hl else "normal"
            label_w_pt = ctx.measure.width_pt(_plain(s, theme), sz.small, weight)
            label_frac = label_w_pt / cell_w_pt
            # Small colour swatch rectangle in axes-x / data-y transform
            ax.add_patch(
                Rectangle(
                    (cursor_frac, key_y - 0.24),
                    swatch_w,
                    0.48,
                    transform=ax.get_yaxis_transform(),
                    facecolor=scolors[s],
                    edgecolor="none",
                    zorder=5,
                    clip_on=False,
                )
            )
            ax.text(
                cursor_frac + swatch_w + 0.012,
                key_y,
                _plain(s, theme),
                transform=ax.get_yaxis_transform(),
                ha="left",
                va="center",
                fontsize=sz.small,
                fontweight=weight,
                color=theme.ink if is_focus else theme.muted,
                zorder=5,
                clip_on=False,
            )
            cursor_frac += swatch_w + 0.012 + label_frac + gap_frac

    spec = _base_spec(
        title,
        label,
        unit,
        values={c: {s: _jsonable(grid[c].get(s)) for s in ordered_series} for c in categories},
        highlight=hl or None,
        baseline=base,
        sort=sort,
        zero=zero,
        reference=list(ref) if ref else None,
        log=log or None,
        fmt=fmt,
    )
    describe = (
        f"Grouped {'dot plot' if dots else 'bar chart'} of {label or 'values'}"
        + (f" ({unit})" if unit else "")
        + f" across {n_cats} categories and {n_ser} series"
    )
    return Panel(
        kind="compare",
        title=title,
        label=label,
        unit=unit,
        spec=spec,
        facts=facts,
        describe=describe,
        _height_mm=_height_mm,
        _min_height_mm=_min_height_mm,
        _draw=_draw,
        color_items=tuple(ordered_series),
        color_focus=tuple(hl or ordered_series),
        color_mode="highlight" if hl else "series",
        color_baseline=base,
        alt_facts=facts[: min(4, len(facts))],
    )
