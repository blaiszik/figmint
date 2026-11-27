"""Grouped multi-series compare panel for multi-benchmark / multi-model comparisons."""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from typing import Any

import numpy as np
from matplotlib.axes import Axes
from matplotlib.lines import Line2D
from matplotlib.patches import Patch, Rectangle
from matplotlib.ticker import FuncFormatter, MaxNLocator
from matplotlib.transforms import Bbox

from ..themes import Theme, contrast_ratio
from .core import (
    MAX_COLORED_SERIES,
    MAX_FACETS,
    PT_TO_MM,
    ExplainError,
    Panel,
    _bare_axes,
    _base_spec,
    _baseline_name,
    _cover_with_ticks,
    _Ctx,
    _diff_with_unit,
    _draw_top_legend,
    _facet_cross_fact,
    _facet_shape,
    _FacetGrid,
    _fit_x_labels,
    _formatter,
    _inline_unit,
    _interval_issue,
    _interval_mode_text,
    _is_number,
    _is_strict,
    _jsonable,
    _legend_extra_mm,
    _Measure,
    _names,
    _narrow_log_ticks,
    _plain,
    _range_with_unit,
    _record_adjustment,
    _reference_line,
    _signed,
    _Sizes,
    _tick_label,
    _to_float,
    _with_unit,
)
from .marks import tag_each, tag_points

MAX_GROUPED_COMPARE_ITEMS = 12
MAX_GROUPED_COMPARE_SERIES = 6


def is_nested_compare(values: object) -> bool:
    """True when ``values`` is a non-empty mapping of ``{category: {series: num}}``."""
    if not isinstance(values, Mapping) or not values:
        return False
    first = next(iter(values.values()))
    return isinstance(first, Mapping)


def _nested_grid(
    nested: Mapping[str, Mapping[str, Any]],
) -> tuple[list[str], list[str], dict[str, dict[str, float | None]]]:
    """``(categories, series, {category: {series: value or None}})`` of a nested compare."""
    if not isinstance(nested, Mapping):
        raise ExplainError(
            f"Grouped compare() expects a mapping of category -> {{series: number}}, got {type(nested).__name__}.",
            fix_hint='Pass a nested dict such as {"Bench A": {"Model 1": 82, "Model 2": 75}}.',
        )
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
    return categories, series_names, grid


def _grouped_intervals(
    error: object,
    categories: Sequence[str],
    series_names: Sequence[str],
    grid: Mapping[str, Mapping[str, float | None]],
) -> tuple[dict[str, dict[str, tuple[float, float]]], set[str]]:
    """Parse ``error=`` for grouped compare(): scalar, ``{cat: {series: err}}``, or ``{series: err}``."""
    from .compare import _compare_intervals

    if isinstance(error, Mapping) and not any(isinstance(v, Mapping) for v in error.values()):
        given = {str(k): v for k, v in error.items()}
        if set(given) <= set(series_names):
            out: dict[str, dict[str, tuple[float, float]]] = {}
            modes: set[str] = set()
            for cat in categories:
                present = {s: v for s, v in grid[cat].items() if v is not None}
                if not present:
                    out[cat] = {}
                    continue
                entry = {s: given[s] for s in present if s in given}
                errs, got = _compare_intervals(entry, dict(present), arg=f"error[{cat!r}]")
                out[cat] = errs
                modes |= got
            return out, modes
    return _facet_intervals(error, categories, grid)


def _parse_count_int(value: object, what: str, hint: str) -> int:
    number = _to_float(value, what) if _is_number(value) else math.nan
    if not (math.isfinite(number) and number >= 0 and float(number).is_integer()):
        raise ExplainError(f"{what} = {value!r} is not a whole-number count.", fix_hint=hint)
    return int(number)


def _grouped_counts(
    n: object,
    categories: Sequence[str],
    series_names: Sequence[str],
    grid: Mapping[str, Mapping[str, float | None]],
) -> tuple[dict[str, int], dict[str, dict[str, int]]]:
    """Parse ``n=`` for grouped compare(): scalar int, ``{cat: int}``, ``{series: int}``, or ``{cat: {series: int}}``.

    Returns ``(per_category_display_counts, per_cell_counts)``.
    """
    hint = (
        'Pass n= as an int, {category: count}, {series: count}, or {category: {series: count}}, '
        'e.g. n={"GPQA": 198, "SWE": 500}.'
    )
    cat_counts: dict[str, int] = {}
    cell_counts: dict[str, dict[str, int]] = {c: {} for c in categories}
    if _is_number(n):
        val = _parse_count_int(n, "compare(n)", hint)
        for c in categories:
            cat_counts[c] = val
            for s in series_names:
                if grid[c].get(s) is not None:
                    cell_counts[c][s] = val
        return cat_counts, cell_counts
    if not isinstance(n, Mapping):
        raise ExplainError(
            f"Grouped compare(n) must be an integer or a mapping, got {type(n).__name__}.",
            fix_hint=hint,
        )
    given = {str(k): v for k, v in n.items()}
    if given and all(isinstance(v, Mapping) for v in given.values()):
        extra = [k for k in given if k not in categories]
        if extra:
            raise ExplainError(
                f"compare(n) names unknown categories {extra[:4]!r}.",
                fix_hint=f"Use categories from: {', '.join(map(repr, list(categories)[:12]))}.",
            )
        for c in categories:
            sub = given.get(c)
            if not isinstance(sub, Mapping):
                continue
            vals_seen: set[int] = set()
            for raw_s, raw_cnt in sub.items():
                s = str(raw_s)
                if s not in series_names:
                    raise ExplainError(
                        f"compare(n[{c!r}]) names unknown series {s!r}.",
                        fix_hint=f"Use series from: {', '.join(map(repr, list(series_names)[:12]))}.",
                    )
                if raw_cnt is None:
                    continue
                cnt = _parse_count_int(raw_cnt, f"compare(n[{c!r}][{s!r}])", hint)
                cell_counts[c][s] = cnt
                vals_seen.add(cnt)
            if len(vals_seen) == 1:
                cat_counts[c] = next(iter(vals_seen))
        return cat_counts, cell_counts
    if set(given) <= set(categories):
        for c, raw_cnt in given.items():
            if raw_cnt is None:
                continue
            cnt = _parse_count_int(raw_cnt, f"compare(n[{c!r}])", hint)
            cat_counts[c] = cnt
            for s in series_names:
                if grid[c].get(s) is not None:
                    cell_counts[c][s] = cnt
        return cat_counts, cell_counts
    if set(given) <= set(series_names):
        for s, raw_cnt in given.items():
            if raw_cnt is None:
                continue
            cnt = _parse_count_int(raw_cnt, f"compare(n[{s!r}])", hint)
            for c in categories:
                if grid[c].get(s) is not None:
                    cell_counts[c][s] = cnt
        return cat_counts, cell_counts
    extra = [k for k in given if k not in categories and k not in series_names]
    raise ExplainError(
        f"compare(n) names {extra[:4]!r}, which are neither categories nor series in values.",
        fix_hint=hint,
    )


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
    error: Any = None,
    error_label: str | None = None,
    n: Any = None,
    reference: float | tuple[float, str] | None = None,
    log: bool = False,
    fmt: str | None = None,
    legend: bool = False,
) -> Panel:
    """Multi-benchmark / multi-series grouped comparison (horizontal bars or Cleveland dots)."""
    categories, series_names, grid = _nested_grid(nested)

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
                fix_hint=f"Keep at most {MAX_GROUPED_COMPARE_ITEMS} categories, or use mint.matrix() / mint.table().",
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
                fix_hint=f"Keep at most {MAX_GROUPED_COMPARE_SERIES} series (≤{MAX_COLORED_SERIES} coloured), or use mint.table().",
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
    errors: dict[str, dict[str, tuple[float, float]]] | None = None
    err_modes: set[str] = set()
    if error is not None:
        errors, err_modes = _grouped_intervals(error, categories, series_names, grid)
    err_bounds = [b for per in (errors or {}).values() for pair in per.values() for b in pair]
    cat_counts, cell_counts = (
        _grouped_counts(n, categories, series_names, grid) if n is not None else ({}, {})
    )
    if log and min([*all_vals, *err_bounds, *([ref[0]] if ref else [])]) <= 0:
        raise ExplainError(
            "compare(log=True) needs strictly positive values (and interval bounds and reference).",
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

    dots = (not zero) or log or (errors is not None)
    fmt_fn = _formatter([*all_vals, *(err_bounds if log else [])], fmt, unit=unit, log=log)
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

    if errors is not None:
        facts.append(_interval_mode_text(err_modes, "intervals"))
    if cat_counts:
        if len(set(cat_counts.values())) == 1 and len(cat_counts) == len(categories):
            facts.append(f"sample size: n={next(iter(cat_counts.values()))} per category")
        else:
            facts.append(
                "sample sizes: " + ", ".join(f"{c} n={cat_counts[c]}" for c in categories if c in cat_counts)
            )
    issues = [_interval_issue("compare", "error", "error_label")] if errors and not error_label else []

    n_cats = len(categories)
    n_ser = len(ordered_series)
    diverging = min(all_vals) < 0 < max(all_vals)

    def _height_mm(cell_w_mm: float, measure: _Measure, sizes: _Sizes, theme: Theme) -> float:
        if sizes.compact:
            return _min_height_mm(cell_w_mm, measure, sizes, theme)
        bar_pitch = (3.7 if n_ser >= 3 else 4.3) * sizes.scale
        cluster_gap = 4.2 * sizes.scale
        if legend:
            header_mm = _legend_extra_mm(
                ordered_series, cell_w_mm, measure, sizes, gutter_mm=18.0
            ) * sizes.scale + (4.0 * sizes.scale if (ref and ref[1]) else 0.0)
        else:
            header_mm = 7.0 * sizes.scale
        axis_mm = 5.5 * sizes.scale if (dots or log) else 1.5 * sizes.scale
        return header_mm + n_cats * (n_ser * bar_pitch + cluster_gap) + axis_mm

    def _min_height_mm(cell_w_mm: float, measure: _Measure, sizes: _Sizes, theme: Theme) -> float:
        bar_pitch = 3.2 * sizes.scale
        cluster_gap = 3.2 * sizes.scale
        if legend:
            header_mm = _legend_extra_mm(
                ordered_series, cell_w_mm, measure, sizes, gutter_mm=18.0
            ) * sizes.scale + (3.5 * sizes.scale if (ref and ref[1]) else 0.0)
        else:
            header_mm = 6.0 * sizes.scale
        return header_mm + n_cats * (n_ser * bar_pitch + cluster_gap) + 2.0 * sizes.scale

    def _draw(ctx: _Ctx, ax: Axes) -> Callable[[], None] | None:
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
        top_y = -0.5 * n_ser - (0.45 if legend else 1.35)  # room at top for inline series key strip
        bot_y = (n_cats - 1) * cluster_step + 0.5 * n_ser + 0.45
        ax.set_ylim(bot_y, top_y)

        if dots:
            lo_v = float(min([*all_vals, *err_bounds, *([ref[0]] if ref else [])]))
            hi_v = float(max([*all_vals, *err_bounds, *([ref[0]] if ref else [])]))
            if log:
                ax.set_xscale("log")
                lims = _narrow_log_ticks(ax.xaxis, lo_v, hi_v, theme.minus_sign, extend=False, data_hi=hi_v)
                ax.set_xlim(*lims)
            else:
                span = (hi_v - lo_v) or abs(hi_v) or 1.0
                ax.set_xlim(lo_v - 0.08 * span, hi_v + 0.16 * span)
            if theme.grid_style != "none" and theme.grid_lw > 0:
                ax.grid(axis="x", color=theme.grid, linestyle=theme.grid_style, linewidth=theme.grid_lw)
            ax.set_axisbelow(True)
            for s_idx, s in enumerate(ordered_series):
                ys_s = []
                xs_s = []
                lo_s = []
                hi_s = []
                cats_s = []
                for c_idx, cat in enumerate(categories):
                    v = grid[cat].get(s)
                    if v is not None:
                        ys_s.append(centers[c_idx] + offsets[s_idx])
                        xs_s.append(v)
                        cats_s.append(cat)
                        if errors is not None and s in errors.get(cat, {}):
                            lo_s.append(errors[cat][s][0])
                            hi_s.append(errors[cat][s][1])
                if xs_s:
                    focus = (not hl) or (s in hl) or (s == base)
                    if errors is not None and len(lo_s) == len(xs_s):
                        ys_arr = np.asarray(ys_s, dtype=float)
                        ax.hlines(ys_arr, lo_s, hi_s, color=scolors[s], linewidth=0.9 * sz.scale, zorder=3)
                        for ends in (lo_s, hi_s):
                            ax.vlines(
                                ends,
                                ys_arr - 0.18,
                                ys_arr + 0.18,
                                color=scolors[s],
                                linewidth=0.9 * sz.scale,
                                zorder=3,
                            )
                    dots_art = ax.scatter(
                        xs_s,
                        ys_s,
                        s=((4.5 if focus else 3.4) * sz.scale) ** 2,
                        color=scolors[s],
                        edgecolor=theme.background,
                        linewidth=0.5,
                        zorder=4 if focus else 3,
                    )
                    tag_points(
                        ctx,
                        dots_art,
                        xs_s,
                        ys_s,
                        [
                            {
                                "name": s,
                                "x": c,
                                "value": v,
                                "lo": (errors or {}).get(c, {}).get(s, (None, None))[0],
                                "hi": (errors or {}).get(c, {}).get(s, (None, None))[1],
                                "n": cell_counts.get(c, {}).get(s),
                                "unit": unit,
                            }
                            for c, v in zip(cats_s, xs_s, strict=True)
                        ],
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
                    bars_s = ax.barh(
                        ys_s,
                        vs_s,
                        height=bar_h,
                        color=scolors[s],
                        edgecolor="none",
                        zorder=2,
                    )
                    cats_s = [c for c in categories if grid[c].get(s) is not None]
                    tag_each(
                        ctx,
                        bars_s.patches,
                        [
                            {
                                "name": s,
                                "x": c,
                                "value": v,
                                "n": cell_counts.get(c, {}).get(s),
                                "unit": unit,
                            }
                            for c, v in zip(cats_s, vs_s, strict=True)
                        ],
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
        value_notes: list[tuple[Any, float, str]] = []
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
                hi_end = errors[cat][s][1] if (errors is not None and s in errors.get(cat, {})) else v
                anchor_x = hi_end if (dots or v >= 0) else 0.0
                vnote = ax.annotate(
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
                value_notes.append((vnote, float(v), scolors[s]))

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

        # Category names on y axis (with optional n= subtitle underneath each category)
        ax.set_yticks(centers, [_plain(c, theme) for c in categories])
        ax.tick_params(axis="y", length=0, labelsize=sz.body, labelcolor=theme.ink, pad=6)
        if cat_counts:
            for tick, cat in zip(ax.get_yticklabels(), categories, strict=True):
                if cat in cat_counts:
                    tick.set_verticalalignment("bottom")
            for c_idx, cat in enumerate(categories):
                if cat not in cat_counts:
                    continue
                ax.annotate(
                    _plain(f"n={cat_counts[cat]}", theme),
                    (0.0, centers[c_idx]),
                    xycoords=("axes fraction", "data"),
                    xytext=(-6.0, -1.0),
                    textcoords="offset points",
                    ha="right",
                    va="top",
                    fontsize=sz.foot,
                    color=theme.muted,
                    annotation_clip=False,
                )

        if legend:
            handles: list[Any] = []
            weights: list[str] = []
            text_colors: list[str] = []
            for s in ordered_series:
                is_focus = (not hl) or (s in hl) or (s == base)
                if dots:
                    handles.append(
                        Line2D(
                            [],
                            [],
                            marker="o",
                            linestyle="none",
                            markersize=5.0 * sz.scale,
                            markerfacecolor=scolors[s],
                            markeredgecolor=theme.background,
                            markeredgewidth=0.5,
                            label=_plain(s, theme),
                        )
                    )
                else:
                    handles.append(
                        Patch(facecolor=scolors[s], edgecolor="none", label=_plain(s, theme))
                    )
                weights.append("bold" if s in hl else "normal")
                text_colors.append(theme.ink if is_focus else theme.muted)
            y_anchor = 1.12 if (ref is not None and ref[1]) else 1.02
            _draw_top_legend(
                ctx,
                ax,
                handles,
                weights=weights,
                text_colors=text_colors,
                y_anchor=y_anchor,
                gutter_mm=18.0,
            )
        else:
            # Inline colour-coded series strip at top of axes (no boxed legend!)
            key_y = top_y + 0.48
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

        if ref is None:
            return None
        ref_x = ref[0]

        def _clear_reference() -> None:
            renderer = ctx.fig.canvas.get_renderer()
            k = ctx.pt_per_px
            frame = ax.get_window_extent(renderer)
            cell = ax.get_tightbbox(renderer)
            right_limit = max(frame.x1, cell.x1 if cell is not None else frame.x1)
            line_px = float(ax.transData.transform((ref_x, 0.0))[0])
            gap = 3.0 / k
            for note, val, col in value_notes:
                box = note.get_window_extent(renderer)
                if not (box.x0 - 1 <= line_px <= box.x1 + 1):
                    continue
                dx, dy = note.xyann
                shift = (line_px + gap - box.x0) * k
                note.set_position((dx + shift, dy))
                moved = note.get_window_extent(renderer)
                if moved.x1 <= right_limit + 1:
                    continue
                note.xy = (val, note.xy[1])
                note.set_horizontalalignment("right")
                if dots:
                    note.set_position((-5.0, dy))
                else:
                    note.set_position((-3.0, dy))
                    paper = theme.background
                    note.set_color(
                        paper if contrast_ratio(paper, col) >= contrast_ratio(theme.ink, col)
                        else theme.ink
                    )
                    note._mintfig_heatmap_text = True  # type: ignore[attr-defined]

        return _clear_reference

    spec = _base_spec(
        title,
        label,
        unit,
        values={c: {s: _jsonable(grid[c].get(s)) for s in ordered_series} for c in categories},
        highlight=hl or None,
        baseline=base,
        sort=sort,
        zero=zero,
        error=_jsonable(error) if errors is not None else None,
        error_label=error_label,
        n=_jsonable(n) if n is not None else None,
        reference=list(ref) if ref else None,
        log=log or None,
        fmt=fmt,
        legend=legend or None,
    )
    notes = [
        nt
        for nt in (
            "log scale" if log else None,
            f"intervals: {error_label}" if errors is not None and error_label else None,
        )
        if nt
    ]
    describe = (
        f"Grouped {'dot plot' if dots else 'bar chart'} of {label or 'values'}"
        + (f" ({unit})" if unit else "")
        + f" across {n_cats} categories and {n_ser} series"
        + (f", with intervals ({error_label})" if errors is not None and error_label else "")
    )
    return Panel(
        kind="compare",
        title=title,
        label=label,
        unit=unit,
        spec=spec,
        facts=facts,
        describe=describe,
        issues=issues,
        _height_mm=_height_mm,
        _min_height_mm=_min_height_mm,
        _draw=_draw,
        measure_note="; ".join(notes) or None,
        color_items=tuple(ordered_series),
        color_focus=tuple(hl or ordered_series),
        color_mode="highlight" if hl else "series",
        color_baseline=base,
        alt_facts=facts[: min(4, len(facts))],
    )


def _facet_intervals(
    error: object,
    categories: Sequence[str],
    grid: Mapping[str, Mapping[str, float | None]],
) -> tuple[dict[str, dict[str, tuple[float, float]]], set[str]]:
    """Read ``compare(error=..., facet=True)``: one half-width for every value, or
    ``{category: {item: (low, high) or half-width}}`` in the shape of ``values``."""
    from .compare import _compare_intervals

    out: dict[str, dict[str, tuple[float, float]]] = {}
    modes: set[str] = set()
    for cat in categories:
        present = {s: v for s, v in grid[cat].items() if v is not None}
        if not present:
            out[cat] = {}
            continue
        if _is_number(error):
            entry: Any = error
        elif isinstance(error, Mapping) and all(isinstance(v, Mapping) for v in error.values()):
            given = {str(k): v for k, v in error.items()}
            if cat not in given:
                raise ExplainError(
                    f"compare(error=..., facet=True) has no intervals for {cat!r}.",
                    fix_hint="Give error= the shape of values: {category: {item: (low, high) "
                    "or half-width}}, one entry per category, or one number for every value.",
                )
            entry = {str(k): v for k, v in given[cat].items() if str(k) in present}
        else:
            raise ExplainError(
                "compare(error=..., facet=True) must be one number or a mapping shaped like "
                "values, {category: {item: interval}}; a flat {item: interval} mapping does "
                "not say which category each interval belongs to.",
                fix_hint='e.g. error={"bench A": {"model 1": (0.71, 0.77), "model 2": 0.03}, ...}, '
                "or error=0.02 for every value; with tidy rows pass the column name "
                '(error="ci_half") or (low, high) columns (error=("lo", "hi")).',
            )
        errs, got = _compare_intervals(entry, dict(present), arg=f"error[{cat!r}]")
        out[cat] = errs
        modes |= got
    return out, modes


def build_faceted_compare(
    nested: Mapping[str, Mapping[str, Any]],
    *,
    title: str | None = None,
    label: str | None = None,
    unit: str | None = None,
    highlight: str | Sequence[str] | None = None,
    baseline: str | None = None,
    sort: bool | str = False,
    zero: bool = True,
    error: Any = None,
    error_label: str | None = None,
    reference: float | tuple[float, str] | None = None,
    log: bool = False,
    fmt: str | None = None,
) -> Panel:
    """Small multiples of a nested compare: one panel per category, the same items in the
    same order in each, on one shared value axis, every value labelled."""
    categories, series_names, grid = _nested_grid(nested)
    if len(categories) > MAX_FACETS:
        if not _is_strict():
            orig_c = len(categories)
            categories = categories[:MAX_FACETS]
            grid = {c: grid[c] for c in categories}
            _record_adjustment(f"compare(facet=True): trimmed {orig_c} facets to first {MAX_FACETS}")
        else:
            raise ExplainError(
                f"compare(facet=True) got {len(categories)} categories; more than {MAX_FACETS} "
                "small multiples is a wall.",
                fix_hint=f"facet=True takes at most {MAX_FACETS} categories: keep the ones the "
                "takeaway is about, or use mint.matrix() / mint.table() for the full grid.",
                rule="too_many_items",
            )
    hl = _names(highlight, series_names, "compare(highlight)")
    base = _baseline_name(baseline, series_names, hl, "compare")
    if len(series_names) > MAX_GROUPED_COMPARE_SERIES:
        if not _is_strict():
            kept = list(dict.fromkeys([*hl, *([base] if base else [])]))
            for s in series_names:
                if len(kept) >= MAX_GROUPED_COMPARE_SERIES:
                    break
                if s not in kept:
                    kept.append(s)
            orig_s = len(series_names)
            series_names = [s for s in series_names if s in kept]
            _record_adjustment(f"compare(facet=True): trimmed {orig_s} items to {len(series_names)}")
        else:
            raise ExplainError(
                f"compare(facet=True) got {len(series_names)} items per category; more than "
                f"{MAX_GROUPED_COMPARE_SERIES} rows in each small panel cannot be compared across panels.",
                fix_hint=f"Keep at most {MAX_GROUPED_COMPARE_SERIES} items, or use mint.matrix() / mint.table().",
                rule="too_many_series",
            )
    if len(categories) < 2:
        raise ExplainError(
            "compare(facet=True) needs at least two categories to make small multiples.",
            fix_hint="Pass {category: {item: value}} with 2-12 categories, or drop facet=True.",
        )
    grid = {c: {s: grid[c].get(s) for s in series_names} for c in categories}
    ref = _reference_line(reference, "compare(reference)")
    all_vals = [v for c in categories for v in grid[c].values() if v is not None]
    if not all_vals:
        raise ExplainError("compare(values) has no finite values.", fix_hint="Pass numbers.")
    errors: dict[str, dict[str, tuple[float, float]]] | None = None
    modes: set[str] = set()
    if error is not None:
        errors, modes = _facet_intervals(error, categories, grid)
    bounds = [b for per in (errors or {}).values() for pair in per.values() for b in pair]
    if log and min([*all_vals, *bounds, *([ref[0]] if ref else [])]) <= 0:
        raise ExplainError(
            "compare(log=True) needs strictly positive values (and interval bounds and reference).",
            fix_hint="Drop log=True or remove non-positive values.",
        )
    if sort in (True, "desc", "asc"):
        focal = hl[0] if hl else series_names[0]
        reverse = sort != "asc"
        categories.sort(
            key=lambda c: (
                grid[c].get(focal) is None,
                -(grid[c].get(focal) or 0.0) if reverse else (grid[c].get(focal) or 0.0),
            )
        )

    dots = (not zero) or log or errors is not None
    fmt_fn = _formatter([*all_vals, *(bounds if log else [])], fmt, unit=unit, log=log)
    bound_fmt = _formatter([*(all_vals if log else []), *bounds] or all_vals, fmt, unit=unit, log=log)
    inline_u = _inline_unit(unit)
    n_cats, n_items = len(categories), len(series_names)
    lower_better = sort == "asc"

    def _u(v: float) -> str:
        return _with_unit(fmt_fn(v), unit)

    def _span(cat: str, s: str) -> str:
        lo_b, hi_b = errors[cat][s]  # type: ignore[index]
        return _range_with_unit(bound_fmt(lo_b), bound_fmt(hi_b), unit)

    # Facts: one cross-facet line (the shared ranking, or where it differs), then one line
    # per category: its leader, the runner-up and (with intervals) whether they overlap.
    rankings: dict[str, list[str]] = {}
    per_facet: list[str] = []
    for cat in categories:
        present = [(s, v) for s, v in grid[cat].items() if v is not None]
        ranked = sorted(present, key=lambda kv: kv[1], reverse=not lower_better)  # type: ignore[arg-type,return-value]
        rankings[cat] = [s for s, _ in ranked]
        if not ranked:
            per_facet.append(f"{cat}: no values")
            continue
        lead_s, lead_v = ranked[0]
        word = "lowest" if lower_better else "highest"
        text = f"{cat}: {word} {lead_s} {_u(lead_v)}"  # type: ignore[arg-type]
        if errors is not None:
            text += f" ({_span(cat, lead_s)})"
        if len(ranked) >= 2:
            sec_s, sec_v = ranked[1]
            text += f", then {sec_s} {_u(sec_v)}"  # type: ignore[arg-type]
            if errors is not None:
                (a_lo, a_hi), (b_lo, b_hi) = errors[cat][lead_s], errors[cat][sec_s]
                apart = not (a_lo <= b_hi and b_lo <= a_hi)
                text += f" ({_span(cat, sec_s)}); intervals {'do not overlap' if apart else 'overlap'}"
        missing = [s for s in series_names if grid[cat][s] is None]
        if missing:
            text += f"; no value for {', '.join(missing)}"
        per_facet.append(text)
    cross = _facet_cross_fact(
        rankings, what="ranking" + (" (lowest first)" if lower_better else ""), word="categories"
    )
    facts = ([cross] if cross else []) + per_facet
    if base is not None:
        for tgt in (hl or [s for s in series_names if s != base])[:3]:
            deltas = [
                grid[c][tgt] - grid[c][base]  # type: ignore[operator]
                for c in categories
                if grid[c][tgt] is not None and grid[c][base] is not None
            ]
            if deltas:
                d_fmt = _formatter(deltas, fmt, unit=unit)
                above = sum(1 for d in deltas if d > 0)
                facts.append(
                    f"{tgt} vs {base}: {_diff_with_unit(_signed(d_fmt(min(deltas))), unit)} to "
                    f"{_diff_with_unit(_signed(d_fmt(max(deltas))), unit)}; above it in {above} of "
                    f"{len(deltas)} categories"
                )
    if errors is not None:
        facts.append(_interval_mode_text(modes, "intervals"))
    issues = [_interval_issue("compare", "error", "error_label")] if errors and not error_label else []

    hi_all = max([*all_vals, *bounds, *([ref[0]] if ref else [])])
    lo_all = min([*all_vals, *bounds, *([ref[0]] if ref else [])])

    def _shape(cell_w_mm: float) -> tuple[int, int]:
        return _facet_shape(n_cats, cell_w_mm, min_mm=38.0, balance=True)

    def _each_mm(sizes: _Sizes, tight: bool) -> float:
        pitch = 4.4 if (tight or sizes.compact) else 5.3
        return 6.0 + n_items * pitch + (5.0 if dots else 1.0)

    def _height_mm(cell_w_mm: float, _m: _Measure, sizes: _Sizes, _t: Theme) -> float:
        nrows, _nc = _shape(cell_w_mm)
        return nrows * _each_mm(sizes, False) + (nrows - 1) * 4.5

    def _min_height_mm(cell_w_mm: float, _m: _Measure, sizes: _Sizes, _t: Theme) -> float:
        nrows, _nc = _shape(cell_w_mm)
        return nrows * _each_mm(sizes, True) + (nrows - 1) * 4.5

    def _frames(ctx: _Ctx, ax: Axes, rect: Bbox) -> list[tuple[Axes, Bbox]]:
        sz = ctx.sizes
        theme = ctx.theme
        _nrows, ncols = _shape(ctx.cell_width_mm)
        grid_ax = _FacetGrid(ctx, ax, rect, n_cats, ncols, share="x", rows=True)
        accent = {s: col for s, col in ctx.colors.items() if s in series_names and s != base}

        def _color(s: str) -> str:
            if s == base:
                return ctx.colors.get(s, theme.ink)
            if hl:
                return accent.get(s, theme.context_fill)
            return ctx.colors.get(s, ctx.default_color)

        colors = {s: _color(s) for s in series_names}
        y = np.arange(n_items, dtype=float)
        k = ctx.pt_per_px
        # Facet titles may run to the next facet's left edge: wrap them to that width.
        name_pt = max(ctx.measure.width_pt(s, sz.body, "bold" if s in hl else "normal") for s in series_names)
        title_pt = max(
            24.0, (rect.width * k - name_pt - 6.0) / ncols - 2.0
        )
        notes_by_ax: list[tuple[Axes, list[Any]]] = []
        first_label_done = False
        for idx, cat in enumerate(categories):
            child, _sub = grid_ax.cell(idx)
            c = idx % ncols
            _bare_axes(child)
            child.set_ylim(n_items - 0.5, -0.5)
            vals = [grid[cat][s] for s in series_names]
            rows = [i for i, v in enumerate(vals) if v is not None]
            errs = (errors or {}).get(cat, {})
            if dots:
                if idx == 0:
                    if log:
                        child.set_xscale("log")
                        pad = max((hi_all / lo_all) ** 0.05, 1.15)
                        child.set_xlim(
                            *_narrow_log_ticks(
                                child.xaxis, lo_all / pad, hi_all * pad, theme.minus_sign,
                                extend=False, data_hi=hi_all,
                            )
                        )
                    else:
                        lo_v = lo_all
                        if not errors and lo_v >= 0 and (hi_all - lo_v) > 0.6 * hi_all:
                            lo_v = 0.0
                        span = (hi_all - lo_v) or abs(hi_all) or 1.0
                        child.set_xlim(lo_v - 0.05 * span, hi_all + 0.03 * span)
                        child.xaxis.set_major_locator(MaxNLocator(nbins=3, steps=[1, 2, 2.5, 5, 10]))
                        child.xaxis.set_major_formatter(
                            FuncFormatter(lambda v, _p, m=theme.minus_sign, a=child.xaxis: _tick_label(v, m, a))
                        )
                        _cover_with_ticks(child.xaxis, lo_all, hi_all)
                child.tick_params(
                    axis="x", length=0, labelsize=sz.small, labelcolor=theme.muted, pad=3,
                    labelbottom=grid_ax.last_in_column(idx),
                )
                if theme.grid_style != "none" and theme.grid_lw > 0:
                    child.grid(axis="x", color=theme.grid, linestyle=theme.grid_style, linewidth=theme.grid_lw)
                child.set_axisbelow(True)
                dot_cols = [colors[series_names[i]] for i in rows]
                dot_cols = [col if col != theme.context_fill else theme.axis for col in dot_cols]
                xs = [vals[i] for i in rows]
                if errors is not None:
                    lows = [errs[series_names[i]][0] for i in rows]
                    highs = [errs[series_names[i]][1] for i in rows]
                    child.hlines(y[rows], lows, highs, color=dot_cols, linewidth=0.9 * sz.scale, zorder=2)
                    for ends in (lows, highs):
                        child.vlines(ends, y[rows] - 0.16, y[rows] + 0.16, color=dot_cols,
                                     linewidth=0.9 * sz.scale, zorder=2)
                else:
                    stem = theme.grid if theme.grid_style != "none" else theme.context_fill
                    child.hlines(y[rows], child.get_xlim()[0], xs, color=stem, linewidth=0.7, zorder=1)
                dots_art = child.scatter(xs, y[rows], s=(4.6 * sz.scale) ** 2, color=dot_cols,
                                         edgecolor=theme.background, linewidth=0.6, zorder=3)
                tag_points(ctx, dots_art, xs, y[rows], [
                    {"name": series_names[i], "x": cat, "value": vals[i],
                     "lo": errs.get(series_names[i], (None, None))[0],
                     "hi": errs.get(series_names[i], (None, None))[1], "unit": unit}
                    for i in rows
                ])
                if log:
                    child.spines["bottom"].set_visible(True)
                    child.spines["bottom"].set_color(theme.axis)
                    child.spines["bottom"].set_linewidth(theme.axis_lw)
                    child.tick_params(axis="x", length=theme.tick_length, width=theme.tick_width,
                                      color=theme.axis)
            else:
                if idx == 0:
                    lo_v = float(min(0.0, lo_all))
                    hi_v = float(max(0.0, hi_all))
                    child.set_xlim(lo_v, hi_v if hi_v > lo_v else lo_v + 1.0)
                bar_kw: dict[str, Any] = {
                    "height": min(theme.bar_height, 0.6) if sz.compact else theme.bar_height,
                    "color": [colors[series_names[i]] for i in rows],
                    "linewidth": theme.bar_edge_lw,
                    "zorder": 2,
                }
                if theme.bar_edgecolor is not None and theme.bar_edge_lw > 0:
                    bar_kw["edgecolor"] = theme.bar_edgecolor
                bars = child.barh(y[rows], [vals[i] for i in rows], **bar_kw)
                tag_each(ctx, bars.patches, [
                    {"name": series_names[i], "x": cat, "value": vals[i], "unit": unit} for i in rows
                ])
                child.axvline(0.0, color=theme.zero_line, linewidth=theme.zero_line_lw, zorder=3)
                child.xaxis.set_visible(False)
            if ref is not None:
                child.axvline(ref[0], color=theme.ink, linewidth=0.7, linestyle=(0, (3, 2)), zorder=4)
            child.set_yticks(y, [_plain(s, theme) for s in series_names])
            child.tick_params(axis="y", length=0, labelsize=sz.body, labelcolor=theme.ink, pad=5,
                              labelleft=(c == 0))
            for tick, s in zip(child.get_yticklabels(), series_names):
                if s in hl:
                    tick.set_fontweight("bold")
            lines = ctx.measure.wrap(cat, title_pt, sz.small, "bold")
            child.set_title(_plain("\n".join(lines[:2]), theme), loc="left", fontsize=sz.small,
                            fontweight="bold", color=theme.ink, pad=3.0)
            notes: list[Any] = []
            for i in rows:
                s, v = series_names[i], float(vals[i])  # type: ignore[arg-type]
                txt = fmt_fn(v)
                if inline_u or not first_label_done:
                    txt = _with_unit(txt, unit)
                    first_label_done = True
                anchor = errs[s][1] if s in errs else (v if (dots or v >= 0) else 0.0)
                notes.append(child.annotate(
                    _plain(txt, theme), (anchor, y[i]), xytext=(4.0, 0.0), textcoords="offset points",
                    ha="left", va="center", fontsize=sz.small,
                    fontweight="bold" if s in hl else "normal",
                    color=theme.muted if (hl and s not in hl and s != base) else theme.ink,
                    annotation_clip=False,
                ))
            notes_by_ax.append((child, notes))

        def _fit_labels() -> None:
            """Value labels end inside their facet and step past a reference line."""
            renderer = ctx.fig.canvas.get_renderer()
            for _ in range(3):
                for child, notes in notes_by_ax:
                    _fit_x_labels(child, notes, log=log)
                    if ref is None:
                        continue
                    line_px = float(child.transData.transform((ref[0], 0.0))[0])
                    for note in notes:
                        box = note.get_window_extent(renderer)
                        if box.x0 - 1 <= line_px <= box.x1 + 1:
                            dx, dy = note.xyann
                            note.set_position((dx + (line_px - box.x0) * k + 3.0, dy))

        ctx.finishers.append(grid_ax.equalize)
        ctx.finishers.append(_fit_labels)
        return grid_ax.frames

    notes = [
        nt
        for nt in (
            "log scale" if log else None,
            f"intervals: {error_label}" if errors and error_label else None,
            (f"dashed: {ref[1] or 'reference'} {_u(ref[0])}" if ref else None),
        )
        if nt
    ]
    spec = _base_spec(
        title,
        label,
        unit,
        values={c: {s: _jsonable(grid[c].get(s)) for s in series_names} for c in categories},
        facet=True,
        highlight=hl or None,
        baseline=base,
        sort=sort,
        zero=zero,
        error=_jsonable(error) if errors is not None else None,
        error_label=error_label,
        reference=list(ref) if ref else None,
        log=log or None,
        fmt=fmt,
    )
    describe = (
        f"Small-multiple {'dot plots' if dots else 'bar charts'} of {label or 'values'}"
        + (f" ({unit})" if unit else "")
        + f", one per category for {n_cats} categories, the same {n_items} items in each on one shared scale"
        + (f", with intervals ({error_label})" if errors and error_label else "")
    )
    colored = len(series_names) <= MAX_COLORED_SERIES
    return Panel(
        kind="compare",
        title=title,
        label=label,
        unit=unit,
        spec=spec,
        facts=facts,
        describe=describe,
        issues=issues,
        _height_mm=_height_mm,
        _min_height_mm=_min_height_mm,
        _draw=lambda _ctx, _ax: None,
        _frames=_frames,
        measure_note="; ".join(notes) or None,
        color_items=tuple(series_names),
        color_focus=tuple(hl or (series_names if colored else [])),
        color_mode="highlight" if hl else ("series" if colored else "uniform"),
        uses_default=not hl and not colored,
        color_baseline=base,
        alt_facts=facts[: min(5, len(facts))],
    )
