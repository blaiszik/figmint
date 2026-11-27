"""Tests for figure-bench v0.1 open leaderboard, site builder, human study app, and PR CI."""

from __future__ import annotations

import copy
import json
import re
import struct
import sys
import zlib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
BENCH_DIR = REPO_ROOT / "evals" / "figure_bench"
LEADERBOARD_DIR = BENCH_DIR / "leaderboard"
SUBMISSIONS_DIR = LEADERBOARD_DIR / "submissions"
SITE_HTML = BENCH_DIR / "site" / "index.html"
HUMAN_STUDY_HTML = BENCH_DIR / "human_study" / "index.html"
WORKFLOW_YML = REPO_ROOT / ".github" / "workflows" / "figure-bench-verify.yml"

if str(LEADERBOARD_DIR) not in sys.path:
    sys.path.insert(0, str(LEADERBOARD_DIR))

import build_site
import verify_submission


def _write_minimal_png(path: Path, width: int = 700, height: int = 420) -> None:
    """Write a valid minimal RGB PNG with exact IHDR dimensions (pure stdlib)."""
    path.parent.mkdir(parents=True, exist_ok=True)

    def _chunk(tag: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    raw_scanline = b"\x00" + (b"\xff\xff\xff" * width)
    idat = zlib.compress(raw_scanline * height, level=1)
    blob = (
        verify_submission.PNG_SIGNATURE
        + _chunk(b"IHDR", ihdr)
        + _chunk(b"IDAT", idat)
        + _chunk(b"IEND", b"")
    )
    path.write_bytes(blob)


def _load_seed(name: str) -> dict:
    return json.loads((SUBMISSIONS_DIR / name).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# 1. Seed submissions & verify_submission.py
# ---------------------------------------------------------------------------


def test_all_three_seed_submissions_pass_verification() -> None:
    seed_files = sorted(SUBMISSIONS_DIR.glob("*.json"))
    assert len(seed_files) >= 6

    for path in seed_files:
        errors = verify_submission.verify_submission_file(path)
        assert errors == [], f"{path.name} failed verification: {errors}"

    # Verify full 100-task and 60-task v0.1 sweep entries exist and pass invariants
    for name in (
        "v01_all100_mintfig_sonnet55.json",
        "v01_all100_matplotlib_hook_sonnet55.json",
        "v01_all100_matplotlib_plain_sonnet55.json",
    ):
        sub = _load_seed(name)
        assert sub["split"] == "all"
        assert sub["task_count"] == 100
        assert len(sub["per_task"]) == 100
        assert "timing_summary" in sub["provenance"]
        assert sub["per_task"][0].get("timing") is not None

    for name in (
        "v01_all60_mintfig_sonnet55.json",
        "v01_all60_matplotlib_hook_sonnet55.json",
        "v01_all60_matplotlib_plain_sonnet55.json",
    ):
        sub = _load_seed(name)
        assert sub["split"] == "all"
        assert sub["task_count"] == 60
        assert len(sub["per_task"]) == 60

    # CLI exit code 0 on submissions directory
    assert verify_submission.main([str(SUBMISSIONS_DIR)]) == 0


def test_seed_submissions_reflect_honest_initial_15_metadata() -> None:
    r6 = _load_seed("v01_seed_r6_mintfig_sonnet55.json")
    b1 = _load_seed("v01_seed_b1_matplotlib_told_sonnet55.json")
    u1 = _load_seed("v01_seed_u1_matplotlib_plain_sonnet55.json")

    for sub in (r6, b1, u1):
        assert sub["schema_version"] == "0.1"
        assert sub["split"] == "v0.1-initial-15"
        assert sub["work_in_progress"] is True
        assert sub["task_count"] == 15
        assert len(sub["per_task"]) == 15
        assert sub["provenance"]["source_report"] == "evals/figure_bench/runs/compare_r6_b1_u1.md"

    assert r6["scores"]["visual_quality"] == 100.0
    assert r6["scores"]["claim_accuracy"] == 100.0
    assert r6["scores"]["median_seconds"] == 16.6
    assert b1["scores"]["visual_quality"] == 100.0
    assert b1["scores"]["claim_accuracy"] == pytest.approx(26.7, abs=0.1)
    assert b1["scores"]["median_seconds"] == 19.5
    assert u1["scores"]["visual_quality"] == pytest.approx(13.3, abs=0.1)
    assert u1["scores"]["median_seconds"] == 14.8


def test_verify_submission_rejects_tampered_aggregates(tmp_path: Path) -> None:
    tampered = _load_seed("v01_seed_u1_matplotlib_plain_sonnet55.json")
    tampered["scores"]["composite"] = 99.5
    tampered["scores"]["visual_quality"] = 95.0

    errors = verify_submission.verify_submission_data(tampered)
    assert any("scores.composite" in e and "does not match" in e for e in errors)
    assert any("scores.visual_quality" in e and "does not match" in e for e in errors)

    out = tmp_path / "tampered.json"
    out.write_text(json.dumps(tampered), encoding="utf-8")
    assert verify_submission.main([str(out)]) == 1


def test_verify_submission_rejects_missing_required_fields() -> None:
    broken = _load_seed("v01_seed_r6_mintfig_sonnet55.json")
    del broken["model"]
    del broken["provenance"]["reproduce_command"]
    broken["split"] = "invalid-split"

    errors = verify_submission.verify_submission_data(broken)
    assert any("missing required top-level field: 'model'" in e for e in errors)
    assert any("provenance.reproduce_command" in e for e in errors)
    assert any("split:" in e for e in errors)


def test_verify_submission_rejects_mismatched_task_count_and_duplicate_tasks() -> None:
    broken = _load_seed("v01_seed_r6_mintfig_sonnet55.json")
    broken["task_count"] = 16
    broken["per_task"][1]["task_id"] = broken["per_task"][0]["task_id"]

    errors = verify_submission.verify_submission_data(broken)
    assert any("task_count (16) does not match len(per_task) (15)" in e for e in errors)
    assert any("duplicate task_id" in e for e in errors)


def test_verify_submission_checks_artifacts_dir_png_existence_and_dimensions(
    tmp_path: Path,
) -> None:
    sub = _load_seed("v01_seed_r6_mintfig_sonnet55.json")
    sub["per_task"] = copy.deepcopy(sub["per_task"][:2])
    sub["task_count"] = 2
    sub["scores"] = verify_submission.compute_aggregates(sub["per_task"])
    sub["artifacts_dir"] = "figs"

    figs_dir = tmp_path / "figs"
    _write_minimal_png(figs_dir / "01_ablation" / "figure.png", width=700, height=400)
    _write_minimal_png(figs_dir / "02_ab_latency" / "figure.png", width=700, height=400)

    # Valid artifacts pass
    assert verify_submission.verify_submission_data(sub, base_dir=tmp_path) == []

    # Tiny PNG rejected
    _write_minimal_png(figs_dir / "02_ab_latency" / "figure.png", width=24, height=24)
    errs_tiny = verify_submission.verify_submission_data(sub, base_dir=tmp_path)
    assert any("tiny dimensions" in e for e in errs_tiny)

    # Missing PNG rejected
    (figs_dir / "02_ab_latency" / "figure.png").unlink()
    errs_missing = verify_submission.verify_submission_data(sub, base_dir=tmp_path)
    assert any("missing PNG for task '02_ab_latency'" in e for e in errs_missing)


# ---------------------------------------------------------------------------
# 2. Static Leaderboard & Visual Explorer (build_site.py -> site/index.html)
# ---------------------------------------------------------------------------


def test_build_site_generates_self_contained_html_with_all_seed_submissions(
    tmp_path: Path,
) -> None:
    out_html = tmp_path / "index.html"
    built = build_site.build_site(submissions_dir=SUBMISSIONS_DIR, output_path=out_html)
    assert built == out_html
    text = out_html.read_text(encoding="utf-8")

    # Zero external CDN / script / stylesheet links
    for forbidden in (
        "cdn.jsdelivr.net",
        "unpkg.com",
        "cdnjs.cloudflare.com",
        "fonts.googleapis.com",
        '<script src="http',
        '<link rel="stylesheet" href="http',
    ):
        assert forbidden not in text

    # Header badge & all 3 seed submissions present
    assert "figure-bench v0.1 (work in progress)" in text
    for seed_id in (
        "v01-seed-r6-mintfig-sonnet55",
        "v01-seed-b1-matplotlib-told-sonnet55",
        "v01-seed-u1-matplotlib-plain-sonnet55",
    ):
        assert seed_id in text

    # Side-by-side comparison controls and all 6 tracks present
    assert "Side-by-Side Task Comparison Explorer" in text
    assert 'id="cmp-left"' in text and 'id="cmp-right"' in text and 'id="cmp-task"' in text
    for track_id in (
        "science_uncertainty",
        "swe_coding",
        "epistemic_traps",
        "multiturn_edit",
        "multi_surface",
        "byo_repair",
    ):
        assert track_id in text

    # Committed site/index.html also exists and matches structure
    assert SITE_HTML.is_file()
    committed = SITE_HTML.read_text(encoding="utf-8")
    assert "v01-seed-r6-mintfig-sonnet55" in committed
    assert "figure-bench v0.1 (work in progress)" in committed


def test_build_site_embeds_bundled_artifact_pngs(tmp_path: Path) -> None:
    sub_dir = tmp_path / "subs"
    sub_dir.mkdir()
    sub = _load_seed("v01_seed_r6_mintfig_sonnet55.json")
    sub["per_task"] = copy.deepcopy(sub["per_task"][:1])
    sub["task_count"] = 1
    sub["scores"] = verify_submission.compute_aggregates(sub["per_task"])
    sub["artifacts_dir"] = "arts"
    _write_minimal_png(sub_dir / "arts" / "01_ablation" / "figure.png", width=700, height=350)
    (sub_dir / "one.json").write_text(json.dumps(sub), encoding="utf-8")

    out_html = tmp_path / "site.html"
    build_site.build_site(submissions_dir=sub_dir, output_path=out_html, embed_images=True)
    html = out_html.read_text(encoding="utf-8")
    assert "data:image/png;base64," in html


# ---------------------------------------------------------------------------
# 3. Single-File Human Blind Reader Study App
# ---------------------------------------------------------------------------


def test_human_study_app_has_display_width_lock_timer_rubric_and_export() -> None:
    assert HUMAN_STUDY_HTML.is_file()
    html = HUMAN_STUDY_HTML.read_text(encoding="utf-8")

    # Zero CDN
    for forbidden in ("cdn.jsdelivr.net", "unpkg.com", "fonts.googleapis.com", '<script src="http'):
        assert forbidden not in html

    # Display-width lock (700 px and 450 px, zoom disabled)
    assert "locked-figure-box" in html
    assert "700" in html and "450" in html
    assert "pointer-events: none" in html
    assert "zoom disabled" in html

    # 3 structured rubric questions + confidence slider
    assert "ans-primary" in html
    assert "ans-uncertainty" in html
    assert "ans-nuance" in html
    assert 'id="ans-confidence"' in html and 'type="range"' in html

    # High-precision timer & anonymized JSON export
    assert "performance.now()" in html
    assert "downloadJson" in html
    assert "human_study_" in html
    assert "answers.json" in html


# ---------------------------------------------------------------------------
# 4. PR Verification GitHub Actions Workflow
# ---------------------------------------------------------------------------


def test_figure_bench_verify_workflow_structure_and_safe_quoting() -> None:
    assert WORKFLOW_YML.is_file()
    raw = WORKFLOW_YML.read_text(encoding="utf-8")

    # Optional PyYAML check if installed in environment
    try:
        import yaml  # type: ignore[import-not-found]
    except ImportError:
        yaml = None

    if yaml is not None:
        parsed = yaml.safe_load(raw)
        assert isinstance(parsed, dict)
        on_block = parsed.get("on") or parsed.get(True)
        assert "pull_request" in on_block
        paths = on_block["pull_request"]["paths"]
        assert "evals/figure_bench/leaderboard/submissions/**" in paths
        assert "evals/figure_bench/tasks/**" in paths
        assert "evals/figure_bench/public_test/**" in paths
        assert "evals/figure_bench/heldout/**" in paths
    else:
        # Pure-stdlib structural verification (no tabs, valid top-level keys, expected path triggers)
        assert "\t" not in raw
        for key in ("name:", "on:", "  pull_request:", "    paths:", "permissions:", "jobs:"):
            assert key in raw
        for expected_path in (
            "evals/figure_bench/leaderboard/submissions/**",
            "evals/figure_bench/tasks/**",
            "evals/figure_bench/public_test/**",
            "evals/figure_bench/heldout/**",
        ):
            assert expected_path in raw

    # Must invoke both submission verification and task validation
    assert "evals/figure_bench/leaderboard/verify_submission.py" in raw
    assert "evals/figure_bench/bench.py validate-tasks" in raw

    # Safe quoting check: no raw ${{ ... }} inside run: blocks
    in_run_block = False
    run_indent = 0
    for line in raw.splitlines():
        stripped = line.lstrip(" ")
        indent = len(line) - len(stripped)
        if re.match(r"^-?\s*run:\s*", stripped):
            rest = re.sub(r"^-?\s*run:\s*", "", stripped)
            assert "${{" not in rest, f"Unsafe raw interpolation in run line: {line}"
            in_run_block = rest.startswith(("|", ">"))
            run_indent = indent
            continue
        if in_run_block:
            if stripped and indent <= run_indent:
                in_run_block = False
            else:
                assert "${{" not in line, f"Unsafe raw interpolation in run block: {line}"
