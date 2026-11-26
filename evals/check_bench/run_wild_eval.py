"""Run the Wild-50 verification corpus against ``mint.check``.

Computes:
- False-positive rate on the 25 clean cases (target: < 2%, i.e., 0/25)
- Defect catch rate on the 25 defective cases (target: > 90%, i.e., >= 23/25)
- Exact-rule recall on defective cases (every expected rule present in issues)
- Breakdown by artist category and defect category

Writes ``evals/check_bench/report.json`` and ``evals/check_bench/REPORT.md``.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from corpus import WILD_50, WildCase

import mintfig as mint


def _git_sha() -> str:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=REPO_ROOT,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return out.strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def evaluate_case(case: WildCase) -> dict[str, Any]:
    """Build and audit a single Wild-50 figure with clean Matplotlib defaults."""
    with matplotlib.rc_context():
        matplotlib.rcdefaults()
        matplotlib.use("Agg")
        t0 = time.perf_counter()
        fig = case.builder()
        try:
            report = mint.check(
                fig,
                claim=case.claim,
                width=case.width,
                dpi=case.dpi,
                bbox_inches=case.bbox_inches,
            )
        finally:
            plt.close(fig)
        elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 1)

    issues = report.get("issues", [])
    issue_rules = [i["rule"] for i in issues]
    rule_set = set(issue_rules)
    expected_set = set(case.expected_rules)
    actual_ship = bool(report["ship"])

    if case.split == "clean":
        passed = actual_ship is True
        exact_rule_match = passed
    else:
        passed = actual_ship is False
        exact_rule_match = passed and expected_set.issubset(rule_set)

    claim_info = report.get("claim") or {}
    unmatched_nums = [
        {
            "text": n["text"],
            "kind": n["kind"],
            "nearest": n.get("nearest"),
        }
        for n in claim_info.get("numbers", [])
        if not n.get("found")
    ]

    return {
        "case_id": case.case_id,
        "split": case.split,
        "artist_category": case.artist_category,
        "defect_category": case.defect_category,
        "description": case.description,
        "expected_ship": case.expected_ship,
        "actual_ship": actual_ship,
        "expected_rules": list(case.expected_rules),
        "actual_rules": issue_rules,
        "passed": passed,
        "exact_rule_match": exact_rule_match,
        "elapsed_ms": elapsed_ms,
        "panel_kinds": [p.get("kind") for p in report.get("panels", [])],
        "panel_count": len(report.get("panels", [])),
        "min_text_px": (report.get("display") or {}).get("min_text_px"),
        "claim_text": claim_info.get("text"),
        "unmatched_claim_numbers": unmatched_nums,
        "issues": [
            {"rule": i["rule"], "severity": i["severity"], "message": i["message"]}
            for i in issues
        ],
    }


def run_eval(cases: tuple[WildCase, ...] = WILD_50) -> dict[str, Any]:
    """Run all Wild-50 cases and compute aggregate and per-category metrics."""
    t0 = time.perf_counter()
    results = [evaluate_case(c) for c in cases]
    total_s = round(time.perf_counter() - t0, 2)

    clean = [r for r in results if r["split"] == "clean"]
    defective = [r for r in results if r["split"] == "defective"]

    false_positives = [r for r in clean if not r["actual_ship"]]
    clean_warnings = [r for r in clean if r["actual_ship"] and r["actual_rules"]]
    caught = [r for r in defective if not r["actual_ship"]]
    exact_caught = [r for r in defective if r["exact_rule_match"]]
    missed = [r for r in defective if not r["exact_rule_match"]]

    fp_rate = len(false_positives) / len(clean) if clean else 0.0
    catch_rate = len(caught) / len(defective) if defective else 0.0
    exact_rule_recall = len(exact_caught) / len(defective) if defective else 0.0

    by_artist: dict[str, dict[str, Any]] = {}
    artist_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in results:
        artist_groups[r["artist_category"]].append(r)
    for cat, items in sorted(artist_groups.items()):
        c_items = [x for x in items if x["split"] == "clean"]
        d_items = [x for x in items if x["split"] == "defective"]
        by_artist[cat] = {
            "total": len(items),
            "clean_total": len(c_items),
            "clean_pass": sum(1 for x in c_items if x["passed"]),
            "clean_fp": sum(1 for x in c_items if not x["passed"]),
            "defective_total": len(d_items),
            "defective_caught": sum(1 for x in d_items if x["passed"]),
            "defective_exact_rule": sum(1 for x in d_items if x["exact_rule_match"]),
        }

    by_defect: dict[str, dict[str, Any]] = {}
    defect_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in defective:
        defect_groups[r["defect_category"] or "unknown"].append(r)
    for cat, items in sorted(defect_groups.items()):
        by_defect[cat] = {
            "total": len(items),
            "caught": sum(1 for x in items if x["passed"]),
            "exact_rule": sum(1 for x in items if x["exact_rule_match"]),
            "recall": round(sum(1 for x in items if x["exact_rule_match"]) / len(items), 4),
        }

    return {
        "git_sha": _git_sha(),
        "total_cases": len(results),
        "elapsed_seconds": total_s,
        "summary": {
            "clean_total": len(clean),
            "clean_passed": len(clean) - len(false_positives),
            "false_positives": len(false_positives),
            "false_positive_rate": round(fp_rate, 4),
            "clean_with_nonblocking_warnings": len(clean_warnings),
            "defective_total": len(defective),
            "defective_caught": len(caught),
            "defect_catch_rate": round(catch_rate, 4),
            "defective_exact_rule_match": len(exact_caught),
            "exact_rule_recall": round(exact_rule_recall, 4),
            "targets": {
                "max_fp_rate": 0.02,
                "min_catch_rate": 0.90,
                "fp_target_met": fp_rate < 0.02,
                "catch_target_met": catch_rate > 0.90,
                "exact_rule_target_met": exact_rule_recall > 0.90,
            },
        },
        "by_artist_category": by_artist,
        "by_defect_category": by_defect,
        "false_positive_cases": [r["case_id"] for r in false_positives],
        "missed_defect_cases": [r["case_id"] for r in missed],
        "cases": results,
    }


def render_markdown(payload: dict[str, Any]) -> str:
    """Render a crisp Markdown report for humans and swarm handoffs."""
    s = payload["summary"]
    t = s["targets"]
    lines = [
        "# Wild-50 `mint.check` Verification Report",
        "",
        f"- **Git SHA**: `{payload['git_sha']}`",
        f"- **Runtime**: {payload['elapsed_seconds']:.2f}s across {payload['total_cases']} figures",
        "",
        "## Headline Metrics",
        "",
        "| Metric | Result | Target | Status |",
        "| --- | --- | --- | --- |",
        f"| Clean False-Positive Rate | {s['false_positives']}/{s['clean_total']} ({s['false_positive_rate']*100:.1f}%) | < 2% (0/25) | {'PASS' if t['fp_target_met'] else 'FAIL'} |",
        f"| Defect Catch Rate (`ship=False`) | {s['defective_caught']}/{s['defective_total']} ({s['defect_catch_rate']*100:.1f}%) | > 90% (>= 23/25) | {'PASS' if t['catch_target_met'] else 'FAIL'} |",
        f"| Exact-Rule Recall | {s['defective_exact_rule_match']}/{s['defective_total']} ({s['exact_rule_recall']*100:.1f}%) | > 90% (>= 23/25) | {'PASS' if t['exact_rule_target_met'] else 'FAIL'} |",
        f"| Clean with Non-Blocking Warnings | {s['clean_with_nonblocking_warnings']}/{s['clean_total']} | 0 (advisory) | INFO |",
        "",
        "## Breakdown by Defect Category",
        "",
        "| Defect Rule | Total | Caught (`ship=False`) | Exact-Rule Match | Recall |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for cat, stats in payload["by_defect_category"].items():
        lines.append(
            f"| `{cat}` | {stats['total']} | {stats['caught']} | "
            f"{stats['exact_rule']} | {stats['recall']*100:.0f}% |"
        )

    lines += [
        "",
        "## Breakdown by Artist Category",
        "",
        "| Artist Category | Total | Clean Pass | Clean FP | Defect Caught | Defect Exact Rule |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for cat, stats in payload["by_artist_category"].items():
        lines.append(
            f"| `{cat}` | {stats['total']} | {stats['clean_pass']}/{stats['clean_total']} | "
            f"{stats['clean_fp']} | {stats['defective_caught']}/{stats['defective_total']} | "
            f"{stats['defective_exact_rule']}/{stats['defective_total']} |"
        )

    fps = [r for r in payload["cases"] if r["split"] == "clean" and not r["actual_ship"]]
    lines += ["", "## False Positives on Clean Cases", ""]
    if not fps:
        lines.append("None (0/25 false positives).")
    else:
        lines += [
            "| Case ID | Artist | Triggered Rules | Unmatched Tokens / Detail |",
            "| --- | --- | --- | --- |",
        ]
        for r in fps:
            rules = ", ".join(f"`{x}`" for x in r["actual_rules"]) or "none"
            if r["unmatched_claim_numbers"]:
                detail = "; ".join(
                    f"`{u['text']}`" + (f" (nearest: {u['nearest']})" if u.get("nearest") else "")
                    for u in r["unmatched_claim_numbers"]
                )
            else:
                detail = "; ".join(i["message"] for i in r["issues"][:2])
            lines.append(f"| `{r['case_id']}` | `{r['artist_category']}` | {rules} | {detail} |")

    clean_warns = [
        r for r in payload["cases"] if r["split"] == "clean" and r["actual_ship"] and r["actual_rules"]
    ]
    if clean_warns:
        lines += ["", "## Clean Cases with Non-Blocking Warnings", ""]
        lines += [
            "| Case ID | Artist | Warning Rules | Detail |",
            "| --- | --- | --- | --- |",
        ]
        for r in clean_warns:
            rules = ", ".join(f"`{x}`" for x in r["actual_rules"])
            detail = "; ".join(i["message"] for i in r["issues"][:2])
            lines.append(f"| `{r['case_id']}` | `{r['artist_category']}` | {rules} | {detail} |")

    missed = [r for r in payload["cases"] if r["split"] == "defective" and not r["exact_rule_match"]]
    lines += ["", "## Missed Defects / Wrong Rule on Defective Cases", ""]
    if not missed:
        lines.append("None (25/25 exact-rule matches).")
    else:
        lines += [
            "| Case ID | Artist | Expected Rule(s) | Actual `ship` | Actual Rules | Panels Read |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        for r in missed:
            exp = ", ".join(f"`{x}`" for x in r["expected_rules"])
            act = ", ".join(f"`{x}`" for x in r["actual_rules"]) or "none"
            panels = ", ".join(str(k) for k in r["panel_kinds"])
            lines.append(
                f"| `{r['case_id']}` | `{r['artist_category']}` | {exp} | "
                f"`{r['actual_ship']}` | {act} | `{panels}` |"
            )

    # Structural extraction diagnostics (colorbar exclusion, QuadMesh/hist/boxplot/violin reading)
    struct_notes: list[tuple[str, str, str]] = []
    for r in payload["cases"]:
        cid = r["case_id"]
        cat = r["artist_category"]
        kinds = r["panel_kinds"]
        if cat == "quadmesh" and all(k == "empty" for k in kinds):
            struct_notes.append((cid, cat, f"QuadMesh not extracted (`panel_kinds={kinds}`)"))
        if ("colorbar" in cid or cat in {"quadmesh", "image_imshow"} or cid == "defect_21_rainbow_scatter_rainbow") and len(kinds) > 1:
            struct_notes.append((cid, cat, f"Colorbar included as extra panel (`panel_kinds={kinds}`)"))
        if cat == "histogram" and "bars" in kinds:
            struct_notes.append((cid, cat, f"Histogram read as categorical `bars` (`panel_kinds={kinds}`)"))
        if cat == "boxplot" and "lines" in kinds:
            struct_notes.append((cid, cat, f"Boxplot geometry read as `lines` (`panel_kinds={kinds}`)"))
        if cat == "violinplot" and all(k == "empty" for k in kinds):
            struct_notes.append((cid, cat, f"Violinplot not extracted (`panel_kinds={kinds}`)"))
    if struct_notes:
        lines += ["", "## Artist Extraction Diagnostics", ""]
        lines += [
            "| Case ID | Artist | Observation |",
            "| --- | --- | --- |",
        ]
        for cid, cat, obs in struct_notes:
            lines.append(f"| `{cid}` | `{cat}` | {obs} |")

    lines += ["", "## Full Case Matrix", ""]
    lines += [
        "| Case ID | Split | Artist | Expected | Actual `ship` | Expected Rules | Actual Rules | ms |",
        "| --- | --- | --- | --- | --- | --- | --- | ---: |",
    ]
    for r in payload["cases"]:
        exp = ", ".join(r["expected_rules"]) or "-"
        act = ", ".join(r["actual_rules"]) or "-"
        mark = "PASS" if r["exact_rule_match"] else "FAIL"
        lines.append(
            f"| `{r['case_id']}` | {r['split']} | `{r['artist_category']}` | "
            f"{mark} | `{r['actual_ship']}` | {exp} | {act} | {r['elapsed_ms']:.0f} |"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    out_dir = Path(__file__).resolve().parent
    payload = run_eval()
    json_path = out_dir / "report.json"
    md_path = out_dir / "REPORT.md"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(payload), encoding="utf-8")

    s = payload["summary"]
    print(
        f"Wild-50 evaluated in {payload['elapsed_seconds']:.2f}s "
        f"(sha={payload['git_sha']}): "
        f"FP={s['false_positives']}/{s['clean_total']} ({s['false_positive_rate']*100:.1f}%), "
        f"Catch={s['defective_caught']}/{s['defective_total']} ({s['defect_catch_rate']*100:.1f}%), "
        f"ExactRule={s['defective_exact_rule_match']}/{s['defective_total']} "
        f"({s['exact_rule_recall']*100:.1f}%)"
    )
    print(f"Wrote {md_path} and {json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
