"""flow() quantitative attrition / cohort / funnel form for fm.explain.

Answers: "How much survives each stage of a pipeline or cohort, where is the
biggest drop, and why?"
Draws sequential top-to-bottom horizontal bars (preserving stage order, always
grounded at zero) with remaining count + % of start beside each bar and
drop-off callouts (count, % of prior stage, optional exclusion reason) in the
lane between consecutive stages.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np
from matplotlib.axes import Axes

from .._tabular import extract_records, is_tabular
from ..themes import FIGMINT_THEME, Theme
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
    _is_strict,
    _issue,
    _jsonable,
    _Measure,
    _names,
    _plain,
    _record_adjustment,
    _signed,
    _Sizes,
    _to_float,
    _with_unit,
)

MAX_FLOW_STAGES = 12
COMFORTABLE_FLOW_STAGES = 8


def _normalize_stages(
    stages: object,
    *,
    name: str | None = None,
    value: str | None = None,
    reason: str | None = None,
) -> list[dict[str, Any]]:
    """Normalize dict, tuple list, or tidy rows into ``[{"name", "value", "reason"}]``."""
    if is_tabular(stages):
        cols, rows = extract_records(stages, what="flow(stages)")
        if not rows:
            raise ExplainError("flow(stages) is empty.", fix_hint="Pass at least two stages.")
        lower_map = {c.lower(): c for c in cols}
        n_col = name or next(
            (lower_map[k] for k in ("stage", "step", "name", "phase", "label") if k in lower_map),
            None,
        )
        v_col = value or next(
            (
                lower_map[k]
                for k in ("count", "value", "n", "remaining", "users", "samples", "items")
                if k in lower_map
            ),
            None,
        )
        r_col = reason or next(
            (
                lower_map[k]
                for k in ("reason", "drop_reason", "exclusion", "excluded", "cause", "note")
                if k in lower_map
            ),
            None,
        )
        if not (n_col and v_col):
            shown = ", ".join(repr(c) for c in cols[:8])
            raise ExplainError(
                f"flow() needs name= and value= columns for row-shaped data (columns: {shown}).",
                fix_hint='Pass flow(rows, name="stage", value="count", reason="drop_reason").',
            )
        for col, arg in ((n_col, "name"), (v_col, "value")):
            if col not in cols:
                raise ExplainError(
                    f"flow({arg}={col!r}) column not found.",
                    fix_hint=f"Available columns: {', '.join(map(repr, cols[:10]))}.",
                )
        if reason is not None and reason not in cols:
            raise ExplainError(
                f"flow(reason={reason!r}) column not found.",
                fix_hint=f"Available columns: {', '.join(map(repr, cols[:10]))}.",
            )
        out: list[dict[str, Any]] = []
        for row in rows:
            nm = str(row.get(n_col, "")).strip()
            val = _to_float(row.get(v_col), f"flow(value[{nm!r}])")
            rsn_raw = row.get(r_col) if r_col is not None else None
            rsn = str(rsn_raw).strip() if rsn_raw is not None and str(rsn_raw).strip() else None
            out.append({"name": nm, "value": val, "reason": rsn})
        return out

    if any(a is not None for a in (name, value, reason)):
        raise ExplainError(
            "flow(name=/value=/reason=) require row-shaped data (list of dicts or DataFrame).",
            fix_hint='Pass rows=[{"stage": "Screened", "count": 1240}, ...] or drop column args.',
        )

    if isinstance(stages, Mapping):
        if not stages:
            raise ExplainError("flow(stages) is empty.", fix_hint="Pass at least two stages.")
        out = []
        for raw_nm, raw_val in stages.items():
            nm = str(raw_nm)
            if (
                isinstance(raw_val, Sequence)
                and not isinstance(raw_val, (str, bytes))
                and len(raw_val) == 2
            ):
                val = _to_float(raw_val[0], f"flow(stages[{nm!r}][0])")
                rsn = str(raw_val[1]).strip() if raw_val[1] is not None and str(raw_val[1]).strip() else None
            else:
                val = _to_float(raw_val, f"flow(stages[{nm!r}])")
                rsn = None
            out.append({"name": nm, "value": val, "reason": rsn})
        return out

    if isinstance(stages, Sequence) and not isinstance(stages, (str, bytes)):
        if not stages:
            raise ExplainError("flow(stages) is empty.", fix_hint="Pass at least two stages.")
        out = []
        for idx, entry in enumerate(stages):
            if (
                isinstance(entry, (str, bytes))
                or not isinstance(entry, Sequence)
                or len(entry) not in {2, 3}
            ):
                raise ExplainError(
                    f"flow(stages[{idx}]) must be (name, count) or (name, count, reason).",
                    fix_hint='e.g. [("Screened", 1240), ("Eligible", 912, "missing baseline")].',
                )
            nm = str(entry[0])
            val = _to_float(entry[1], f"flow(stages[{nm!r}])")
            rsn = (
                str(entry[2]).strip()
                if len(entry) == 3 and entry[2] is not None and str(entry[2]).strip()
                else None
            )
            out.append({"name": nm, "value": val, "reason": rsn})
        return out

    raise ExplainError(
        f"flow(stages) expected a dict, list of (stage, count[, reason]) tuples, or rows; got {type(stages).__name__}.",
        fix_hint='e.g. fm.flow([("Screened", 1240), ("Eligible", 912, "missing baseline")]).',
    )


@_guarded("flow")
def flow(
    stages: (
        Mapping[str, float]
        | Sequence[tuple[str, float]]
        | Sequence[tuple[str, float, str | None]]
        | Sequence[Mapping[str, Any]]
    ),
    *,
    name: str | None = None,
    value: str | None = None,
    reason: str | None = None,
    title: str | None = None,
    label: str | None = None,
    unit: str | None = None,
    highlight: str | Sequence[str] | None = None,
    show_pct: bool = True,
    fmt: str | None = None,
) -> Panel:
    """How much survives each stage of a pipeline or cohort, where is the biggest drop, and why?

    ``stages`` preserves sequential top-to-bottom order and accepts ``{stage: count}``,
    ``[(stage, count[, drop_reason]), ...]``, or row-shaped data with ``name=``, ``value=``,
    and optional ``reason=`` (explaining the drop entering each stage).
    """
    records = _normalize_stages(stages, name=name, value=value, reason=reason)
    if len(records) < 2:
        raise ExplainError(
            "flow() needs at least two stages to show retention or attrition.",
            fix_hint="Pass two or more ordered stages, or use compare() for a single snapshot.",
        )
    for rec in records:
        if rec["value"] < 0:
            raise ExplainError(
                f"flow() stage {rec['name']!r} has negative value {rec['value']}.",
                fix_hint="flow() requires non-negative counts; use waterfall() for signed deltas.",
            )
    if records[0]["value"] <= 0:
        raise ExplainError(
            f"flow() first stage {records[0]['name']!r} must be positive (got {records[0]['value']}).",
            fix_hint="Start the flow with a positive initial cohort or total.",
        )

    if len(records) > MAX_FLOW_STAGES:
        if not _is_strict():
            orig_n = len(records)
            # Keep first, last, and intermediate stages with largest drops
            req_hl = (
                [highlight]
                if isinstance(highlight, str)
                else ([str(h) for h in highlight] if highlight is not None else [])
            )
            hl_req = set(req_hl)
            must = {0, orig_n - 1} | {i for i, r in enumerate(records) if r["name"] in hl_req}
            drops = sorted(
                range(1, orig_n - 1),
                key=lambda i: abs(records[i]["value"] - records[i - 1]["value"]),
                reverse=True,
            )
            chosen = set(must)
            for idx in drops:
                if len(chosen) >= MAX_FLOW_STAGES:
                    break
                chosen.add(idx)
            records = [records[i] for i in sorted(chosen)]
            _record_adjustment(f"flow(): kept {len(records)} of {orig_n} stages (first, last, and largest drops)")
        else:
            raise ExplainError(
                f"flow() got {len(records)} stages; more than {MAX_FLOW_STAGES} is crowded in one funnel.",
                fix_hint=f"Group minor intermediate steps into at most {MAX_FLOW_STAGES} stages.",
                rule="too_many_items",
            )

    stage_names = [r["name"] for r in records]
    vals = [float(r["value"]) for r in records]
    hl = _names(highlight, stage_names, "flow(highlight)")

    issues: list[dict[str, Any]] = []
    if len(records) > COMFORTABLE_FLOW_STAGES:
        issues.append(
            _issue(
                "many_items",
                "warning",
                f"{len(records)} flow stages is long for one glance.",
                "Combine minor intermediate filters if the detail is not needed.",
            )
        )

    start_val = vals[0]
    end_val = vals[-1]
    max_val = max(vals)
    transitions: list[tuple[int, float, float, str | None]] = []
    for i in range(1, len(records)):
        prev_v = vals[i - 1]
        delta = vals[i] - prev_v
        step_pct = (100.0 * delta / prev_v) if prev_v > 0 else 0.0
        transitions.append((i, delta, step_pct, records[i]["reason"]))

    all_nums = [*vals, *(abs(d) for _, d, _, _ in transitions if d != 0)]
    val_fmt = _formatter(all_nums, fmt, unit=unit)

    def _v(x: float) -> str:
        return _with_unit(val_fmt(x), unit)

    def _pct_str(p: float) -> str:
        ap = abs(p)
        if ap >= 10 or abs(p - round(p)) < 0.05:
            return f"{p:.0f}%"
        return f"{p:.1f}%"

    def _signed_pct(p: float) -> str:
        if p < 0:
            return f"\N{MINUS SIGN}{_pct_str(abs(p))}"
        if p > 0:
            return f"+{_pct_str(abs(p))}"
        return "0%"

    # Facts
    ret_pct = 100.0 * end_val / start_val
    net_drop = start_val - end_val
    facts: list[str] = [
        (
            f"{stage_names[0]} {_v(start_val)} \N{RIGHTWARDS ARROW} {stage_names[-1]} {_v(end_val)} "
            f"({ret_pct:.1f}% retained; {_v(net_drop)} dropped across {len(records) - 1} steps)"
            if net_drop >= 0
            else f"{stage_names[0]} {_v(start_val)} \N{RIGHTWARDS ARROW} {stage_names[-1]} {_v(end_val)} "
            f"({ret_pct:.1f}% of initial across {len(records) - 1} steps)"
        )
    ]

    drop_transitions = [t for t in transitions if t[1] < 0]
    biggest_drop_idx: int | None = None
    if drop_transitions:
        worst = min(drop_transitions, key=lambda t: t[1])
        biggest_drop_idx = worst[0]
        wi, wd, wp, wrsn = worst
        rsn_suffix = f" ({wrsn})" if wrsn else ""
        facts.append(
            f"largest drop: {stage_names[wi - 1]} \N{RIGHTWARDS ARROW} {stage_names[wi]} "
            f"({_diff_with_unit(_signed(val_fmt(wd)), unit)}, {_signed_pct(wp)} of prior stage){rsn_suffix}"
        )

    for nm in hl:
        idx = stage_names.index(nm)
        p_init = 100.0 * vals[idx] / start_val
        extra = ""
        if idx > 0:
            prev_v = vals[idx - 1]
            d = vals[idx] - prev_v
            sp = (100.0 * d / prev_v) if prev_v > 0 else 0.0
            rsn = records[idx]["reason"]
            extra = f", {_diff_with_unit(_signed(val_fmt(d)), unit)} ({_signed_pct(sp)}) from {stage_names[idx - 1]}"
            if rsn:
                extra += f": {rsn}"
        facts.append(f"{nm}: {_v(vals[idx])} ({p_init:.1f}% of {stage_names[0]}{extra})")

    n_rows = len(records)
    hl_set = set(hl)
    has_reasons = any(r["reason"] for r in records[1:])

    def _wrapped(
        cell_width_mm: float,
        measure: _Measure,
        sizes: _Sizes,
        theme: Theme = FIGMINT_THEME,
    ) -> list[str]:
        cell_pt = cell_width_mm * sizes.scale / PT_TO_MM
        out: list[str] = []
        for idx, nm in enumerate(stage_names):
            weight = "bold" if (nm in hl_set or idx in {0, n_rows - 1}) else "normal"
            lines = measure.wrap(nm, 0.34 * cell_pt, sizes.body, weight)
            if len(lines) > 2:
                lines = [lines[0], " ".join(lines[1:])]
            out.append("\n".join(lines))
        return out

    def _pitch(wrapped: list[str], tight: bool = False) -> float:
        lines = max(nm.count("\n") + 1 for nm in wrapped)
        if tight:
            return 8.6 if lines == 1 else 10.2
        return 9.6 if lines == 1 else 11.4

    def _draw(ctx: _Ctx, ax: Axes) -> None:
        sz = ctx.sizes
        theme = ctx.theme
        y = np.arange(n_rows, dtype=float)
        bar_h = 0.44
        focus_mode = bool(hl_set)
        accent_drop = theme.accent_colors[0] if theme.accent_colors else theme.series_colors[1]

        pad_r = (0.44 if has_reasons else 0.30) * max_val
        ax.set_xlim(0.0, max_val + pad_r)
        ax.set_ylim(n_rows - 0.55, -0.50)
        _bare_axes(ax)
        ax.xaxis.set_visible(False)

        conn_x: list[float] = []
        conn_y0: list[float] = []
        conn_y1: list[float] = []

        for idx, rec in enumerate(records):
            nm = rec["name"]
            val = vals[idx]
            if nm in hl_set:
                col = ctx.colors.get(nm, accent_drop)
                alpha = 1.0
            elif focus_mode:
                col = theme.context_fill
                alpha = 1.0
            elif idx == n_rows - 1:
                col = theme.ink
                alpha = 0.90
            else:
                col = ctx.default_color
                alpha = 0.92 if idx == 0 else 0.78

            if val > 0:
                ax.barh(
                    [idx],
                    [val],
                    height=bar_h,
                    color=col,
                    alpha=alpha,
                    edgecolor="none",
                    zorder=2,
                )

            # Value + % of initial label beside bar
            pct_init = 100.0 * val / start_val
            val_txt = _v(val)
            if show_pct:
                val_txt = f"{val_txt} ({_pct_str(pct_init)})"
            is_bold = nm in hl_set or idx in {0, n_rows - 1}
            ax.annotate(
                _plain(val_txt, theme),
                (val, idx),
                xytext=(5.0, 0.0),
                textcoords="offset points",
                ha="left",
                va="center",
                fontsize=sz.small,
                fontweight="bold" if is_bold else "normal",
                color=theme.ink if (is_bold or not focus_mode) else theme.muted,
                annotation_clip=False,
            )

            # Step-down connector & drop callout in the dedicated lane y = idx - 0.5
            if idx > 0:
                prev_v = vals[idx - 1]
                delta = val - prev_v
                step_pct = (100.0 * delta / prev_v) if prev_v > 0 else 0.0
                rsn = rec["reason"]
                anchor_x = min(val, prev_v)
                conn_x.append(anchor_x)
                conn_y0.append(idx - 1 + bar_h * 0.5)
                conn_y1.append(idx - bar_h * 0.5)

                if delta != 0 or rsn:
                    d_str = _diff_with_unit(_signed(val_fmt(delta)), unit)
                    p_str = _signed_pct(step_pct)
                    drop_txt = f"{d_str} ({p_str})"
                    if rsn:
                        drop_txt += f" \N{MIDDLE DOT} {rsn}"
                    is_key_drop = (nm in hl_set) or (not focus_mode and idx == biggest_drop_idx)
                    # Keep long drop reasons inside the plot area when anchor is near max_val
                    text_x = min(anchor_x, 0.72 * max_val) if rsn else anchor_x
                    ax.annotate(
                        _plain(drop_txt, theme),
                        (text_x, idx - 0.5),
                        xytext=(6.0, 0.0),
                        textcoords="offset points",
                        ha="left",
                        va="center",
                        fontsize=sz.small,
                        fontweight="bold" if is_key_drop else "normal",
                        color=ctx.text_color(accent_drop) if is_key_drop else theme.muted,
                        annotation_clip=False,
                    )

        if conn_x:
            ax.vlines(
                conn_x,
                conn_y0,
                conn_y1,
                color=theme.axis,
                linewidth=0.75 * sz.scale,
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

        shown_names = _wrapped(ctx.cell_width_mm, ctx.measure, sz, theme)
        ax.set_yticks(y, [_plain(nm, theme) for nm in shown_names])
        ax.tick_params(axis="y", length=0, labelsize=sz.body, labelcolor=theme.ink, pad=5)
        for tick, (idx, nm) in zip(ax.get_yticklabels(), enumerate(stage_names), strict=True):
            tick.set_linespacing(1.05)
            if nm in hl_set or idx in {0, n_rows - 1}:
                tick.set_fontweight("bold")
            elif focus_mode:
                tick.set_color(theme.muted)

    spec_stages = [
        [r["name"], _jsonable(r["value"]), r["reason"]]
        if r["reason"] is not None
        else [r["name"], _jsonable(r["value"])]
        for r in records
    ]
    spec = _base_spec(
        title,
        label,
        unit,
        stages=spec_stages,
        highlight=hl or None,
        show_pct=None if show_pct else False,
        fmt=fmt,
    )
    describe = (
        f"Sequential attrition flow of {label or 'counts'}"
        + (f" ({unit})" if unit else "")
        + f" across {len(records)} stages ({stage_names[0]} to {stage_names[-1]})"
    )
    return Panel(
        kind="flow",
        title=title,
        label=label,
        unit=unit,
        spec=spec,
        facts=facts,
        describe=describe,
        issues=issues,
        _height_mm=lambda w, m, s, t: n_rows * _pitch(_wrapped(w, m, s, t)) + 1.5,
        _min_height_mm=lambda w, m, s, t: n_rows * _pitch(_wrapped(w, m, s, t), tight=True) + 1.0,
        _draw=_draw,
        color_items=tuple(stage_names),
        color_focus=tuple(hl),
        color_mode="highlight" if hl else "uniform",
        uses_default=not hl,
        alt_facts=facts[: min(3, len(facts))],
    )
