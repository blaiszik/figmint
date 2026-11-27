"""Bridge for importing and auditing external figure benchmarks (MatPlotBench, PandasPlotBench, etc.).

Enables running outside datasets through ``figure-bench``'s library-agnostic auditors
(``neutral.py``, ``svg_audit.py``, ``pixel_audit.py``) with full per-task timing capture,
while keeping zero ``mintfig`` dependency.

Subcommands:
    import-matplotbench   Convert MatPlotAgent/benchmark_data into task folders.
    import-pandasplotbench Convert PandasPlotBench JSON/JSONL export into task folders.
    audit-outputs         Audit any <outputs_dir>/<task_id>/ folder (PNG/SVG/script) with timing.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import bench
import neutral
import pixel_audit
import svg_audit

_SLUG_BAD = re.compile(r"[^a-z0-9_-]+")


def _slug(raw: Any, prefix: str) -> str:
    s = _SLUG_BAD.sub("_", str(raw).strip().lower()).strip("_")
    return f"{prefix}_{s}" if s else f"{prefix}_item"


# --------------------------------------------------------------------------- importers


def import_matplotbench(
    src_dir: Path,
    out_dir: Path,
    *,
    instruction_field: str = "simple_instruction",
    limit: int | None = None,
) -> dict[str, Any]:
    """Import MatPlotBench (``benchmark_instructions.json`` + ``data/{id}/``) into task folders."""
    t0 = time.perf_counter()
    inst_path = src_dir / "benchmark_instructions.json"
    if not inst_path.is_file():
        cand = src_dir / "benchmark_data" / "benchmark_instructions.json"
        if cand.is_file():
            src_dir = src_dir / "benchmark_data"
            inst_path = cand
        else:
            raise FileNotFoundError(f"Could not find benchmark_instructions.json under {src_dir}")

    items = json.loads(inst_path.read_text(encoding="utf-8"))
    if not isinstance(items, list):
        raise TypeError("benchmark_instructions.json must contain a JSON list")
    if limit is not None and limit > 0:
        items = items[:limit]

    out_dir.mkdir(parents=True, exist_ok=True)
    imported: list[str] = []
    for idx, item in enumerate(items, 1):
        raw_id = item.get("id", idx)
        tid = _slug(raw_id, "mpb")
        tdir = out_dir / tid
        data_dst = tdir / "data"
        data_dst.mkdir(parents=True, exist_ok=True)

        prompt = (
            item.get(instruction_field)
            or item.get("simple_instruction")
            or item.get("expert_instruction")
            or item.get("instruction")
            or ""
        ).strip()

        # Copy per-task data files if present under data/{id}/
        data_src = src_dir / "data" / str(raw_id)
        copied_files: list[str] = []
        if data_src.is_dir():
            for child in sorted(data_src.iterdir()):
                if child.is_file():
                    shutil.copy2(child, data_dst / child.name)
                    copied_files.append(f"data/{child.name}")

        files_note = (
            f"\n\n**Assistant:** Available data files in this folder: {', '.join(f'`{f}`' for f in copied_files)}."
            if copied_files
            else ""
        )
        ctx = f"# Thread (External: MatPlotBench #{raw_id})\n\n**User:** {prompt}{files_note}\n"
        (tdir / "context.md").write_text(ctx, encoding="utf-8")
        (tdir / "external_meta.json").write_text(
            json.dumps(
                {
                    "source_benchmark": "MatPlotBench",
                    "source_id": raw_id,
                    "task_id": tid,
                    "instruction_field": instruction_field,
                    "data_files": copied_files,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        imported.append(tid)

    manifest = {
        "source_benchmark": "MatPlotBench",
        "source_dir": str(src_dir),
        "out_dir": str(out_dir),
        "count": len(imported),
        "import_s": round(time.perf_counter() - t0, 3),
        "tasks": imported,
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def import_pandasplotbench(
    src_path: Path,
    out_dir: Path,
    *,
    limit: int | None = None,
) -> dict[str, Any]:
    """Import PandasPlotBench JSON or JSONL export into isolated task folders."""
    t0 = time.perf_counter()
    if not src_path.is_file():
        raise FileNotFoundError(f"PandasPlotBench source file not found: {src_path}")

    raw = src_path.read_text(encoding="utf-8").strip()
    if raw.startswith("["):
        records = json.loads(raw)
    else:
        records = [json.loads(ln) for ln in raw.splitlines() if ln.strip()]
    if limit is not None and limit > 0:
        records = records[:limit]

    out_dir.mkdir(parents=True, exist_ok=True)
    imported: list[str] = []
    for idx, rec in enumerate(records, 1):
        raw_id = rec.get("id", idx)
        tid = _slug(raw_id, "ppb")
        tdir = out_dir / tid
        data_dst = tdir / "data"
        data_dst.mkdir(parents=True, exist_ok=True)

        csv_body = rec.get("data_csv") or rec.get("csv") or ""
        data_files: list[str] = []
        if isinstance(csv_body, str) and csv_body.strip():
            (data_dst / "dataset.csv").write_text(csv_body.strip() + "\n", encoding="utf-8")
            data_files.append("data/dataset.csv")

        prompt = (
            rec.get("task__plot_description")
            or rec.get("task")
            or rec.get("prompt")
            or rec.get("instruction")
            or ""
        ).strip()
        df_desc = (rec.get("data_description") or rec.get("df_description") or "").strip()
        extra_block = f"\n\n**Assistant:** Dataset summary:\n{df_desc}" if df_desc else ""
        if data_files:
            extra_block += f"\nSaved to `{data_files[0]}`."

        ctx = f"# Thread (External: PandasPlotBench #{raw_id})\n\n**User:** {prompt}{extra_block}\n"
        (tdir / "context.md").write_text(ctx, encoding="utf-8")
        (tdir / "external_meta.json").write_text(
            json.dumps(
                {
                    "source_benchmark": "PandasPlotBench",
                    "source_id": raw_id,
                    "task_id": tid,
                    "library_hint": rec.get("plotting_lib") or rec.get("library"),
                    "data_files": data_files,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        imported.append(tid)

    manifest = {
        "source_benchmark": "PandasPlotBench",
        "source_file": str(src_path),
        "out_dir": str(out_dir),
        "count": len(imported),
        "import_s": round(time.perf_counter() - t0, 3),
        "tasks": imported,
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


# --------------------------------------------------------------------------- neutral output auditor

_EXT_CAPTURE = r"""
import json, os, runpy, sys, time
from pathlib import Path
script, png_name, audit_out, bench_dir, display_w = sys.argv[1:6]
display_w = int(display_w)
sys.path.insert(0, bench_dir)
target = Path(png_name).resolve()
audits = []
audit_s = 0.0
import matplotlib
matplotlib.use("Agg")
import matplotlib as mpl
from matplotlib.figure import Figure
import neutral

_orig = Figure.savefig
def _hooked(self, fname, *a, **k):
    global audit_s
    res = _orig(self, fname, *a, **k)
    try:
        hit = isinstance(fname, (str, os.PathLike)) and Path(fname).resolve().suffix.lower() == ".png"
    except OSError:
        hit = False
    if hit:
        p = Path(fname).resolve()
        dpi = k.get("dpi") or mpl.rcParams["savefig.dpi"]
        dpi = self.dpi if dpi == "figure" else float(dpi)
        tight = (k.get("bbox_inches") or mpl.rcParams["savefig.bbox"]) == "tight"
        t_a = time.perf_counter()
        try:
            aud = neutral.audit_saved_figure(self, p, dpi=dpi, tight=tight, display_width_px=display_w)
            aud["saved_png"] = str(p)
            audits.append(aud)
        except Exception as exc:
            audits.append({"error": f"{type(exc).__name__}: {exc}"})
        audit_s += time.perf_counter() - t_a
    return res

Figure.savefig = _hooked
t0 = time.perf_counter()
try:
    runpy.run_path(script, run_name="__main__")
finally:
    wall = time.perf_counter() - t0
    with open(audit_out, "w", encoding="utf-8") as fh:
        json.dump(
            {
                "audits": audits,
                "exec_s": round(max(0.0, wall - audit_s), 4),
                "audit_s": round(audit_s, 4),
                "wall_s": round(wall, 4),
            },
            fh,
            ensure_ascii=False,
            default=str,
        )
"""


def _find_first(folder: Path, candidates: tuple[str, ...], suffix: str) -> Path | None:
    for name in candidates:
        p = folder / name
        if p.is_file():
            return p
    found = sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() == suffix)
    return found[0] if found else None


def audit_external_outputs(
    outputs_dir: Path,
    *,
    display_width_px: int = 700,
    surface: str = "chat",
    run_scripts: bool = False,
    python_bin: str = sys.executable,
    timeout_s: int = 60,
) -> dict[str, Any]:
    """Audit any external benchmark output tree (<outputs_dir>/<task_id>/) with full timing."""
    t_all0 = time.perf_counter()
    if not outputs_dir.is_dir():
        raise FileNotFoundError(f"Outputs directory not found: {outputs_dir}")

    task_dirs = sorted(p for p in outputs_dir.iterdir() if p.is_dir() and not p.name.startswith("."))
    per_task: dict[str, dict[str, Any]] = {}
    audit_wall_vals: list[float] = []
    exec_vals: list[float] = []
    ext_time_vals: list[float] = []

    for tdir in task_dirs:
        t0 = time.perf_counter()
        tid = tdir.name
        script = _find_first(tdir, ("figure.py", "plot.py", "code.py", "solution.py"), ".py")
        png = _find_first(tdir, ("figure.png", "plot.png", "output.png"), ".png")
        svg = _find_first(tdir, ("figure.svg", "plot.svg", "output.svg"), ".svg")
        timing_file = tdir / "timing.json"

        neutral_res: dict[str, Any] | None = None
        script_rc: int | None = None
        script_exec_s: float | None = None
        script_audit_s: float | None = None

        if run_scripts and script is not None:
            cap = tdir / ".ext_capture.py"
            aud_out = tdir / ".ext_audit.json"
            cap.write_text(_EXT_CAPTURE, encoding="utf-8")
            try:
                proc = subprocess.run(
                    [python_bin, str(cap), str(script), png.name if png else "figure.png", str(aud_out), str(HERE), str(display_width_px)],
                    cwd=tdir,
                    capture_output=True,
                    text=True,
                    timeout=timeout_s,
                    check=False,
                    env={**os.environ, "MPLCONFIGDIR": "/tmp/mpl-figbench"},
                )
                script_rc = proc.returncode
            except subprocess.TimeoutExpired:
                script_rc = -1
            if aud_out.is_file():
                meta = json.loads(aud_out.read_text(encoding="utf-8"))
                valid = [a for a in meta.get("audits", []) if "error" not in a]
                if valid:
                    neutral_res = valid[-1]
                    if png is None and neutral_res.get("saved_png"):
                        cand_png = Path(neutral_res["saved_png"])
                        if cand_png.is_file():
                            png = cand_png
                if isinstance(meta.get("exec_s"), (int, float)):
                    script_exec_s = float(meta["exec_s"])
                    exec_vals.append(script_exec_s)
                if isinstance(meta.get("audit_s"), (int, float)):
                    script_audit_s = float(meta["audit_s"])
            cap.unlink(missing_ok=True)
            aud_out.unlink(missing_ok=True)
            if png is None:
                png = _find_first(tdir, ("figure.png", "plot.png", "output.png"), ".png")

        svg_res = svg_audit.audit_svg(svg, display_width_px=display_width_px) if svg is not None else None
        px_res = (
            pixel_audit.audit_png(png, display_width_px=display_width_px, surface=surface)
            if png is not None
            else None
        )

        defects: list[str] = []
        if neutral_res is not None:
            for chk in neutral.neutral_checks(neutral_res):
                if not chk["passed"]:
                    defects.append(chk["name"])
            if neutral_res.get("banned_colormaps"):
                defects.append("banned_colormaps")
            if neutral_res.get("truncated_bar_axes"):
                defects.append("truncated_bar_baseline")
        elif svg_res is not None:
            for chk in svg_audit.svg_checks(svg_res):
                if not chk["passed"]:
                    defects.append(chk["name"])

        if px_res is not None:
            if px_res.get("empty_canvas"):
                defects.append("empty_canvas")
            if px_res.get("rainbow_colormap_suspected") and "banned_colormaps" not in defects:
                defects.append("rainbow_colormap_suspected")
            if not px_res.get("cvd_ok", True):
                defects.append("cvd_issue")
            if not px_res.get("grayscale_ok", True):
                defects.append("grayscale_low_contrast")
        elif neutral_res is None and svg_res is None:
            defects.append("missing_figure")

        ext_timing = None
        if timing_file.is_file():
            try:
                ext_timing = json.loads(timing_file.read_text(encoding="utf-8"))
                sec = ext_timing.get("seconds", ext_timing.get("seconds_total"))
                if isinstance(sec, (int, float)) and not isinstance(sec, bool):
                    ext_time_vals.append(float(sec))
            except (OSError, json.JSONDecodeError):
                ext_timing = None

        audit_wall_s = round(time.perf_counter() - t0, 4)
        audit_wall_vals.append(audit_wall_s)
        per_task[tid] = {
            "task_id": tid,
            "clean": len(defects) == 0,
            "defects": defects,
            "min_text_px": (neutral_res or svg_res or {}).get("min_text_px"),
            "uncertainty_named": (neutral_res or svg_res or {}).get("uncertainty_named"),
            "png_px": (px_res or {}).get("png_px"),
            "script_rc": script_rc,
            "timing": {
                "audit_wall_s": audit_wall_s,
                "script_exec_s": script_exec_s,
                "script_audit_s": script_audit_s,
                **({"external": ext_timing} if ext_timing is not None else {}),
            },
        }

    n = len(per_task)
    clean_n = sum(1 for r in per_task.values() if r["clean"])
    defect_counts: dict[str, int] = {}
    for r in per_task.values():
        for d in r["defects"]:
            defect_counts[d] = defect_counts.get(d, 0) + 1

    return {
        "outputs_dir": str(outputs_dir),
        "display_width_px": display_width_px,
        "surface": surface,
        "run_scripts": run_scripts,
        "task_count": n,
        "clean_count": clean_n,
        "clean_rate_pct": round(100.0 * clean_n / n, 1) if n else 0.0,
        "defect_counts": dict(sorted(defect_counts.items(), key=lambda kv: (-kv[1], kv[0]))),
        "timing_summary": {
            "total_wall_s": round(time.perf_counter() - t_all0, 3),
            "per_task_audit_wall_s": bench.summarize_timings(audit_wall_vals, decimals=4),
            "per_task_script_exec_s": bench.summarize_timings(exec_vals, decimals=4),
            "external_seconds": bench.summarize_timings(ext_time_vals, decimals=2),
        },
        "per_task": per_task,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_mpb = sub.add_parser("import-matplotbench", help="Import MatPlotBench into task folders.")
    p_mpb.add_argument("--src", required=True, type=Path, help="Path to MatPlotAgent/benchmark_data")
    p_mpb.add_argument("--out", required=True, type=Path, help="Output folder for imported tasks")
    p_mpb.add_argument("--instruction", choices=["simple_instruction", "expert_instruction"], default="simple_instruction")
    p_mpb.add_argument("--limit", type=int, default=None)

    p_ppb = sub.add_parser("import-pandasplotbench", help="Import PandasPlotBench JSON/JSONL into task folders.")
    p_ppb.add_argument("--src", required=True, type=Path, help="Path to PandasPlotBench JSON/JSONL file")
    p_ppb.add_argument("--out", required=True, type=Path, help="Output folder for imported tasks")
    p_ppb.add_argument("--limit", type=int, default=None)

    p_aud = sub.add_parser("audit-outputs", help="Run arm-neutral layout/pixel/timing audit on external outputs.")
    p_aud.add_argument("outputs_dir", type=Path, help="Directory containing <task_id>/{figure.png, figure.svg, figure.py}")
    p_aud.add_argument("--display-width", type=int, default=700)
    p_aud.add_argument("--surface", default="chat")
    p_aud.add_argument("--run-scripts", action="store_true", help="Re-execute Python scripts under neutral Figure.savefig hook")
    p_aud.add_argument("--python", default=sys.executable)
    p_aud.add_argument("--timeout", type=int, default=60)
    p_aud.add_argument("--out", type=Path, default=None, help="Write JSON report here")

    args = parser.parse_args(argv)
    if args.cmd == "import-matplotbench":
        res = import_matplotbench(args.src, args.out, instruction_field=args.instruction, limit=args.limit)
        print(f"Imported {res['count']} MatPlotBench task(s) -> {args.out} in {res['import_s']}s")
        return 0
    if args.cmd == "import-pandasplotbench":
        res = import_pandasplotbench(args.src, args.out, limit=args.limit)
        print(f"Imported {res['count']} PandasPlotBench task(s) -> {args.out} in {res['import_s']}s")
        return 0
    if args.cmd == "audit-outputs":
        res = audit_external_outputs(
            args.outputs_dir,
            display_width_px=args.display_width,
            surface=args.surface,
            run_scripts=args.run_scripts,
            python_bin=args.python,
            timeout_s=args.timeout,
        )
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(json.dumps(res, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(
            f"Audited {res['task_count']} external task(s): {res['clean_count']}/{res['task_count']} "
            f"clean ({res['clean_rate_pct']}%) in {res['timing_summary']['total_wall_s']}s | "
            f"defects={res['defect_counts']}"
        )
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
