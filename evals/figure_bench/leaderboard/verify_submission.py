"""Verify figure-bench v0.1 leaderboard submissions against schema and invariants.

Zero external dependencies beyond the Python standard library.

Checks performed:
1. Required fields, types, enums, string patterns, and numeric ranges from ``schema.json``.
2. ``task_count == len(per_task)`` and unique ``task_id`` entries.
3. Aggregate ``scores`` match exact averages (and median for ``median_seconds``) computed
   from ``per_task`` within rounding tolerance (prevents tampered top-level totals).
4. Required ``provenance`` metadata is present and non-empty.
5. When ``artifacts_dir`` is set, verifies each task's PNG file exists, has a valid PNG
   signature, and has sensible non-degenerate image dimensions.

Usage:
    python evals/figure_bench/leaderboard/verify_submission.py submissions/*.json
"""

from __future__ import annotations

import argparse
import datetime
import json
import math
import re
import statistics
import struct
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
DEFAULT_SCHEMA_PATH = HERE / "schema.json"
REPO_ROOT = HERE.parents[2]

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
AGGREGATE_TOLERANCE = 0.15
MIN_PNG_DIMENSION_PX = 100
MAX_PNG_DIMENSION_PX = 16384


def load_schema(schema_path: Path | None = None) -> dict[str, Any]:
    """Load the canonical leaderboard JSON schema."""
    path = schema_path or DEFAULT_SCHEMA_PATH
    return json.loads(path.read_text(encoding="utf-8"))


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _check_score_range(
    value: Any,
    field: str,
    *,
    allow_null: bool = False,
    min_val: float = 0.0,
    max_val: float | None = 100.0,
    errors: list[str],
) -> None:
    if value is None:
        if not allow_null:
            errors.append(f"{field}: must be a number, got null")
        return
    if not _is_number(value):
        errors.append(f"{field}: must be a finite number, got {type(value).__name__}")
        return
    if value < min_val:
        errors.append(f"{field}: {value} is below minimum {min_val}")
    if max_val is not None and value > max_val:
        errors.append(f"{field}: {value} exceeds maximum {max_val}")


def read_png_dimensions(png_path: Path) -> tuple[int, int]:
    """Return ``(width, height)`` of a PNG file by inspecting its IHDR chunk."""
    header = png_path.read_bytes()[:24]
    if len(header) < 24 or header[:8] != PNG_SIGNATURE:
        raise ValueError(f"{png_path}: not a valid PNG file (bad signature)")
    chunk_type = header[12:16]
    if chunk_type != b"IHDR":
        raise ValueError(f"{png_path}: missing IHDR chunk (found {chunk_type!r})")
    width, height = struct.unpack(">II", header[16:24])
    return width, height


def compute_aggregates(per_task: list[dict[str, Any]]) -> dict[str, float | None]:
    """Compute canonical aggregate scores directly from ``per_task`` entries."""
    if not per_task:
        return {
            "composite": None,
            "visual_quality": None,
            "claim_accuracy": None,
            "uncertainty_calibration": None,
            "reader_score": None,
            "delivery_rate": None,
            "median_seconds": None,
        }

    def _mean(key: str, *, allow_null: bool = False) -> float | None:
        vals = [row[key] for row in per_task if _is_number(row.get(key))]
        if not vals:
            return None if allow_null else 0.0
        return round(sum(vals) / len(vals), 1)

    secs = [row["seconds"] for row in per_task if _is_number(row.get("seconds"))]
    median_sec = round(statistics.median(secs), 1) if secs else None

    return {
        "composite": _mean("composite"),
        "visual_quality": _mean("visual_quality"),
        "claim_accuracy": _mean("claim_accuracy"),
        "uncertainty_calibration": _mean("uncertainty_calibration", allow_null=True),
        "reader_score": _mean("reader_score", allow_null=True),
        "delivery_rate": _mean("delivery"),
        "median_seconds": median_sec,
    }


def _resolve_artifacts_dir(artifacts_dir: str, base_dir: Path | None) -> Path | None:
    raw = Path(artifacts_dir)
    if raw.is_absolute():
        return raw if raw.is_dir() else None
    candidates = []
    if base_dir is not None:
        candidates.append(base_dir / raw)
    candidates.append(REPO_ROOT / raw)
    candidates.append(HERE / raw)
    for cand in candidates:
        if cand.is_dir():
            return cand
    return None


def _find_task_png(artifacts_root: Path, row: dict[str, Any]) -> Path | None:
    fig_path = row.get("figure_path")
    if isinstance(fig_path, str) and fig_path.strip():
        cand = artifacts_root / fig_path
        return cand if cand.is_file() else None
    tid = row.get("task_id", "")
    for rel in (Path(tid) / "figure.png", Path(f"{tid}.png")):
        cand = artifacts_root / rel
        if cand.is_file():
            return cand
    return None


def verify_submission_data(
    data: Any,
    *,
    base_dir: Path | None = None,
    schema: dict[str, Any] | None = None,
) -> list[str]:
    """Validate a parsed submission dict. Returns a list of errors (empty means valid)."""
    errors: list[str] = []
    schema_obj = schema or load_schema()

    if not isinstance(data, dict):
        return ["submission root must be a JSON object"]

    # 1. Top-level required & allowed keys
    required_top = set(schema_obj["required"])
    allowed_top = set(schema_obj["properties"].keys())
    for key in sorted(required_top - set(data.keys())):
        errors.append(f"missing required top-level field: {key!r}")
    for key in sorted(set(data.keys()) - allowed_top):
        errors.append(f"unexpected top-level field: {key!r}")

    # 2. Schema version, strings, enums, booleans
    if data.get("schema_version") != "0.1":
        errors.append(f"schema_version: expected '0.1', got {data.get('schema_version')!r}")

    sub_id = data.get("submission_id")
    id_pattern = schema_obj["properties"]["submission_id"]["pattern"]
    if not isinstance(sub_id, str) or not re.match(id_pattern, sub_id):
        errors.append(f"submission_id: invalid slug {sub_id!r} (must match {id_pattern})")

    date_val = data.get("date")
    if not isinstance(date_val, str) or not re.match(r"^\d{4}-\d{2}-\d{2}$", date_val):
        errors.append(f"date: must be YYYY-MM-DD, got {date_val!r}")
    else:
        try:
            datetime.date.fromisoformat(date_val)
        except ValueError:
            errors.append(f"date: not a valid calendar date: {date_val!r}")

    for str_field in ("team", "model", "library", "skill_or_prompt"):
        val = data.get(str_field)
        if not isinstance(val, str) or not val.strip():
            errors.append(f"{str_field}: must be a non-empty string")

    if not isinstance(data.get("hook_enabled"), bool):
        errors.append("hook_enabled: must be a boolean")

    if "work_in_progress" in data and not isinstance(data["work_in_progress"], bool):
        errors.append("work_in_progress: must be a boolean")

    valid_splits = set(schema_obj["properties"]["split"]["enum"])
    if data.get("split") not in valid_splits:
        errors.append(f"split: {data.get('split')!r} not in {sorted(valid_splits)}")

    task_count = data.get("task_count")
    if not _is_int(task_count) or task_count < 1:
        errors.append(f"task_count: must be an integer >= 1, got {task_count!r}")

    # 3. Provenance validation
    prov = data.get("provenance")
    prov_schema = schema_obj["properties"]["provenance"]
    if not isinstance(prov, dict):
        errors.append("provenance: must be an object")
    else:
        allowed_prov = set(prov_schema["properties"].keys())
        for key in sorted(set(prov.keys()) - allowed_prov):
            errors.append(f"provenance: unexpected field {key!r}")
        for req in prov_schema["required"]:
            val = prov.get(req)
            if not isinstance(val, str) or not val.strip():
                errors.append(f"provenance.{req}: must be a non-empty string")
        if isinstance(prov.get("commit"), str) and len(prov["commit"].strip()) < 4:
            errors.append("provenance.commit: must be at least 4 characters")
        if "first_submission_clean_rate" in prov:
            _check_score_range(
                prov["first_submission_clean_rate"],
                "provenance.first_submission_clean_rate",
                allow_null=True,
                errors=errors,
            )
        if "timing_summary" in prov and prov["timing_summary"] is not None and not isinstance(prov["timing_summary"], dict):
            errors.append("provenance.timing_summary: must be an object or null")

    # 4. Scores block validation
    scores = data.get("scores")
    scores_schema = schema_obj["properties"]["scores"]
    if not isinstance(scores, dict):
        errors.append("scores: must be an object")
    else:
        req_scores = set(scores_schema["required"])
        allowed_scores = set(scores_schema["properties"].keys())
        for key in sorted(req_scores - set(scores.keys())):
            errors.append(f"scores: missing required field {key!r}")
        for key in sorted(set(scores.keys()) - allowed_scores):
            errors.append(f"scores: unexpected field {key!r}")
        _check_score_range(scores.get("composite"), "scores.composite", errors=errors)
        _check_score_range(scores.get("visual_quality"), "scores.visual_quality", errors=errors)
        _check_score_range(scores.get("claim_accuracy"), "scores.claim_accuracy", errors=errors)
        _check_score_range(
            scores.get("uncertainty_calibration"),
            "scores.uncertainty_calibration",
            allow_null=True,
            errors=errors,
        )
        _check_score_range(
            scores.get("reader_score"),
            "scores.reader_score",
            allow_null=True,
            errors=errors,
        )
        _check_score_range(scores.get("delivery_rate"), "scores.delivery_rate", errors=errors)
        _check_score_range(
            scores.get("median_seconds"),
            "scores.median_seconds",
            allow_null=True,
            min_val=0.0,
            max_val=None,
            errors=errors,
        )

    # 5. per_task array validation
    per_task = data.get("per_task")
    item_schema = schema_obj["properties"]["per_task"]["items"]
    valid_tracks = set(item_schema["properties"]["track"]["enum"])
    valid_item_splits = set(item_schema["properties"]["split"]["enum"])
    req_item_keys = set(item_schema["required"])
    allowed_item_keys = set(item_schema["properties"].keys())
    task_id_pattern = item_schema["properties"]["task_id"]["pattern"]

    valid_rows: list[dict[str, Any]] = []
    if not isinstance(per_task, list) or len(per_task) == 0:
        errors.append("per_task: must be a non-empty array")
    else:
        if _is_int(task_count) and len(per_task) != task_count:
            errors.append(f"task_count ({task_count}) does not match len(per_task) ({len(per_task)})")
        seen_ids: set[str] = set()
        for idx, row in enumerate(per_task):
            prefix = f"per_task[{idx}]"
            if not isinstance(row, dict):
                errors.append(f"{prefix}: must be an object")
                continue
            for key in sorted(req_item_keys - set(row.keys())):
                errors.append(f"{prefix}: missing required field {key!r}")
            for key in sorted(set(row.keys()) - allowed_item_keys):
                errors.append(f"{prefix}: unexpected field {key!r}")

            tid = row.get("task_id")
            if not isinstance(tid, str) or not re.match(task_id_pattern, tid):
                errors.append(f"{prefix}.task_id: invalid id {tid!r}")
            elif tid in seen_ids:
                errors.append(f"{prefix}.task_id: duplicate task_id {tid!r}")
            else:
                seen_ids.add(tid)

            if row.get("track") not in valid_tracks:
                errors.append(f"{prefix}.track: {row.get('track')!r} not in {sorted(valid_tracks)}")
            if row.get("split") not in valid_item_splits:
                errors.append(
                    f"{prefix}.split: {row.get('split')!r} not in {sorted(valid_item_splits)}"
                )
            if not isinstance(row.get("passed"), bool):
                errors.append(f"{prefix}.passed: must be a boolean")

            _check_score_range(row.get("visual_quality"), f"{prefix}.visual_quality", errors=errors)
            _check_score_range(row.get("claim_accuracy"), f"{prefix}.claim_accuracy", errors=errors)
            _check_score_range(
                row.get("uncertainty_calibration"),
                f"{prefix}.uncertainty_calibration",
                allow_null=True,
                errors=errors,
            )
            _check_score_range(
                row.get("reader_score"),
                f"{prefix}.reader_score",
                allow_null=True,
                errors=errors,
            )
            _check_score_range(row.get("delivery"), f"{prefix}.delivery", errors=errors)
            _check_score_range(row.get("composite"), f"{prefix}.composite", errors=errors)
            _check_score_range(
                row.get("seconds"),
                f"{prefix}.seconds",
                allow_null=True,
                min_val=0.0,
                max_val=None,
                errors=errors,
            )
            if "attempts" in row and (not _is_int(row["attempts"]) or row["attempts"] < 1):
                errors.append(f"{prefix}.attempts: must be an integer >= 1")
            if "failed_checks" in row and (
                not isinstance(row["failed_checks"], list)
                or not all(isinstance(c, str) for c in row["failed_checks"])
            ):
                errors.append(f"{prefix}.failed_checks: must be an array of strings")
            if "display_width_px" in row and (
                not _is_int(row["display_width_px"])
                or not (100 <= row["display_width_px"] <= 4096)
            ):
                errors.append(f"{prefix}.display_width_px: must be integer in [100, 4096]")
            if "timing" in row and row["timing"] is not None and not isinstance(row["timing"], dict):
                errors.append(f"{prefix}.timing: must be an object or null")
            valid_rows.append(row)

    # 6. Anti-tampering check: aggregate scores MUST match per_task calculations
    if isinstance(scores, dict) and valid_rows and len(valid_rows) == len(per_task or []):
        expected = compute_aggregates(valid_rows)
        for metric, exp_val in expected.items():
            got_val = scores.get(metric)
            if exp_val is None and got_val is None:
                continue
            if exp_val is None and got_val is not None:
                errors.append(
                    f"scores.{metric}: reported {got_val} but per_task has no non-null values"
                )
            elif exp_val is not None and got_val is None:
                errors.append(
                    f"scores.{metric}: reported null but per_task computes {exp_val}"
                )
            elif _is_number(got_val) and abs(float(got_val) - float(exp_val)) > AGGREGATE_TOLERANCE:
                errors.append(
                    f"scores.{metric}: reported {got_val} does not match per_task aggregate "
                    f"{exp_val} (diff={abs(float(got_val) - float(exp_val)):.2f} > {AGGREGATE_TOLERANCE})"
                )

    # 7. Optional artifacts_dir verification (PNG existence + IHDR dimensions)
    artifacts_dir = data.get("artifacts_dir")
    if artifacts_dir is not None:
        if not isinstance(artifacts_dir, str) or not artifacts_dir.strip():
            errors.append("artifacts_dir: must be a non-empty path string or null")
        else:
            root = _resolve_artifacts_dir(artifacts_dir, base_dir)
            if root is None:
                errors.append(f"artifacts_dir: directory not found: {artifacts_dir!r}")
            else:
                for row in valid_rows:
                    tid = row.get("task_id", "<unknown>")
                    png = _find_task_png(root, row)
                    if png is None:
                        errors.append(
                            f"artifacts_dir: missing PNG for task {tid!r} under {artifacts_dir!r}"
                        )
                        continue
                    try:
                        w, h = read_png_dimensions(png)
                    except ValueError as exc:
                        errors.append(f"artifacts_dir: {exc}")
                        continue
                    if w < MIN_PNG_DIMENSION_PX or h < MIN_PNG_DIMENSION_PX:
                        errors.append(
                            f"artifacts_dir: {png.name} for {tid!r} has tiny dimensions "
                            f"{w}x{h} px (min {MIN_PNG_DIMENSION_PX} px)"
                        )
                    if w > MAX_PNG_DIMENSION_PX or h > MAX_PNG_DIMENSION_PX:
                        errors.append(
                            f"artifacts_dir: {png.name} for {tid!r} has excessive dimensions "
                            f"{w}x{h} px (max {MAX_PNG_DIMENSION_PX} px)"
                        )

    return errors


def verify_submission_file(path: Path, *, schema: dict[str, Any] | None = None) -> list[str]:
    """Load and validate a submission JSON file."""
    if not path.is_file():
        return [f"file not found: {path}"]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"invalid JSON in {path}: {exc}"]
    return verify_submission_data(data, base_dir=path.parent, schema=schema)


def _expand_paths(raw_paths: list[str]) -> list[Path]:
    files: list[Path] = []
    for raw in raw_paths:
        p = Path(raw)
        if p.is_dir():
            files.extend(sorted(p.glob("*.json")))
        else:
            files.append(p)
    return files


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify figure-bench v0.1 leaderboard submission JSON files."
    )
    parser.add_argument(
        "paths",
        nargs="+",
        help="Submission JSON file(s) or directory containing submission JSONs.",
    )
    parser.add_argument(
        "--schema",
        type=Path,
        default=DEFAULT_SCHEMA_PATH,
        help="Path to leaderboard schema.json.",
    )
    args = parser.parse_args(argv)
    schema = load_schema(args.schema)
    files = _expand_paths(args.paths)
    if not files:
        print("No submission JSON files found.", file=sys.stderr)
        return 1

    all_ok = True
    for path in files:
        errs = verify_submission_file(path, schema=schema)
        if errs:
            all_ok = False
            print(f"FAIL {path}:")
            for err in errs:
                print(f"  - {err}")
        else:
            print(f"OK   {path}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
