"""Tests for GitHub PR figure cards, check PR comments, GitHub Action, and 1.0 stability docs."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import matplotlib
import pytest

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from PIL import Image

import mintfig as mint
from mintfig.explainer import read_png_text
from mintfig.pr_card import format_check_pr_comment, save_pr_card


@pytest.fixture(autouse=True)
def _defaults_and_close():
    """Reset Matplotlib rcParams so earlier journal-plate tests do not leak tiny ticks."""
    with matplotlib.rc_context():
        matplotlib.rcdefaults()
        matplotlib.use("Agg")
        yield
    plt.close("all")

REPO_ROOT = Path(__file__).resolve().parents[1]
ACTION_YML = REPO_ROOT / ".github" / "actions" / "mintfig-check" / "action.yml"
ACTION_README = REPO_ROOT / ".github" / "actions" / "mintfig-check" / "README.md"
EXAMPLE_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "mintfig-check-example.yml"
STABILITY_POLICY = REPO_ROOT / "docs" / "STABILITY_POLICY.md"


def _sample_explanation(*, style: str = "mintfig", takeaway: str | None = None) -> mint.Explanation:
    return mint.explain(
        takeaway or "Removing retrieval costs 8 points of accuracy; fine-tuning costs 13",
        mint.compare(
            {"full model": 0.82, "no retrieval": 0.74, "no fine-tuning": 0.69},
            title="Ablation accuracy",
            label="Test accuracy",
            baseline="full model",
            highlight=["no retrieval", "no fine-tuning"],
        ),
        source="ablation_2026 (5 seeds)",
        style=style,
    )


def _corner_luminance(png_path: Path) -> float:
    with Image.open(png_path) as im:
        rgb = im.convert("RGB")
        r, g, b = rgb.getpixel((4, 4))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


# --------------------------------------------------------------------------- #
# save_pr_card
# --------------------------------------------------------------------------- #


class TestSavePrCard:
    def test_live_explanation_renders_light_and_dark_and_markdown(self, tmp_path: Path) -> None:
        exp = _sample_explanation()
        try:
            card = save_pr_card(exp, tmp_path, name="ablation")
        finally:
            plt.close(exp.fig)

        assert card["ok"] is True
        assert card["ship"] is True
        assert card["light_style"] == "mintfig"
        assert card["dark_style"] == "dark"

        light_png = Path(card["light_path"])
        dark_png = Path(card["dark_path"])
        md_file = Path(card["markdown_path"])
        assert light_png.name == "ablation.light.png"
        assert dark_png.name == "ablation.dark.png"
        assert light_png.is_file()
        assert dark_png.is_file()
        assert md_file.is_file()

        # Verify real PNGs with light vs dark backgrounds and embedded specs.
        assert light_png.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
        assert dark_png.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
        assert _corner_luminance(light_png) > 200.0
        assert _corner_luminance(dark_png) < 60.0

        light_meta = read_png_text(light_png)
        dark_meta = read_png_text(dark_png)
        assert "mintfig:spec" in light_meta
        assert "mintfig:spec" in dark_meta
        assert json.loads(dark_meta["mintfig:spec"]).get("style") == "dark"

        md = card["markdown"]
        assert md_file.read_text(encoding="utf-8").strip() == md.strip()
        assert f"**{exp.takeaway}**" in md
        assert "<picture>" in md
        assert "</picture>" in md
        assert 'media="(prefers-color-scheme: dark)"' in md
        assert 'media="(prefers-color-scheme: light)"' in md
        assert 'width="700"' in md
        assert 'alt="' in md
        assert "<details>" in md
        assert "<summary>Numbers &amp; reproduce (mintfig)</summary>" in md
        assert "0.82" in md
        assert "mintfig explain " in md

    def test_from_saved_png_path_round_trips_cleanly(self, tmp_path: Path) -> None:
        exp = _sample_explanation(style="editorial")
        orig_png = tmp_path / "orig.png"
        try:
            exp.save(orig_png)
        finally:
            plt.close(exp.fig)

        out_dir = tmp_path / "card_out"
        card = save_pr_card(orig_png, out_dir, name="editorial_ablation")

        assert card["ok"] is True
        assert card["ship"] is True
        assert card["light_style"] == "editorial"
        assert card["dark_style"] == "dark"
        assert Path(card["light_path"]).is_file()
        assert Path(card["dark_path"]).is_file()
        assert _corner_luminance(Path(card["light_path"])) > 200.0
        assert _corner_luminance(Path(card["dark_path"])) < 60.0
        assert "<picture>" in card["markdown"]
        assert "prefers-color-scheme: dark" in card["markdown"]

    def test_dark_input_falls_back_to_mintfig_for_light(self, tmp_path: Path) -> None:
        exp = _sample_explanation(style="dark")
        try:
            card = save_pr_card(exp, tmp_path, name="already_dark")
        finally:
            plt.close(exp.fig)

        assert card["ship"] is True
        assert card["light_style"] == "mintfig"
        assert card["dark_style"] == "dark"
        assert _corner_luminance(Path(card["light_path"])) > 200.0
        assert _corner_luminance(Path(card["dark_path"])) < 60.0

    def test_repo_prefix_rewrites_paths_cleanly(self, tmp_path: Path) -> None:
        exp = _sample_explanation()
        try:
            rel_card = save_pr_card(
                exp,
                tmp_path / "rel",
                name="bench",
                repo_prefix="docs/pr_figures/",
            )
            url_card = save_pr_card(
                exp,
                tmp_path / "url",
                name="bench.png",
                repo_prefix="https://raw.githubusercontent.com/org/repo/main/docs/figs/",
            )
        finally:
            plt.close(exp.fig)

        assert rel_card["light_ref"] == "docs/pr_figures/bench.light.png"
        assert rel_card["dark_ref"] == "docs/pr_figures/bench.dark.png"
        assert 'srcset="docs/pr_figures/bench.dark.png"' in rel_card["markdown"]
        assert 'srcset="docs/pr_figures/bench.light.png"' in rel_card["markdown"]
        assert 'src="docs/pr_figures/bench.light.png"' in rel_card["markdown"]
        assert "//bench" not in rel_card["markdown"]

        assert (
            url_card["light_ref"]
            == "https://raw.githubusercontent.com/org/repo/main/docs/figs/bench.light.png"
        )
        assert (
            url_card["dark_ref"]
            == "https://raw.githubusercontent.com/org/repo/main/docs/figs/bench.dark.png"
        )
        assert (
            'srcset="https://raw.githubusercontent.com/org/repo/main/docs/figs/bench.dark.png"'
            in url_card["markdown"]
        )
        # Reproduce command uses local filename instead of remote HTTPS URL.
        assert "mintfig explain bench.light.png --show-spec" in url_card["markdown"]

    def test_optional_details_flags_and_html_escaping(self, tmp_path: Path) -> None:
        exp = _sample_explanation(
            takeaway='Model "A" & B beat baseline by 8 points (<0.05 noise)'
        )
        try:
            no_details = save_pr_card(
                exp,
                tmp_path / "minimal",
                include_facts=False,
                include_reproduce=False,
            )
            facts_only = save_pr_card(
                exp,
                tmp_path / "facts",
                include_facts=True,
                include_reproduce=False,
            )
        finally:
            plt.close(exp.fig)

        assert "<details>" not in no_details["markdown"]
        assert "&quot;A&quot;" in no_details["markdown"]
        assert "&amp;" in no_details["markdown"]
        assert "&lt;0.05" in no_details["markdown"]

        assert "<summary>Numbers (mintfig)</summary>" in facts_only["markdown"]
        assert "mintfig explain" not in facts_only["markdown"]

    def test_cli_pr_card_flag_on_explain_plot_and_diff(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from mintfig.cli import main as cli_main

        # 1. mintfig explain --pr-card
        spec = {
            "takeaway": "Full model leads by 8 points",
            "panels": [
                {
                    "kind": "compare",
                    "values": {"full model": 0.82, "no retrieval": 0.74},
                    "label": "Test accuracy",
                }
            ],
            "source": "ablation",
        }
        spec_path = tmp_path / "spec.json"
        spec_path.write_text(json.dumps(spec), encoding="utf-8")
        explain_dir = tmp_path / "pr_explain"
        rc_exp = cli_main(["explain", str(spec_path), "--pr-card", str(explain_dir)])
        out_exp = json.loads(capsys.readouterr().out)
        assert rc_exp == 0
        assert out_exp["ship"] is True
        assert (explain_dir / "figure.light.png").is_file()
        assert (explain_dir / "figure.dark.png").is_file()
        assert (explain_dir / "figure.md").is_file()

        # 2. mintfig plot --pr-card
        csv_path = tmp_path / "scores.csv"
        csv_path.write_text("variant,score\nA,10\nB,25\nC,18\n", encoding="utf-8")
        plot_dir = tmp_path / "pr_plot"
        rc_plot = cli_main(
            [
                "plot",
                str(csv_path),
                "--kind",
                "compare",
                "--takeaway",
                "B scores 25, ahead of A",
                "--pr-card",
                str(plot_dir),
            ]
        )
        out_plot = json.loads(capsys.readouterr().out)
        assert rc_plot == 0
        assert out_plot["ship"] is True
        assert (plot_dir / "scores.light.png").is_file()
        assert (plot_dir / "scores.dark.png").is_file()
        assert (plot_dir / "scores.md").is_file()

        # 3. mintfig diff --pr-card
        base_csv = tmp_path / "base.csv"
        head_csv = tmp_path / "head.csv"
        base_csv.write_text("bench,latency_ms\nparse,100\nrender,200\n", encoding="utf-8")
        head_csv.write_text("bench,latency_ms\nparse,80\nrender,160\n", encoding="utf-8")
        diff_dir = tmp_path / "pr_diff"
        rc_diff = cli_main(["diff", str(base_csv), str(head_csv), "--pr-card", str(diff_dir)])
        out_diff = capsys.readouterr().out
        assert rc_diff == 0
        assert "<picture>" in out_diff
        assert (diff_dir / "diff.light.png").is_file()
        assert (diff_dir / "diff.dark.png").is_file()
        assert (diff_dir / "diff.md").is_file()


# --------------------------------------------------------------------------- #
# format_check_pr_comment
# --------------------------------------------------------------------------- #


class TestFormatCheckPrComment:
    def test_mixed_ship_and_fix_first_reports(self) -> None:
        # 1. Clean figure that ships
        fig_ok, ax_ok = plt.subplots(figsize=(5.5, 3.2), dpi=150, layout="constrained")
        ax_ok.bar(["A", "B", "C"], [10, 25, 18])
        ax_ok.set_ylabel("Throughput (req/s)")
        ax_ok.set_title("B reaches 25 req/s, 2.5x above A")
        rep_ok = mint.check(fig_ok, dpi=150)
        rep_ok["path"] = "scripts/good_plot.py"
        plt.close(fig_ok)

        # 2. Defective figure with claim mismatch + small text + nonzero bar baseline
        fig_bad, ax_bad = plt.subplots(figsize=(12, 5), dpi=150)
        ax_bad.bar(["full model", "no retrieval", "no fine-tuning"], [0.82, 0.74, 0.69])
        ax_bad.set_ylim(0.6, 0.85)
        ax_bad.set_title("Removing retrieval costs 12 points of accuracy")
        rep_bad = mint.check(fig_bad, dpi=150)
        rep_bad["path"] = "scripts/bad_plot.py"
        plt.close(fig_bad)

        assert rep_ok["ship"] is True
        assert rep_bad["ship"] is False

        md = format_check_pr_comment([rep_ok, rep_bad], title="PR Figure Audit")

        assert "### PR Figure Audit" in md
        assert "1 of 2" in md
        assert "`scripts/good_plot.py`" in md
        assert "`scripts/bad_plot.py`" in md
        assert "SHIP" in md
        assert "FIX FIRST" in md
        assert "min text" in md
        assert "12 points" in md
        assert "closest in data:" in md
        assert "8 points" in md
        assert "claim_number_mismatch" in md
        assert "**Fix:**" in md

    def test_clean_zero_issue_summary(self) -> None:
        clean_reports = [
            {
                "path": "figs/latency.py",
                "ship": True,
                "display": {"width_px": 700, "shown_px": [700, 400], "min_text_px": 12.5},
                "claim": {
                    "text": "Latency dropped 40%",
                    "hedged": False,
                    "numbers": [{"text": "40%", "found": True, "how": "diff"}],
                },
                "issues": [],
                "advisories": [],
            },
            {
                "path": "figs/accuracy.py",
                "ship": True,
                "display": {"width_px": 700, "shown_px": [700, 380], "min_text_px": 13.0},
                "claim": None,
                "issues": [],
                "advisories": [],
            },
        ]
        md = format_check_pr_comment(clean_reports)

        assert "All 2 figures ready to ship" in md
        assert "0 issues found" in md
        assert "FIX FIRST" not in md
        assert "**Fix:**" not in md
        assert "1/1 matched" in md
        assert "700×400 px" in md

    def test_wrapped_json_pdf_preflight_and_script_error(self) -> None:
        wrapped = {
            "schema_version": "0.2",
            "target": "notebooks/eval.ipynb",
            "figures": [
                {
                    "path": None,
                    "ship": True,
                    "display": {"width_px": 700, "min_text_px": 11.8},
                    "claim": None,
                    "issues": [],
                }
            ],
        }
        pdf_report = {
            "schema_version": "0.2",
            "path": "paper/fig1.pdf",
            "ok": False,
            "passed": False,
            "journal": "nature",
            "dimensions_mm": {"width": 120.0, "height": 80.0},
            "issues": [
                {
                    "rule": "dimensions",
                    "severity": "error",
                    "message": "Width 120.0 mm does not match Nature column presets.",
                    "fix_hint": "Use width='single' (89 mm) or width='double' (183 mm).",
                }
            ],
        }
        script_error = {
            "path": "scripts/crash.py",
            "ship": False,
            "error": "ModuleNotFoundError: No module named 'nonexistent'",
            "issues": [],
        }

        md = format_check_pr_comment([wrapped, pdf_report, script_error])

        assert "`notebooks/eval.ipynb`" in md
        assert "`paper/fig1.pdf`" in md
        assert "120.0×80.0 mm (nature)" in md
        assert "Use width='single' (89 mm)" in md
        assert "`scripts/crash.py`" in md
        assert "`script_error`" in md
        assert "ModuleNotFoundError" in md

    def test_empty_reports(self) -> None:
        md = format_check_pr_comment([], title="mintfig check")
        assert "### mintfig check" in md
        assert "No figures checked." in md


# --------------------------------------------------------------------------- #
# GitHub Action, Example Workflow & Stability Policy Validation
# --------------------------------------------------------------------------- #


def _extract_top_level_blocks(yaml_text: str) -> dict[str, list[str]]:
    """Lightweight stdlib YAML block splitter for top-level mapping keys."""
    blocks: dict[str, list[str]] = {}
    current_key: str | None = None
    for line in yaml_text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            if current_key is not None:
                blocks[current_key].append(line)
            continue
        if not line[0].isspace():
            assert ":" in line, f"Invalid top-level YAML line: {line!r}"
            key, _, rest = line.partition(":")
            current_key = key.strip()
            blocks[current_key] = [rest.strip()] if rest.strip() else []
        else:
            assert current_key is not None, f"Indented line before top-level key: {line!r}"
            blocks[current_key].append(line)
    return blocks


def _extract_indented_keys(lines: list[str], indent: int = 2) -> list[str]:
    prefix = " " * indent
    keys: list[str] = []
    for line in lines:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line.startswith(prefix) and not line.startswith(prefix + " ") and ":" in line:
            keys.append(line.strip().split(":", 1)[0].strip())
    return keys


def _extract_run_blocks(yaml_text: str) -> list[str]:
    """Extract all multi-line `run: |` blocks from a GitHub Action/Workflow YAML."""
    blocks: list[str] = []
    lines = yaml_text.splitlines()
    i = 0
    while i < len(lines):
        m = re.match(r"^(\s*)run:\s*\|\s*$", lines[i])
        if m:
            base_indent = len(m.group(1))
            i += 1
            body: list[str] = []
            while i < len(lines):
                ln = lines[i]
                if ln.strip() == "":
                    body.append("")
                    i += 1
                    continue
                cur_indent = len(ln) - len(ln.lstrip(" "))
                if cur_indent <= base_indent:
                    break
                body.append(ln[base_indent + 2 :])
                i += 1
            blocks.append("\n".join(body))
        else:
            i += 1
    return blocks


def _maybe_parse_yaml(path: Path) -> dict[str, Any] | None:
    try:
        import yaml  # type: ignore[import-not-found]
    except ImportError:
        return None
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


class TestActionAndDocs:
    def test_action_yml_structure_and_safety(self) -> None:
        assert ACTION_YML.is_file()
        text = ACTION_YML.read_text(encoding="utf-8")
        assert "\t" not in text, "YAML files must use spaces, never tabs"

        blocks = _extract_top_level_blocks(text)
        for key in ("name", "description", "inputs", "outputs", "runs"):
            assert key in blocks, f"Missing required top-level key {key!r} in action.yml"

        input_keys = set(_extract_indented_keys(blocks["inputs"], indent=2))
        expected_inputs = {
            "paths",
            "width",
            "journal",
            "strict",
            "fail-on-fix",
            "python-version",
            "use-existing-python",
            "mintfig-version",
            "write-summary",
        }
        assert expected_inputs <= input_keys
        assert "git" in text and "fetch" in text and "GITHUB_BASE_REF" in text

        output_keys = set(_extract_indented_keys(blocks["outputs"], indent=2))
        expected_outputs = {"passed", "checked-count", "failed-count", "report-markdown"}
        assert expected_outputs <= output_keys

        # Every output must wire to the composite step output.
        outputs_text = "\n".join(blocks["outputs"])
        for out_name in expected_outputs:
            assert f"steps.mintfig-check.outputs.{out_name}" in outputs_text

        runs_text = "\n".join(blocks["runs"])
        assert 'using: "composite"' in runs_text or "using: composite" in runs_text
        assert "actions/setup-python@v5" in runs_text

        # Every `run:` step in a composite action must declare `shell: bash`
        # and NEVER interpolate `${{ inputs.* }}` directly inside the script body.
        run_blocks = _extract_run_blocks(text)
        assert len(run_blocks) >= 2
        assert runs_text.count("shell: bash") >= len(run_blocks)
        for block in run_blocks:
            assert "${{ inputs." not in block, (
                "Pass inputs via env: instead of interpolating ${{ inputs.* }} inside run:"
            )

        # Embedded Python runner inside `python - <<'PY' ... PY` must compile cleanly
        # and terminate the heredoc at column 0 once YAML block indentation is stripped.
        py_match = re.search(r"python - <<'PY'\n(.*?)\nPY(?:\n|$)", run_blocks[-1], re.DOTALL)
        assert py_match is not None, "Expected quoted heredoc python - <<'PY' in action.yml"
        compile(py_match.group(1), str(ACTION_YML), "exec")

        parsed = _maybe_parse_yaml(ACTION_YML)
        if parsed is not None:
            assert parsed["runs"]["using"] == "composite"
            assert parsed["inputs"]["width"]["default"] == "chat"
            assert parsed["inputs"]["journal"]["default"] == "nature"
            assert parsed["inputs"]["strict"]["default"] == "false"
            assert parsed["inputs"]["fail-on-fix"]["default"] == "true"
            assert parsed["inputs"]["python-version"]["default"] == "3.12"
            assert parsed["inputs"]["mintfig-version"]["default"] == ""
            assert parsed["inputs"]["write-summary"]["default"] == "true"

    def test_action_embedded_runner_executes_and_writes_outputs(self, tmp_path: Path) -> None:
        text = ACTION_YML.read_text(encoding="utf-8")
        run_blocks = _extract_run_blocks(text)
        py_match = re.search(r"python - <<'PY'\n(.*?)\nPY(?:\n|$)", run_blocks[-1], re.DOTALL)
        assert py_match is not None
        runner_code = py_match.group(1)

        script = tmp_path / "good_plot.py"
        script.write_text(
            "import matplotlib\n"
            "matplotlib.use('Agg')\n"
            "import matplotlib.pyplot as plt\n"
            "fig, ax = plt.subplots(figsize=(5.5, 3.2), dpi=150, layout='constrained')\n"
            "ax.bar(['A', 'B', 'C'], [10, 25, 18])\n"
            "ax.set_ylabel('Throughput (req/s)')\n"
            "ax.set_title('B reaches 25 req/s, 2.5x above A')\n"
            "fig.savefig('good_plot.png', dpi=150)\n",
            encoding="utf-8",
        )
        gh_output = tmp_path / "github_output.txt"
        gh_summary = tmp_path / "github_summary.md"

        env = os.environ.copy()
        src_dir = str(REPO_ROOT / "src")
        env["PYTHONPATH"] = (
            f"{src_dir}{os.pathsep}{env['PYTHONPATH']}" if env.get("PYTHONPATH") else src_dir
        )
        env["INPUT_PATHS"] = str(script)
        env["INPUT_WIDTH"] = "chat"
        env["INPUT_JOURNAL"] = "nature"
        env["INPUT_STRICT"] = "false"
        env["INPUT_FAIL_ON_FIX"] = "true"
        env["INPUT_WRITE_SUMMARY"] = "true"
        env["GITHUB_OUTPUT"] = str(gh_output)
        env["GITHUB_STEP_SUMMARY"] = str(gh_summary)

        proc = subprocess.run(
            [sys.executable, "-c", runner_code],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.returncode == 0, f"Action runner failed: {proc.stderr}\n{proc.stdout}"

        output_text = gh_output.read_text(encoding="utf-8")
        assert "passed=true\n" in output_text
        assert "checked-count=1\n" in output_text
        assert "failed-count=0\n" in output_text
        assert "report-markdown<<MINTFIG_EOF_" in output_text

        summary_text = gh_summary.read_text(encoding="utf-8")
        assert "### mintfig check" in summary_text
        assert "ready to ship" in summary_text
        assert "SHIP" in summary_text

    def test_example_workflow_is_manual_dispatch_only(self) -> None:
        assert EXAMPLE_WORKFLOW.is_file()
        text = EXAMPLE_WORKFLOW.read_text(encoding="utf-8")
        assert "\t" not in text

        blocks = _extract_top_level_blocks(text)
        for key in ("name", "on", "permissions", "jobs"):
            assert key in blocks

        on_keys = set(_extract_indented_keys(blocks["on"], indent=2))
        assert on_keys == {"workflow_dispatch"}, (
            f"Example workflow must be workflow_dispatch-only, found triggers: {on_keys}"
        )
        assert "./.github/actions/mintfig-check" in text

        for block in _extract_run_blocks(text):
            assert "${{ inputs." not in block
            assert "${{ steps." not in block

        parsed = _maybe_parse_yaml(EXAMPLE_WORKFLOW)
        if parsed is not None:
            triggers = parsed.get("on", parsed.get(True))
            assert isinstance(triggers, dict)
            assert set(triggers.keys()) == {"workflow_dispatch"}

    def test_action_readme_and_stability_policy_cover_required_topics(self) -> None:
        assert ACTION_README.is_file()
        readme = ACTION_README.read_text(encoding="utf-8")
        for token in ("paths", "report-markdown", "GITHUB_STEP_SUMMARY", "save_pr_card"):
            assert token in readme

        assert STABILITY_POLICY.is_file()
        policy = STABILITY_POLICY.read_text(encoding="utf-8")
        for token in (
            "Semantic Versioning",
            "mintfig.__all__",
            "schema_version",
            "mintfig:spec",
            "DeprecationWarning",
            "2 minor releases",
            "mintfig._explain",
            "0.3.x",
            "1.0.0",
        ):
            assert token in policy
