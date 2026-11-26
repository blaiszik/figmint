"""Regression tests for runner backend isolation, reproducible export, save_figure API, and proof layout."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pytest
from matplotlib.figure import Figure
from PIL import Image
from pypdf import PdfReader

matplotlib.use("Agg")

import mintfig as mint
from mintfig import proof as proof_mod
from mintfig.cli import _format_all_specs, _format_single_spec
from mintfig.export import rasterize_heavy, save_figure
from mintfig.plate import Plate
from mintfig.preflight import CheckResult, preflight_figure
from mintfig.runner import run_script
from mintfig.specs import JournalSpec, get_spec, mm_to_in

PT_TO_MM = 25.4 / 72.0

DOUBLE_90_SCRIPT = (
    "import mintfig as mint\n"
    "def build():\n"
    "    return mint.Plate(journal='nature', width='double', height_mm=90.0, layout=(1, 3))\n"
)

DETERMINISM_SCRIPT = (
    "import numpy as np\n"
    "import mintfig as mint\n"
    "def build():\n"
    "    p = mint.Plate(journal='nature', width='double', height_mm=70.0, layout=(1, 2))\n"
    "    x = np.linspace(0, 5, 60)\n"
    "    p['a'].plot(x, np.exp(-x), label='decay')\n"
    "    p['a'].set_xlabel('Time (s)')\n"
    "    p['a'].set_ylabel('Signal')\n"
    "    rng = np.random.default_rng(3)\n"
    "    p['b'].imshow(rng.random((12, 12)), cmap='viridis')\n"
    "    p['b'].scatter(rng.normal(size=300), rng.normal(size=300), s=2)\n"
    "    p.label_panels()\n"
    "    return p\n"
)


def _mintfig_cmd() -> list[str]:
    mintfig_bin = Path(sys.executable).parent / "mintfig"
    if mintfig_bin.exists():
        return [str(mintfig_bin)]
    return [sys.executable, "-m", "mintfig.cli"]


def _env_without_backend(tmp_path: Path) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k != "MPLBACKEND"}
    env.setdefault("MPLCONFIGDIR", str(tmp_path / "mplconfig"))
    return env


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _small_plate(journal: str = "nature") -> Plate:
    plate = Plate(journal=journal, width="single", height_mm=60.0, layout=(1, 1))
    x = np.linspace(0, 4, 50)
    plate["a"].plot(x, np.sin(x))
    plate["a"].set_xlabel("x (a.u.)")
    plate["a"].set_ylabel("y (a.u.)")
    return plate


class TestRunnerHeadlessBackend:
    def test_cli_run_without_mplbackend_locks_exact_mm(self, tmp_path: Path) -> None:
        script = tmp_path / "double90.py"
        script.write_text(DOUBLE_90_SCRIPT, encoding="utf-8")
        out_dir = tmp_path / "bundle"
        proc = subprocess.run(
            [
                *_mintfig_cmd(),
                "run",
                str(script),
                "--journal",
                "nature",
                "--bundle",
                str(out_dir),
                "--no-proof",
                "--json",
            ],
            capture_output=True,
            text=True,
            check=False,
            env=_env_without_backend(tmp_path),
        )
        assert proc.returncode in (0, 1), proc.stderr
        payload = json.loads(proc.stdout)
        assert payload["dimensions_mm"]["width"] == pytest.approx(183.0, abs=0.01)
        assert payload["dimensions_mm"]["height"] == pytest.approx(90.0, abs=0.01)

        box = PdfReader(str(out_dir / "figure.pdf")).pages[0].mediabox
        assert float(box.width) * PT_TO_MM == pytest.approx(183.0, abs=0.01)
        assert float(box.height) * PT_TO_MM == pytest.approx(90.0, abs=0.01)

    def test_run_script_ignores_script_backend_switch_and_restores_caller_backend(
        self, tmp_path: Path
    ) -> None:
        script = tmp_path / "switches.py"
        script.write_text(
            "import matplotlib\n"
            "matplotlib.use('svg')\n"
            "import matplotlib.pyplot as plt\n"
            "plt.switch_backend('pdf')\n" + DOUBLE_90_SCRIPT,
            encoding="utf-8",
        )
        original_use = matplotlib.use
        original_switch = plt.switch_backend
        plt.switch_backend("pdf")
        try:
            result = run_script(script, journal="nature")
            assert result.report is not None
            assert result.report.width_mm == pytest.approx(183.0, abs=0.01)
            assert result.report.height_mm == pytest.approx(90.0, abs=0.01)
            assert matplotlib.get_backend().lower() == "pdf"
            assert matplotlib.use is original_use
            assert plt.switch_backend is original_switch
        finally:
            plt.switch_backend("agg")


class TestBuildErrorLineInfo:
    def test_build_exception_reports_script_line(self, tmp_path: Path) -> None:
        script = tmp_path / "bad_build.py"
        script.write_text(
            "import mintfig as mint\n"
            "\n"
            "def build():\n"
            "    x = 1\n"
            "    raise RuntimeError('boom in build')\n",
            encoding="utf-8",
        )
        result = run_script(script)
        assert result.exit_code == 2
        assert result.stage == "runtime"
        assert result.error == "RuntimeError in build() at bad_build.py:5: boom in build"

    def test_build_exception_in_helper_reports_innermost_script_line(
        self, tmp_path: Path
    ) -> None:
        script = tmp_path / "bad_helper.py"
        script.write_text(
            "import mintfig as mint\n"
            "\n"
            "def helper():\n"
            "    return mint.Plate(journal='nature', width='nope', height_mm=50.0)\n"
            "\n"
            "def build():\n"
            "    return helper()\n",
            encoding="utf-8",
        )
        result = run_script(script)
        assert result.exit_code == 2
        assert result.error is not None
        assert result.error.startswith("ValueError in build() at bad_helper.py:4: ")


class TestReproducibleExport:
    @pytest.mark.parametrize("suffix", [".pdf", ".svg", ".png"])
    def test_save_figure_twice_is_byte_identical(self, tmp_path: Path, suffix: str) -> None:
        # Two identically built figures: a re-save of the *same* live figure can
        # differ in SVG clip-path ids because constrained_layout re-solves the
        # layout with last-bit float differences between consecutive draws.
        paths = []
        for name in ("a", "b"):
            plate = _small_plate()
            try:
                paths.append(save_figure(plate.fig, tmp_path / f"{name}{suffix}"))
            finally:
                plt.close(plate.fig)
        assert paths[0].read_bytes() == paths[1].read_bytes()

    def test_figure_without_layout_engine_resaves_identically(self, tmp_path: Path) -> None:
        fig, ax = plt.subplots(figsize=(3.0, 2.0))
        ax.plot([0, 1, 2], [1, 0, 1])
        ax.set_xlabel("x")
        try:
            for suffix in (".pdf", ".svg"):
                first = save_figure(fig, tmp_path / f"same1{suffix}")
                second = save_figure(fig, tmp_path / f"same2{suffix}")
                assert first.read_bytes() == second.read_bytes(), suffix
        finally:
            plt.close(fig)

    def test_vector_metadata_keeps_creator_and_drops_dates(self, tmp_path: Path) -> None:
        plate = _small_plate()
        try:
            pdf = save_figure(plate.fig, tmp_path / "m.pdf")
            svg = save_figure(plate.fig, tmp_path / "m.svg")
        finally:
            plt.close(plate.fig)
        info = PdfReader(str(pdf)).metadata
        assert info is not None
        assert info.get("/Creator") == "mintfig"
        assert "/CreationDate" not in info
        svg_text = svg.read_text(encoding="utf-8")
        assert "mintfig" in svg_text
        assert "<dc:date>" not in svg_text

    def test_bundle_twice_produces_identical_vector_and_preview_files(
        self, tmp_path: Path
    ) -> None:
        script = tmp_path / "det.py"
        script.write_text(DETERMINISM_SCRIPT, encoding="utf-8")
        outs = [tmp_path / "out1", tmp_path / "out2"]
        for out in outs:
            proc = subprocess.run(
                [*_mintfig_cmd(), "run", str(script), "--bundle", str(out), "--no-proof", "--json"],
                capture_output=True,
                text=True,
                check=False,
                env=_env_without_backend(tmp_path),
            )
            assert proc.returncode in (0, 1), proc.stderr
        for name in ("figure.pdf", "figure.svg", "preview.png"):
            assert _sha256(outs[0] / name) == _sha256(outs[1] / name), name


class TestSaveFigureRasterizationSideEffects:
    def test_save_figure_restores_rasterized_state(self, tmp_path: Path) -> None:
        rng = np.random.default_rng(0)
        plate = Plate(journal="nature", width="single", height_mm=60.0, layout=(1, 1))
        ax = plate["a"]
        dense = ax.scatter(rng.normal(size=20_000), rng.normal(size=20_000), s=1)
        already = ax.scatter(rng.normal(size=20_000), rng.normal(size=20_000), s=1)
        already.set_rasterized(True)
        try:
            save_figure(plate.fig, tmp_path / "dense.pdf", rasterize_above=10_000)
            assert dense.get_rasterized() is False
            assert already.get_rasterized() is True
        finally:
            plt.close(plate.fig)

    def test_rasterize_heavy_remains_permanent(self) -> None:
        rng = np.random.default_rng(1)
        fig, ax = plt.subplots()
        dense = ax.scatter(rng.normal(size=20_000), rng.normal(size=20_000), s=1)
        try:
            assert rasterize_heavy(fig, threshold=10_000) == 1
            assert dense.get_rasterized() is True
        finally:
            plt.close(fig)


class TestSaveFigureJournalArgument:
    def _png_width_px(self, path: Path) -> int:
        with Image.open(path) as img:
            return img.size[0]

    def test_journal_name_spec_and_figure_tag(self, tmp_path: Path) -> None:
        fig, ax = mint.figure("science", width="single", height_mm=40.0)
        ax.plot([0, 1], [0, 1])
        science = get_spec("science")
        nature = get_spec("nature")
        expected_science = round(mm_to_in(55.0) * science.dpi_combo)
        expected_nature = round(mm_to_in(55.0) * nature.dpi_combo)
        try:
            by_name = save_figure(fig, tmp_path / "name.png", journal="science")
            by_spec_obj = save_figure(fig, tmp_path / "specobj.png", journal=science)
            legacy = save_figure(fig, tmp_path / "legacy.png", spec=science)
            tagged = save_figure(fig, tmp_path / "tagged.png")
            override = save_figure(fig, tmp_path / "override.png", journal="nature")
            with pytest.raises(ValueError):
                save_figure(fig, tmp_path / "conflict.png", journal="nature", spec=science)
        finally:
            plt.close(fig)
        for path in (by_name, by_spec_obj, legacy, tagged):
            assert abs(self._png_width_px(path) - expected_science) <= 1, path.name
        assert abs(self._png_width_px(override) - expected_nature) <= 1

    def test_untagged_figure_defaults_to_500_dpi(self, tmp_path: Path) -> None:
        fig = plt.figure(figsize=(2.0, 1.0))
        try:
            out = save_figure(fig, tmp_path / "plain.png")
        finally:
            plt.close(fig)
        assert self._png_width_px(out) == 1000


class TestLastVerifiedDefault:
    def test_custom_spec_defaults_to_unverified(self) -> None:
        base = get_spec("nature")
        custom = JournalSpec(
            name="custom",
            display_name="Custom Journal",
            widths_mm={"single": 80.0},
            max_height_mm=200.0,
            max_page_height_mm=240.0,
            font_family=base.font_family,
            font_min_pt=5.0,
            font_max_pt=8.0,
            body_pt=7.0,
            tick_pt=6.0,
            legend_pt=6.0,
            panel_label_pt=8.0,
            panel_label_case="lower",
        )
        assert custom.last_verified == ""
        assert "(unverified)" in _format_single_spec(custom)

    @pytest.mark.parametrize("journal", ["nature", "science", "science_advances"])
    def test_builtin_specs_keep_explicit_dates(self, journal: str) -> None:
        spec = get_spec(journal)
        assert spec.last_verified == "2026-11-23"
        assert "verified 2026-11-23" in _format_single_spec(spec)
        assert "2026-11-23" in _format_all_specs()


class TestProofScorecardRows:
    @pytest.mark.parametrize("n_rows", [8, 9, 10])
    def test_two_line_messages_never_touch_row_dividers(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, n_rows: int
    ) -> None:
        captured: list[Figure] = []

        class _CapturingFigure(Figure):
            def __init__(self, *args: object, **kwargs: object) -> None:
                super().__init__(*args, **kwargs)  # type: ignore[arg-type]
                captured.append(self)

        monkeypatch.setattr(proof_mod, "Figure", _CapturingFigure)

        plate = _small_plate()
        try:
            report = preflight_figure(plate.fig, "nature")
            long_msg = (
                "width 121.9 mm does not match allowed nature widths [89, 120, 183] mm "
                "(+/-0.5 mm); height 80.0 mm <= 170.0 mm"
            )
            checks = [
                CheckResult(rule=f"rule_{i}", status="warn" if i % 2 else "pass", message=long_msg)
                for i in range(n_rows)
            ]
            report.checks[:] = checks
            out = proof_mod.render_proof_sheet(plate.fig, report, tmp_path / "proof.png", dpi=120)
        finally:
            plt.close(plate.fig)

        assert out.exists()
        proof_fig = captured[0]
        ui_ax = proof_fig.axes[0]
        renderer = proof_fig.canvas.get_renderer()

        divider_ys = [
            ui_ax.transData.transform((0.0, line.get_ydata()[0]))[1]
            for line in ui_ax.lines
            if matplotlib.colors.same_color(line.get_color(), proof_mod._ROW_DIVIDER_COLOR)
        ]
        assert len(divider_ys) == n_rows - 1

        messages = [t for t in ui_ax.texts if t.get_text() and "\n" in t.get_text()]
        assert len(messages) == n_rows
        for text in messages:
            bbox = text.get_window_extent(renderer)
            for y in divider_ys:
                clearance = min(abs(bbox.y0 - y), abs(bbox.y1 - y))
                straddles = bbox.y0 <= y <= bbox.y1
                assert not straddles, f"divider at y={y:.1f}px crosses {text.get_text()!r}"
                assert clearance >= 1.0, f"divider at y={y:.1f}px touches {text.get_text()!r}"


USE_CONTEXT_SCRIPT = (
    "import matplotlib.pyplot as plt\n"
    "import mintfig as mint\n"
    "from mintfig.specs import mm_to_in\n"
    "with mint.pub.use('nature'):\n"
    "    fig, ax = plt.subplots(figsize=(mm_to_in(89.0), mm_to_in(60.0)), layout='constrained')\n"
    "    ax.plot([0, 1], [0, 1])\n"
    "    ax.set_xlabel('x (a.u.)')\n"
    "    ax.set_ylabel('y (a.u.)')\n"
)

# Stock Matplotlib font embedding, pinned so earlier tests that applied a mintfig
# style globally cannot hide the live-rcParams prediction under test.
STOCK_FONT_RC = {"pdf.fonttype": 3, "svg.fonttype": "path"}


class TestPdfResultOverridesLivePrediction:
    """The exported PDF decides ``vector_fonts``; live rcParams are only a prediction."""

    def test_use_context_figure_warns_without_bundle(self, tmp_path: Path) -> None:
        script = tmp_path / "plot.py"
        script.write_text(USE_CONTEXT_SCRIPT, encoding="utf-8")
        with matplotlib.rc_context(STOCK_FONT_RC):
            result = run_script(script, journal="nature")
        assert result.report is not None
        rules = {c.rule: c.status for c in result.report.checks}
        assert rules["vector_fonts"] == "warn"

    def test_bundle_replaces_live_warning_with_pdf_pass(self, tmp_path: Path) -> None:
        script = tmp_path / "plot.py"
        script.write_text(USE_CONTEXT_SCRIPT, encoding="utf-8")
        with matplotlib.rc_context(STOCK_FONT_RC):
            result = run_script(script, journal="nature", bundle_dir=tmp_path / "out")
        assert result.report is not None
        rules = {c.rule: c.status for c in result.report.checks}
        assert rules["vector_fonts"] == "pass"
        assert result.report.warnings == []
        payload = json.loads((tmp_path / "out" / "report.json").read_text(encoding="utf-8"))
        assert payload["summary"]["warnings"] == 0


BOLD_LABEL_SCRIPT = (
    "import mintfig as mint\n"
    "def build():\n"
    "    p = mint.Plate(journal='nature', width='single', height_mm=60.0, layout=(1, 2))\n"
    "    p['a'].plot([0, 1], [0, 1])\n"
    "    p['b'].plot([0, 1], [1, 0])\n"
    "    p.label_panels()\n"
    "    return p\n"
)


class TestCliPinsHashSeed:
    """``mintfig run`` pins PYTHONHASHSEED so embedded bold-font subsets are reproducible."""

    def test_no_rerun_when_seed_already_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from mintfig import cli

        monkeypatch.setenv("PYTHONHASHSEED", "7")
        monkeypatch.setattr(
            cli.subprocess, "call", lambda *a, **k: pytest.fail("must not re-run")
        )
        assert cli._rerun_with_fixed_hash_seed() is None

    def test_rerun_sets_seed_zero_and_returns_child_code(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from mintfig import cli

        seen: dict[str, object] = {}

        def fake_call(cmd: list[str], env: dict[str, str]) -> int:
            seen["cmd"], seen["seed"] = cmd, env["PYTHONHASHSEED"]
            return 1

        monkeypatch.delenv("PYTHONHASHSEED", raising=False)
        monkeypatch.setattr(cli.subprocess, "call", fake_call)
        assert cli._rerun_with_fixed_hash_seed() == 1
        assert seen["seed"] == "0"
        assert seen["cmd"][:3] == [sys.executable, "-m", "mintfig.cli"]

    def test_unset_seed_matches_seed_zero_pdf(self, tmp_path: Path) -> None:
        script = tmp_path / "plot.py"
        script.write_text(BOLD_LABEL_SCRIPT, encoding="utf-8")
        digests = []
        for name, seed in (("unset", None), ("zero", "0")):
            env = {k: v for k, v in os.environ.items() if k not in {"MPLBACKEND", "PYTHONHASHSEED"}}
            if seed is not None:
                env["PYTHONHASHSEED"] = seed
            out = tmp_path / name
            proc = subprocess.run(
                [sys.executable, "-m", "mintfig.cli", "run", str(script), "--bundle", str(out), "--json"],
                capture_output=True,
                text=True,
                env=env,
                check=False,
            )
            assert proc.returncode == 0, proc.stderr
            assert json.loads(proc.stdout)["ok"] is True
            digests.append(hashlib.sha256((out / "figure.pdf").read_bytes()).hexdigest())
        assert digests[0] == digests[1]
