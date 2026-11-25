"""Structured booktabs-style table form (``fm.table``) for exact lookups and scorecards.

Designed as an independent module so ``explainer.py`` stays modular. Obeys the
same contract as every other ``fm.explain`` form: declarative spec, computed
``facts``, shared entity colours across panels, theme/palette support, and
strict layout/legibility verification.
"""

from __future__ import annotations

import math
import numbers
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

from matplotlib.patches import Rectangle

from ._tabular import extract_table_data

if TYPE_CHECKING:
    from matplotlib.axes import Axes

    from .explainer import Panel, _Ctx, _Measure, _Sizes
    from .themes import Theme

MAX_TABLE_ROWS = 20
MAX_TABLE_COLS = 8


def _is_missing(val: Any) -> bool:
    if val is None:
        return True
    if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
        return True
    return bool(isinstance(val, str) and not val.strip())


def _as_float_or_none(val: Any) -> float | None:
    if _is_missing(val) or isinstance(val, bool):
        return None
    if isinstance(val, numbers.Real):
        f = float(val)
        return f if math.isfinite(f) else None
    if isinstance(val, str):
        text = val.strip()
        try:
            f = float(text)
        except ValueError:
            return None
        return f if math.isfinite(f) else None
    return None


def _wrap_header(text: str, max_pt: float, measure: _Measure, size_pt: float) -> str:
    """Wrap a multi-word header onto at most two balanced lines when needed."""
    if "\n" in text or measure.width_pt(text, size_pt) <= max_pt:
        return text
    words = text.split()
    if len(words) < 2:
        return text
    best = text
    best_width = float("inf")
    for idx in range(1, len(words)):
        top = " ".join(words[:idx])
        bot = " ".join(words[idx:])
        w = max(measure.width_pt(top, size_pt), measure.width_pt(bot, size_pt))
        if w < best_width:
            best_width = w
            best = f"{top}\n{bot}"
    return best


def _format_cell_markdown(headers: list[str], aligns: list[str], rows: list[list[str]]) -> str:
    """Render formatted table strings as a clean GitHub-Flavored Markdown table."""
    widths = [
        max(len(headers[c]), *(len(r[c]) for r in rows), 3) for c in range(len(headers))
    ]
    align_sep = {
        "left": lambda w: ":" + "-" * (w - 1),
        "right": lambda w: "-" * (w - 1) + ":",
        "center": lambda w: ":" + "-" * max(1, w - 2) + ":",
    }

    def _pad(val: str, w: int, al: str) -> str:
        if al == "right":
            return val.rjust(w)
        if al == "center":
            return val.center(w)
        return val.ljust(w)

    lines = [
        "| " + " | ".join(_pad(headers[c], widths[c], aligns[c]) for c in range(len(headers))) + " |",
        "| " + " | ".join(align_sep[aligns[c]](widths[c]) for c in range(len(headers))) + " |",
    ]
    for row in rows:
        lines.append(
            "| " + " | ".join(_pad(row[c], widths[c], aligns[c]) for c in range(len(headers))) + " |"
        )
    return "\n".join(lines)


def table(
    rows: Sequence[Mapping[str, Any]] | Mapping[str, Sequence[Any]] | Sequence[Sequence[Any]],
    *,
    columns: Sequence[str] | None = None,
    title: str | None = None,
    label: str | None = None,
    unit: str | None = None,
    units: Mapping[str, str] | None = None,
    highlight: str | Sequence[str] | None = None,
    baseline: str | None = None,
    bold_best: bool | str | Mapping[str, str] = False,
    sort: str | None = None,
    align: Mapping[str, str] | None = None,
    fmt: str | Mapping[str, str] | None = None,
) -> Panel:
    """Exact lookup table or multi-metric scorecard with booktabs rules and aligned figures.

    ``rows`` accepts a list of row dicts (``[{"Model": "A", "GPQA": 84.1, ...}]``),
    a pandas DataFrame, a column-oriented dict ``{"Model": [...], "GPQA": [...]}``,
    or a 2-D list paired with ``columns=[...]``.

    - ``highlight`` emphasizes 1–3 rows by column-0 name (sharing colours with
      adjacent chart panels in the same figure).
    - ``baseline`` marks a reference row in ink and states highlighted/best rows
      against it in ``facts``.
    - ``bold_best`` bolds each numeric column's winner: ``True`` / ``"max"``,
      ``"min"``, or ``{col: "max" | "min"}`` for mixed-direction scorecards
      (e.g. ``{"GPQA": "max", "Cost": "min"}``).
    - ``sort`` sorts by a column name (``"col"`` ascending, ``"-col"`` descending).
    - ``units`` attaches per-column units (``{"GPQA": "%", "Cost": "$/M"}``).
    - ``fmt`` sets a global format string or ``{col: fmt_str}``.
    """
    from ._explain.core import (
        _LINE,
        PT_TO_MM,
        ExplainError,
        Panel,
        _bare_axes,
        _baseline_name,
        _formatter,
        _is_strict,
        _jsonable,
        _names,
        _plain,
        _record_adjustment,
        _relative_luminance,
        _with_unit,
    )

    def _line_mm(pt: float) -> float:
        return pt * _LINE * PT_TO_MM

    col_names, raw_rows = extract_table_data(rows, columns=columns)
    if not col_names:
        raise ExplainError("table() has no columns.", fix_hint="Pass at least one column.")
    if not raw_rows:
        raise ExplainError("table() has no rows.", fix_hint="Pass at least one row.")

    # Column limit
    if len(col_names) > MAX_TABLE_COLS:
        if not _is_strict():
            orig = len(col_names)
            col_names = col_names[:MAX_TABLE_COLS]
            raw_rows = [r[:MAX_TABLE_COLS] for r in raw_rows]
            _record_adjustment(f"table(): trimmed {orig} columns to first {MAX_TABLE_COLS}")
        else:
            raise ExplainError(
                f"table() got {len(col_names)} columns; beyond {MAX_TABLE_COLS} columns "
                "a chat table becomes unreadable.",
                fix_hint=f"Keep at most {MAX_TABLE_COLS} columns via columns=[...], or split into two tables.",
                rule="too_many_items",
            )

    # Validate units / align / fmt / bold_best column keys
    unit_map: dict[str, str] = {}
    if units is not None:
        if not isinstance(units, Mapping):
            raise ExplainError(
                "table(units) must be a mapping of column name -> unit.",
                fix_hint='e.g. units={"GPQA": "%", "Cost": "$/M"}.',
            )
        for k, v in units.items():
            ks = str(k)
            if ks not in col_names:
                raise ExplainError(
                    f"table(units) names unknown column {ks!r}.",
                    fix_hint=f"Use column names from: {', '.join(map(repr, col_names))}.",
                )
            unit_map[ks] = str(v)

    fmt_map: dict[str, str] = {}
    global_fmt: str | None = None
    if isinstance(fmt, str):
        global_fmt = fmt
    elif isinstance(fmt, Mapping):
        for k, v in fmt.items():
            ks = str(k)
            if ks not in col_names:
                raise ExplainError(
                    f"table(fmt) names unknown column {ks!r}.",
                    fix_hint=f"Use column names from: {', '.join(map(repr, col_names))}.",
                )
            fmt_map[ks] = str(v)
    elif fmt is not None:
        raise ExplainError(
            "table(fmt) must be a format string or a dict of {column: fmt}.",
            fix_hint='e.g. fmt=".1f" or fmt={"Score": ".1f", "Cost": "${:.2f}"}.',
        )

    # Optional sort before row-limit trimming so top rows are kept
    if sort is not None:
        if not isinstance(sort, str) or not sort.strip():
            raise ExplainError(
                "table(sort) must be a column name (prefix '-' for descending).",
                fix_hint=f'e.g. sort="-{col_names[-1]}" or sort="{col_names[0]}".',
            )
        desc = sort.startswith("-")
        sort_col = sort[1:] if desc else sort
        if sort_col not in col_names:
            raise ExplainError(
                f"table(sort={sort!r}) names unknown column {sort_col!r}.",
                fix_hint=f"Use a column from: {', '.join(map(repr, col_names))} (prefix '-' for descending).",
            )
        cidx = col_names.index(sort_col)
        col_nums = [_as_float_or_none(r[cidx]) for r in raw_rows]
        if any(v is not None for v in col_nums):
            present = [i for i, v in enumerate(col_nums) if v is not None]
            missing_idx = [i for i, v in enumerate(col_nums) if v is None]
            present.sort(key=lambda i: col_nums[i], reverse=desc)  # type: ignore[arg-type,return-value]
            raw_rows = [raw_rows[i] for i in (*present, *missing_idx)]
        else:
            raw_rows = sorted(
                raw_rows,
                key=lambda r: ("" if _is_missing(r[cidx]) else str(r[cidx]).lower()),
                reverse=desc,
            )

    row_keys = [
        "\N{EM DASH}" if _is_missing(r[0]) else str(r[0]) for r in raw_rows
    ]

    # Row limit
    if len(raw_rows) > MAX_TABLE_ROWS:
        if not _is_strict():
            req_hl = (
                [highlight]
                if isinstance(highlight, str)
                else ([str(h) for h in highlight] if highlight is not None else [])
            )
            must_keep = set(req_hl)
            if baseline is not None:
                must_keep.add(str(baseline))
            kept_idx: list[int] = [i for i, rk in enumerate(row_keys) if rk in must_keep]
            for i in range(len(raw_rows)):
                if len(kept_idx) >= MAX_TABLE_ROWS:
                    break
                if i not in kept_idx:
                    kept_idx.append(i)
            kept_idx.sort()
            orig_n = len(raw_rows)
            raw_rows = [raw_rows[i] for i in kept_idx]
            row_keys = [row_keys[i] for i in kept_idx]
            _record_adjustment(f"table(): trimmed {orig_n} rows to {len(raw_rows)}")
        else:
            raise ExplainError(
                f"table() got {len(raw_rows)} rows; beyond {MAX_TABLE_ROWS} rows a chat "
                "table is scanned, not read.",
                fix_hint=f"Keep at most {MAX_TABLE_ROWS} rows (e.g. top rows in sort=), or split into two tables.",
                rule="too_many_items",
            )

    hl = _names(highlight, row_keys, "table(highlight)")
    base = _baseline_name(baseline, row_keys, hl, "table")

    # Detect numeric columns (excluding column 0 unless only 1 column exists)
    n_rows = len(raw_rows)
    n_cols = len(col_names)
    col_numeric: list[bool] = []
    col_floats: list[list[float | None]] = []
    for c in range(n_cols):
        vals = [raw_rows[r][c] for r in range(n_rows)]
        parsed = [_as_float_or_none(v) for v in vals]
        non_missing = [v for v in vals if not _is_missing(v)]
        is_num = (
            bool(non_missing)
            and all(_as_float_or_none(v) is not None for v in non_missing)
            and (c > 0 or n_cols == 1)
        )
        col_numeric.append(is_num)
        col_floats.append(parsed)

    # Alignment per column
    col_align: list[str] = ["right" if col_numeric[c] else "left" for c in range(n_cols)]
    if align is not None:
        if not isinstance(align, Mapping):
            raise ExplainError(
                "table(align) must map column name to 'left', 'right' or 'center'.",
                fix_hint='e.g. align={"Rank": "center"}.',
            )
        for k, v in align.items():
            ks = str(k)
            vs = str(v).lower()
            if ks not in col_names:
                raise ExplainError(
                    f"table(align) names unknown column {ks!r}.",
                    fix_hint=f"Use column names from: {', '.join(map(repr, col_names))}.",
                )
            if vs not in {"left", "right", "center"}:
                raise ExplainError(
                    f"table(align[{ks!r}]) must be 'left', 'right' or 'center', got {v!r}.",
                    fix_hint='Use "left", "right", or "center".',
                )
            col_align[col_names.index(ks)] = vs

    # Best-in-column bolding
    best_dir: dict[int, str] = {}
    if bold_best is True or bold_best == "max":
        for c in range(n_cols):
            if col_numeric[c]:
                best_dir[c] = "max"
    elif bold_best == "min":
        for c in range(n_cols):
            if col_numeric[c]:
                best_dir[c] = "min"
    elif isinstance(bold_best, Mapping):
        for k, v in bold_best.items():
            ks = str(k)
            vs = str(v).lower()
            if ks not in col_names:
                raise ExplainError(
                    f"table(bold_best) names unknown column {ks!r}.",
                    fix_hint=f"Use column names from: {', '.join(map(repr, col_names))}.",
                )
            if vs not in {"max", "min"}:
                raise ExplainError(
                    f"table(bold_best[{ks!r}]) must be 'max' or 'min', got {v!r}.",
                    fix_hint='Use "max" (higher is better) or "min" (lower is better).',
                )
            best_dir[col_names.index(ks)] = vs
    elif bold_best not in (False, None):
        raise ExplainError(
            f"table(bold_best={bold_best!r}) is not valid.",
            fix_hint='Pass True, False, "max", "min", or {column: "max"|"min"}.',
        )

    best_cells: set[tuple[int, int]] = set()
    for c, direction in best_dir.items():
        finite_pairs = [(r, col_floats[c][r]) for r in range(n_rows) if col_floats[c][r] is not None]
        if not finite_pairs:
            continue
        target_val = (
            max(v for _, v in finite_pairs)  # type: ignore[type-var]
            if direction == "max"
            else min(v for _, v in finite_pairs)  # type: ignore[type-var]
        )
        for r, v in finite_pairs:
            if v is not None and target_val is not None and math.isclose(v, target_val, rel_tol=1e-9, abs_tol=1e-12):
                best_cells.add((r, c))

    # Format headers (include per-column unit cleanly when not already in header)
    header_labels: list[str] = []
    for c, cname in enumerate(col_names):
        u = unit_map.get(cname)
        if u and f"({u})" not in cname and f"[{u}]" not in cname:
            header_labels.append(f"{cname} ({u})")
        else:
            header_labels.append(cname)

    # Format cell strings
    col_formatters: dict[int, Any] = {}
    formatted: list[list[str]] = [["" for _ in range(n_cols)] for _ in range(n_rows)]
    missing_count = 0
    for c in range(n_cols):
        cname = col_names[c]
        u = unit_map.get(cname) or (unit if col_numeric[c] and not unit_map else None)
        if col_numeric[c]:
            finite_vals = [v for v in col_floats[c] if v is not None]
            cfmt = fmt_map.get(cname, global_fmt)
            fmt_fn = _formatter(finite_vals, cfmt, unit=u)
            col_formatters[c] = fmt_fn
            for r in range(n_rows):
                fv = col_floats[c][r]
                if fv is None:
                    formatted[r][c] = "\N{EM DASH}"
                    missing_count += 1
                else:
                    formatted[r][c] = fmt_fn(fv)
        else:
            for r in range(n_rows):
                val = raw_rows[r][c]
                if _is_missing(val):
                    formatted[r][c] = "\N{EM DASH}"
                    missing_count += 1
                else:
                    formatted[r][c] = str(val)

    def _cell_with_unit(val_str: str, u: str | None) -> str:
        if not u:
            return val_str
        if val_str.startswith("$") and u.startswith("$"):
            return val_str + u[1:]
        return _with_unit(val_str, u)

    # Compute facts
    facts: list[str] = [f"{n_rows} rows \N{MULTIPLICATION SIGN} {n_cols} columns"]
    base_idx = row_keys.index(base) if base is not None else None
    for c in range(n_cols):
        if not col_numeric[c]:
            continue
        cname = col_names[c]
        u = unit_map.get(cname) or (unit if not unit_map else None)
        fmt_fn = col_formatters[c]
        finite_pairs = [(r, col_floats[c][r]) for r in range(n_rows) if col_floats[c][r] is not None]
        if not finite_pairs:
            continue
        hi_r, hi_v = max(finite_pairs, key=lambda kv: kv[1])  # type: ignore[arg-type,return-value]
        lo_r, lo_v = min(finite_pairs, key=lambda kv: kv[1])  # type: ignore[arg-type,return-value]
        hi_txt = _cell_with_unit(fmt_fn(hi_v), u)
        lo_txt = _cell_with_unit(fmt_fn(lo_v), u)
        if hi_r == lo_r:
            facts.append(f"{cname}: all {hi_txt}")
        else:
            facts.append(f"{cname}: highest {row_keys[hi_r]} ({hi_txt}), lowest {row_keys[lo_r]} ({lo_txt})")
        if base_idx is not None and col_floats[c][base_idx] is not None:
            bv = col_floats[c][base_idx]
            assert bv is not None
            targets = [row_keys.index(nm) for nm in hl] if hl else [hi_r]
            for tr in targets:
                if tr == base_idx or col_floats[c][tr] is None:
                    continue
                tv = col_floats[c][tr]
                assert tv is not None
                diff = tv - bv
                sign = "+" if diff > 0 else ("\N{MINUS SIGN}" if diff < 0 else "")
                dtxt = _cell_with_unit(fmt_fn(abs(diff)), u)
                facts.append(f"{cname}: {row_keys[tr]} vs {base} is {sign}{dtxt}")
    if missing_count:
        facts.append(f"{missing_count} empty cell(s) shown as \N{EM DASH}")

    markdown_text = _format_cell_markdown(header_labels, col_align, formatted)

    # Height computation: proportional to row count + header height
    def _height_mm(cell_w_mm: float, measure: _Measure, sizes: _Sizes, theme: Theme) -> float:
        row_h = max(_line_mm(sizes.small) * 1.48, 5.2 * sizes.scale)
        # Estimate whether any header wraps to 2 lines
        head_lines = 1
        est_col_pt = (cell_w_mm / PT_TO_MM) / max(n_cols, 1)
        if any(measure.width_pt(h, sizes.small) > est_col_pt * 1.15 and " " in h for h in header_labels):
            head_lines = 2
        head_h = max(_line_mm(sizes.small) * (1.25 * head_lines + 0.55), 6.2 * sizes.scale)
        return head_h + n_rows * row_h + 2.2 * sizes.scale

    def _min_height_mm(cell_w_mm: float, measure: _Measure, sizes: _Sizes, theme: Theme) -> float:
        row_h = max(_line_mm(sizes.small) * 1.32, 4.6 * sizes.scale)
        head_h = max(_line_mm(sizes.small) * 1.7, 5.8 * sizes.scale)
        return head_h + n_rows * row_h + 1.8 * sizes.scale

    def _draw(ctx: _Ctx, ax: Axes) -> Any:
        sz = ctx.sizes
        theme = ctx.theme
        measure = ctx.measure
        cell_w_pt = ctx.cell_width_mm / PT_TO_MM

        pad_pt = 4.2 * sz.scale
        stripe_pad_pt = 4.0 * sz.scale if (hl or base) else 1.5 * sz.scale

        # Measure natural column widths
        data_widths = [
            max(
                (measure.width_pt(_plain(formatted[r][c], theme), sz.small) for r in range(n_rows)),
                default=14.0,
            )
            for c in range(n_cols)
        ]
        head_widths_1 = [
            measure.width_pt(_plain(header_labels[c], theme), sz.small) * 1.06
            for c in range(n_cols)
        ]

        # Decide whether to wrap headers to fit width
        need_1 = [max(data_widths[c], head_widths_1[c]) + 2 * pad_pt for c in range(n_cols)]
        need_1[0] += stripe_pad_pt
        drawn_headers = list(header_labels)
        if sum(need_1) > cell_w_pt:
            # Try wrapping multi-word headers
            for c in range(n_cols):
                target_w = max(data_widths[c], head_widths_1[c] * 0.58)
                wrapped = _wrap_header(header_labels[c], target_w, measure, sz.small)
                drawn_headers[c] = wrapped
            head_widths_2 = [
                max(
                    measure.width_pt(_plain(line, theme), sz.small) * 1.06
                    for line in drawn_headers[c].split("\n")
                )
                for c in range(n_cols)
            ]
            need = [max(data_widths[c], head_widths_2[c]) + 2 * pad_pt for c in range(n_cols)]
            need[0] += stripe_pad_pt
        else:
            need = need_1

        total_need = sum(need)
        if total_need > cell_w_pt * 1.04:
            raise ExplainError(
                f"table() needs about {total_need:.0f} pt width but this panel has {cell_w_pt:.0f} pt.",
                fix_hint="Give the table a full-width row via layout=, drop or shorten columns "
                "with columns=[...], or use a tighter fmt=.",
                rule="table_too_wide",
            )

        # Distribute any surplus width proportionally across columns (slightly favouring col 0)
        surplus = max(0.0, cell_w_pt - total_need)
        weights = [1.4 if c == 0 else 1.0 for c in range(n_cols)]
        w_sum = sum(weights)
        col_w = [need[c] + surplus * (weights[c] / w_sum) for c in range(n_cols)]
        total_w = sum(col_w)
        col_x = [0.0]
        for w in col_w:
            col_x.append(col_x[-1] + w / total_w)

        has_two_line_head = any("\n" in h for h in drawn_headers)
        head_units = 1.65 if has_two_line_head else 1.18
        total_y = head_units + n_rows

        _bare_axes(ax)
        ax.set_xticks([])
        ax.set_yticks([])
        ax.set_xlim(0.0, 1.0)
        ax.set_ylim(total_y, 0.0)

        light_ground = _relative_luminance(theme.background) > 0.5
        tint_alpha = 0.11 if light_ground else 0.18
        base_alpha = 0.06 if light_ground else 0.10

        # Row background tints + left accent stripes (Patches, never Line2D)
        stripe_w = min(0.012, 2.2 / max(total_w, 1.0))
        for r in range(n_rows):
            y0 = head_units + r
            rk = row_keys[r]
            if rk in hl:
                accent = ctx.colors.get(rk, theme.series_colors[0])
                ax.add_patch(
                    Rectangle(
                        (0.0, y0),
                        1.0,
                        1.0,
                        facecolor=accent,
                        edgecolor="none",
                        alpha=tint_alpha,
                        zorder=1,
                    )
                )
                ax.add_patch(
                    Rectangle(
                        (0.0, y0 + 0.06),
                        stripe_w,
                        0.88,
                        facecolor=accent,
                        edgecolor="none",
                        alpha=0.95,
                        zorder=2,
                    )
                )
            elif base is not None and rk == base:
                ax.add_patch(
                    Rectangle(
                        (0.0, y0),
                        1.0,
                        1.0,
                        facecolor=theme.ink,
                        edgecolor="none",
                        alpha=base_alpha,
                        zorder=1,
                    )
                )
                ax.add_patch(
                    Rectangle(
                        (0.0, y0 + 0.06),
                        stripe_w,
                        0.88,
                        facecolor=theme.ink,
                        edgecolor="none",
                        alpha=0.85,
                        zorder=2,
                    )
                )

        # Booktabs horizontal rules via hlines (LineCollection -> never trips struck-by-line)
        ax.hlines(0.02, 0.0, 1.0, color=theme.ink, linewidth=0.9 * sz.scale, zorder=3)
        ax.hlines(head_units, 0.0, 1.0, color=theme.ink, linewidth=0.8 * sz.scale, zorder=3)
        if n_rows > 1:
            inner_ys = [head_units + r for r in range(1, n_rows)]
            ax.hlines(inner_ys, 0.0, 1.0, color=theme.grid, linewidth=0.45 * sz.scale, zorder=2)
        ax.hlines(total_y - 0.02, 0.0, 1.0, color=theme.ink, linewidth=0.9 * sz.scale, zorder=3)

        # Column header text
        pad_frac = pad_pt / max(total_w, 1.0)
        stripe_frac = stripe_pad_pt / max(total_w, 1.0)
        for c in range(n_cols):
            al = col_align[c]
            left_x = col_x[c] + (stripe_frac if c == 0 else 0.0) + pad_frac
            right_x = col_x[c + 1] - pad_frac
            if al == "right":
                tx, ha = right_x, "right"
            elif al == "center":
                tx, ha = 0.5 * (left_x + right_x), "center"
            else:
                tx, ha = left_x, "left"
            t = ax.text(
                tx,
                head_units * 0.52,
                _plain(drawn_headers[c], theme),
                ha=ha,
                va="center",
                fontsize=sz.small,
                fontweight="bold",
                color=theme.ink,
                zorder=4,
            )
            t._figmint_heatmap_text = True  # type: ignore[attr-defined]

        # Data cell text
        for r in range(n_rows):
            yc = head_units + r + 0.5
            rk = row_keys[r]
            is_hl = rk in hl
            is_base = base is not None and rk == base
            for c in range(n_cols):
                al = col_align[c]
                left_x = col_x[c] + (stripe_frac if c == 0 else 0.0) + pad_frac
                right_x = col_x[c + 1] - pad_frac
                if al == "right":
                    tx, ha = right_x, "right"
                elif al == "center":
                    tx, ha = 0.5 * (left_x + right_x), "center"
                else:
                    tx, ha = left_x, "left"

                cell_str = formatted[r][c]
                is_dash = cell_str == "\N{EM DASH}"
                is_winner = (r, c) in best_cells
                weight = "bold" if (is_winner or (c == 0 and (is_hl or is_base))) else "normal"
                color = theme.muted if is_dash else theme.ink
                t = ax.text(
                    tx,
                    yc,
                    _plain(cell_str, theme),
                    ha=ha,
                    va="center",
                    fontsize=sz.small,
                    fontweight=weight,
                    color=color,
                    zorder=4,
                )
                t._figmint_heatmap_text = True  # type: ignore[attr-defined]
        return None

    spec: dict[str, Any] = {
        "rows": [_jsonable(r) for r in raw_rows],
        "columns": list(col_names),
        "title": title,
        "label": label,
        "unit": unit,
        "units": dict(unit_map) if unit_map else None,
        "highlight": hl or None,
        "baseline": base,
        "bold_best": bold_best if bold_best else None,
        "align": dict(align) if align else None,
        "fmt": fmt,
    }
    describe = f"Table of {n_rows} rows across {', '.join(col_names)}"
    panel = Panel(
        kind="table",
        title=title,
        label=label,
        unit=unit,
        spec=spec,
        facts=facts,
        describe=describe,
        _height_mm=_height_mm,
        _min_height_mm=_min_height_mm,
        _draw=_draw,
        color_items=tuple(row_keys),
        color_focus=tuple(hl),
        color_mode="highlight" if hl else "none",
        color_baseline=base,
        alt_facts=facts[: min(4, len(facts))],
    )
    panel._markdown = markdown_text  # type: ignore[attr-defined]
    return panel
