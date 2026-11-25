"""Tidy / row-shaped tabular data adapters for mintfig.explain forms.

Supports both standard-library row lists (``list[dict]``, e.g. from
``csv.DictReader`` or ``json.loads``) and duck-typed ``pandas.DataFrame``
objects without importing pandas.
"""

from __future__ import annotations

import difflib
import math
import numbers
from collections.abc import Mapping, Sequence
from typing import Any


def _is_number(value: object) -> bool:
    return isinstance(value, (numbers.Real,)) and not isinstance(value, bool)


def _looks_numeric(value: object) -> bool:
    if value is None or isinstance(value, bool):
        return False
    if _is_number(value):
        return True
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return False
        try:
            float(text)
        except ValueError:
            return False
        return True
    return False


def is_dataframe(obj: object) -> bool:
    """True for a pandas-like 2-D DataFrame (duck-typed, no pandas import)."""
    return (
        not isinstance(obj, (str, bytes, Mapping))
        and hasattr(obj, "columns")
        and hasattr(obj, "index")
        and hasattr(obj, "iloc")
    )


def is_row_records(obj: object) -> bool:
    """True for a non-empty sequence of row mappings (``[{"col": val}, ...]``)."""
    return (
        isinstance(obj, Sequence)
        and not isinstance(obj, (str, bytes))
        and len(obj) > 0
        and isinstance(obj[0], Mapping)
    )


def is_tabular(obj: object) -> bool:
    """True when ``obj`` is either a DataFrame or a non-empty list of row dicts."""
    return is_dataframe(obj) or is_row_records(obj)


def _col_hint(name: str, columns: Sequence[str]) -> str:
    close = difflib.get_close_matches(name, list(columns), n=1, cutoff=0.5)
    hint = f" Did you mean {close[0]!r}?" if close else ""
    shown = ", ".join(repr(c) for c in columns[:10])
    extra = f" (+{len(columns) - 10} more)" if len(columns) > 10 else ""
    return f"Available columns: {shown}{extra}.{hint}"


def extract_records(
    obj: object,
    *,
    what: str,
    include_named_index: bool = False,
) -> tuple[list[str], list[dict[str, Any]]]:
    """Normalize a DataFrame or ``list[dict]`` into ``(columns, rows)``.

    Raises :class:`mintfig.explainer.ExplainError` on malformed inputs.
    """
    from ._explain.core import ExplainError

    if is_dataframe(obj):
        cols = [str(c) for c in obj.columns]  # type: ignore[attr-defined]
        raw_rows = obj.to_dict(orient="records")  # type: ignore[attr-defined]
        rows = [{str(k): v for k, v in row.items()} for row in raw_rows]
        if include_named_index:
            idx = obj.index  # type: ignore[attr-defined]
            idx_name = getattr(idx, "name", None)
            idx_vals = list(idx)
            is_default_range = (
                idx_name is None
                and len(idx_vals) == len(rows)
                and all(isinstance(v, (int, numbers.Integral)) and int(v) == i for i, v in enumerate(idx_vals))
            )
            if not is_default_range and idx_vals:
                col_label = str(idx_name) if idx_name is not None else ""
                if col_label in cols:
                    col_label = "index"
                cols = [col_label, *cols]
                rows = [{col_label: idx_vals[i], **rows[i]} for i in range(len(rows))]
        return cols, rows

    if is_row_records(obj):
        cols_seen: list[str] = []
        col_set: set[str] = set()
        rows_out: list[dict[str, Any]] = []
        for idx, item in enumerate(obj):  # type: ignore[union-attr]
            if not isinstance(item, Mapping):
                raise ExplainError(
                    f"{what} row {idx} is {type(item).__name__}, expected a dict.",
                    fix_hint="Pass a uniform list of row dicts, e.g. [{'name': 'a', 'value': 1}, ...].",
                )
            row_dict = {str(k): v for k, v in item.items()}
            for key in row_dict:
                if key not in col_set:
                    col_set.add(key)
                    cols_seen.append(key)
            rows_out.append(row_dict)
        return cols_seen, rows_out

    raise ExplainError(
        f"{what} expected a list of row dicts or a pandas DataFrame, got {type(obj).__name__}.",
        fix_hint="Pass a list of dicts (e.g. list(csv.DictReader(f))) or a DataFrame.",
    )


def _column_is_numeric(rows: list[dict[str, Any]], col: str) -> bool:
    seen = [row.get(col) for row in rows if row.get(col) is not None]
    non_empty = [v for v in seen if not (isinstance(v, str) and not v.strip())]
    if not non_empty:
        return False
    return all(_looks_numeric(v) for v in non_empty)


def _infer_two_col_pair(
    cols: list[str], rows: list[dict[str, Any]]
) -> tuple[str, str] | None:
    """When a table has exactly 2 columns (one label, one numeric), infer ``(label_col, value_col)``."""
    if len(cols) != 2:
        return None
    num0 = _column_is_numeric(rows, cols[0])
    num1 = _column_is_numeric(rows, cols[1])
    if num1 and not num0:
        return cols[0], cols[1]
    if num0 and not num1:
        return cols[1], cols[0]
    return None


def _require_col(col: str, cols: list[str], what: str) -> str:
    from ._explain.core import ExplainError

    if col not in cols:
        raise ExplainError(
            f"{what} column {col!r} not found.",
            fix_hint=_col_hint(col, cols),
        )
    return col


def _is_missing(val: Any) -> bool:
    if val is None:
        return True
    if isinstance(val, float) and math.isnan(val):
        return True
    return bool(isinstance(val, str) and not val.strip())


def resolve_named_table(
    data: object,
    what: str,
    *,
    name: str | None = None,
    value: str | None = None,
    error: Any = None,
    n: Any = None,
    boost: Any = None,
    form: str = "compare",
) -> tuple[dict[str, Any], Any, Any, Any] | None:
    """Extract ``({name: val}, error, n, boost)`` from row records or a DataFrame.

    Returns ``None`` when ``data`` is not tabular (standard dict/Series/pairs
    handling should run instead).
    """
    from ._explain.core import ExplainError

    if not is_tabular(data):
        if name is not None or value is not None:
            raise ExplainError(
                f"{form}(name=/value=) requires row-shaped data (a list of dicts or a DataFrame), "
                f"got {type(data).__name__}.",
                fix_hint=f"Pass a list of row dicts or DataFrame to {form}(), or drop name=/value= for a dict.",
            )
        return None

    cols, rows = extract_records(data, what=what)
    if not rows:
        raise ExplainError(f"{what} is empty.", fix_hint="Pass at least one row.")

    if name is None and value is None:
        inferred = _infer_two_col_pair(cols, rows)
        if inferred is not None:
            name, value = inferred
        else:
            shown = ", ".join(repr(c) for c in cols[:8])
            raise ExplainError(
                f"{what} received row-shaped data with {len(cols)} columns ({shown}); "
                "pass name= and value= to choose which columns to plot.",
                fix_hint=(
                    f'Pass {form}(rows, name="{cols[0]}", value="{cols[-1]}") '
                    f"(columns: {shown}), or convert to a dict {{name: number}}."
                ),
            )
    elif name is None or value is None:
        missing_arg = "name=" if name is None else "value="
        raise ExplainError(
            f"{what} needs both name= and value= when reading row-shaped data (missing {missing_arg}).",
            fix_hint=_col_hint(name or value or "", cols),
        )

    _require_col(name, cols, f"{form}(name)")
    _require_col(value, cols, f"{form}(value)")

    out: dict[str, Any] = {}
    dups: list[str] = []
    for row in rows:
        key = str(row.get(name, ""))
        if key in out:
            dups.append(key)
        out[key] = row.get(value)
    if dups:
        raise ExplainError(
            f"{what} has duplicate {name!r} values ({dups[:4]!r}); {form}() needs one value per item.",
            fix_hint=(
                "Aggregate duplicates first (e.g. mean per item), pass group= for a grouped comparison, "
                f'or pass raw observations to mint.distribution(rows, group="{name}", value="{value}").'
            ),
        )

    resolved_error = error
    if isinstance(error, str) and error in cols:
        resolved_error = {str(row.get(name, "")): row.get(error) for row in rows}
    elif (
        isinstance(error, (tuple, list))
        and len(error) == 2
        and all(isinstance(c, str) for c in error)
        and all(c in cols for c in error)
    ):
        lo_col, hi_col = str(error[0]), str(error[1])
        resolved_error = {
            str(row.get(name, "")): (row.get(lo_col), row.get(hi_col)) for row in rows
        }

    resolved_n = n
    if isinstance(n, str) and n in cols:
        resolved_n = {str(row.get(name, "")): row.get(n) for row in rows}

    resolved_boost = boost
    if isinstance(boost, str) and boost in cols:
        resolved_boost = {str(row.get(name, "")): row.get(boost) for row in rows}

    return out, resolved_error, resolved_n, resolved_boost


def resolve_grouped_compare_table(
    data: object,
    *,
    name: str | None,
    group: str,
    value: str | None,
) -> dict[str, dict[str, Any]]:
    """Pivot tidy rows into ``{item_name: {series_name: val}}`` for grouped ``compare()``."""
    from ._explain.core import ExplainError

    cols, rows = extract_records(data, what="compare(values)")
    if not rows:
        raise ExplainError("compare(values) is empty.", fix_hint="Pass at least one row.")
    if not name or not value:
        shown = ", ".join(repr(c) for c in cols[:8])
        raise ExplainError(
            f"compare(group={group!r}) also needs name= and value= (columns: {shown}).",
            fix_hint=f'Pass compare(rows, name="{cols[0]}", group="{group}", value="{cols[-1]}").',
        )
    _require_col(name, cols, "compare(name)")
    _require_col(group, cols, "compare(group)")
    _require_col(value, cols, "compare(value)")

    nested: dict[str, dict[str, Any]] = {}
    for row in rows:
        cat = str(row.get(name, ""))
        ser = str(row.get(group, ""))
        bucket = nested.setdefault(cat, {})
        if ser in bucket:
            raise ExplainError(
                f"compare() grouped table has duplicate ({cat!r}, {ser!r}).",
                fix_hint="Aggregate duplicates first (one value per item × group).",
            )
        val = row.get(value)
        bucket[ser] = None if _is_missing(val) else val
    return nested


def resolve_trend_table(
    data: object,
    *,
    x_col: Any,
    y_col: str | None,
    series_col: Any = None,
    band: Any = None,
) -> tuple[list[Any], dict[str, list[Any]] | None, dict[str, list[list[Any]]] | None, Any]:
    """Pivot long/tidy rows or a DataFrame into ``(x_vals, series, points, band)``."""
    from ._explain.core import ExplainError

    cols, rows = extract_records(data, what="trend(data)")
    if not rows:
        raise ExplainError("trend(data) is empty.", fix_hint="Pass at least one row.")
    if not isinstance(x_col, str):
        raise ExplainError(
            "When passing data= to trend(), the first argument x must be a column name.",
            fix_hint=f'e.g. mint.trend("{cols[0]}", y="{cols[-1]}", data=rows). {_col_hint("", cols)}',
        )
    if not y_col or not isinstance(y_col, str):
        raise ExplainError(
            "When passing data= to trend(), pass y= naming the numeric value column.",
            fix_hint=f'e.g. mint.trend("{x_col}", y="value", data=rows). {_col_hint("", cols)}',
        )
    _require_col(x_col, cols, "trend(x)")
    _require_col(y_col, cols, "trend(y)")
    if series_col is not None:
        if not isinstance(series_col, str):
            raise ExplainError(
                "When passing data= to trend(), series must be a column name (or None for one series).",
                fix_hint=_col_hint("", cols),
            )
        _require_col(series_col, cols, "trend(series)")

    x_vals: list[Any] = []
    x_index: dict[Any, int] = {}
    series_names: list[str] = []
    buckets: dict[str, dict[int, list[Any]]] = {}

    for row in rows:
        xv = row.get(x_col)
        if _is_missing(xv):
            continue
        if xv not in x_index:
            x_index[xv] = len(x_vals)
            x_vals.append(xv)
        xi = x_index[xv]
        sname = str(row.get(series_col, "")) if series_col is not None else ""
        if sname not in buckets:
            buckets[sname] = {}
            series_names.append(sname)
        yv = row.get(y_col)
        if not _is_missing(yv):
            buckets[sname].setdefault(xi, []).append(yv)

    if not x_vals:
        raise ExplainError(
            f"trend(data) has no non-empty values in x column {x_col!r}.",
            fix_hint="Check the x column name and ensure rows contain values.",
        )

    has_replicates = any(
        len(vals) > 1 for by_x in buckets.values() for vals in by_x.values()
    )
    n_x = len(x_vals)

    if has_replicates:
        points: dict[str, list[list[Any]]] = {}
        for sname in series_names:
            by_x = buckets[sname]
            points[sname] = [by_x.get(i, []) for i in range(n_x)]
        return x_vals, None, points, band

    series_out: dict[str, list[Any]] = {}
    for sname in series_names:
        by_x = buckets[sname]
        series_out[sname] = [by_x[i][0] if i in by_x else None for i in range(n_x)]

    resolved_band = band
    if isinstance(band, str) and band in cols:
        band_map: dict[str, list[Any]] = {s: [None] * n_x for s in series_names}
        for row in rows:
            xv = row.get(x_col)
            if xv not in x_index:
                continue
            sname = str(row.get(series_col, "")) if series_col is not None else ""
            bv = row.get(band)
            if not _is_missing(bv):
                band_map[sname][x_index[xv]] = bv
        resolved_band = band_map[""] if series_col is None else band_map
    elif (
        isinstance(band, (tuple, list))
        and len(band) == 2
        and all(isinstance(c, str) and c in cols for c in band)
    ):
        lo_col, hi_col = str(band[0]), str(band[1])
        lo_map: dict[str, list[Any]] = {s: [None] * n_x for s in series_names}
        hi_map: dict[str, list[Any]] = {s: [None] * n_x for s in series_names}
        for row in rows:
            xv = row.get(x_col)
            if xv not in x_index:
                continue
            sname = str(row.get(series_col, "")) if series_col is not None else ""
            lv, hv = row.get(lo_col), row.get(hi_col)
            if not _is_missing(lv):
                lo_map[sname][x_index[xv]] = lv
            if not _is_missing(hv):
                hi_map[sname][x_index[xv]] = hv
        if series_col is None:
            resolved_band = (lo_map[""], hi_map[""])
        else:
            resolved_band = {s: (lo_map[s], hi_map[s]) for s in series_names}

    if series_col is None:
        return x_vals, series_out[""], None, resolved_band  # type: ignore[return-value]
    return x_vals, series_out, None, resolved_band


def resolve_change_table(
    data: object,
    *,
    before_col: Any,
    after_col: Any,
    name_col: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Extract ``(before_dict, after_dict)`` from row records or a DataFrame."""
    from ._explain.core import ExplainError

    cols, rows = extract_records(data, what="change(data)")
    if not rows:
        raise ExplainError("change(data) is empty.", fix_hint="Pass at least one row.")
    if not isinstance(before_col, str) or not isinstance(after_col, str):
        raise ExplainError(
            "When passing data= to change(), before and after must be column names.",
            fix_hint=f'e.g. mint.change("before", "after", data=rows, name="item"). {_col_hint("", cols)}',
        )
    _require_col(before_col, cols, "change(before)")
    _require_col(after_col, cols, "change(after)")

    if name_col is None:
        candidates = [c for c in cols if c not in {before_col, after_col} and not _column_is_numeric(rows, c)]
        if len(candidates) == 1:
            name_col = candidates[0]
        else:
            raise ExplainError(
                "change(data=) needs name= naming the item column.",
                fix_hint=_col_hint("", cols),
            )
    else:
        _require_col(name_col, cols, "change(name)")

    left: dict[str, Any] = {}
    right: dict[str, Any] = {}
    for row in rows:
        key = str(row.get(name_col, ""))
        left[key] = row.get(before_col)
        right[key] = row.get(after_col)
    return left, right


def resolve_distribution_table(
    data: object,
    *,
    group: str | None = None,
    value: str | None = None,
    form: str = "distribution",
) -> dict[str, list[Any]] | list[Any] | None:
    """Extract ``{group: [values]}`` (or ``[values]``) from tidy rows or a DataFrame.

    Returns ``None`` when ``data`` should be handled by the standard wide/mapping path
    (including wide all-numeric DataFrames when ``group`` and ``value`` are omitted).
    """
    from ._explain.core import ExplainError

    if not is_tabular(data):
        if group is not None or value is not None:
            raise ExplainError(
                f"{form}(group=/value=) requires row-shaped data (a list of dicts or a DataFrame), "
                f"got {type(data).__name__}.",
                fix_hint=f"Pass rows/DataFrame to {form}(), or drop group=/value= for a dict.",
            )
        return None

    # Wide all-numeric DataFrame with no group=/value= -> preserve legacy wide behavior
    if is_dataframe(data) and group is None and value is None:
        cols, rows = extract_records(data, what=f"{form}(groups)")
        if not rows:
            return None
        inferred = _infer_two_col_pair(cols, rows)
        if inferred is None:
            # All columns numeric -> wide DataFrame (one column per group)
            if all(_column_is_numeric(rows, c) for c in cols):
                return None
            shown = ", ".join(repr(c) for c in cols[:8])
            raise ExplainError(
                f"{form}() got a long/mixed DataFrame with columns ({shown}); "
                "pass group= and value= to choose which columns to plot.",
                fix_hint=f'Pass {form}(df, group="...", value="..."), or a wide numeric DataFrame.',
            )
        group, value = inferred
    else:
        cols, rows = extract_records(data, what=f"{form}(groups)")
        if not rows:
            raise ExplainError(f"{form}() data is empty.", fix_hint="Pass at least 3 rows.")
        if group is None and value is None:
            inferred = _infer_two_col_pair(cols, rows)
            if inferred is not None:
                group, value = inferred
            elif len(cols) == 1 and _column_is_numeric(rows, cols[0]):
                value = cols[0]
            else:
                shown = ", ".join(repr(c) for c in cols[:8])
                raise ExplainError(
                    f"{form}() got row-shaped data with columns ({shown}); "
                    "pass value= (and optionally group=) to choose which columns to plot.",
                    fix_hint=f'Pass {form}(rows, group="{cols[0]}", value="{cols[-1]}").',
                )

    if value is None:
        raise ExplainError(
            f"{form}(group={group!r}) also needs value= naming the numeric column.",
            fix_hint=_col_hint("", cols),
        )
    _require_col(value, cols, f"{form}(value)")
    if group is None:
        return [row.get(value) for row in rows]
    _require_col(group, cols, f"{form}(group)")

    grouped: dict[str, list[Any]] = {}
    for row in rows:
        g = str(row.get(group, ""))
        grouped.setdefault(g, []).append(row.get(value))
    return grouped


def resolve_relate_table(
    data: object,
    *,
    x_col: Any,
    y_col: Any,
    names: Any = None,
    groups: Any = None,
) -> tuple[list[Any], list[Any], list[Any] | None, list[Any] | None]:
    """Extract ``(x, y, names, groups)`` columns from row records or a DataFrame."""
    from ._explain.core import ExplainError

    cols, rows = extract_records(data, what="relate(data)")
    if not rows:
        raise ExplainError("relate(data) is empty.", fix_hint="Pass at least two rows.")
    if not isinstance(x_col, str) or not isinstance(y_col, str):
        raise ExplainError(
            "When passing data= to relate(), x and y must be column names.",
            fix_hint=f'e.g. mint.relate("cost", "score", data=rows, x_label=..., y_label=...). {_col_hint("", cols)}',
        )
    _require_col(x_col, cols, "relate(x)")
    _require_col(y_col, cols, "relate(y)")
    xs = [row.get(x_col) for row in rows]
    ys = [row.get(y_col) for row in rows]

    out_names = names
    if isinstance(names, str):
        _require_col(names, cols, "relate(names)")
        out_names = [row.get(names) for row in rows]
    out_groups = groups
    if isinstance(groups, str):
        _require_col(groups, cols, "relate(groups)")
        out_groups = [row.get(groups) for row in rows]
    return xs, ys, out_names, out_groups


def resolve_matrix_table(
    data: object,
    *,
    rows_arg: Any,
    cols_arg: Any,
    value_col: str | None = None,
) -> tuple[list[list[Any]], list[str], list[str]] | None:
    """Pivot long rows/DataFrame into ``(grid_2d, row_names, col_names)`` when requested.

    Returns ``None`` when ``data`` is a normal 2-D matrix or wide DataFrame.
    """
    from ._explain.core import ExplainError

    want_pivot = (
        is_row_records(data)
        or value_col is not None
        or (is_dataframe(data) and isinstance(rows_arg, str) and isinstance(cols_arg, str))
    )
    if not want_pivot:
        return None
    if not is_tabular(data):
        raise ExplainError(
            f"matrix(value={value_col!r}) requires row-shaped data (list of dicts or DataFrame).",
            fix_hint='Pass a list of row dicts or DataFrame with rows="...", cols="...", value="...".',
        )

    cols, records = extract_records(data, what="matrix(values)")
    if not records:
        raise ExplainError("matrix(values) is empty.", fix_hint="Pass at least one row.")
    if not isinstance(rows_arg, str) or not isinstance(cols_arg, str):
        shown = ", ".join(repr(c) for c in cols[:8])
        raise ExplainError(
            f"matrix() got row-shaped data with columns ({shown}); pass rows=, cols= and value= as column names.",
            fix_hint=f'e.g. mint.matrix(records, rows="{cols[0]}", cols="{cols[min(1, len(cols) - 1)]}", value="{cols[-1]}").',
        )
    _require_col(rows_arg, cols, "matrix(rows)")
    _require_col(cols_arg, cols, "matrix(cols)")
    if value_col is None:
        remaining = [c for c in cols if c not in {rows_arg, cols_arg} and _column_is_numeric(records, c)]
        if len(remaining) == 1:
            value_col = remaining[0]
        else:
            raise ExplainError(
                "matrix() needs value= naming the numeric cell column when pivoting row-shaped data.",
                fix_hint=_col_hint("", cols),
            )
    else:
        _require_col(value_col, cols, "matrix(value)")

    row_names: list[str] = []
    col_names: list[str] = []
    cells: dict[tuple[str, str], Any] = {}
    for rec in records:
        rk = str(rec.get(rows_arg, ""))
        ck = str(rec.get(cols_arg, ""))
        if rk not in row_names:
            row_names.append(rk)
        if ck not in col_names:
            col_names.append(ck)
        if (rk, ck) in cells:
            raise ExplainError(
                f"matrix() pivot has duplicate cell ({rk!r}, {ck!r}).",
                fix_hint="Aggregate duplicates before passing to matrix().",
            )
        val = rec.get(value_col)
        cells[(rk, ck)] = None if _is_missing(val) else val

    grid = [[cells.get((r, c)) for c in col_names] for r in row_names]
    return grid, row_names, col_names


def extract_table_data(
    rows: object,
    *,
    columns: Sequence[str] | None = None,
) -> tuple[list[str], list[list[Any]]]:
    """Normalize any tabular input for :func:`mintfig.table` into ``(col_names, cell_rows)``.

    Accepts:
    - ``list[dict]`` (row records)
    - ``pandas.DataFrame`` (preserving meaningful non-RangeIndex as column 0)
    - ``dict[str, Sequence]`` (column-oriented mapping)
    - 2-D sequence of rows (with ``columns=[...]``)
    """
    from ._explain.core import ExplainError

    if is_dataframe(rows):
        cols, recs = extract_records(rows, what="table(rows)", include_named_index=True)
        if columns is not None:
            chosen = [str(c) for c in columns]
            for col in chosen:
                _require_col(col, cols, "table(columns)")
            cols = chosen
        return cols, [[rec.get(c) for c in cols] for rec in recs]

    if is_row_records(rows):
        cols, recs = extract_records(rows, what="table(rows)")
        if columns is not None:
            chosen = [str(c) for c in columns]
            for col in chosen:
                _require_col(col, cols, "table(columns)")
            cols = chosen
        return cols, [[rec.get(c) for c in cols] for rec in recs]

    if isinstance(rows, Mapping):
        if not rows:
            raise ExplainError("table(rows) is empty.", fix_hint="Pass at least one row.")
        all_cols = [str(k) for k in rows]
        lengths: list[int] = []
        col_vals: dict[str, list[Any]] = {}
        for k, v in rows.items():
            if isinstance(v, (str, bytes)) or not isinstance(v, Sequence):
                raise ExplainError(
                    f"table() column {k!r} must be a sequence of cell values, got {type(v).__name__}.",
                    fix_hint='Pass [{"col": val}, ...] or {"col": [v1, v2, ...]}.',
                )
            lst = list(v)
            lengths.append(len(lst))
            col_vals[str(k)] = lst
        if len(set(lengths)) != 1:
            raise ExplainError(
                f"table() columns have unequal lengths: {dict(zip(all_cols, lengths))}.",
                fix_hint="Every column list must have the same number of rows.",
            )
        chosen = all_cols if columns is None else [str(c) for c in columns]
        for col in chosen:
            _require_col(col, all_cols, "table(columns)")
        n_rows = lengths[0]
        return chosen, [[col_vals[c][i] for c in chosen] for i in range(n_rows)]

    if isinstance(rows, Sequence) and not isinstance(rows, (str, bytes)):
        seq = list(rows)
        if not seq:
            raise ExplainError("table(rows) is empty.", fix_hint="Pass at least one row.")
        if columns is None:
            raise ExplainError(
                "table() needs columns=[...] when rows is a 2-D list of lists.",
                fix_hint='Pass columns=["Model", "Score", ...] or pass a list of dicts [{"Model": ..., "Score": ...}].',
            )
        if isinstance(columns, (str, bytes)):
            raise ExplainError(
                "table(columns) must be a list of column names.",
                fix_hint='e.g. columns=["Model", "Score"].',
            )
        col_names = [str(c) for c in columns]
        out_rows: list[list[Any]] = []
        for idx, row in enumerate(seq):
            if isinstance(row, (str, bytes)) or not isinstance(row, Sequence):
                raise ExplainError(
                    f"table(rows[{idx}]) must be a sequence of cell values.",
                    fix_hint="Pass a 2-D list of rows or a list of dicts.",
                )
            vals = list(row)
            if len(vals) != len(col_names):
                raise ExplainError(
                    f"table(rows[{idx}]) has {len(vals)} cells but columns has {len(col_names)} names.",
                    fix_hint="Every row must match len(columns).",
                )
            out_rows.append(vals)
        return col_names, out_rows

    raise ExplainError(
        f"table(rows) expected a list of dicts, DataFrame, dict of columns, or 2-D list; got {type(rows).__name__}.",
        fix_hint='e.g. mint.table([{"Model": "A", "Score": 91.2}, {"Model": "B", "Score": 84.5}]).',
    )
