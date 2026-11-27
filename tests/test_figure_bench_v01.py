"""Comprehensive test suite for figure-bench v0.1 scoring engine and CLI."""

from __future__ import annotations

import ast
import importlib.util
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pytest
from PIL import Image

HERE = Path(__file__).resolve().parents[1] / "evals" / "figure_bench"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

svg_audit = _load("svg_audit", HERE / "svg_audit.py")
pixel_audit = _load("pixel_audit", HERE / "pixel_audit.py")
rubric = _load("rubric", HERE / "rubric.py")
bench = _load("figure_bench_v01_mod", HERE / "bench.py")


@pytest.fixture(autouse=True)
def _close_figs():
    yield
    plt.close("all")


# --------------------------------------------------------------------------- svg_audit tests


def test_svg_audit_clean_figure(tmp_path: Path) -> None:
    svg = tmp_path / "clean.svg"
    svg.write_text(
        """<svg xmlns="http://www.w3.org/2000/svg" width="700" height="420" viewBox="0 0 700 420">
        <style>.axis-label { font-size: 13px; }</style>
        <g id="title"><text x="40" y="34" font-size="18">Reranker gains 1.6 points (mean ± SD, 5 seeds)</text></g>
        <g class="grid"><line x1="60" y1="200" x2="640" y2="200" stroke="#dddddd" stroke-width="1"/></g>
        <polyline points="80,300 300,250 600,150" fill="none" stroke="#1f77b4" stroke-width="2"/>
        <text x="60" y="380" class="axis-label">Baseline</text>
        <text x="420" y="380" class="axis-label">With reranker</text>
        <g transform="translate(30, 220) rotate(-90)">
          <text x="0" y="0" font-size="13" text-anchor="middle">Accuracy (%)</text>
        </g>
        </svg>""",
        encoding="utf-8",
    )
    res = svg_audit.audit_svg(svg, display_width_px=700)
    checks = {c["name"]: c["passed"] for c in svg_audit.svg_checks(res)}
    assert all(checks.values()), res
    assert res["texts"] == 4
    assert res["min_text_px"] == pytest.approx(13.0, abs=0.1)
    assert res["uncertainty_named"] is True
    assert "Reranker gains 1.6 points (mean ± SD, 5 seeds)" in res["headlines"]
    assert "Baseline" in res["text_strings"]


def test_svg_audit_flags_small_overlap_struck_clipped_and_malformed(tmp_path: Path) -> None:
    svg = tmp_path / "bad.svg"
    svg.write_text(
        """<svg xmlns="http://www.w3.org/2000/svg" width="1400" height="500" viewBox="0 0 1400 500">
        <text x="100" y="100" font-size="14">Small at 700px</text>
        <text x="300" y="200" font-size="28">First label</text>
        <text x="305" y="202" font-size="28">Second label</text>
        <path d="M 280 280 L 520 280" fill="none" stroke="#d62728" stroke-width="3"/>
        <text x="320" y="285" font-size="28">Struck text</text>
        <text x="1360" y="150" font-size="28">Runs past right edge</text>
        <text x="100" y="400" font-size="28"><tspan>Share of Share of 40%% -5 nan</tspan></text>
        </svg>""",
        encoding="utf-8",
    )
    res = svg_audit.audit_svg(svg, display_width_px=700)
    checks = {c["name"]: c["passed"] for c in svg_audit.svg_checks(res)}
    assert res["min_text_px"] == pytest.approx(7.0, abs=0.1)
    assert checks["text_legible"] is False
    assert checks["no_text_overlap"] is False
    assert checks["no_text_struck_by_lines"] is False
    assert checks["no_text_clipped"] is False
    assert checks["text_well_formed"] is False
    assert len(res["text_faults"]) >= 4


def test_svg_audit_matplotlib_svg_fonttype_none(tmp_path: Path) -> None:
    svg = tmp_path / "mpl.svg"
    with plt.rc_context({"svg.fonttype": "none"}):
        fig, ax = plt.subplots(figsize=(6, 4))
        ax.bar(["A", "B"], [10, 14])
        ax.set_title("Gain of 4 units (95% CI)")
        fig.tight_layout()
        fig.savefig(svg)
    res = svg_audit.audit_svg(svg, display_width_px=700)
    assert res["texts"] >= 3
    assert res["uncertainty_named"] is True
    assert any("Gain of 4 units" in s for s in res["text_strings"])


# --------------------------------------------------------------------------- pixel_audit tests


def test_pixel_audit_zero_mintfig_imports() -> None:
    tree = ast.parse((HERE / "pixel_audit.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not alias.name.startswith("mintfig")
        elif isinstance(node, ast.ImportFrom):
            assert not (node.module or "").startswith("mintfig")


def test_pixel_audit_rainbow_vs_safe_and_discrete_palettes(tmp_path: Path) -> None:
    grid = np.linspace(0, 1, 256).reshape(16, 16)
    for bad_cmap in ("jet", "rainbow", "hsv", "gist_rainbow", "nipy_spectral"):
        p = tmp_path / f"{bad_cmap}.png"
        fig, ax = plt.subplots(figsize=(5, 4))
        ax.imshow(grid, cmap=bad_cmap)
        fig.savefig(p, dpi=100)
        plt.close(fig)
        res = pixel_audit.audit_png(p)
        assert res["rainbow_colormap_suspected"] is True, f"missed {bad_cmap}: {res}"

    for safe_cmap in ("viridis", "plasma", "inferno", "cividis", "coolwarm", "RdBu"):
        p = tmp_path / f"{safe_cmap}.png"
        fig, ax = plt.subplots(figsize=(5, 4))
        ax.imshow(grid, cmap=safe_cmap)
        fig.savefig(p, dpi=100)
        plt.close(fig)
        res = pixel_audit.audit_png(p)
        assert res["rainbow_colormap_suspected"] is False, f"false positive on {safe_cmap}: {res}"

    # Discrete 3-, 4-, 5-color categorical bar plots MUST NEVER false-positive
    for n in (3, 4, 5):
        p = tmp_path / f"discrete_{n}.png"
        fig, ax = plt.subplots(figsize=(6, 4))
        ax.bar(range(n), [3, 5, 4, 6, 2][:n], color=plt.cm.tab10.colors[:n])
        ax.set_title("Discrete categorical chart")
        fig.tight_layout()
        fig.savefig(p, dpi=100)
        plt.close(fig)
        res = pixel_audit.audit_png(p)
        assert res["rainbow_colormap_suspected"] is False, f"FP on {n}-color discrete chart: {res}"
        assert res["empty_canvas"] is False
        assert res["edge_clipped"] is False


def test_pixel_audit_empty_edge_clipped_dark_and_cvd(tmp_path: Path) -> None:
    # Blank white canvas -> empty_canvas
    blank = tmp_path / "blank.png"
    Image.new("RGB", (400, 300), (255, 255, 255)).save(blank)
    res_blank = pixel_audit.audit_png(blank)
    assert res_blank["empty_canvas"] is True
    assert res_blank["ink_fraction"] < 0.002

    # Edge-clipped ink (solid bar touching right edge)
    clipped = tmp_path / "clipped.png"
    arr = np.full((300, 400, 3), 255, dtype=np.uint8)
    arr[40:260, 200:400] = (30, 80, 180)
    Image.fromarray(arr).save(clipped)
    res_clip = pixel_audit.audit_png(clipped)
    assert res_clip["edge_clipped"] is True
    assert res_clip["edge_ink_ratio"] > 0.05

    # Dark surface with dark bg + crisp light ink passes
    dark_ok = tmp_path / "dark_ok.png"
    arr_d = np.full((300, 400, 3), (18, 24, 38), dtype=np.uint8)
    arr_d[60:220, 60:140] = (96, 165, 250)
    arr_d[100:220, 180:260] = (248, 250, 252)
    Image.fromarray(arr_d).save(dark_ok)
    res_dark = pixel_audit.audit_png(dark_ok, surface="dark")
    assert res_dark["is_dark_background"] is True
    assert res_dark["cvd_ok"] is True
    assert res_dark["grayscale_ok"] is True
    assert res_dark["issues"] == []

    # Isoluminant red vs green collision under deuteranopia
    rg = tmp_path / "rg_collision.png"
    arr_rg = np.full((300, 400, 3), 255, dtype=np.uint8)
    arr_rg[60:240, 50:170] = (210, 60, 50)
    arr_rg[60:240, 220:340] = (80, 145, 55)
    Image.fromarray(arr_rg).save(rg)
    res_rg = pixel_audit.audit_png(rg)
    assert res_rg["cvd_collision_suspected"] is True
    assert res_rg["cvd_ok"] is False


def test_render_at_display_width_downscales_and_strips_metadata(tmp_path: Path) -> None:
    import mintfig as mint

    wide_png = tmp_path / "wide.png"
    mint.explain(
        "Accuracy drops 8 points",
        mint.compare({"full": 82.0, "no retrieval": 74.0}, label="Accuracy", unit="%"),
    ).save(wide_png)
    assert b"mintfig:takeaway" in wide_png.read_bytes()

    out_png = tmp_path / "shown.png"
    sw, sh = pixel_audit.render_at_display_width(wide_png, out_png, width_px=450)
    assert sw == 450
    assert sh > 0
    assert b"mintfig:" not in out_png.read_bytes()

    # Never upscales a narrower image
    small_png = tmp_path / "small.png"
    Image.new("RGB", (320, 200), (255, 255, 255)).save(small_png)
    nw, nh = pixel_audit.render_at_display_width(small_png, tmp_path / "small_out.png", width_px=700)
    assert (nw, nh) == (320, 200)


# --------------------------------------------------------------------------- rubric tests


def test_rubric_legacy_fallback_and_validation() -> None:
    tasks = rubric.discover_task_dirs(HERE)
    assert len(tasks) >= 15
    for tdir in tasks:
        errs = rubric.validate_task_dir(tdir)
        assert errs == [], f"{tdir.name} failed validation: {errs}"
        rub = rubric.load_rubric(tdir)
        assert rub["schema_version"] == "0.1"
        assert rub["split"] in rubric.VALID_SPLITS
        assert rub["track"] in rubric.VALID_TRACKS
        assert rub["accept"]


def test_rubric_validate_catches_invalid_task(tmp_path: Path) -> None:
    bad = tmp_path / "public_test" / "pt99_broken"
    bad.mkdir(parents=True)
    (bad / "context.md").write_text("", encoding="utf-8")
    (bad / "rubric.json").write_text(
        json.dumps(
            {
                "schema_version": "0.0",
                "id": "wrong_id",
                "split": "dev",
                "track": "unknown_track",
                "domain": "",
                "title": "Test",
                "display_width_px": -10,
                "surface": "mars",
                "what": "something",
                "accept": [],
                "rel_tol": -0.1,
                "abs_tol": 0.0,
                "uncertainty_required": "yes",
                "no_effect_trap": False,
                "reader_questions": [{"kind": "primary", "question": "", "expected": ""}],
            }
        ),
        encoding="utf-8",
    )
    errs = rubric.validate_task_dir(bad)
    assert any("context.md is empty" in e for e in errs)
    assert any("missing data/" in e for e in errs)
    assert any("schema_version" in e for e in errs)
    assert any("does not match directory name" in e for e in errs)
    assert any("does not match parent folder" in e for e in errs)
    assert any("track" in e for e in errs)
    assert any("surface" in e for e in errs)
    assert any("display_width_px" in e for e in errs)


def test_rubric_score_no_effect_trap_and_terminal_surface(tmp_path: Path) -> None:
    png = tmp_path / "figure.png"
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.bar(["Control", "Treatment"], [10.0, 10.2], yerr=[0.8, 0.9], color=["#4e79a7", "#f28e2b"])
    ax.set_title("Control vs Treatment (n = 20, 95% CI)")
    fig.tight_layout()
    fig.savefig(png, dpi=100)
    plt.close(fig)

    trap_rubric = {
        "schema_version": "0.1",
        "id": "pt20_null_trap",
        "split": "public-test",
        "track": "epistemic_traps",
        "domain": "Clinical",
        "title": "Null treatment effect",
        "display_width_px": 700,
        "surface": "chat",
        "what": "observed difference +0.2 is within 95% CI noise",
        "accept": [0.2],
        "rel_tol": 0.2,
        "abs_tol": 0.1,
        "uncertainty_required": True,
        "no_effect_trap": True,
        "forbidden_overclaim_phrases": ["dramatic victory"],
        "required_disclosures": [],
        "reader_questions": [],
    }

    # Overclaiming reply MUST fail uncertainty_calibration
    overclaim_reply = (
        "Treatment clearly beats control by +0.2 points (95% CI) and proves a real effect.\n\n"
        "![Null](figure.png)\n"
    )
    res_bad = rubric.score_submission(trap_rubric, png_path=png, reply_text=overclaim_reply)
    assert res_bad["uncertainty_calibration"]["overclaim_detected"] is True
    assert res_bad["uncertainty_calibration"]["passed"] is False
    assert res_bad["uncertainty_calibration"]["score"] == 0.0
    assert res_bad["passed"] is False

    # Properly hedged / negated reply MUST pass
    hedged_reply = (
        "Observed difference is +0.2 (95% CI crosses 0, n = 20); this does not prove a real effect "
        "and sits within noise.\n\n![Null](figure.png)\n"
    )
    res_good = rubric.score_submission(trap_rubric, png_path=png, reply_text=hedged_reply)
    assert res_good["uncertainty_calibration"]["overclaim_detected"] is False
    assert res_good["uncertainty_calibration"]["passed"] is True
    assert res_good["uncertainty_calibration"]["score"] == 100.0
    assert res_good["claim_accuracy"]["passed"] is True
    assert res_good["delivery"]["passed"] is True
    assert res_good["passed"] is True
    assert res_good["composite"] == 100.0

    # Terminal surface scores fenced text without needing a PNG
    term_rubric = {
        **trap_rubric,
        "id": "pt21_terminal",
        "surface": "terminal",
        "display_width_px": 72,
        "no_effect_trap": False,
        "uncertainty_required": False,
        "accept": [42.0],
        "abs_tol": 1.0,
    }
    term_reply = (
        "Peak throughput hits 42 req/s:\n\n"
        "```text\n"
        "Service    Throughput\n"
        "api        ████████████ 42 req/s\n"
        "worker     ██████       21 req/s\n"
        "```\n"
    )
    res_term = rubric.score_submission(term_rubric, png_path=None, reply_text=term_reply)
    assert res_term["visual_quality"]["passed"] is True
    assert res_term["delivery"]["passed"] is True
    assert res_term["passed"] is True


# --------------------------------------------------------------------------- bench.py CLI & arms tests


def test_bench_version_list_validate_and_new_task(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert bench.BENCH_VERSION == "0.1"

    bench.main(["list", "--split", "heldout"])
    out = capsys.readouterr().out
    assert "h1_survey" in out
    assert "01_ablation" not in out

    bench.main(["validate-tasks"])
    val_out = capsys.readouterr().out
    assert "0 failed" in val_out

    # Scaffold a brand new public-test task in an isolated base-dir and validate it
    bench.main([
        "new-task",
        "--id", "pt01_demo_task",
        "--split", "public-test",
        "--track", "science_uncertainty",
        "--domain", "Clinical",
        "--base-dir", str(tmp_path),
    ])
    created = tmp_path / "public_test" / "pt01_demo_task"
    assert (created / "context.md").is_file()
    assert (created / "data" / "sample.csv").is_file()
    assert (created / "rubric.json").is_file()

    bench.main(["validate-tasks", "--split", "public-test", "--base-dir", str(tmp_path)])
    assert "1 passed, 0 failed" in capsys.readouterr().out

    # Corrupt the rubric and verify validate-tasks exits 1
    (created / "rubric.json").write_text('{"schema_version": "bad"}', encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        bench.main(["validate-tasks", "--split", "public-test", "--base-dir", str(tmp_path)])
    assert exc.value.code == 1


def test_grade_dir_end_to_end(tmp_path: Path) -> None:
    # Build two outputs for existing dev tasks: 01_ablation (PNG + SVG + reply) and 02_ab_latency (PNG + reply)
    outputs = tmp_path / "outputs"
    t1 = outputs / "01_ablation"
    t2 = outputs / "02_ab_latency"
    t1.mkdir(parents=True)
    t2.mkdir(parents=True)

    with plt.rc_context({"svg.fonttype": "none"}):
        fig, ax = plt.subplots(figsize=(6, 4))
        ax.barh(["no reranker", "full model"], [80.5, 82.1], color=["#4e79a7", "#f28e2b"])
        ax.set_title("Reranker buys 1.6 points (5 seeds)")
        fig.tight_layout()
        fig.savefig(t1 / "figure.png", dpi=100)
        fig.savefig(t1 / "figure.svg")
        plt.close(fig)
    (t1 / "reply.md").write_text(
        "Removing the reranker costs 1.6 points across 5 seeds.\n\n![Ablation](figure.png)\n",
        encoding="utf-8",
    )
    (t1 / "timing.json").write_text(json.dumps({"seconds": 18.4}), encoding="utf-8")

    fig, ax = plt.subplots(figsize=(6, 4))
    ax.bar(["Old", "New"], [424.2, 340.7], color=["#76b7b2", "#4e79a7"])
    ax.set_title("New checkout cuts median latency by 83.5 ms")
    fig.tight_layout()
    fig.savefig(t2 / "figure.png", dpi=100)
    plt.close(fig)
    (t2 / "reply.md").write_text(
        "Median checkout latency fell by 83.5 ms (19.7%), trimming the right-skewed tail.\n\n"
        "![Latency](figure.png)\n",
        encoding="utf-8",
    )
    (t2 / "timing.json").write_text(json.dumps({"seconds": 22.0}), encoding="utf-8")

    meta_file = tmp_path / "meta.json"
    meta_file.write_text(
        json.dumps({"team": "test-team", "model": "demo-llm", "library": "altair", "hook_enabled": False}),
        encoding="utf-8",
    )
    out_json = tmp_path / "report.json"
    out_md = tmp_path / "report.md"

    bench.main([
        "grade-dir",
        str(outputs),
        "--split", "dev",
        "--meta", str(meta_file),
        "--out", str(out_json),
        "--markdown", str(out_md),
    ])

    report = json.loads(out_json.read_text(encoding="utf-8"))
    assert report["bench_version"] == "0.1"
    assert report["task_count"] == 2
    assert report["team"] == "test-team"
    assert report["library"] == "altair"
    assert report["scores"]["composite"] >= 95.0
    assert report["scores"]["delivery_rate"] == 100.0
    assert report["scores"]["median_seconds"] == pytest.approx(20.2, abs=0.1)
    assert report["per_task"]["01_ablation"]["visual_quality"]["source"] == "svg_audit+pixel_audit"
    assert report["per_task"]["02_ab_latency"]["visual_quality"]["source"] == "pixel_audit"
    assert out_md.is_file() and "01_ablation" in out_md.read_text(encoding="utf-8")


def test_matplotlib_hook_arm_and_custom_arm(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    run = tmp_path / "hook_run"
    bench.main([
        "start", "01_ablation", "--run", str(run), "--arm", "matplotlib-hook",
        "--python", sys.executable,
    ])
    start_out = capsys.readouterr().out
    assert "mint.check" in start_out

    script = tmp_path / "fig.py"
    script.write_text(
        """import matplotlib.pyplot as plt
fig, ax = plt.subplots(figsize=(6, 4))
ax.barh(["no reranker", "full model"], [80.5, 82.1])
ax.set_title("The reranker buys 1.6 points (5 seeds)")
fig.tight_layout()
fig.savefig("figure.png", dpi=100)
""",
        encoding="utf-8",
    )
    reply = tmp_path / "reply.md"
    reply.write_text("The reranker buys 1.6 points across 5 seeds.\n\n![Ablation](figure.png)\n", encoding="utf-8")

    bench.main(["submit", "01_ablation", str(script), "--run", str(run), "--reply", str(reply)])
    sub_out = capsys.readouterr().out
    assert "--- mint.check report ---" in sub_out
    assert "PASSED" in sub_out

    state = json.loads((run / "01_ablation" / ".bench" / "state.json").read_text(encoding="utf-8"))
    att = state["attempts"][0]
    assert att["passed"] is True
    assert "mint_check" in att
    assert att["mint_check"]["ship"] is True
    checks = {c["name"]: c["passed"] for c in att["checks"]}
    assert checks["no_mintfig"] is True

    # matplotlib-hook MUST still reject user scripts that import mintfig directly
    bad_run = tmp_path / "hook_bad_run"
    bench.main([
        "start", "01_ablation", "--run", str(bad_run), "--arm", "matplotlib-hook",
        "--python", sys.executable,
    ])
    bad_script = tmp_path / "bad_fig.py"
    bad_script.write_text("import mintfig\n" + script.read_text(encoding="utf-8"), encoding="utf-8")
    bench.main(["submit", "01_ablation", str(bad_script), "--run", str(bad_run)])
    bad_state = json.loads((bad_run / "01_ablation" / ".bench" / "state.json").read_text(encoding="utf-8"))
    bad_checks = {c["name"]: c["passed"] for c in bad_state["attempts"][0]["checks"]}
    assert bad_checks["no_mintfig"] is False
    assert bad_state["attempts"][0]["passed"] is False

    # Custom arm with --skill and --library
    custom_run = tmp_path / "custom_run"
    skill_md = tmp_path / "MY_SKILL.md"
    skill_md.write_text("# My Plot Skill\n", encoding="utf-8")
    bench.main([
        "start", "02_ab_latency", "--run", str(custom_run), "--arm", "custom",
        "--skill", str(skill_md), "--library", "seaborn", "--python", sys.executable,
    ])
    cout = capsys.readouterr().out
    assert "seaborn" in cout and "MY_SKILL.md" in cout
    bench.main(["submit", "02_ab_latency", str(script), "--run", str(custom_run), "--reply", str(reply)])
    cstate = json.loads((custom_run / "02_ab_latency" / ".bench" / "state.json").read_text(encoding="utf-8"))
    assert cstate["attempts"][0]["passed"] is True


def test_readers_prepare_downscales_to_display_width(tmp_path: Path) -> None:
    run = tmp_path / "wide_run"
    bench.main([
        "start", "01_ablation", "--run", str(run), "--arm", "matplotlib-plain",
        "--python", sys.executable,
    ])
    script = tmp_path / "wide.py"
    script.write_text(
        """import matplotlib.pyplot as plt
fig, ax = plt.subplots(figsize=(10, 5))
ax.barh(["no reranker", "full model"], [80.5, 82.1])
ax.set_title("Reranker gains 1.6 points")
fig.savefig("figure.png", dpi=150)
""",
        encoding="utf-8",
    )
    bench.main(["submit", "01_ablation", str(script), "--run", str(run)])

    # Default display width (700 px for chat task) downscales 1500px PNG to 700px
    readers_chat = tmp_path / "readers_chat"
    bench.main(["readers-prepare", str(run), "--out", str(readers_chat)])
    key = json.loads((readers_chat / "key.json").read_text(encoding="utf-8"))
    (fid, item), = key.items()
    copied = readers_chat / item["batch"] / fid / "figure.png"
    with Image.open(copied) as im:
        assert im.width == 700
    assert item["shown_px"][0] == 700

    # Explicit --display-width 450 downscales to 450px
    readers_narrow = tmp_path / "readers_narrow"
    bench.main(["readers-prepare", str(run), "--out", str(readers_narrow), "--display-width", "450"])
    key2 = json.loads((readers_narrow / "key.json").read_text(encoding="utf-8"))
    (fid2, item2), = key2.items()
    copied2 = readers_narrow / item2["batch"] / fid2 / "figure.png"
    with Image.open(copied2) as im:
        assert im.width == 450
    assert item2["display_width_px"] == 450


# --------------------------------------------------------------------------- 100-task suite, hardening & timing


def test_v01_suite_has_100_validated_tasks_with_full_rubrics() -> None:
    tasks = rubric.discover_task_dirs(HERE)
    assert len(tasks) == 100

    splits: dict[str, int] = {}
    tracks_by_split: dict[str, set[str]] = {}
    surfaces: set[str] = set()
    for tdir in tasks:
        assert rubric.validate_task_dir(tdir) == [], f"{tdir.name} failed validation"
        rub = rubric.load_rubric(tdir)
        assert rub["_source"] == "rubric.json", f"{tdir.name} missing canonical rubric.json"
        assert len(rub["reader_questions"]) >= 3, f"{tdir.name} has < 3 reader_questions"
        splits[rub["split"]] = splits.get(rub["split"], 0) + 1
        tracks_by_split.setdefault(rub["split"], set()).add(rub["track"])
        surfaces.add(rub["surface"])

    assert splits == {"dev": 25, "public-test": 50, "heldout": 25}
    for sp in ("dev", "public-test", "heldout"):
        assert tracks_by_split[sp] == set(rubric.VALID_TRACKS)
    assert {"chat", "narrow", "slide", "dark", "html", "terminal"} <= surfaces


def test_hardened_rubric_disclosures_overclaims_and_structural_checks(tmp_path: Path) -> None:
    import neutral

    # 1. Truncated bar chart detected by neutral.audit_saved_figure and penalized when forbid_truncated_bars=True
    trunc_png = tmp_path / "trunc.png"
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.bar(["A", "B"], [94.1, 95.8], color=["#4e79a7", "#f28e2b"])
    ax.set_ylim(93.0, 97.0)
    ax.set_title("Charger-D gains +1.7 pp (n = 6 units)")
    fig.tight_layout()
    fig.savefig(trunc_png, dpi=100)
    aud_trunc = neutral.audit_saved_figure(fig, trunc_png, dpi=100, tight=False)
    plt.close(fig)
    assert aud_trunc["truncated_bar_axes"], "should detect truncated bar y-axis"
    assert aud_trunc["has_log_axis"] is False
    assert any("Charger-D" in s for s in aud_trunc["all_texts"])

    rub_trunc = {
        "schema_version": "0.1", "id": "t_trunc", "split": "dev", "track": "epistemic_traps",
        "domain": "Power", "title": "Truncated bait", "display_width_px": 700, "surface": "chat",
        "what": "+1.7 pp gain", "accept": [1.7], "rel_tol": 0.1, "abs_tol": 0.1,
        "uncertainty_required": True, "no_effect_trap": False,
        "forbidden_overclaim_phrases": ["massive advantage"],
        "required_disclosures": ["n=6|6 units|s.d."],
        "forbid_truncated_bars": True, "require_log_scale": False, "min_panels": 0,
        "reader_questions": [],
    }
    # Non-trap task with forbidden_overclaim_phrases MUST allow normal comparative phrasing ("clearly higher")
    reply = "Charger-D is clearly higher by +1.7 pp across n = 6 units.\n\n![Eff](figure.png)\n"
    res = rubric.score_submission(rub_trunc, png_path=trunc_png, reply_text=reply, neutral_audit=aud_trunc)
    assert any("truncated_bar_baseline" in i for i in res["visual_quality"]["issues"])
    assert res["uncertainty_calibration"]["overclaim_detected"] is False
    assert res["uncertainty_calibration"]["missing_disclosures"] == []
    assert res["uncertainty_calibration"]["passed"] is True

    # 2. require_log_scale catches linear-scale figure and passes log-scale figure
    log_png = tmp_path / "log.png"
    fig2, ax2 = plt.subplots(figsize=(6, 4))
    ax2.plot([1, 10, 100, 1000], [1, 5, 25, 125])
    ax2.set_xscale("log")
    ax2.set_yscale("log")
    ax2.set_title("Log-log slope 0.70")
    fig2.tight_layout()
    fig2.savefig(log_png, dpi=100)
    aud_log = neutral.audit_saved_figure(fig2, log_png, dpi=100, tight=False)
    plt.close(fig2)
    assert aud_log["has_log_axis"] is True

    rub_log = {**rub_trunc, "forbid_truncated_bars": False, "require_log_scale": True, "uncertainty_required": False, "required_disclosures": []}
    res_lin = rubric.score_submission(rub_log, png_path=trunc_png, reply_text="Gain 1.7.\n\n![f](figure.png)\n", neutral_audit=aud_trunc)
    assert any("missing_log_scale" in i for i in res_lin["visual_quality"]["issues"])
    res_log = rubric.score_submission(rub_log, png_path=log_png, reply_text="Slope 1.7.\n\n![f](figure.png)\n", neutral_audit=aud_log)
    assert not any("missing_log_scale" in i for i in res_log["visual_quality"]["issues"])


def test_comprehensive_timing_capture_grade_and_export(tmp_path: Path) -> None:
    run = tmp_path / "timed_run"
    bench.main(["start", "01_ablation", "--run", str(run), "--arm", "matplotlib-hook", "--python", sys.executable])
    work = run / "01_ablation"
    script = tmp_path / "fig.py"
    script.write_text(
        """import matplotlib.pyplot as plt
fig, ax = plt.subplots(figsize=(6, 4))
ax.barh(["no reranker", "full model"], [80.5, 82.1])
ax.set_title("Reranker adds 1.6 points (5 seeds)")
fig.tight_layout()
fig.savefig("figure.png", dpi=100)
""",
        encoding="utf-8",
    )
    reply = tmp_path / "reply.md"
    reply.write_text("Reranker adds 1.6 points across 5 seeds.\n\n![Ablation](figure.png)\n", encoding="utf-8")
    bench.main(["submit", "01_ablation", str(script), "--run", str(run), "--reply", str(reply)])

    # Simulate sweep_timing.json and Claude CLI agent.log JSON output
    (work / ".bench" / "sweep_timing.json").write_text(
        json.dumps({"start_s": 0.4, "agent_wall_s": 9.2, "wall_s": 9.6, "timed_out": False}),
        encoding="utf-8",
    )
    (work / ".bench" / "agent.log").write_text(
        json.dumps({
            "type": "result", "subtype": "success", "duration_ms": 9100, "duration_api_ms": 7800,
            "ttft_ms": 620, "num_turns": 4, "total_cost_usd": 0.042,
            "usage": {"input_tokens": 100, "output_tokens": 420, "output_tokens_details": {"thinking_tokens": 80}},
        }),
        encoding="utf-8",
    )

    # Check per-task timing.json written on submit
    t_json = json.loads((work / ".bench" / "timing.json").read_text(encoding="utf-8"))
    assert t_json["attempts"] == 1
    assert t_json["total_render_s"] >= 0.0
    assert t_json["total_script_exec_s"] >= 0.0
    assert t_json["total_audit_s"] >= 0.0
    assert len(t_json["per_attempt"]) == 1
    assert "think_s" in t_json["per_attempt"][0]
    assert "delivery_check_s" in t_json["per_attempt"][0]

    # Grade run and verify timing_summary + parsed agent_cli + by_split + by_track
    bench.main(["grade", "--run", str(run)])
    results = json.loads((run / "results.json").read_text(encoding="utf-8"))
    assert "timing_summary" in results
    assert results["timing_summary"]["seconds_to_pass"]["count"] == 1
    assert results["timing_summary"]["cli_duration_s"]["median"] == pytest.approx(9.1, abs=0.05)
    assert results["timing_summary"]["cli_api_duration_s"]["median"] == pytest.approx(7.8, abs=0.05)
    assert "dev" in results["by_split"]
    assert "science_uncertainty" in results["by_track"]
    detail = results["tasks_detail"][0]
    assert detail["timing"]["agent_cli"]["num_turns"] == 4
    assert detail["timing"]["agent_cli"]["tokens"]["thinking_tokens"] == 80

    # Export submission and verify it passes verify_submission with timing fields intact
    sub_out = tmp_path / "submission.json"
    bench.main([
        "export-submission", "--run", str(run), "--out", str(sub_out),
        "--submission-id", "test-timed-run", "--model", "Test Model", "--split", "dev",
    ])
    sub_data = json.loads(sub_out.read_text(encoding="utf-8"))
    assert "timing_summary" in sub_data["provenance"]
    assert sub_data["per_task"][0]["timing"]["attempts"] == 1


def test_external_bridge_import_and_audit(tmp_path: Path) -> None:
    ext = _load("external_bridge", HERE / "external_bridge.py")

    # 1. Mock MatPlotBench import
    mpb_src = tmp_path / "mpb_src"
    (mpb_src / "data" / "1").mkdir(parents=True)
    (mpb_src / "data" / "1" / "points.csv").write_text("x,y\n1,2\n2,4\n", encoding="utf-8")
    (mpb_src / "benchmark_instructions.json").write_text(
        json.dumps([{"id": 1, "simple_instruction": "Plot y vs x from points.csv"}]),
        encoding="utf-8",
    )
    mpb_out = tmp_path / "mpb_tasks"
    m1 = ext.import_matplotbench(mpb_src, mpb_out)
    assert m1["count"] == 1
    assert (mpb_out / "mpb_1" / "context.md").is_file()
    assert (mpb_out / "mpb_1" / "data" / "points.csv").is_file()

    # 2. Mock PandasPlotBench import
    ppb_jsonl = tmp_path / "ppb.jsonl"
    ppb_jsonl.write_text(
        json.dumps({"id": "task-7", "task": "Bar chart of sales", "data_csv": "cat,val\nA,10\nB,20\n"}) + "\n",
        encoding="utf-8",
    )
    ppb_out = tmp_path / "ppb_tasks"
    m2 = ext.import_pandasplotbench(ppb_jsonl, ppb_out)
    assert m2["count"] == 1
    assert (ppb_out / "ppb_task-7" / "data" / "dataset.csv").is_file()

    # 3. Audit external outputs with --run-scripts + timing capture
    ext_outs = tmp_path / "ext_outputs"
    good = ext_outs / "mpb_1"
    bad = ext_outs / "mpb_2"
    good.mkdir(parents=True)
    bad.mkdir(parents=True)
    (good / "figure.py").write_text(
        """import matplotlib.pyplot as plt
fig, ax = plt.subplots(figsize=(6, 4))
ax.plot([1, 2, 3], [2, 4, 6])
ax.set_title("Linear growth (n = 3)")
fig.tight_layout()
fig.savefig("figure.png", dpi=100)
""",
        encoding="utf-8",
    )
    (good / "timing.json").write_text(json.dumps({"seconds": 12.5}), encoding="utf-8")
    (bad / "figure.py").write_text(
        """import matplotlib.pyplot as plt
import numpy as np
fig, ax = plt.subplots(figsize=(14, 6))
ax.imshow(np.linspace(0, 1, 64).reshape(8, 8), cmap="jet")
ax.set_title("Tiny title with %% typo", fontsize=6)
fig.savefig("figure.png", dpi=100)
""",
        encoding="utf-8",
    )
    rep = ext.audit_external_outputs(ext_outs, display_width_px=700, run_scripts=True, python_bin=sys.executable)
    assert rep["task_count"] == 2
    assert rep["per_task"]["mpb_1"]["clean"] is True
    assert rep["per_task"]["mpb_2"]["clean"] is False
    assert "banned_colormaps" in rep["per_task"]["mpb_2"]["defects"]
    assert "text_legible" in rep["per_task"]["mpb_2"]["defects"]
    assert rep["timing_summary"]["per_task_script_exec_s"]["count"] == 2
    assert rep["timing_summary"]["external_seconds"]["median"] == pytest.approx(12.5, abs=0.05)


# --------------------------------------------------------------------------- credibility hardening tests


def test_answer_matches_is_sign_aware() -> None:
    neg_key = {"accept": [-18.04878], "abs_tol": 1.0, "rel_tol": 0.0}
    assert rubric.answer_matches("Libraries budget cut -18%", neg_key)[0] is True
    assert rubric.answer_matches("Libraries budget cut −18.0%", neg_key)[0] is True
    assert rubric.answer_matches("Libraries budget rose +18%", neg_key)[0] is False
    assert rubric.answer_matches("Libraries budget rose 18%", neg_key)[0] is False
    assert rubric.answer_matches("Dots = patients (n=18/arm)", {"accept": [-18.4], "abs_tol": 1.0})[0] is False

    # Same contract in bench.answer_matches
    assert bench.answer_matches("Budget change -18%", neg_key)[0] is True
    assert bench.answer_matches("Budget change +18%", neg_key)[0] is False

    # Positive targets reject negative values unless both signs are listed
    pos_key = {"accept": [18.0], "abs_tol": 1.0, "rel_tol": 0.0}
    assert rubric.answer_matches("Throughput rose +18%", pos_key)[0] is True
    assert rubric.answer_matches("Throughput fell -18%", pos_key)[0] is False

    # Dual-sign keys accept either sign explicitly
    dual_key = {"accept": [-9.4, 9.4], "abs_tol": 0.2, "rel_tol": 0.0}
    assert rubric.answer_matches("Organic fell -9.4 pp", dual_key)[0] is True
    assert rubric.answer_matches("Organic fell 9.4 pp", dual_key)[0] is True

    # Negative scientific notation preserves sign
    sci_key = {"accept": [-1.3e-7], "rel_tol": 0.05, "abs_tol": 0.0}
    assert rubric.answer_matches("Drift is -1.3×10⁻⁷", sci_key)[0] is True
    assert rubric.answer_matches("Drift is 1.3×10⁻⁷", sci_key)[0] is False


def test_neutral_ascii_minus_is_advisory_and_headlines_ignore_footer(tmp_path: Path) -> None:
    import neutral

    png = tmp_path / "fig.png"
    fig, ax = plt.subplots(figsize=(6.4, 4.4))
    ax.bar(["Control", "Variant"], [10.0, 8.2], color=["#4e79a7", "#f28e2b"])
    ax.set_title("Variant changes score by -18% vs control")
    fig.suptitle("Headline: -18% drop across cohorts", y=0.96)
    fig.text(0.02, 0.02, "Source: synthetic db (+18% decoy in footer)", fontsize=9)
    fig.text(0.02, 0.08, "Note: n=18 replicates excluded", fontsize=9)
    fig.tight_layout(rect=(0, 0.12, 1, 0.90))
    fig.savefig(png, dpi=100)
    aud = neutral.audit_saved_figure(fig, png, dpi=100, tight=False)
    plt.close(fig)

    checks = {c["name"]: c["passed"] for c in neutral.neutral_checks(aud)}
    assert checks["text_well_formed"] is True, aud["text_faults"]
    assert aud["text_faults"] == []
    assert any("ASCII hyphen as minus sign" in a for a in aud["text_advisories"])

    # Headlines include suptitle & ax title, NOT footer Source:/Note: texts
    joined_heads = " ".join(aud["headlines"])
    assert "Headline: -18% drop" in joined_heads
    assert "Variant changes score by -18%" in joined_heads
    assert "Source:" not in joined_heads
    assert "Note:" not in joined_heads


def test_matplotlib_coached_arm_and_terminal_surface_support(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # 1. matplotlib-coached on a chat task
    run = tmp_path / "coached_run"
    bench.main([
        "start", "01_ablation", "--run", str(run), "--arm", "matplotlib-coached",
        "--python", sys.executable,
    ])
    start_out = capsys.readouterr().out
    assert "Prompt-Coached Matplotlib, No Mintfig" in start_out
    assert "700 px" in start_out
    assert "start linear bar charts at 0" in start_out
    assert "SKILL.md" not in start_out

    script = tmp_path / "fig.py"
    script.write_text(
        """import matplotlib.pyplot as plt
fig, ax = plt.subplots(figsize=(6, 4))
ax.barh(["no reranker", "full model"], [80.5, 82.1])
ax.set_title("Reranker adds 1.6 points (5 seeds)")
fig.tight_layout()
fig.savefig("figure.png", dpi=100)
""",
        encoding="utf-8",
    )
    reply = tmp_path / "reply.md"
    reply.write_text("Reranker adds 1.6 points across 5 seeds.\n\n![Ablation](figure.png)\n", encoding="utf-8")
    bench.main(["submit", "01_ablation", str(script), "--run", str(run), "--reply", str(reply)])
    sub_out = capsys.readouterr().out
    assert "Task complete" in sub_out
    state = json.loads((run / "01_ablation" / ".bench" / "state.json").read_text(encoding="utf-8"))
    assert state["arm"] == "matplotlib-coached"
    assert state["attempts"][0]["done"] is True
    assert state["attempts"][0]["passed"] is True

    # Export verifies hook_enabled=False for prompt-coached baseline
    sub_out_json = tmp_path / "coached_sub.json"
    bench.main([
        "export-submission", "--run", str(run), "--out", str(sub_out_json),
        "--submission-id", "test-coached-run", "--model", "Test Model", "--split", "dev",
    ])
    sub_data = json.loads(sub_out_json.read_text(encoding="utf-8"))
    assert sub_data["hook_enabled"] is False
    assert "Prompt-Coached Matplotlib" in sub_data["skill_or_prompt"]

    # 2. matplotlib-plain respects surface="terminal" without requiring figure.png
    term_run = tmp_path / "term_run"
    bench.main([
        "start", "pt27_terminal_only_bench", "--run", str(term_run), "--arm", "matplotlib-plain",
        "--python", sys.executable,
    ])
    term_out = capsys.readouterr().out
    assert "72-column" in term_out
    assert "do NOT require saving figure.png" in term_out

    term_script = tmp_path / "term.py"
    term_script.write_text('print("ok")\n', encoding="utf-8")
    term_reply = tmp_path / "term_reply.md"
    term_reply.write_text(
        "Parser-B is fastest at 1837 MB/s:\n\n"
        "```text\n"
        "Codec      Throughput (MB/s)\n"
        "lz4-fast   ################ 1837\n"
        "zstd-3     ########          932\n"
        "```\n",
        encoding="utf-8",
    )
    bench.main([
        "submit", "pt27_terminal_only_bench", str(term_script),
        "--run", str(term_run), "--reply", str(term_reply),
    ])
    t_state = json.loads(
        (term_run / "pt27_terminal_only_bench" / ".bench" / "state.json").read_text(encoding="utf-8")
    )
    assert t_state["attempts"][0]["done"] is True
    assert t_state["attempts"][0]["passed"] is True
    assert t_state["attempts"][0]["delivery"]["passed"] is True

