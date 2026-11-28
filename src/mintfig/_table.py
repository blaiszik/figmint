"""Structured booktabs-style table form (``mint.table``) for exact lookups and scorecards.

Designed as an independent module so ``explainer.py`` stays modular. Obeys the
same contract as every other ``mint.explain`` form: declarative spec, computed
``facts``, shared entity colours across panels, theme/palette support, and
strict layout/legibility verification.
"""

from __future__ import annotations

import math
import numbers
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

from matplotlib.collections import LineCollection
from matplotlib.patches import Rectangle

from ._tabular import extract_table_data

if TYPE_CHECKING:
    from matplotlib.axes import Axes

    from .explainer import Panel, _Ctx, _Measure, _Sizes
    from .themes import Theme

MAX_TABLE_ROWS = 20
MAX_TABLE_COLS = 8
#: In-cell graphic width (pt at scale 1): the least that still reads, and the most it grows to.
_GRAPHIC_MIN_PT = 16.0
_GRAPHIC_PREF_PT = 44.0
#: Gap between a cell's number and its graphic (pt at scale 1).
_GRAPHIC_GAP_PT = 4.0


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
    bars: str | Sequence[str] | None = None,
    interval: Mapping[str, Any] | None = None,
    interval_label: str | None = None,
    spark: Mapping[str, Mapping[str, Sequence[Any]]] | None = None,
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

    Table-graphics (each drawn in the cell beside its number, on one scale per column):

    - ``bars`` names numeric columns that gain a thin bar from zero (both ways when
      the column has negative values).
    - ``interval`` adds a dot-and-whisker: ``{col: {row: (lo, hi)}}``, or
      ``{col: ("lo_col", "hi_col")}`` naming two columns of ``rows`` (then not shown
      as columns). Say what the interval is with ``interval_label=`` ("95% CI").
    - ``spark`` adds sparklines on one shared y range: ``{title: {row: [values]}}``.
      A new title adds a column with the last value beside each line; an existing
      column name draws the sparkline beside that column's number.
    """
    from ._explain.core import (
        _LINE,
        PT_TO_MM,
        ExplainError,
        Panel,
        _bare_axes,
        _baseline_name,
        _diff_with_unit,
        _formatter,
        _interval_issue,
        _is_strict,
        _jsonable,
        _names,
        _plain,
        _range_with_unit,
        _record_adjustment,
        _text_color,
        _with_unit,
    )
    from ._explain.marks import tag

    def _line_mm(pt: float) -> float:
        return pt * _LINE * PT_TO_MM

    all_cols, full_rows = extract_table_data(rows, columns=columns)
    if not all_cols:
        raise ExplainError("table() has no columns.", fix_hint="Pass at least one column.")
    if not full_rows:
        raise ExplainError("table() has no rows.", fix_hint="Pass at least one row.")

    def _cols_hint(cols: Sequence[str]) -> str:
        return f"Use column names from: {', '.join(map(repr, cols))}."

    # Table-graphics arguments: parse their shape first (interval column pairs are hidden).
    iv_spec: dict[str, Any] = {}
    hidden: list[str] = []
    if interval is not None:
        if not isinstance(interval, Mapping) or not interval:
            raise ExplainError(
                "table(interval) must map a column name to its intervals.",
                fix_hint='e.g. interval={"Acc": {"Alpha": (0.71, 0.77)}} or '
                'interval={"Acc": ("Acc lo", "Acc hi")}.',
            )
        for k, v in interval.items():
            ks = str(k)
            if ks not in all_cols:
                raise ExplainError(
                    f"table(interval) names unknown column {ks!r}.", fix_hint=_cols_hint(all_cols[1:])
                )
            if isinstance(v, Mapping):
                iv_spec[ks] = dict(v)
            elif (
                isinstance(v, Sequence)
                and not isinstance(v, (str, bytes))
                and len(v) == 2
                and all(isinstance(x, str) for x in v)
            ):
                pair = (str(v[0]), str(v[1]))
                for nm in pair:
                    if nm not in all_cols or nm in (all_cols[0], ks) or pair[0] == pair[1]:
                        raise ExplainError(
                            f"table(interval[{ks!r}]) names {nm!r} as a bound column.",
                            fix_hint="Name two other columns of rows (low, high). "
                            + _cols_hint([c for c in all_cols[1:] if c != ks]),
                        )
                iv_spec[ks] = pair
                hidden.extend(nm for nm in pair if nm not in hidden)
            else:
                raise ExplainError(
                    f"table(interval[{ks!r}]) must be {{row: (lo, hi)}} or a pair of column names.",
                    fix_hint=f'e.g. interval={{"{ks}": ("{ks} lo", "{ks} hi")}}.',
                )
        clash = [c for c in iv_spec if c in hidden]
        if clash:
            raise ExplainError(
                f"table(interval) uses column {clash[0]!r} both as a value and as a bound.",
                fix_hint="Give each interval its own two bound columns.",
            )

    spark_spec: dict[str, dict[str, list[float | None]]] = {}
    if spark is not None:
        if not isinstance(spark, Mapping) or not spark:
            raise ExplainError(
                "table(spark) must map a column title to {row: [values]}.",
                fix_hint='e.g. spark={"Trend": {"Alpha": [0.61, 0.70, 0.74]}}.',
            )
        for t, series in spark.items():
            ts = str(t)
            if ts == all_cols[0] or ts in hidden:
                raise ExplainError(
                    f"table(spark) cannot draw in column {ts!r}.",
                    fix_hint="Use a new column title, or a numeric column that is shown.",
                )
            if not isinstance(series, Mapping) or not series:
                raise ExplainError(
                    f"table(spark[{ts!r}]) must map row names to lists of values.",
                    fix_hint=f'e.g. spark={{"{ts}": {{"Alpha": [0.61, 0.70, 0.74]}}}}.',
                )
            parsed: dict[str, list[float | None]] = {}
            for rn, vals in series.items():
                if isinstance(vals, (str, bytes)) or not isinstance(vals, Sequence):
                    raise ExplainError(
                        f"table(spark[{ts!r}][{rn!r}]) must be a list of numbers.",
                        fix_hint="Pass the series as a list, e.g. [0.61, 0.70, 0.74].",
                    )
                if any(not _is_missing(x) and _as_float_or_none(x) is None for x in vals):
                    raise ExplainError(
                        f"table(spark[{ts!r}][{rn!r}]) has a value that is not a number.",
                        fix_hint="Use numbers, with None for a gap.",
                    )
                pv = [_as_float_or_none(x) for x in vals]
                if sum(x is not None for x in pv) < 2:
                    raise ExplainError(
                        f"table(spark[{ts!r}][{rn!r}]) needs at least two numbers.",
                        fix_hint="A sparkline shows a change: pass two or more values per row.",
                    )
                parsed[str(rn)] = pv
            spark_spec[ts] = parsed

    if bars is None:
        bar_cols: list[str] = []
    elif isinstance(bars, str):
        bar_cols = [bars]
    elif isinstance(bars, Sequence):
        bar_cols = [str(b) for b in bars]
    else:
        raise ExplainError(
            "table(bars) must be a column name or a list of column names.",
            fix_hint=f'e.g. bars="{all_cols[-1]}".',
        )

    # Column limit: shown columns plus new sparkline columns
    visible = [c for c in all_cols if c not in hidden]
    new_spark = [t for t in spark_spec if t not in visible]
    n_shown = len(visible) + len(new_spark)
    if n_shown > MAX_TABLE_COLS:
        if not _is_strict():
            keep = max(1, MAX_TABLE_COLS - len(new_spark))
            visible = visible[:keep]
            new_spark = new_spark[: MAX_TABLE_COLS - len(visible)]
            spark_spec = {t: s for t, s in spark_spec.items() if t in visible or t in new_spark}
            bar_cols = [b for b in bar_cols if b in visible or b not in all_cols]
            iv_spec = {k: v for k, v in iv_spec.items() if k in visible}
            hidden = [nm for v in iv_spec.values() if isinstance(v, tuple) for nm in v]
            _record_adjustment(f"table(): trimmed {n_shown} columns to first {MAX_TABLE_COLS}")
        else:
            raise ExplainError(
                f"table() shows {n_shown} columns (sparkline columns count); beyond "
                f"{MAX_TABLE_COLS} columns a chat table becomes unreadable.",
                fix_hint=f"Keep at most {MAX_TABLE_COLS} columns via columns=[...], or split into two tables.",
                rule="too_many_items",
            )
    spec_cols = [c for c in all_cols if c in visible or c in hidden]
    col_names = all_cols
    raw_rows = full_rows

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
            if ks not in col_names and ks not in spark_spec:
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
            if ks not in col_names and ks not in spark_spec:
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
    untrimmed_keys = set(row_keys)

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

    # Rows keep every column for the spec; the drawn table shows the visible ones.
    full_rows = raw_rows
    spec_rows = [[r[all_cols.index(c)] for c in spec_cols] for r in full_rows]
    col_names = list(visible)
    raw_rows = [[r[all_cols.index(c)] for c in visible] for r in full_rows]

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

    # Table-graphics: check names against the shown columns and rows.
    numeric_names = [col_names[c] for c in range(1, n_cols) if col_numeric[c]]

    def _numeric_col(name: str, arg: str) -> int:
        c = col_names.index(name) if name in col_names else -1
        if c <= 0 or not col_numeric[c]:
            raise ExplainError(
                f"table({arg}) names {name!r}, which is not a numeric column of the table.",
                fix_hint="Use a numeric column from: "
                + (", ".join(map(repr, numeric_names)) or "(none)")
                + ".",
            )
        return c

    def _known_row(name: str, arg: str) -> int | None:
        if name in row_keys:
            return row_keys.index(name)
        if name in untrimmed_keys:
            return None  # its row was trimmed (lenient mode)
        raise ExplainError(
            f"table({arg}) names unknown row {name!r}.",
            fix_hint=f"Use row names from: {', '.join(map(repr, row_keys))}.",
        )

    gfx_kind: dict[int, str] = {}

    def _claim_col(c: int, kind: str) -> None:
        if c in gfx_kind:
            raise ExplainError(
                f"table() column {col_names[c]!r} gets both {gfx_kind[c]}= and {kind}=.",
                fix_hint="Give each column one graphic: bars=, interval= or spark=.",
            )
        gfx_kind[c] = kind

    for b in bar_cols:
        _claim_col(_numeric_col(b, "bars"), "bars")

    iv_bounds: dict[int, list[tuple[float, float] | None]] = {}
    for cname, how in iv_spec.items():
        c = _numeric_col(cname, "interval")
        _claim_col(c, "interval")
        given: list[tuple[int, Any, Any]] = []
        if isinstance(how, tuple):
            lo_i, hi_i = all_cols.index(how[0]), all_cols.index(how[1])
            given = [(r, full_rows[r][lo_i], full_rows[r][hi_i]) for r in range(n_rows)]
        else:
            for rn, pair in how.items():
                r_idx = _known_row(str(rn), f"interval[{cname!r}]")
                if r_idx is None:
                    continue
                if (
                    isinstance(pair, (str, bytes))
                    or not isinstance(pair, Sequence)
                    or len(pair) != 2
                    or any(_as_float_or_none(x) is None for x in pair)
                ):
                    raise ExplainError(
                        f"table(interval[{cname!r}][{rn!r}]) must be two numbers (low, high).",
                        fix_hint="e.g. (0.71, 0.77).",
                    )
                given.append((r_idx, pair[0], pair[1]))
        bounds: list[tuple[float, float] | None] = [None] * n_rows
        for r, lo_raw, hi_raw in given:
            lo_v, hi_v = _as_float_or_none(lo_raw), _as_float_or_none(hi_raw)
            if lo_v is None or hi_v is None or col_floats[c][r] is None:
                continue
            if lo_v > hi_v:
                raise ExplainError(
                    f"table(interval[{cname!r}]) for row {row_keys[r]!r} has its low bound "
                    f"{lo_v:g} above its high bound {hi_v:g}.",
                    fix_hint="Give each interval as (low, high).",
                )
            bounds[r] = (lo_v, hi_v)
        iv_bounds[c] = bounds

    spark_rows: dict[str, list[list[float | None] | None]] = {}
    for sp_title, series in spark_spec.items():
        per_row: list[list[float | None] | None] = [None] * n_rows
        for rn, vals in series.items():
            r_idx = _known_row(rn, f"spark[{sp_title!r}]")
            if r_idx is not None:
                per_row[r_idx] = vals
        spark_rows[sp_title] = per_row
        if sp_title in col_names:
            _claim_col(_numeric_col(sp_title, "spark"), "spark")

    panel_issues: list[dict[str, Any]] = []
    if iv_bounds and not interval_label:
        panel_issues.append(_interval_issue("table", "interval", "interval_label"))

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
            finite_vals += [b for pair in iv_bounds.get(c, []) if pair for b in pair]
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

    # In-cell graphics by drawn column; a new sparkline title adds a column at the end.
    graphics: dict[int, dict[str, Any]] = {}
    for c, kind in gfx_kind.items():
        vals_c = col_floats[c]
        finite_c = [v for v in vals_c if v is not None]
        if kind == "bars":
            graphics[c] = {"kind": "bars", "values": vals_c, "lead": True,
                           "lo": min(0.0, *finite_c), "hi": max(0.0, *finite_c)}
        elif kind == "interval":
            ends = finite_c + [b for pair in iv_bounds[c] if pair for b in pair]
            fmt_fn = col_formatters[c]
            graphics[c] = {
                "kind": "interval", "values": vals_c, "lead": True, "bounds": iv_bounds[c],
                "lo": min(ends), "hi": max(ends), "label": interval_label,
                "bounds_text": [
                    _range_with_unit(fmt_fn(p[0]), fmt_fn(p[1]), None) if p else None
                    for p in iv_bounds[c]
                ],
            }
    for sp_title, per_row in spark_rows.items():
        every = [v for s in per_row if s for v in s if v is not None]
        lasts = [next((v for v in reversed(s) if v is not None), None) if s else None for s in per_row]
        if sp_title in col_names:
            c = col_names.index(sp_title)
        else:
            c = len(header_labels)
            u = unit_map.get(sp_title)
            header_labels.append(f"{sp_title} ({u})" if u and f"({u})" not in sp_title else sp_title)
            col_align.append("right")
            last_fmt = _formatter(
                [v for v in lasts if v is not None], fmt_map.get(sp_title, global_fmt), unit=u
            )
            for r in range(n_rows):
                if lasts[r] is None:
                    formatted[r].append("\N{EM DASH}")
                    missing_count += 1
                else:
                    formatted[r].append(last_fmt(lasts[r]))
        graphics[c] = {"kind": "spark", "series": per_row, "values": lasts,
                       "lead": c < n_cols, "lo": min(every), "hi": max(every)}
    n_all = len(header_labels)
    col_title = [*col_names, *(t for t in spark_rows if t not in col_names)]

    # Compute facts
    facts: list[str] = [f"{n_rows} rows \N{MULTIPLICATION SIGN} {n_all} columns"]
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
                if u and u.strip().startswith("%"):  # a difference of percents is in points
                    dtxt = _diff_with_unit(f"{sign}{fmt_fn(abs(diff))}", u)
                else:
                    dtxt = sign + _cell_with_unit(fmt_fn(abs(diff)), u)
                facts.append(f"{cname}: {row_keys[tr]} vs {base} is {dtxt}")
    for c, bounds in iv_bounds.items():
        rated = [(r, col_floats[c][r]) for r in range(n_rows) if bounds[r] is not None]
        if len(rated) < 2:
            continue
        pick = min if best_dir.get(c) == "min" else max
        best_r = pick(rated, key=lambda kv: kv[1])[0]  # type: ignore[arg-type,return-value]
        b_lo, b_hi = bounds[best_r]  # type: ignore[misc]
        over = [
            row_keys[r] for r, _ in rated
            if r != best_r and bounds[r][0] <= b_hi and bounds[r][1] >= b_lo  # type: ignore[index]
        ]
        cname = col_names[c]
        if over:
            noun, verb = ("interval", "overlaps") if len(over) == 1 else ("intervals", "overlap")
            facts.append(
                f"{cname}: the {noun} of {', '.join(over)} {verb} that of the best row, "
                f"{row_keys[best_r]}"
            )
        else:
            facts.append(f"{cname}: no interval overlaps that of the best row, {row_keys[best_r]}")
    if missing_count:
        facts.append(f"{missing_count} empty cell(s) shown as \N{EM DASH}")

    md_rows = [list(row) for row in formatted]
    for c, g in graphics.items():
        if g["kind"] == "interval":
            for r, txt in enumerate(g["bounds_text"]):
                if txt:
                    md_rows[r][c] = f"{formatted[r][c]} ({txt})"
    markdown_text = _format_cell_markdown(header_labels, col_align, md_rows)

    # Height computation: proportional to row count + header height
    def _height_mm(cell_w_mm: float, measure: _Measure, sizes: _Sizes, theme: Theme) -> float:
        row_h = max(_line_mm(sizes.small) * 1.48, 5.2 * sizes.scale)
        # Estimate whether any header wraps to 2 lines
        head_lines = 1
        est_col_pt = (cell_w_mm / PT_TO_MM) / max(n_all, 1)
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
        gap_pt = _GRAPHIC_GAP_PT * sz.scale
        g_min = _GRAPHIC_MIN_PT * sz.scale
        g_pref = _GRAPHIC_PREF_PT * sz.scale

        # Measure natural column widths (a graphic column also needs its graphic)
        data_widths = [
            max(
                (measure.width_pt(_plain(formatted[r][c], theme), sz.small) for r in range(n_rows)),
                default=14.0,
            )
            for c in range(n_all)
        ]
        body_widths = [
            data_widths[c] + (gap_pt + g_min if c in graphics else 0.0) for c in range(n_all)
        ]
        head_widths_1 = [
            measure.width_pt(_plain(header_labels[c], theme), sz.small) * 1.06
            for c in range(n_all)
        ]

        # Decide whether to wrap headers to fit width
        need_1 = [max(body_widths[c], head_widths_1[c]) + 2 * pad_pt for c in range(n_all)]
        need_1[0] += stripe_pad_pt
        drawn_headers = list(header_labels)
        if sum(need_1) > cell_w_pt:
            # Try wrapping multi-word headers
            for c in range(n_all):
                target_w = max(body_widths[c], head_widths_1[c] * 0.58)
                wrapped = _wrap_header(header_labels[c], target_w, measure, sz.small)
                drawn_headers[c] = wrapped
            head_widths_2 = [
                max(
                    measure.width_pt(_plain(line, theme), sz.small) * 1.06
                    for line in drawn_headers[c].split("\n")
                )
                for c in range(n_all)
            ]
            need = [max(body_widths[c], head_widths_2[c]) + 2 * pad_pt for c in range(n_all)]
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

        # Surplus width first lets each graphic grow to its preferred width, then is
        # shared proportionally across columns (slightly favouring col 0)
        surplus = max(0.0, cell_w_pt - total_need)
        col_w = list(need)
        grow = {c: max(0.0, data_widths[c] + gap_pt + g_pref + 2 * pad_pt - need[c]) for c in graphics}
        want = sum(grow.values())
        if want > 0:
            share = min(1.0, surplus / want)
            for c, extra in grow.items():
                col_w[c] += extra * share
            surplus -= want * share
        weights = [1.4 if c == 0 else 1.0 for c in range(n_all)]
        w_sum = sum(weights)
        col_w = [col_w[c] + surplus * (weights[c] / w_sum) for c in range(n_all)]
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

        # Crisp left accent stripes only (no muddy full-row background washes so the
        # booktabs surface stays airy and in-cell graphics / entity text carry the colour).
        stripe_w = min(0.009, 1.8 / max(total_w, 1.0))
        for r in range(n_rows):
            y0 = head_units + r
            rk = row_keys[r]
            if rk in hl:
                accent = ctx.colors.get(rk, theme.series_colors[0])
                ax.add_patch(
                    Rectangle(
                        (0.0, y0 + 0.14),
                        stripe_w,
                        0.72,
                        facecolor=accent,
                        edgecolor="none",
                        alpha=0.95,
                        zorder=2,
                    )
                )
            elif base is not None and rk == base:
                ax.add_patch(
                    Rectangle(
                        (0.0, y0 + 0.14),
                        stripe_w,
                        0.72,
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

        pad_frac = pad_pt / max(total_w, 1.0)
        stripe_frac = stripe_pad_pt / max(total_w, 1.0)
        gap_frac = gap_pt / max(total_w, 1.0)

        def _span(c: int) -> tuple[float, float]:
            return col_x[c] + (stripe_frac if c == 0 else 0.0) + pad_frac, col_x[c + 1] - pad_frac

        # Where each graphic column puts its number (right edge) and its graphic.
        text_right: dict[int, float] = {}
        g_span: dict[int, tuple[float, float]] = {}
        for c, g in graphics.items():
            left_x, right_x = _span(c)
            dw = data_widths[c] / max(total_w, 1.0)
            if g["lead"]:
                text_right[c] = left_x + dw
                g_span[c] = (left_x + dw + gap_frac, right_x)
            else:
                text_right[c] = right_x
                g_span[c] = (left_x, right_x - dw - gap_frac)

        # Column header text
        for c in range(n_all):
            al = "left" if c in graphics else col_align[c]
            left_x, right_x = _span(c)
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
            t._mintfig_heatmap_text = True  # type: ignore[attr-defined]

        def _unit_of(c: int) -> str | None:
            if c >= n_cols:
                return unit_map.get(col_title[c])
            return unit_map.get(col_names[c]) or (unit if col_numeric[c] and not unit_map else None)

        def _record(r: int, c: int) -> dict[str, Any]:
            g = graphics.get(c)
            if c >= n_cols:
                value: Any = g["values"][r] if g else None
            else:
                value = col_floats[c][r] if col_numeric[c] else raw_rows[r][c]
            rec: dict[str, Any] = {"name": row_keys[r], "x": col_title[c], "unit": _unit_of(c),
                                   "value": value}
            if g and g["kind"] == "interval" and g["bounds"][r]:
                rec["lo"], rec["hi"] = g["bounds"][r]
            return rec

        # Data cell text
        for r in range(n_rows):
            yc = head_units + r + 0.5
            rk = row_keys[r]
            is_hl = rk in hl
            is_base = base is not None and rk == base
            for c in range(n_all):
                al = col_align[c]
                left_x, right_x = _span(c)
                if c in graphics:
                    tx, ha = text_right[c], "right"
                elif al == "right":
                    tx, ha = right_x, "right"
                elif al == "center":
                    tx, ha = 0.5 * (left_x + right_x), "center"
                else:
                    tx, ha = left_x, "left"

                cell_str = formatted[r][c]
                is_dash = cell_str == "\N{EM DASH}"
                is_winner = (r, c) in best_cells
                weight = "bold" if (is_winner or (c == 0 and (is_hl or is_base))) else "normal"
                if is_dash:
                    color = theme.muted
                elif c == 0 and is_hl:
                    accent = ctx.colors.get(rk, theme.series_colors[0])
                    color = _text_color(accent, background=theme.background, ink=theme.ink)
                else:
                    color = theme.ink
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
                t._mintfig_heatmap_text = True  # type: ignore[attr-defined]
                if c > 0 and not is_dash:
                    tag(ctx, t, **_record(r, c))

        # In-cell graphics, one scale per column
        def _row_color(rk: str, other: str) -> str:
            if rk in hl:
                return ctx.colors.get(rk, theme.series_colors[0])
            if base is not None and rk == base:
                return ctx.colors.get(rk, theme.ink)
            return other

        lw = 0.9 * sz.scale
        for c, g in graphics.items():
            g0, g1 = g_span[c]
            lo, hi = float(g["lo"]), float(g["hi"])
            if g["kind"] == "bars":
                if hi <= lo:
                    continue
                def _bx(v: float, g0: float = g0, g1: float = g1, lo: float = lo, hi: float = hi) -> float:
                    return g0 + (v - lo) / (hi - lo) * (g1 - g0)
                if lo < 0:
                    ax.vlines(_bx(0.0), head_units + 0.12, total_y - 0.12, color=theme.zero_line,
                              linewidth=theme.zero_line_lw * sz.scale, zorder=3)
                for r, v in enumerate(g["values"]):
                    if v is None or v == 0:
                        continue
                    x0, x1 = sorted((_bx(0.0), _bx(v)))
                    bar = ax.add_patch(
                        Rectangle(
                            (x0, head_units + r + 0.32), x1 - x0, 0.36,
                            facecolor=_row_color(row_keys[r], theme.context_fill),
                            edgecolor="none", zorder=3,
                        )
                    )
                    tag(ctx, bar, quiet=True, **_record(r, c))
            elif g["kind"] == "interval":
                pad = 0.06 * (hi - lo) or abs(hi) * 0.05 or 1.0
                lo, hi = lo - pad, hi + pad
                def _ix(v: float, g0: float = g0, g1: float = g1, lo: float = lo, hi: float = hi) -> float:
                    return g0 + (v - lo) / (hi - lo) * (g1 - g0)
                for r, v in enumerate(g["values"]):
                    if v is None:
                        continue
                    yc = head_units + r + 0.5
                    col = _row_color(row_keys[r], theme.axis)
                    if g["bounds"][r]:
                        b0, b1 = (_ix(b) for b in g["bounds"][r])
                        whisker = ax.hlines(yc, b0, b1, color=col, linewidth=lw, zorder=3)
                        ax.vlines([b0, b1], yc - 0.16, yc + 0.16, color=col, linewidth=lw, zorder=3)
                        tag(ctx, whisker, quiet=True, **_record(r, c))
                    dot = ax.scatter([_ix(v)], [yc], s=(3.8 * sz.scale) ** 2, color=col,
                                     edgecolor=theme.background, linewidth=0.6, zorder=3.5)
                    tag(ctx, dot, quiet=True, **_record(r, c))
            else:
                end_r = 2.6 * sz.scale / max(total_w, 1.0)  # room for the end dot
                g1 -= end_r
                for r, series in enumerate(g["series"]):
                    if not series:
                        continue
                    yc = head_units + r + 0.5
                    step = (g1 - g0) / max(len(series) - 1, 1)
                    segs: list[list[tuple[float, float]]] = [[]]
                    for i, v in enumerate(series):
                        if v is None:
                            segs.append([])
                            continue
                        y = yc + 0.3 - ((v - lo) / (hi - lo) * 0.6 if hi > lo else 0.3)
                        segs[-1].append((g0 + i * step, y))
                    end = next(s[-1] for s in reversed(segs) if s)
                    col = _row_color(row_keys[r], theme.context_line)
                    line = ax.add_collection(
                        LineCollection([s for s in segs if len(s) > 1], colors=col, linewidths=lw,
                                       capstyle="round", joinstyle="round", zorder=3)
                    )
                    tag(ctx, line, quiet=True, **_record(r, c))
                    dot = ax.scatter([end[0]], [end[1]], s=(3.4 * sz.scale) ** 2,
                                     color=col, edgecolor="none", zorder=3.5)
                    tag(ctx, dot, quiet=True, **_record(r, c))
        return None

    spec: dict[str, Any] = {
        "rows": [_jsonable(r) for r in spec_rows],
        "columns": list(spec_cols),
        "title": title,
        "label": label,
        "unit": unit,
        "units": dict(unit_map) if unit_map else None,
        "highlight": hl or None,
        "baseline": base,
        "bold_best": bold_best if bold_best else None,
        "align": dict(align) if align else None,
        "fmt": fmt,
        "bars": list(bar_cols) or None,
        "interval": _jsonable(iv_spec) or None,
        "interval_label": interval_label if iv_spec else None,
        "spark": _jsonable(spark_spec) or None,
    }
    describe = f"Table of {n_rows} rows across {', '.join(col_title)}"
    drawn = [
        f"{word} in {', '.join(col_title[c] for c, g in graphics.items() if g['kind'] == kind)}"
        for kind, word in (("bars", "bars"), ("interval", "intervals"), ("spark", "sparklines"))
        if any(g["kind"] == kind for g in graphics.values())
    ]
    if drawn:
        describe += "; in-cell " + "; ".join(drawn)
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
        issues=panel_issues,
        measure_note=f"intervals: {interval_label}" if iv_bounds and interval_label else None,
    )
    panel._markdown = markdown_text  # type: ignore[attr-defined]
    # What the text and HTML surfaces need to draw the same cells on the same scales.
    panel._table_view = {  # type: ignore[attr-defined]
        "headers": list(header_labels),
        "aligns": list(col_align),
        "cells": [list(row) for row in formatted],
        "row_keys": list(row_keys),
        "highlight": list(hl),
        "graphics": graphics,
        "interval_label": interval_label,
    }
    return panel
