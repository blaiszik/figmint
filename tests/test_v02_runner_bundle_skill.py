"""Tests for mintfig v0.2: versioned specs, high-precision preflight, runner, bundle, and skill installer."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pytest
from PIL import Image
from pypdf import PdfReader

matplotlib.use("Agg")

from mintfig.cli import main as cli_main
from mintfig.plate import Plate
from mintfig.preflight import CheckResult, preflight_figure, preflight_pdf
from mintfig.runner import run_script
from mintfig.skill import VALID_TARGETS, get_agents_snippet, get_skill_markdown, install_skill
from mintfig.specs import get_spec, mm_to_in
from mintfig.style import use

PT_TO_MM = 25.4 / 72.0


def _check_by_rule(checks: list[CheckResult], rule: str) -> CheckResult:
    for check in checks:
        if check.rule == rule:
            return check
    raise AssertionError(f"Rule {rule!r} not found in {[c.rule for c in checks]}")


def _collect_pdf_fonts(reader: PdfReader) -> list[dict[str, str]]:
    fonts: list[dict[str, str]] = []
    seen: set[int] = set()

    def _walk(res_obj: object) -> None:
        if res_obj is None:
            return
        res = res_obj.get_object() if hasattr(res_obj, "get_object") else res_obj
        if not isinstance(res, dict):
            return
        font_dict = res.get("/Font")
        if font_dict is not None:
            font_dict = font_dict.get_object() if hasattr(font_dict, "get_object") else font_dict
            if isinstance(font_dict, dict):
                for name, fref in font_dict.items():
                    fobj = fref.get_object() if hasattr(fref, "get_object") else fref
                    if id(fobj) in seen:
                        continue
                    seen.add(id(fobj))
                    fonts.append(
                        {
                            "name": str(name),
                            "subtype": str(fobj.get("/Subtype", "")),
                            "basefont": str(fobj.get("/BaseFont", "")),
                        }
                    )
        xobjs = res.get("/XObject")
        if xobjs is not None:
            xobjs = xobjs.get_object() if hasattr(xobjs, "get_object") else xobjs
            if isinstance(xobjs, dict):
                for xref in xobjs.values():
                    xobj = xref.get_object() if hasattr(xref, "get_object") else xref
                    if isinstance(xobj, dict) and "/Resources" in xobj:
                        _walk(xobj["/Resources"])

    for page in reader.pages:
        _walk(page.get("/Resources"))
    return fonts


class TestSpecVersioning:
    @pytest.mark.parametrize("journal", ["nature", "science", "science_advances"])
    def test_journal_spec_provenance_fields(self, journal: str) -> None:
        spec = get_spec(journal)
        assert isinstance(spec.spec_version, str)
        assert len(spec.spec_version.strip()) >= 3
        assert isinstance(spec.last_verified, str)
        assert len(spec.last_verified.strip()) >= 8
        assert spec.source_url.startswith("https://")

    def test_cli_specs_json_includes_provenance(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        rc = cli_main(["specs", "--json"])
        out = capsys.readouterr().out
        assert rc == 0
        data = json.loads(out)
        # Support either dict keyed by journal name or list/wrapper with specs
        if isinstance(data, dict) and "journals" in data:
            entries = data["journals"]
        else:
            entries = data
        if isinstance(entries, dict):
            for name in ("nature", "science", "science_advances"):
                assert name in entries
                assert entries[name]["spec_version"]
                assert entries[name]["last_verified"]
                assert str(entries[name]["source_url"]).startswith("https://")
        else:
            by_name = {item["name"]: item for item in entries}
            for name in ("nature", "science", "science_advances"):
                assert name in by_name
                assert by_name[name]["spec_version"]
                assert by_name[name]["last_verified"]
                assert str(by_name[name]["source_url"]).startswith("https://")


class TestHighPrecisionPreflight:
    def test_clean_plate_zero_errors_zero_warnings_and_agent_schema(self) -> None:
        plate = Plate(journal="nature", width="double", height_mm=95.0, layout=(1, 2))
        x = np.linspace(0.0, 10.0, 50)
        plate["a"].plot(x, np.sin(x))
        plate["a"].set_xlabel("Time (s)")
        plate["a"].set_ylabel("Amplitude (mV)")
        plate["b"].plot(x, np.cos(x))
        plate["b"].set_xlabel("Time (s)")
        plate["b"].set_ylabel("Phase (rad)")
        plate.label_panels()
        try:
            report = plate.preflight()
            assert report.passed is True
            assert report.failures == []
            assert report.warnings == []

            agent = report.to_agent_dict()
            assert agent["schema_version"] == "0.2"
            assert agent["ok"] is True
            assert agent["journal"] == "nature"
            assert agent["spec_version"]
            assert str(agent["spec_source_url"]).startswith("https://")
            assert agent["dimensions_mm"]["width"] == pytest.approx(183.0, abs=0.1)
            assert agent["dimensions_mm"]["height"] == pytest.approx(95.0, abs=0.1)
            assert agent["summary"]["errors"] == 0
            assert agent["summary"]["warnings"] == 0
            assert agent["recommended_max_loops"] == 2
            assert agent["issues"] == []
        finally:
            plt.close(plate.fig)

    def test_severity_split_panel_attribution_and_fix_hints(self, tmp_path: Path) -> None:
        # 1. Wrong width -> error + fix_hint
        p_dim = Plate(journal="nature", width=140.0, height_mm=80.0, layout=(1, 1))
        p_dim["a"].plot([0, 1], [0, 1])
        try:
            rep = p_dim.preflight()
            chk = _check_by_rule(rep.checks, "dimensions")
            assert chk.status == "fail"
            assert chk.severity == "error"
            assert chk.fix_hint
        finally:
            plt.close(p_dim.fig)

        # 2. Tiny text on panel b + banned jet colormap on panel a -> error + panel + fix_hint
        p_multi = Plate(journal="nature", width="double", height_mm=90.0, layout=(1, 2))
        rng = np.random.default_rng(1)
        p_multi["a"].imshow(rng.random((16, 16)), cmap="jet")
        p_multi["b"].plot([0, 1], [0, 1])
        p_multi["b"].text(0.5, 0.5, "tiny note", fontsize=3.5)
        try:
            rep = p_multi.preflight()
            cmap_chk = _check_by_rule(rep.checks, "colormaps")
            assert cmap_chk.severity == "error"
            assert cmap_chk.panel == "a"
            assert cmap_chk.fix_hint

            font_chk = _check_by_rule(rep.checks, "font_sizes")
            assert font_chk.severity == "error"
            assert font_chk.panel == "b"
            assert font_chk.fix_hint
            assert any("tiny note" in e for e in font_chk.elements) or font_chk.elements
        finally:
            plt.close(p_multi.fig)

        # 3. Canvas clipping -> error + fix_hint
        p_clip = Plate(journal="nature", width="single", height_mm=65.0, layout=(1, 1))
        p_clip["a"].plot([0, 1], [0, 1])
        p_clip.fig.text(1.04, 0.5, "OverflowText", clip_on=False)
        try:
            rep = p_clip.preflight()
            clip_chk = _check_by_rule(rep.checks, "canvas_clipping")
            assert clip_chk.severity == "error"
            assert clip_chk.fix_hint
        finally:
            plt.close(p_clip.fig)

        # 4. Type 3 PDF -> error + fix_hint in preflight_pdf
        t3_pdf = tmp_path / "type3.pdf"
        with use("nature"):
            fig, ax = plt.subplots(figsize=(mm_to_in(89.0), mm_to_in(65.0)), layout="constrained")
            ax.plot([0, 1], [0, 1])
            ax.set_xlabel("X axis")
            ax.set_ylabel("Y axis")
            with plt.rc_context({"pdf.fonttype": 3}):
                fig.savefig(t3_pdf, format="pdf")
            plt.close(fig)

        pdf_rep = preflight_pdf(t3_pdf, "nature")
        assert pdf_rep.passed is False
        font_pdf_checks = [c for c in pdf_rep.checks if c.status == "fail"]
        assert font_pdf_checks
        assert any(c.severity == "error" and c.fix_hint for c in font_pdf_checks)

        # 5. Hairline stroke -> warning + fix_hint; scatter lw=0 must NOT warn
        p_hair = Plate(journal="nature", width="single", height_mm=65.0, layout=(1, 1))
        p_hair["a"].plot([0, 1, 2], [0, 1, 0.5], linewidth=0.1)
        try:
            rep = p_hair.preflight()
            hair_chk = _check_by_rule(rep.checks, "hairline_strokes")
            assert hair_chk.status == "warn"
            assert hair_chk.severity == "warning"
            assert hair_chk.fix_hint
        finally:
            plt.close(p_hair.fig)

        p_scat = Plate(journal="nature", width="single", height_mm=65.0, layout=(1, 1))
        p_scat["a"].scatter(rng.normal(size=50), rng.normal(size=50), s=8, linewidths=0)
        p_scat["a"].set_xlabel("X")
        p_scat["a"].set_ylabel("Y")
        try:
            rep = p_scat.preflight()
            assert _check_by_rule(rep.checks, "hairline_strokes").status == "pass"
        finally:
            plt.close(p_scat.fig)

    def test_overlap_precision_ignores_grazing_and_fails_severe_collision(self) -> None:
        # 1. Borderline grazing (< 3 px overlap) must NOT falsely fail
        p_graze = Plate(journal="nature", width="single", height_mm=65.0, layout=(1, 1))
        ax = p_graze["a"]
        ax.plot([0, 1], [0, 1])
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        t1 = ax.text(0.5, 0.5, "Alpha", ha="center", va="bottom")
        p_graze.fig.canvas.draw()
        renderer = p_graze.fig.canvas.get_renderer()
        bb1 = t1.get_window_extent(renderer)
        # Place t2 with only ~1.5 px vertical overlap (well below the 3 px threshold)
        inv = ax.transData.inverted()
        _, y_top_data = inv.transform((bb1.x0, bb1.y1 - 1.5))
        ax.text(0.5, y_top_data, "Beta", ha="center", va="bottom")
        try:
            rep = preflight_figure(p_graze.fig, "nature")
            ov = _check_by_rule(rep.checks, "text_overlaps")
            assert ov.status != "fail", f"Grazing 1.5px labels falsely failed: {ov.message}"
        finally:
            plt.close(p_graze.fig)

        # 2. Severe overlapping labels (>= 35% overlap) MUST fail with both strings + panel + fix_hint
        p_hit = Plate(journal="nature", width="double", height_mm=80.0, layout=(1, 2))
        p_hit["a"].plot([0, 1], [0, 1])
        p_hit["b"].plot([0, 1], [0, 1])
        p_hit["b"].text(0.5, 0.5, "CollisionOne", ha="center", va="center")
        p_hit["b"].text(0.5, 0.5, "CollisionTwo", ha="center", va="center")
        try:
            rep = preflight_figure(p_hit.fig, "nature")
            assert rep.passed is False
            ov = _check_by_rule(rep.checks, "text_overlaps")
            assert ov.status == "fail"
            assert ov.severity == "error"
            assert ov.panel == "b"
            assert ov.fix_hint
            joined = " ".join(ov.elements) + " " + ov.message
            assert "CollisionOne" in joined
            assert "CollisionTwo" in joined
        finally:
            plt.close(p_hit.fig)


class TestRunnerAndCLI:
    def test_runner_discovery_contracts(self, tmp_path: Path) -> None:
        # 1. def build() -> Plate
        s_build = tmp_path / "s_build.py"
        s_build.write_text(
            "import mintfig as mint\n"
            "def build():\n"
            "    p = mint.Plate(journal='nature', width='single', height_mm=64.0)\n"
            "    p['a'].plot([0, 1, 2], [0, 1, 0.5])\n"
            "    p['a'].set_xlabel('Time (s)')\n"
            "    p['a'].set_ylabel('Signal')\n"
            "    return p\n",
            encoding="utf-8",
        )
        r1 = run_script(s_build, journal="nature")
        assert r1.ok is True
        assert r1.exit_code == 0
        assert r1.stage == "preflight"
        d1 = r1.to_dict()
        assert d1["schema_version"] == "0.2"
        assert d1["ok"] is True

        # 2. def build(journal) -> Plate
        s_build_j = tmp_path / "s_build_j.py"
        s_build_j.write_text(
            "import mintfig as mint\n"
            "def build(journal='nature'):\n"
            "    p = mint.Plate(journal=journal, width='full', height_mm=90.0)\n"
            "    p['a'].plot([0, 1], [0, 1])\n"
            "    p['a'].set_xlabel('X')\n"
            "    p['a'].set_ylabel('Y')\n"
            "    return p\n",
            encoding="utf-8",
        )
        r2 = run_script(s_build_j, journal="science")
        assert r2.ok is True
        assert r2.exit_code == 0
        assert r2.report is not None
        assert r2.report.journal == "science"
        assert r2.report.width_mm == pytest.approx(184.0, abs=0.2)

        # 3. Top-level `plate`
        s_plate = tmp_path / "s_plate.py"
        s_plate.write_text(
            "import mintfig as mint\n"
            "plate = mint.Plate(journal='nature', width='single', height_mm=64.0)\n"
            "plate['a'].plot([0, 1], [1, 2])\n"
            "plate['a'].set_xlabel('X')\n"
            "plate['a'].set_ylabel('Y')\n",
            encoding="utf-8",
        )
        r3 = run_script(s_plate, journal="nature")
        assert r3.ok is True
        assert r3.exit_code == 0

        # 4. Top-level `fig`
        s_fig = tmp_path / "s_fig.py"
        s_fig.write_text(
            "import mintfig as mint\n"
            "fig, ax = mint.figure(journal='nature', width='single', height_mm=64.0)\n"
            "ax.plot([0, 1], [0, 2])\n"
            "ax.set_xlabel('X')\n"
            "ax.set_ylabel('Y')\n",
            encoding="utf-8",
        )
        r4 = run_script(s_fig, journal="nature")
        assert r4.ok is True
        assert r4.exit_code == 0

    def test_runner_exit_codes_preflight_contract_runtime(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Exit code 1: preflight error (jet colormap)
        s_fail = tmp_path / "s_fail.py"
        s_fail.write_text(
            "import numpy as np\n"
            "import mintfig as mint\n"
            "def build():\n"
            "    p = mint.Plate(journal='nature', width='single', height_mm=64.0)\n"
            "    p['a'].imshow(np.arange(16).reshape(4, 4), cmap='jet')\n"
            "    return p\n",
            encoding="utf-8",
        )
        rc_fail = cli_main(["run", str(s_fail), "--journal", "nature", "--json"])
        out_fail = json.loads(capsys.readouterr().out)
        assert rc_fail == 1
        assert out_fail["schema_version"] == "0.2"
        assert out_fail["ok"] is False
        assert any(i["severity"] == "error" and i["fix_hint"] for i in out_fail["issues"])

        # Exit code 2: missing contract
        s_nocontract = tmp_path / "s_nocontract.py"
        s_nocontract.write_text("x = 42\n", encoding="utf-8")
        rc_contract = cli_main(["run", str(s_nocontract), "--journal", "nature", "--json"])
        out_contract = json.loads(capsys.readouterr().out)
        assert rc_contract == 2
        assert out_contract["schema_version"] == "0.2"
        assert out_contract["ok"] is False
        assert out_contract["stage"] == "contract"
        assert out_contract["fix_hint"]

        # Exit code 2: runtime exception
        s_crash = tmp_path / "s_crash.py"
        s_crash.write_text(
            "def build():\n"
            "    raise RuntimeError('boom in plot script')\n",
            encoding="utf-8",
        )
        rc_crash = cli_main(["run", str(s_crash), "--journal", "nature", "--json"])
        out_crash = json.loads(capsys.readouterr().out)
        assert rc_crash == 2
        assert out_crash["schema_version"] == "0.2"
        assert out_crash["ok"] is False
        assert out_crash["stage"] == "runtime"
        assert "boom in plot script" in str(out_crash.get("error", ""))

    def test_cli_run_with_bundle_writes_all_seven_artifacts(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        script = tmp_path / "clean_plot.py"
        script_src = (
            "import numpy as np\n"
            "import mintfig as mint\n"
            "def build():\n"
            "    p = mint.Plate(journal='nature', width='single', height_mm=64.0)\n"
            "    x = np.linspace(0, 5, 40)\n"
            "    p['a'].plot(x, np.exp(-x))\n"
            "    p['a'].set_xlabel('Time (s)')\n"
            "    p['a'].set_ylabel('Decay')\n"
            "    return p\n"
        )
        script.write_text(script_src, encoding="utf-8")

        out_dir = tmp_path / "bundle_out"
        rc = cli_main(
            [
                "run",
                str(script),
                "--journal",
                "nature",
                "--bundle",
                str(out_dir),
                "--json",
            ]
        )
        payload = json.loads(capsys.readouterr().out)
        assert rc == 0
        assert payload["schema_version"] == "0.2"
        assert payload["ok"] is True

        expected_files = [
            "figure.pdf",
            "figure.svg",
            "preview.png",
            "proof.png",
            "figure.tex",
            "reproduce.py",
            "report.json",
        ]
        for fname in expected_files:
            fpath = out_dir / fname
            assert fpath.exists(), f"Missing bundle artifact: {fname}"

        # Verify PDF MediaBox & 0 Type 3 fonts
        reader = PdfReader(str(out_dir / "figure.pdf"))
        box = reader.pages[0].mediabox
        assert float(box.width) * PT_TO_MM == pytest.approx(89.0, abs=0.15)
        assert float(box.height) * PT_TO_MM == pytest.approx(64.0, abs=0.15)
        fonts = _collect_pdf_fonts(reader)
        assert fonts
        assert [f for f in fonts if f["subtype"] == "/Type3"] == []

        # Verify SVG, PNGs, LaTeX, reproduce.py, report.json
        svg_text = (out_dir / "figure.svg").read_text(encoding="utf-8")
        assert "<svg" in svg_text
        for png_name in ("preview.png", "proof.png"):
            with Image.open(out_dir / png_name) as img:
                assert img.format == "PNG"
                assert img.width >= 400
        tex = (out_dir / "figure.tex").read_text(encoding="utf-8")
        assert "\\begin{figure}" in tex
        assert "89.0mm" in tex
        assert "figure.pdf" in tex
        assert (out_dir / "reproduce.py").read_text(encoding="utf-8") == script_src
        rep_json = json.loads((out_dir / "report.json").read_text(encoding="utf-8"))
        assert rep_json["schema_version"] == "0.2"
        assert rep_json["ok"] is True

        # Verify --no-proof skips proof.png
        out_noproof = tmp_path / "bundle_noproof"
        rc2 = cli_main(
            [
                "run",
                str(script),
                "--journal",
                "nature",
                "--bundle",
                str(out_noproof),
                "--no-proof",
                "--json",
            ]
        )
        capsys.readouterr()
        assert rc2 == 0
        assert (out_noproof / "figure.pdf").exists()
        assert not (out_noproof / "proof.png").exists()


class TestPlateBundleAPI:
    def test_plate_bundle_with_and_without_proof_and_source_code(
        self, tmp_path: Path
    ) -> None:
        plate = Plate(journal="nature", width="single", height_mm=65.0, layout=(1, 1))
        plate["a"].plot([0, 1, 2], [0, 1, 0.5])
        plate["a"].set_xlabel("X")
        plate["a"].set_ylabel("Y")
        try:
            d1 = tmp_path / "with_proof"
            res1 = plate.bundle(
                d1,
                source_code="# demo\nprint('ok')\n",
                caption="Custom figure caption.",
                label="fig:custom",
                include_proof=True,
            )
            assert res1.figure_pdf.exists()
            assert res1.figure_svg.exists()
            assert res1.preview_png.exists()
            assert res1.proof_png is not None and res1.proof_png.exists()
            assert res1.reproduce_py is not None and res1.reproduce_py.exists()
            assert "Custom figure caption." in res1.figure_tex.read_text(encoding="utf-8")
            assert "\\label{fig:custom}" in res1.figure_tex.read_text(encoding="utf-8")
            assert "print('ok')" in res1.reproduce_py.read_text(encoding="utf-8")
            assert res1.report_json.exists()
            as_dict = res1.to_dict()
            assert as_dict["figure_pdf"] == str(res1.figure_pdf)

            d2 = tmp_path / "no_proof"
            res2 = plate.bundle(d2, include_proof=False)
            assert res2.proof_png is None
            assert res2.reproduce_py is None
            assert not (d2 / "proof.png").exists()
            assert not (d2 / "reproduce.py").exists()
        finally:
            plt.close(plate.fig)


class TestSkillInstallerAndCLI:
    def test_skill_assets_readable(self) -> None:
        md = get_skill_markdown()
        assert "mintfig run" in md
        assert "--bundle" in md
        assert "--json" in md
        snippet = get_agents_snippet()
        assert "<!-- mintfig:start -->" in snippet
        assert "<!-- mintfig:end -->" in snippet
        for t in ("claude", "antigravity", "cursor", "codex", "agents-md", "claude-md"):
            assert t in VALID_TARGETS

    def test_install_skill_creates_targets_and_is_idempotent(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Pre-populate AGENTS.md and CLAUDE.md with user content
        agents_md = tmp_path / "AGENTS.md"
        claude_md = tmp_path / "CLAUDE.md"
        agents_md.write_text("# My Repo\n\nExisting top notes.\n", encoding="utf-8")
        claude_md.write_text("# Claude Notes\n\nKeep this untouched.\n", encoding="utf-8")

        rc1 = cli_main(
            [
                "skill",
                "--install",
                "--root",
                str(tmp_path),
                "--target",
                "claude,antigravity,cursor,codex,agents-md,claude-md",
            ]
        )
        capsys.readouterr()
        assert rc1 == 0

        claude_skill = tmp_path / ".claude/skills/mintfig/SKILL.md"
        agy_skill = tmp_path / ".agents/skills/mintfig/SKILL.md"
        cursor_rule = tmp_path / ".cursor/rules/mintfig.mdc"
        codex_skill = tmp_path / ".codex/skills/mintfig/SKILL.md"

        assert claude_skill.exists()
        assert agy_skill.exists()
        assert cursor_rule.exists()
        assert codex_skill.exists()
        assert cursor_rule.read_text(encoding="utf-8").startswith("---")

        agents_after_1 = agents_md.read_text(encoding="utf-8")
        claude_after_1 = claude_md.read_text(encoding="utf-8")
        assert "Existing top notes." in agents_after_1
        assert "Keep this untouched." in claude_after_1
        assert agents_after_1.count("<!-- mintfig:start -->") == 1
        assert agents_after_1.count("<!-- mintfig:end -->") == 1
        assert claude_after_1.count("<!-- mintfig:start -->") == 1

        # Second run must be byte-identical and preserve user text
        written_2 = install_skill(
            tmp_path,
            targets=("claude", "antigravity", "cursor", "codex", "agents-md", "claude-md"),
        )
        assert len(written_2) == 6
        assert agents_md.read_text(encoding="utf-8") == agents_after_1
        assert claude_md.read_text(encoding="utf-8") == claude_after_1

    def test_cli_skill_print_and_snippet_no_disk_writes(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        rc_print = cli_main(["skill", "--print", "--root", str(tmp_path)])
        out_print = capsys.readouterr().out
        assert rc_print == 0
        assert "mintfig run" in out_print

        rc_snip = cli_main(["skill", "--snippet", "--root", str(tmp_path)])
        out_snip = capsys.readouterr().out
        assert rc_snip == 0
        assert "<!-- mintfig:start -->" in out_snip

        # Must not have written any files into tmp_path
        assert list(tmp_path.iterdir()) == []
