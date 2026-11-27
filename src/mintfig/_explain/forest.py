"""forest() effect-size / A/B test / meta-analysis plot form for mint.explain."""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from typing import Any

import numpy as np
from matplotlib.axes import Axes
from matplotlib.patches import Polygon
from matplotlib.ticker import FuncFormatter, MaxNLocator

from ..themes import MINTFIG_THEME, Theme
from .compare import _compare_counts, _compare_intervals, _sort_order
from .core import (
    MAX_COMPARE_ITEMS,
    PT_TO_MM,
    ExplainError,
    Panel,
    _bare_axes,
    _base_spec,
    _baseline_name,
    _cover_with_ticks,
    _Ctx,
    _formatter,
    _guarded,
    _has_items,
    _inline_unit,
    _interval_issue,
    _is_strict,
    _Measure,
    _measure_text,
    _named_values,
    _names,
    _narrow_log_ticks,
    _pairs,
    _plain,
    _record_adjustment,
    _reference_line,
    _signed,
    _Sizes,
    _tick_label,
    _to_float,
    _with_unit,
)
from .marks import tag as tag_mark
from .marks import tag_points

# --------------------------------------------------------------------------- #
# forest
# --------------------------------------------------------------------------- #


def _parse_pooled(
    pooled: Any, *, log: bool
) -> tuple[str, float, float, float, int | None] | None:
    """Parse ``forest(pooled=...)`` from ``(est, lo, hi)`` or a mapping."""
    if pooled is None:
        return None
    hint = (
        "Pass pooled=(est, lo, hi) or "
        'pooled={"label": "Pooled", "value": 1.4, "lo": 1.1, "hi": 1.8}.'
    )
    p_n: int | None = None
    if _has_items(pooled):
        entries = {str(k): v for k, v in _pairs(pooled)}
        p_label = str(entries.get("label") or "Pooled").strip() or "Pooled"
        val_raw = (
            entries["value"]
            if "value" in entries
            else entries.get("est", entries.get("estimate"))
        )
        lo_raw = entries.get("lo", entries.get("low"))
        hi_raw = entries.get("hi", entries.get("high"))
        if val_raw is None or lo_raw is None or hi_raw is None:
            raise ExplainError(
                "forest(pooled) dict needs 'value', 'lo', and 'hi' keys.",
                fix_hint=hint,
            )
        est = _to_float(val_raw, "forest(pooled['value'])")
        lo = _to_float(lo_raw, "forest(pooled['lo'])")
        hi = _to_float(hi_raw, "forest(pooled['hi'])")
        if entries.get("n") is not None:
            n_val = _to_float(entries["n"], "forest(pooled['n'])")
            if not (math.isfinite(n_val) and n_val >= 0 and float(n_val).is_integer()):
                raise ExplainError(
                    f"forest(pooled['n']) = {entries['n']!r} is not a whole count.",
                    fix_hint="Pass a non-negative integer for pooled['n'].",
                )
            p_n = int(n_val)
    elif isinstance(pooled, (Sequence, np.ndarray)) and not isinstance(pooled, (str, bytes)):
        items = list(pooled)
        if len(items) != 3:
            raise ExplainError(
                f"forest(pooled) tuple expects 3 numbers (est, lo, hi), got {len(items)}.",
                fix_hint=hint,
            )
        p_label = "Pooled"
        est = _to_float(items[0], "forest(pooled[0])")
        lo = _to_float(items[1], "forest(pooled[1])")
        hi = _to_float(items[2], "forest(pooled[2])")
    else:
        raise ExplainError(
            f"forest(pooled) must be (est, lo, hi) or a dict, got {type(pooled).__name__}.",
            fix_hint=hint,
        )
    if not (math.isfinite(est) and math.isfinite(lo) and math.isfinite(hi)):
        raise ExplainError(
            f"forest(pooled) = ({est}, {lo}, {hi}) must be finite.",
            fix_hint=hint,
        )
    if not (lo <= est <= hi):
        raise ExplainError(
            f"forest(pooled) interval ({lo}, {hi}) does not bracket estimate {est}.",
            fix_hint="Pass (est, lo, hi) with lo <= est <= hi.",
        )
    if log and (lo <= 0 or est <= 0 or hi <= 0):
        raise ExplainError(
            "forest(log=True) needs strictly positive pooled estimate and interval bounds.",
            fix_hint="Use positive ratios with log=True, or drop log=True.",
        )
    return p_label, est, lo, hi, p_n


@_guarded("forest", aliases={"measure": "label"})
def forest(
    data: Mapping[str, float] | Sequence[tuple[str, float]],
    *,
    error: Any,
    error_label: str | None = None,
    reference: float | tuple[float, str] | None = 0.0,
    pooled: tuple[float, float, float] | Mapping[str, Any] | None = None,
    n: Mapping[str, int] | Sequence[int] | None = None,
    label: str | None = None,
    unit: str | None = None,
    baseline: str | None = None,
    highlight: str | Sequence[str] | None = None,
    title: str | None = None,
    log: bool = False,
    sort: bool | str = True,
    fmt: str | None = None,
) -> Panel:
    """Effect-size, A/B test, or meta-analysis forest plot with null line, whiskers, pooled diamond, and tabular readout.

    ``data`` maps each study, arm, or subgroup name to its point estimate.
    ``error`` gives each item's confidence interval as ``{name: (lo, hi)}`` or
    half-widths; ``error_label`` names the interval (e.g. ``"95% CI"``) in the
    panel subtitle. ``reference`` draws the vertical null line (default ``0.0``
    for differences, or ``1.0`` with ``log=True`` for odds/hazard ratios).
    Pass ``pooled=(est, lo, hi)`` or ``pooled={"label": "Pooled", "value": ...,
    "lo": ..., "hi": ...}`` to add a bottom summary diamond separated by a subtle
    rule. ``n`` adds sample sizes to the right-aligned tabular readout and scales
    point-estimate squares subtly by ``sqrt(n)``.
    """
    if error is None:
        raise ExplainError(
            "forest() requires error= intervals for each item.",
            fix_hint='Pass error={"Study A": (0.8, 2.4), ...} and error_label="95% CI".',
        )
    parsed = _named_values(data, "forest(data)")
    if not parsed:
        raise ExplainError(
            "forest(data) is empty.",
            fix_hint='Pass a mapping such as {"Cohort A": 2.4, "Cohort B": 1.1}.',
        )
    if len(parsed) > MAX_COMPARE_ITEMS:
        if not _is_strict():
            req_hl = (
                [highlight]
                if isinstance(highlight, str)
                else ([str(h) for h in highlight] if highlight is not None else [])
            )
            keep: list[str] = [nm for nm in req_hl if nm in parsed]
            if baseline is not None and str(baseline) in parsed and str(baseline) not in keep:
                keep.append(str(baseline))
            for nm in parsed:
                if len(keep) >= MAX_COMPARE_ITEMS:
                    break
                if nm not in keep:
                    keep.append(nm)
            keep_set = set(keep)
            parsed = {nm: parsed[nm] for nm in parsed if nm in keep_set}
            if _has_items(error):
                error = {str(k): v for k, v in _pairs(error) if str(k) in keep_set}
            if n is not None and _has_items(n):
                n = {str(k): v for k, v in _pairs(n) if str(k) in keep_set}
            _record_adjustment(f"forest(): trimmed to {len(parsed)} items")
        else:
            raise ExplainError(
                f"forest() got {len(parsed)} items; more than {MAX_COMPARE_ITEMS} rows crowd a chat figure.",
                fix_hint=f"Keep at most {MAX_COMPARE_ITEMS} items or split into two panels.",
                rule="too_many_items",
            )

    errors, _modes = _compare_intervals(error, parsed)
    counts = _compare_counts(n, list(parsed)) if n is not None else {}
    pooled_info = _parse_pooled(pooled, log=log)
    ref = _reference_line(reference, "forest(reference)")

    if log:
        bad_vals = [nm for nm, v in parsed.items() if v <= 0 or errors[nm][0] <= 0 or errors[nm][1] <= 0]
        if bad_vals:
            raise ExplainError(
                f"forest(log=True) needs strictly positive values and interval bounds (check {bad_vals[:3]!r}).",
                fix_hint="Drop log=True for signed differences, or use positive odds/hazard ratios.",
            )
        if ref is not None and ref[0] <= 0:
            raise ExplainError(
                f"forest(log=True) cannot draw a reference line at {ref[0]}.",
                fix_hint="Pass reference=1.0 for odds/hazard ratios on a log scale, or drop log=True.",
            )

    order = _sort_order(sort)
    if order == "desc":
        names = sorted(parsed, key=lambda nm: parsed[nm], reverse=True)
    elif order == "asc":
        names = sorted(parsed, key=lambda nm: parsed[nm])
    else:
        names = list(parsed)

    hl = _names(highlight, names)
    base = _baseline_name(baseline, names, hl, "forest")
    issues: list[dict[str, Any]] = []
    err_label = error_label.strip() if isinstance(error_label, str) and error_label.strip() else None
    if err_label is None:
        issues.append(_interval_issue("forest", "error", "error_label"))

    values = [parsed[nm] for nm in names]
    all_nums = [*values, *(b for nm in names for b in errors[nm])]
    if pooled_info is not None:
        all_nums.extend([pooled_info[1], pooled_info[2], pooled_info[3]])
    fmt_fn = _formatter(all_nums, fmt, unit=unit, log=log)

    signed_around_zero = (not log) and (ref is not None) and (ref[0] == 0.0)

    def _fmt_est(v: float) -> str:
        s = fmt_fn(v)
        return _signed(s) if signed_around_zero else s

    def _u_est(v: float) -> str:
        return _with_unit(_fmt_est(v), unit)

    def _row_readout(est_v: float, lo_v: float, hi_v: float, *, with_u: bool) -> str:
        e_s, l_s, h_s = _fmt_est(est_v), _fmt_est(lo_v), _fmt_est(hi_v)
        if with_u and unit and _inline_unit(unit):
            return f"{_with_unit(e_s, unit)} [{l_s}, {h_s}]"
        return f"{e_s} [{l_s}, {h_s}]"

    # Automatic facts: items excluding null, largest effect, pooled summary, per-item highlights.
    facts: list[str] = []
    err_desc = err_label or "CI"
    ref_val = ref[0] if ref is not None else None
    ref_str = (
        _with_unit(_formatter([ref_val], fmt, unit=unit, log=log)(ref_val), unit)
        if ref_val is not None
        else ""
    )

    if ref_val is not None:
        excludes = [nm for nm in names if errors[nm][0] > ref_val or errors[nm][1] < ref_val]
        if excludes:
            listed = ", ".join(excludes[:4]) + (f" (+{len(excludes) - 4} more)" if len(excludes) > 4 else "")
            facts.append(
                f"{len(excludes)} of {len(names)} items exclude null ({ref_str}): {listed}"
            )
        else:
            facts.append(f"0 of {len(names)} items exclude null ({ref_str})")

    def _effect_mag(v: float) -> float:
        if log:
            anchor = ref_val if (ref_val is not None and ref_val > 0) else 1.0
            return abs(math.log(v / anchor))
        anchor = ref_val if ref_val is not None else 0.0
        return abs(v - anchor)

    largest_nm = max(names, key=lambda nm: _effect_mag(parsed[nm]))
    l_lo, l_hi = errors[largest_nm]
    facts.append(
        f"largest effect: {largest_nm} = {_u_est(parsed[largest_nm])} "
        f"({err_desc} [{_fmt_est(l_lo)}, {_fmt_est(l_hi)}])"
    )

    if pooled_info is not None:
        p_label, p_est, p_lo, p_hi, p_n = pooled_info
        p_null = ""
        if ref_val is not None:
            p_excl = p_lo > ref_val or p_hi < ref_val
            p_null = f"; {'excludes' if p_excl else 'crosses'} null ({ref_str})"
        p_n_str = f", n={p_n:,}" if p_n is not None else ""
        facts.append(
            f"{p_label}: {_u_est(p_est)} ({err_desc} [{_fmt_est(p_lo)}, {_fmt_est(p_hi)}]){p_n_str}{p_null}"
        )

    focus_list = list(dict.fromkeys([*hl, *([base] if base else []), *names[:4]]))[:5]
    for nm in focus_list:
        lo_v, hi_v = errors[nm]
        n_txt = f", n={counts[nm]:,}" if nm in counts else ""
        facts.append(
            f"{nm}: {_u_est(parsed[nm])} ({err_desc} [{_fmt_est(lo_v)}, {_fmt_est(hi_v)}]){n_txt}"
        )

    alt_facts = facts[: min(4, len(facts))]

    # Subtitle measure note
    note_bits: list[str] = []
    if err_label:
        note_bits.append(f"whiskers: {err_label}")
    else:
        note_bits.append("whiskers: unlabelled interval")
    if pooled_info is not None:
        note_bits.append(f"diamond: {pooled_info[0]}")
    if ref is not None:
        ref_lbl = ref[1] if ref[1] else f"null = {ref_str}"
        note_bits.append(f"dashed: {ref_lbl}")
    if log:
        note_bits.append("log scale")
    measure_note = "; ".join(note_bits)

    n_items = len(names)
    has_pooled = pooled_info is not None
    y_rows = np.arange(n_items, dtype=float)
    y_sep = float(n_items) - 0.38
    y_pooled = float(n_items) + 0.35

    all_row_labels = [*names, *([pooled_info[0]] if pooled_info is not None else [])]

    def _wrapped(
        cell_width_mm: float,
        measure: _Measure,
        sizes: _Sizes,
        theme: Theme = MINTFIG_THEME,
    ) -> list[str]:
        cell_pt = cell_width_mm * sizes.scale / PT_TO_MM
        ell = theme.ellipsis
        out: list[str] = []
        for nm in all_row_labels:
            weight = "bold" if (nm in hl or (pooled_info is not None and nm == pooled_info[0])) else "normal"
            lines = measure.wrap(nm, 0.34 * cell_pt, sizes.body, weight)
            if len(lines) > 2:
                lines = [lines[0], " ".join(lines[1:])]
            fitted: list[str] = []
            for line in lines:
                min_len = max(4, len(ell) + 2)
                while (
                    len(line) > min_len
                    and measure.width_pt(line, sizes.body, weight) > 0.38 * cell_pt
                ):
                    if len(ell) == 1:
                        line = line[:-2].rstrip() + ell
                    else:
                        line = line.removesuffix(ell)[:-1].rstrip() + ell
                fitted.append(line)
            out.append("\n".join(fitted))
        return out

    def _pitch(wrapped: list[str], *, tight: bool = False, compact: bool = False) -> float:
        lines = max((w.count("\n") + 1 for w in wrapped), default=1)
        if compact:
            return {1: 4.8, 2: 7.4}.get(lines, 9.6)
        if tight:
            return {1: 5.2, 2: 7.8}.get(lines, 10.0)
        return {1: 6.0, 2: 8.6}.get(lines, 11.0)

    def _extra_mm() -> float:
        return (5.5 if has_pooled else 0.0) + 12.0 + (3.5 if (ref is not None and ref[1]) else 0.0)

    def _draw(ctx: _Ctx, ax: Axes) -> Callable[[], None] | None:
        sz = ctx.sizes
        theme = ctx.theme
        accent = {
            name: col for name, col in ctx.colors.items() if name in names and name != base
        }
        emphasis = set(hl) if hl else set(accent)

        def _color(name: str) -> str:
            if name == base:
                return ctx.colors.get(name, theme.ink)
            if hl or accent:
                return accent.get(name, theme.axis)
            return ctx.default_color

        dot_colors = [_color(nm) for nm in names]
        lows = np.array([errors[nm][0] for nm in names], dtype=float)
        highs = np.array([errors[nm][1] for nm in names], dtype=float)
        vals = np.asarray(values, dtype=float)

        _bare_axes(ax)
        y_bottom = (y_pooled + 0.6) if has_pooled else (n_items - 0.45)
        ax.set_ylim(y_bottom, -0.65)

        lo_x = float(min(lows.min(), pooled_info[2] if pooled_info else np.inf, ref_val if ref_val is not None else np.inf))
        hi_x = float(max(highs.max(), pooled_info[3] if pooled_info else -np.inf, ref_val if ref_val is not None else -np.inf))

        if log:
            ax.set_xscale("log")
            pad = max((hi_x / lo_x) ** 0.06, 1.12)
            ax.set_xlim(
                *_narrow_log_ticks(
                    ax.xaxis, lo_x / pad, hi_x * pad, theme.minus_sign, extend=False, data_hi=hi_x
                )
            )
            ax.tick_params(
                axis="x",
                length=theme.tick_length,
                width=theme.tick_width,
                color=theme.axis,
                labelsize=sz.small,
                labelcolor=theme.muted,
            )
            ax.spines["bottom"].set_visible(True)
            ax.spines["bottom"].set_color(theme.axis)
            ax.spines["bottom"].set_linewidth(theme.axis_lw)
        else:
            span = (hi_x - lo_x) or abs(hi_x) or 1.0
            ax.set_xlim(lo_x - 0.06 * span, hi_x + 0.06 * span)
            minus = theme.minus_sign
            ax.xaxis.set_major_locator(MaxNLocator(nbins=5 if ctx.cell_width_mm >= 100 else 4, steps=[1, 2, 2.5, 5, 10]))
            ax.xaxis.set_major_formatter(
                FuncFormatter(lambda v, _p, m=minus, a=ax.xaxis: _tick_label(v, m, a))
            )
            ax.tick_params(axis="x", length=0, labelsize=sz.small, labelcolor=theme.muted, pad=3)
            ax._mintfig_cover = (lo_x, hi_x)  # type: ignore[attr-defined]
            _cover_with_ticks(ax.xaxis, lo_x, hi_x)

        if theme.grid_style != "none" and theme.grid_lw > 0:
            ax.grid(axis="x", color=theme.grid, linestyle=theme.grid_style, linewidth=theme.grid_lw)
        ax.set_axisbelow(True)

        x_title = _measure_text(label, unit)
        if x_title:
            ax.set_xlabel(
                _plain(x_title, theme),
                fontsize=sz.small,
                color=theme.muted,
                labelpad=3,
            )

        # Vertical null reference line
        ref_note: Any = None
        if ref is not None:
            ax.axvline(
                ref[0],
                color=theme.ink,
                linewidth=0.85 * sz.scale,
                linestyle=(0, (3, 2)),
                zorder=1.5,
            )
            if ref[1]:
                ref_note = ax.annotate(
                    _plain(ref[1], theme),
                    (ref[0], 1.0),
                    xycoords=("data", "axes fraction"),
                    xytext=(0.0, 3.0),
                    textcoords="offset points",
                    ha="center",
                    va="bottom",
                    fontsize=sz.small,
                    color=theme.muted,
                    annotation_clip=False,
                )

        # Horizontal CI whiskers + caps
        ax.hlines(y_rows, lows, highs, color=dot_colors, linewidth=1.15 * sz.scale, zorder=2)
        for ends in (lows, highs):
            ax.vlines(
                ends,
                y_rows - 0.14,
                y_rows + 0.14,
                color=dot_colors,
                linewidth=1.0 * sz.scale,
                zorder=2,
            )

        # Square point estimate markers (subtly scaled by sqrt(n) when sample sizes vary)
        if counts and len({counts[nm] for nm in names if nm in counts and counts[nm] > 0}) >= 2:
            pos_n = [counts.get(nm, 0) for nm in names]
            sq = np.sqrt(np.array([max(v, 1) for v in pos_n], dtype=float))
            sq_lo, sq_hi = float(sq.min()), float(sq.max())
            marker_sizes = (
                (4.3 + 2.4 * (sq - sq_lo) / max(sq_hi - sq_lo, 1e-9)) * sz.scale
            ) ** 2
        else:
            marker_sizes = np.full(n_items, (5.2 * sz.scale) ** 2)

        dots_art = ax.scatter(
            vals,
            y_rows,
            s=marker_sizes,
            marker="s",
            color=dot_colors,
            edgecolor=theme.background,
            linewidth=0.6 * sz.scale,
            zorder=3,
        )
        tag_points(
            ctx,
            dots_art,
            vals,
            y_rows,
            [
                {
                    "name": nm,
                    "value": parsed[nm],
                    "lo": errors[nm][0],
                    "hi": errors[nm][1],
                    "n": counts.get(nm),
                    "unit": unit,
                }
                for nm in names
            ],
        )

        # Pooled diamond row separated by subtle horizontal rule
        if pooled_info is not None:
            p_label, p_est, p_lo, p_hi, p_n = pooled_info
            ax.axhline(
                y_sep,
                color=theme.axis,
                linewidth=0.75 * sz.scale,
                zorder=1,
            )
            p_col = theme.ink
            diamond_pts = [
                (p_lo, y_pooled),
                (p_est, y_pooled - 0.24),
                (p_hi, y_pooled),
                (p_est, y_pooled + 0.24),
            ]
            poly = Polygon(
                diamond_pts,
                closed=True,
                facecolor=p_col,
                edgecolor=p_col,
                linewidth=0.7 * sz.scale,
                zorder=3.5,
            )
            ax.add_patch(poly)
            tag_mark(
                ctx,
                poly,
                name=p_label,
                value=p_est,
                lo=p_lo,
                hi=p_hi,
                n=p_n,
                unit=unit,
            )
            if p_hi <= p_lo:
                ax.scatter(
                    [p_est],
                    [y_pooled],
                    s=(6.0 * sz.scale) ** 2,
                    marker="D",
                    color=p_col,
                    zorder=4,
                )

        # Left y-axis labels
        shown_names = _wrapped(ctx.cell_width_mm, ctx.measure, sz, theme)
        y_ticks = [*y_rows.tolist(), *([y_pooled] if has_pooled else [])]
        ax.set_yticks(y_ticks, [_plain(nm, theme) for nm in shown_names])
        ax.tick_params(axis="y", length=0, labelsize=sz.body, labelcolor=theme.ink, pad=5)
        for idx, (tick, raw_nm) in enumerate(zip(ax.get_yticklabels(), all_row_labels, strict=True)):
            tick.set_linespacing(1.05)
            is_pool_row = has_pooled and idx == len(all_row_labels) - 1
            if is_pool_row or raw_nm in emphasis:
                tick.set_fontweight("bold")

        # Right-aligned tabular readout: est [lo, hi]  (and n=... when provided)
        readouts = [
            _row_readout(parsed[nm], errors[nm][0], errors[nm][1], with_u=True)
            for nm in names
        ]
        n_texts = [f"n={counts[nm]:,}" if nm in counts else "" for nm in names]
        if pooled_info is not None:
            p_label, p_est, p_lo, p_hi, p_n = pooled_info
            readouts.append(_row_readout(p_est, p_lo, p_hi, with_u=True))
            n_texts.append(f"n={p_n:,}" if p_n is not None else "")

        has_n_col = any(bool(t) for t in n_texts)
        est_hdr = err_label or "Est [CI]"
        col1_w = max(
            ctx.measure.width_pt(est_hdr, sz.small, "normal"),
            *(ctx.measure.width_pt(r, sz.small, "bold") for r in readouts),
        )
        col1_x = 8.0 + col1_w
        ax.annotate(
            _plain(est_hdr, theme),
            (1.0, 1.0),
            xycoords="axes fraction",
            xytext=(col1_x, 3.0),
            textcoords="offset points",
            ha="right",
            va="bottom",
            fontsize=sz.small,
            color=theme.muted,
            annotation_clip=False,
        )
        col2_x = col1_x
        if has_n_col:
            col2_w = max(
                ctx.measure.width_pt("n", sz.small, "normal"),
                *(ctx.measure.width_pt(t, sz.small, "normal") for t in n_texts if t),
            )
            col2_x = col1_x + 8.0 + col2_w
            ax.annotate(
                "n",
                (1.0, 1.0),
                xycoords="axes fraction",
                xytext=(col2_x, 3.0),
                textcoords="offset points",
                ha="right",
                va="bottom",
                fontsize=sz.small,
                color=theme.muted,
                annotation_clip=False,
            )

        for idx, (yi, raw_nm, r_txt, n_txt) in enumerate(
            zip(y_ticks, all_row_labels, readouts, n_texts, strict=True)
        ):
            is_pool_row = has_pooled and idx == len(all_row_labels) - 1
            is_bold = is_pool_row or (raw_nm in emphasis)
            ax.annotate(
                _plain(r_txt, theme),
                (1.0, yi),
                xycoords=("axes fraction", "data"),
                xytext=(col1_x, 0.0),
                textcoords="offset points",
                ha="right",
                va="center",
                fontsize=sz.small,
                color=theme.ink,
                fontweight="bold" if is_bold else "normal",
                annotation_clip=False,
            )
            if has_n_col and n_txt:
                ax.annotate(
                    _plain(n_txt, theme),
                    (1.0, yi),
                    xycoords=("axes fraction", "data"),
                    xytext=(col2_x, 0.0),
                    textcoords="offset points",
                    ha="right",
                    va="center",
                    fontsize=sz.small,
                    color=theme.muted,
                    annotation_clip=False,
                )

        if ref_note is not None:
            def _finish() -> None:
                from .core import _keep_inside_x

                _keep_inside_x(ctx, ax, ref_note)

            return _finish
        return None

    # Spec serialization (round-trips through mint.load)
    spec_error = {nm: [float(errors[nm][0]), float(errors[nm][1])] for nm in parsed}
    spec_pooled: dict[str, Any] | None = None
    if pooled_info is not None:
        p_label, p_est, p_lo, p_hi, p_n = pooled_info
        spec_pooled = {
            "label": p_label,
            "value": float(p_est),
            "lo": float(p_lo),
            "hi": float(p_hi),
        }
        if p_n is not None:
            spec_pooled["n"] = int(p_n)

    total_rows = n_items + (1 if has_pooled else 0)
    return Panel(
        kind="forest",
        title=title,
        label=label,
        unit=unit,
        spec=_base_spec(
            title,
            label,
            unit,
            data={nm: float(parsed[nm]) for nm in parsed},
            error=spec_error,
            error_label=err_label,
            reference=list(ref) if ref is not None else None,
            pooled=spec_pooled,
            n=counts or None,
            baseline=base,
            highlight=hl or None,
            log=log or None,
            sort=sort if sort is not True else None,
            fmt=fmt,
        ),
        facts=facts,
        alt_facts=alt_facts,
        describe=(
            f"Forest plot of {label or 'effect sizes'}"
            + (f" ({unit})" if unit else "")
            + f" across {n_items} item(s)"
            + (f" with {pooled_info[0]} diamond" if pooled_info is not None else "")
            + (f" ({err_label})" if err_label else "")
        ),
        issues=issues,
        _height_mm=lambda w, measure, sizes, theme: (
            max(18.0, _pitch(_wrapped(w, measure, sizes, theme), compact=sizes.compact) * total_rows)
            + _extra_mm()
        ),
        _min_height_mm=lambda w, measure, sizes, theme: (
            max(16.0, _pitch(_wrapped(w, measure, sizes, theme), tight=True, compact=sizes.compact) * total_rows)
            + _extra_mm()
        ),
        _draw=_draw,
        measure_note=measure_note,
        color_items=tuple(names),
        color_focus=tuple(hl),
        color_mode="highlight" if hl else "uniform",
        uses_default=not hl,
        color_baseline=base,
    )
