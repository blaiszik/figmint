"""Zero-dependency tabular file loader and data inspector for agent workflows.

Reads CSV, TSV, JSON, or JSONL files without pandas, profiles columns and shapes,
and recommends ready-to-run ``figmint`` forms so agents skip exploratory boilerplate.
"""

from __future__ import annotations

import csv
import json
import math
import re
import statistics
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from ._explain.core import ExplainError
from ._tabular import extract_records, is_tabular

__all__ = ["auto_panel", "inspect_data", "load_table_file"]

_NULL_TOKENS = {"", "na", "n/a", "nan", "none", "null", "-", "—"}
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}(-\d{2})?([T ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?)?$")
_TIME_COL_HINTS = ("date", "time", "day", "week", "month", "year", "step", "epoch", "dose", "iter", "round", "version")
_DELTA_COL_HINTS = ("delta", "diff", "change", "gain", "contrib", "contribution", "impact", "effect")
_FLOW_STAGE_HINTS = ("stage", "step", "phase", "funnel", "cohort", "gate", "filter")
_FLOW_REASON_HINTS = ("reason", "drop_reason", "exclusion", "excluded", "cause", "note")
_COST_COL_HINTS = ("cost", "price", "latency", "ms", "time", "flops", "params", "memory", "size")
_SCORE_COL_HINTS = ("score", "acc", "accuracy", "pass", "f1", "gpqa", "swe", "aime", "quality", "win", "rate")


def _parse_scalar(raw: Any) -> Any:
    if raw is None or isinstance(raw, (int, float, bool)):
        if isinstance(raw, float) and not math.isfinite(raw):
            return None
        return raw
    text = str(raw).strip()
    if text.lower() in _NULL_TOKENS:
        return None
    # Preserve ISO dates and strings with leading zeros like "001"
    if _ISO_DATE_RE.match(text):
        return text
    cleaned = text.replace(",", "")
    if cleaned.endswith("%") and len(cleaned) > 1:
        try:
            return float(cleaned[:-1])
        except ValueError:
            return text
    try:
        num = float(cleaned)
    except ValueError:
        return text
    if not math.isfinite(num):
        return None
    if num.is_integer() and "." not in cleaned and "e" not in cleaned.lower():
        return int(num)
    return num


def load_table_file(path: str | Path) -> list[dict[str, Any]]:
    """Load rows from a ``.csv``, ``.tsv``, ``.json``, or ``.jsonl`` file without pandas."""
    src = Path(path)
    if not src.exists():
        raise ExplainError(
            f"Data file {src} does not exist.",
            fix_hint="Check the file path and pass a .csv, .tsv, .json, or .jsonl file.",
        )
    suffix = src.suffix.lower()
    raw_text = src.read_text(encoding="utf-8-sig")

    if suffix in {".csv", ".tsv"}:
        delimiter = "\t" if suffix == ".tsv" else ","
        reader = csv.DictReader(raw_text.splitlines(), delimiter=delimiter)
        if not reader.fieldnames:
            raise ExplainError(
                f"{src.name} has no header row.",
                fix_hint="Ensure the first line contains column names.",
            )
        rows: list[dict[str, Any]] = []
        for raw_row in reader:
            if not any(v is not None and str(v).strip() for v in raw_row.values()):
                continue
            rows.append({str(k).strip(): _parse_scalar(v) for k, v in raw_row.items() if k is not None})
        return rows

    if suffix in {".jsonl", ".ndjson"}:
        rows = []
        for idx, line in enumerate(raw_text.splitlines(), 1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                obj = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ExplainError(
                    f"{src.name} line {idx} is invalid JSON: {exc}.",
                    fix_hint="Ensure every non-empty line in a JSONL file is a JSON object.",
                ) from exc
            if not isinstance(obj, Mapping):
                raise ExplainError(
                    f"{src.name} line {idx} is {type(obj).__name__}, expected a JSON object.",
                    fix_hint="Each JSONL line must be a {...} dict.",
                )
            rows.append({str(k): _parse_scalar(v) for k, v in obj.items()})
        return rows

    if suffix == ".json":
        try:
            payload = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise ExplainError(
                f"{src.name} is not valid JSON: {exc}.",
                fix_hint="Fix JSON syntax or pass a CSV/TSV/JSONL file.",
            ) from exc
        if isinstance(payload, Mapping):
            # Wrapper keys like {"rows": [...]} or {"data": [...]}
            for wrapper_key in ("rows", "data", "records", "results", "items"):
                inner = payload.get(wrapper_key)
                if isinstance(inner, list) and inner and isinstance(inner[0], Mapping):
                    return [{str(k): _parse_scalar(v) for k, v in r.items()} for r in inner]
            # Column-oriented dict {"col": [v1, v2, ...]}
            if payload and all(
                isinstance(v, list) for v in payload.values()
            ):
                cols = [str(k) for k in payload]
                lengths = {len(v) for v in payload.values()}
                if len(lengths) == 1:
                    n = next(iter(lengths))
                    return [
                        {c: _parse_scalar(payload[c][i]) for c in cols}
                        for i in range(n)
                    ]
            # Single flat mapping {"item": number, ...} -> 2-column rows
            if payload and all(not isinstance(v, (dict, list)) for v in payload.values()):
                return [{"name": str(k), "value": _parse_scalar(v)} for k, v in payload.items()]
            raise ExplainError(
                f"{src.name} is a JSON object whose shape could not be interpreted as rows.",
                fix_hint="Use a list of row dicts [{...}, ...], a column dict {'col': [...]}, or {'rows': [...]}.",
            )
        if isinstance(payload, list):
            if not payload:
                return []
            if isinstance(payload[0], Mapping):
                return [{str(k): _parse_scalar(v) for k, v in r.items()} for r in payload]
        raise ExplainError(
            f"{src.name} must contain a list of row objects or a column mapping.",
            fix_hint="Pass a CSV, TSV, JSONL, or tabular JSON file.",
        )

    raise ExplainError(
        f"Unsupported data file suffix {suffix!r} for {src.name}.",
        fix_hint="Supported formats: .csv, .tsv, .json, .jsonl, .ndjson.",
    )


def _is_num(val: Any) -> bool:
    return isinstance(val, (int, float)) and not isinstance(val, bool) and math.isfinite(float(val))


def _profile_column(col: str, values: Sequence[Any]) -> dict[str, Any]:
    non_null = [v for v in values if v is not None and not (isinstance(v, str) and not v.strip())]
    missing = len(values) - len(non_null)
    unique_vals = list(dict.fromkeys(str(v) for v in non_null))

    if non_null and all(_is_num(v) for v in non_null):
        nums = [float(v) for v in non_null]
        lo, hi = min(nums), max(nums)
        pos = [v for v in nums if v > 0]
        spans_decades = bool(pos and (max(pos) / min(pos) >= 50.0))
        return {
            "name": col,
            "type": "numeric",
            "non_null": len(nums),
            "missing": missing,
            "unique": len(set(nums)),
            "min": round(lo, 6),
            "median": round(float(statistics.median(nums)), 6),
            "mean": round(float(statistics.fmean(nums)), 6),
            "max": round(hi, 6),
            "has_negative": lo < 0,
            "spans_decades": spans_decades,
        }

    if non_null and all(isinstance(v, str) and bool(_ISO_DATE_RE.match(v)) for v in non_null):
        return {
            "name": col,
            "type": "date",
            "non_null": len(non_null),
            "missing": missing,
            "unique": len(unique_vals),
            "min": min(unique_vals),
            "max": max(unique_vals),
        }

    col_type = "categorical" if len(unique_vals) <= max(20, int(0.6 * max(len(non_null), 1))) else "text"
    return {
        "name": col,
        "type": col_type,
        "non_null": len(non_null),
        "missing": missing,
        "unique": len(unique_vals),
        "samples": unique_vals[:6],
    }


def inspect_data(
    source: str | Path | Sequence[Mapping[str, Any]] | Any,
) -> dict[str, Any]:
    """Inspect a tabular file, list of row dicts, or DataFrame and recommend ``figmint`` forms.

    Returns a JSON-serializable dict with ``rows``, ``columns``, ``column_profiles``,
    ``recommendations`` (ordered best-fit forms with concrete Python & CLI commands),
    and ``preview`` (first 3 rows).
    """
    src_label: str | None = None
    if isinstance(source, (str, Path)):
        src_label = str(source)
        rows = load_table_file(source)
        cols = list(dict.fromkeys(k for r in rows for k in r))
    elif is_tabular(source):
        cols, rows = extract_records(source, what="inspect_data(source)")
        rows = [{k: _parse_scalar(v) for k, v in r.items()} for r in rows]
    else:
        raise ExplainError(
            f"inspect_data() expected a file path, list of dicts, or DataFrame; got {type(source).__name__}.",
            fix_hint='Pass a path like "results.csv" or rows=[{"model": "A", "score": 0.8}].',
        )

    if not rows:
        return {
            "source": src_label,
            "rows": 0,
            "columns": cols,
            "column_profiles": [],
            "recommendations": [],
            "preview": [],
        }

    profiles = [_profile_column(c, [r.get(c) for r in rows]) for c in cols]
    by_name = {p["name"]: p for p in profiles}
    num_cols = [p["name"] for p in profiles if p["type"] == "numeric"]
    date_cols = [p["name"] for p in profiles if p["type"] == "date"]
    cat_cols = [p["name"] for p in profiles if p["type"] in {"categorical", "text"}]
    lower_cols = {c.lower(): c for c in cols}

    recs: list[dict[str, Any]] = []

    def _add_rec(
        kind: str,
        reason: str,
        python_call: str,
        cli_flags: str = "",
        params: dict[str, Any] | None = None,
    ) -> None:
        if any(r["kind"] == kind and r["python"] == python_call for r in recs):
            return
        entry: dict[str, Any] = {"kind": kind, "reason": reason, "python": python_call}
        if cli_flags and src_label:
            entry["cli"] = f'figmint plot {src_label} --kind {kind} {cli_flags} --takeaway "..." --out fig.png'
        if params:
            entry["params"] = params
        recs.append(entry)

    # 1. Timeline spans: explicit start & end numeric columns
    start_c = next((lower_cols[k] for k in ("start", "t_start", "start_s", "start_ms", "begin") if k in lower_cols), None)
    end_c = next((lower_cols[k] for k in ("end", "t_end", "end_s", "end_ms", "finish") if k in lower_cols), None)
    if start_c in num_cols and end_c in num_cols and cat_cols:
        nm_c = cat_cols[0]
        grp_col = cat_cols[1] if len(cat_cols) >= 2 and by_name[cat_cols[1]]["unique"] <= 4 else None
        grp_extra = f', group="{grp_col}"' if grp_col else ""
        cli_g = f" --group {grp_col}" if grp_col else ""
        _add_rec(
            "timeline",
            f"Detected start/end span columns ({start_c!r}, {end_c!r}) for {len(rows)} stages.",
            f'fm.timeline(rows, name="{nm_c}", start="{start_c}", end="{end_c}"{grp_extra})',
            f"--name {nm_c} --start {start_c} --end {end_c}{cli_g}",
            {"name": nm_c, "start": start_c, "end": end_c, **({"group": grp_col} if grp_col else {})},
        )

    # 1b. Flow / attrition funnel: stage column + monotonic non-increasing positive count column (+ optional reason)
    if cat_cols and len(num_cols) == 1 and 3 <= len(rows) <= 12:
        stage_c = cat_cols[0]
        val_c = num_cols[0]
        rsn_c = next((c for c in cat_cols[1:] if any(h in c.lower() for h in _FLOW_REASON_HINTS)), None)
        col_vals = [r.get(val_c) for r in rows]
        if (
            by_name[stage_c]["unique"] == len(rows)
            and all(_is_num(v) and float(v) >= 0 for v in col_vals)
            and float(col_vals[0]) > float(col_vals[-1])
            and all(float(col_vals[i]) <= float(col_vals[i - 1]) for i in range(1, len(col_vals)))
            and (rsn_c is not None or any(h in stage_c.lower() for h in _FLOW_STAGE_HINTS))
        ):
            rsn_py = f', reason="{rsn_c}"' if rsn_c else ""
            rsn_cli = f" --reason {rsn_c}" if rsn_c else ""
            _add_rec(
                "flow",
                f"Monotonic attrition across {len(rows)} stages in {stage_c!r} ({col_vals[0]} -> {col_vals[-1]}).",
                f'fm.flow(rows, name="{stage_c}", value="{val_c}"{rsn_py})',
                f"--name {stage_c} --value {val_c}{rsn_cli}",
                {"name": stage_c, "value": val_c, **({"reason": rsn_c} if rsn_c else {})},
            )

    # 2. Trend: date column or time/step/dose numeric column
    x_cand = (
        date_cols[0]
        if date_cols
        else next(
            (c for c in num_cols if any(h in c.lower() for h in _TIME_COL_HINTS) and by_name[c]["unique"] >= 3),
            None,
        )
    )
    if x_cand is not None:
        y_cands = [c for c in num_cols if c != x_cand]
        if y_cands:
            y_c = y_cands[0]
            series_c = next((c for c in cat_cols if 2 <= by_name[c]["unique"] <= 12), None)
            log_x_flag = bool(by_name[x_cand].get("spans_decades"))
            log_x_note = ", log_x=True" if log_x_flag else ""
            if series_c:
                # Check if replicates exist
                pairs = [(r.get(x_cand), r.get(series_c)) for r in rows]
                rep_note = " (repeated rows auto-plot as replicate points)" if len(pairs) > len(set(pairs)) else ""
                _add_rec(
                    "trend",
                    f"Ordered x column {x_cand!r} with {by_name[series_c]['unique']} series in {series_c!r}{rep_note}.",
                    f'fm.trend("{x_cand}", "{series_c}", y="{y_c}", data=rows{log_x_note})',
                    f"--x {x_cand} --series {series_c} --y {y_c}",
                    {"x": x_cand, "series": series_c, "y": y_c, "log_x": log_x_flag},
                )
            else:
                _add_rec(
                    "trend",
                    f"Ordered x column {x_cand!r} against {y_c!r}.",
                    f'fm.trend("{x_cand}", y="{y_c}", data=rows{log_x_note})',
                    f"--x {x_cand} --y {y_c}",
                    {"x": x_cand, "y": y_c, "log_x": log_x_flag},
                )

    # 3. Grouped compare / matrix: 2 categorical + 1 numeric with unique pairs
    if len(cat_cols) >= 2 and num_cols:
        c0, c1, val_c = cat_cols[0], cat_cols[1], num_cols[0]
        pairs = [(r.get(c0), r.get(c1)) for r in rows]
        if len(pairs) == len(set(pairs)):
            u0, u1 = by_name[c0]["unique"], by_name[c1]["unique"]
            if 2 <= u1 <= 4 and u0 <= 12:
                _add_rec(
                    "compare",
                    f"Tidy 2D grid ({u0} {c0} × {u1} {c1}) fits grouped horizontal bars.",
                    f'fm.compare(rows, name="{c0}", group="{c1}", value="{val_c}")',
                    f"--name {c0} --group {c1} --value {val_c}",
                    {"name": c0, "group": c1, "value": val_c},
                )
            if u0 <= 16 and u1 <= 12:
                _add_rec(
                    "matrix",
                    f"Two categorical dimensions ({u0}×{u1}) fit an annotated heat table.",
                    f'fm.matrix(rows, rows="{c0}", cols="{c1}", value="{val_c}")',
                    f"--rows {c0} --cols {c1} --value {val_c}",
                    {"rows": c0, "cols": c1, "value": val_c},
                )

    # 4. Distribution vs single-item compare / waterfall / change / scorecard
    if cat_cols and num_cols:
        id_col = cat_cols[0]
        u_id = by_name[id_col]["unique"]
        val_c = num_cols[0]
        if u_id < len(rows) and u_id <= 8 and (len(rows) / max(u_id, 1)) >= 3:
            log_f = bool(by_name[val_c].get("spans_decades"))
            use_q = (len(rows) / max(u_id, 1)) >= 15
            log_flag = ", log=True" if log_f else ""
            q_flag = ', mode="quantile"' if use_q else ""
            _add_rec(
                "distribution",
                f"Multiple raw observations per {id_col!r} ({len(rows)} rows across {u_id} groups).",
                f'fm.distribution(rows, group="{id_col}", value="{val_c}"{log_flag}{q_flag})',
                f"--group {id_col} --value {val_c}",
                {"group": id_col, "value": val_c, "log": log_f, "mode": "quantile" if use_q else "dots"},
            )
        elif u_id == len(rows):
            if len(num_cols) == 1:
                if by_name[val_c]["has_negative"] and any(h in val_c.lower() for h in _DELTA_COL_HINTS):
                    _add_rec(
                        "waterfall",
                        f"Signed contribution column {val_c!r} across {len(rows)} steps.",
                        f'fm.waterfall(rows, name="{id_col}", value="{val_c}")',
                        f"--name {id_col} --value {val_c}",
                        {"name": id_col, "value": val_c},
                    )
                _add_rec(
                    "compare",
                    f"One value per {id_col!r} ({len(rows)} items) for ranked comparison.",
                    f'fm.compare(rows, name="{id_col}", value="{val_c}")',
                    f"--name {id_col} --value {val_c}",
                    {"name": id_col, "value": val_c},
                )
            elif len(num_cols) == 2:
                _add_rec(
                    "change",
                    f"Two numeric states ({num_cols[0]!r}, {num_cols[1]!r}) per {id_col!r} fit a slopegraph.",
                    f'fm.change("{num_cols[0]}", "{num_cols[1]}", data=rows, name="{id_col}")',
                    f"--before {num_cols[0]} --after {num_cols[1]} --name {id_col}",
                    {"before": num_cols[0], "after": num_cols[1], "name": id_col},
                )
            elif len(num_cols) >= 3 and len(rows) <= 20:
                _add_rec(
                    "table",
                    f"Multi-metric scorecard ({len(rows)} rows × {len(cols)} columns).",
                    f'fm.table(rows, bold_best=True, sort="-{num_cols[0]}")',
                    f"--sort -{num_cols[0]}",
                    {"bold_best": True, "sort": f"-{num_cols[0]}"},
                )

    # 5. Relate / Pareto frontier for >=2 continuous numeric columns
    if len(num_cols) >= 2 and len(rows) >= 3:
        cost_c = next((c for c in num_cols if any(h in c.lower() for h in _COST_COL_HINTS)), None)
        score_c = next((c for c in num_cols if c != cost_c and any(h in c.lower() for h in _SCORE_COL_HINTS)), None)
        rx = cost_c or num_cols[0]
        ry = score_c or next(c for c in num_cols if c != rx)
        nm_col = cat_cols[0] if cat_cols else None
        nm_extra = f', names="{nm_col}"' if nm_col else ""
        use_front = bool(cost_c and score_c and len(rows) <= 20 and nm_col)
        front_extra = ", frontier=True, label_all=True" if use_front else ""
        _add_rec(
            "relate",
            f"Continuous pair ({rx!r} vs {ry!r}) across {len(rows)} points.",
            f'fm.relate("{rx}", "{ry}", data=rows{nm_extra}{front_extra}, x_label="{rx}", y_label="{ry}")',
            f"--x {rx} --y {ry}" + (f" --names {nm_col}" if nm_col else ""),
            {"x": rx, "y": ry, "names": nm_col, "frontier": use_front, "label_all": use_front},
        )

    # Always offer table fallback for compact tabular data
    if not recs and len(rows) <= 20 and len(cols) <= 8:
        _add_rec("table", f"Compact {len(rows)}×{len(cols)} table for exact lookup.", "fm.table(rows)", "", {})

    return {
        "source": src_label,
        "rows": len(rows),
        "columns": cols,
        "column_profiles": profiles,
        "recommendations": recs[:4],
        "preview": rows[:3],
    }


def auto_panel(
    source: str | Path | Sequence[Mapping[str, Any]] | Any,
    *,
    title: str | None = None,
    label: str | None = None,
    unit: str | None = None,
    highlight: str | Sequence[str] | None = None,
    baseline: str | None = None,
) -> Any:
    """Automatically build the top-recommended :class:`Panel` for a data file or table.

    Uses :func:`inspect_data` to pick the highest-ranked form and column mapping,
    then constructs the corresponding panel cleanly with zero column boilerplate.
    """
    from . import explainer as fm_exp

    if isinstance(source, (str, Path)):
        rows = load_table_file(source)
        info = inspect_data(rows)
    elif is_tabular(source):
        _, rows = extract_records(source, what="auto_panel(source)")
        rows = [{k: _parse_scalar(v) for k, v in r.items()} for r in rows]
        info = inspect_data(rows)
    else:
        raise ExplainError(
            f"auto_panel() expected a data file path, list of dicts, or DataFrame; got {type(source).__name__}.",
            fix_hint='Pass a path like "results.csv" or rows=[{"model": "A", "score": 0.8}].',
        )

    recs = info.get("recommendations") or []
    if not recs:
        raise ExplainError(
            "auto_panel() could not infer a chart form for this dataset.",
            fix_hint="Call fm.inspect_data(source) to view columns and choose an explicit form.",
        )

    top = recs[0]
    kind = top["kind"]
    params = dict(top.get("params") or {})
    common: dict[str, Any] = {}
    if title is not None:
        common["title"] = title
    if label is not None:
        common["label"] = label
    if unit is not None:
        common["unit"] = unit
    if highlight is not None:
        common["highlight"] = highlight

    if kind == "timeline":
        return fm_exp.timeline(
            rows,
            name=params.get("name"),
            start=params.get("start"),
            end=params.get("end"),
            group=params.get("group"),
            **common,
        )
    if kind == "flow":
        return fm_exp.flow(
            rows,
            name=params.get("name"),
            value=params.get("value"),
            reason=params.get("reason"),
            **common,
        )
    if kind == "waterfall":
        return fm_exp.waterfall(
            rows,
            name=params.get("name"),
            value=params.get("value"),
            **common,
        )
    if kind == "trend":
        kw = {**common, "data": rows, "y": params.get("y"), "x_label": params.get("x")}
        if params.get("log_x"):
            kw["log_x"] = True
        if baseline is not None:
            kw["baseline"] = baseline
        kw.setdefault("label", params.get("y"))
        return fm_exp.trend(params["x"], params.get("series"), **kw)
    if kind == "compare":
        kw = {**common, "name": params.get("name"), "value": params.get("value")}
        if params.get("group"):
            kw["group"] = params["group"]
        if baseline is not None:
            kw["baseline"] = baseline
        kw.setdefault("label", params.get("value"))
        return fm_exp.compare(rows, **kw)
    if kind == "distribution":
        kw = {
            **common,
            "group": params.get("group"),
            "value": params.get("value"),
            "mode": params.get("mode", "dots"),
        }
        if params.get("log"):
            kw["log"] = True
        if baseline is not None:
            kw["baseline"] = baseline
        kw.setdefault("label", params.get("value"))
        return fm_exp.distribution(rows, **kw)
    if kind == "change":
        kw = {**common, "data": rows, "name": params.get("name")}
        kw.setdefault("label", f"{params['before']} -> {params['after']}")
        return fm_exp.change(params["before"], params["after"], **kw)
    if kind == "matrix":
        kw = {
            **common,
            "rows": params.get("rows"),
            "cols": params.get("cols"),
            "value": params.get("value"),
        }
        kw.setdefault("label", params.get("value"))
        return fm_exp.matrix(rows, **kw)
    if kind == "relate":
        kw = {
            **common,
            "data": rows,
            "x_label": params["x"],
            "y_label": params["y"],
        }
        if params.get("names"):
            kw["names"] = params["names"]
        if params.get("frontier"):
            kw["frontier"] = True
        if params.get("label_all"):
            kw["label_all"] = True
        return fm_exp.relate(params["x"], params["y"], **kw)
    # Default: table
    kw = {**common}
    if baseline is not None:
        kw["baseline"] = baseline
    if params.get("bold_best"):
        kw["bold_best"] = True
    if params.get("sort"):
        kw["sort"] = params["sort"]
    return fm_exp.table(rows, **kw)
