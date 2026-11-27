"""Tests for `mintfig demo`, 6-surface showcase HTML, CLI `mcp`/`demo` wiring, and `mintfig doctor`."""

from __future__ import annotations

import json
import re
import sys
import types
from pathlib import Path
from typing import Any

import matplotlib
import matplotlib.pyplot as plt
import pytest

matplotlib.use("Agg")

from mintfig.cli import main as cli_main
from mintfig.demo import run_demo

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
_BRAILLE_RE = re.compile(r"[\u2801-\u28ff]")


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


@pytest.fixture(autouse=True)
def _close_figs() -> Any:
    yield
    plt.close("all")


def test_cli_help_lists_mcp_and_demo(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        cli_main(["--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "mcp" in out
    assert "demo" in out

    with pytest.raises(SystemExit) as exc2:
        cli_main(["demo", "--help"])
    assert exc2.value.code == 0
    demo_help = capsys.readouterr().out
    for flag in ("--html", "--style", "--width", "--no-color", "--ascii"):
        assert flag in demo_help


def test_demo_no_color_fits_72_cols_and_renders_all_sections(
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = cli_main(["demo", "--no-color"])
    assert rc == 0
    out = capsys.readouterr().out

    assert "\x1b[" not in out
    assert "Detected surface:" in out
    assert "Retrieval" in out
    assert "LoRA-only" in out
    assert "91.4%" in out
    assert "LR decay" in out
    assert _BRAILLE_RE.search(out) is not None
    # PR KPI Summary Card box borders & inline sparklines
    assert "╭" in out and "╯" in out
    assert any(ch in out for ch in "▁▂▃▄▅▆▇█")
    # 2-line Next steps footer
    assert "mintfig mcp --install" in out
    assert "mintfig plot data.csv --braille" in out
    assert "mintfig demo --html showcase.html" in out

    max_len = max(len(line) for line in out.splitlines())
    assert max_len <= 72, f"Expected all lines <= 72 cols, got max_len={max_len}"


def test_demo_ascii_is_pure_ascii_and_fits_72_cols(
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = cli_main(["demo", "--ascii"])
    assert rc == 0
    out = capsys.readouterr().out

    assert "\x1b[" not in out
    assert "Detected surface:" in out
    assert _BRAILLE_RE.search(out) is None
    assert "╭" not in out
    assert "+" in out and "-" in out and "|" in out
    non_ascii = [ch for ch in out if ord(ch) >= 128]
    assert non_ascii == [], f"Unexpected non-ASCII characters: {non_ascii[:10]}"
    max_len = max(len(line) for line in out.splitlines())
    assert max_len <= 72


def test_demo_color_pine_and_custom_width(capsys: pytest.CaptureFixture[str]) -> None:
    res = run_demo(width=72, color=True, style="pine", ascii_only=False)
    out = capsys.readouterr().out
    assert res["width"] == 72
    assert res["color"] is True
    assert "\x1b[" in out
    assert "\x1b[38;2;" in out or "\x1b[1;38;2;" in out
    stripped_lines = [_strip_ansi(ln) for ln in out.splitlines()]
    assert max(len(ln) for ln in stripped_lines) <= 72


def test_demo_html_showcase_contains_all_six_surfaces(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    html_path = tmp_path / "showcase.html"
    rc = cli_main(["demo", "--no-color", "--html", str(html_path)])
    assert rc == 0
    term_out = capsys.readouterr().out
    assert max(len(line) for line in term_out.splitlines()) <= 72

    assert html_path.is_file()
    content = html_path.read_text(encoding="utf-8")

    # Zero-CDN self-contained HTML5
    assert content.lstrip().startswith("<!DOCTYPE html>")
    assert "<script src=" not in content
    assert '<link rel="stylesheet" href="http' not in content
    assert "One Dataset, Six Surfaces" in content

    # All 6 surface cards present
    expected_surfaces = (
        "terminal_braille",
        "chat_png_mint",
        "dark_png_pine",
        "pr_card",
        "interactive_html",
        "nature_publication",
    )
    for surface_key in expected_surfaces:
        assert f'data-surface="{surface_key}"' in content

    # Surface 1: Pine #0F1715 terminal frame + Braille curves
    assert "#0F1715" in content
    assert _BRAILLE_RE.search(content) is not None

    # Surfaces 2, 3, 4, 6: Embedded base64 PNGs (4 distinct images)
    png_matches = re.findall(r"data:image/png;base64,[A-Za-z0-9+/=]+", content)
    assert len(png_matches) >= 4
    assert len(set(png_matches)) >= 4

    # Surface 5: Interactive hover-to-cite HTML fragment (<svg + data-mf)
    assert "<svg" in content
    assert "data-mf=" in content
    assert "Copy SVG" in content

    # Surface 6: Nature 89 mm publication preview + auto-drafted caption.txt + LaTeX figure.tex
    assert "Nature" in content and "89 mm" in content
    assert "Auto-drafted caption.txt" in content
    assert "Retrieval reaches 91.4%" in content
    assert "\\begin{figure}" in content


def test_demo_optional_mintchip_table_included_when_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeTable:
        def text(self, *, width: int = 72, color: bool = False, ascii: bool = False, braille: bool = True) -> str:
            return "mintchip shared-scale Braille table (5 seeds)\nRetrieval  91.4%  +16.3 pts"

    fake_mc = types.SimpleNamespace(table=lambda *a, **kw: _FakeTable())
    monkeypatch.setattr("mintfig.demo.import_mintchip", lambda: fake_mc)

    res = run_demo(width=72, color=False, quiet=True)
    assert res["has_mintchip"] is True
    assert "mintchip shared-scale Braille table" in res["terminal"]
    assert max(len(ln) for ln in res["terminal"].splitlines()) <= 72


def test_demo_skips_mintchip_gracefully_when_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("mintfig.demo.import_mintchip", lambda: None)
    res = run_demo(width=72, color=False, quiet=True)
    assert res["has_mintchip"] is False
    assert "Detected surface:" in res["terminal"]


def test_doctor_json_and_text_report_upgraded_fields(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = cli_main(["doctor", "--json", "--out", str(tmp_path)])
    assert rc == 0
    report = json.loads(capsys.readouterr().out)

    # Preserve legacy `surfaces` contract expected by test_delivery.py
    assert set(report["surfaces"]) == {
        "inline_image_protocol",
        "body_font",
        "stdout_is_tty",
        "notebook",
    }

    # New upgraded fields
    assert isinstance(report["surface"], str) and report["surface"]
    assert isinstance(report["harness"], str) and report["harness"]
    assert isinstance(report["surface_info"], dict)
    assert report["graphics_protocol"] in {"kitty", "iterm2", "unicode"}
    assert isinstance(report["tmux_passthrough"], dict)
    assert {"in_tmux", "supported", "active"} <= set(report["tmux_passthrough"])
    assert isinstance(report["truecolor"], bool)
    assert isinstance(report["braille"], bool)
    assert isinstance(report["mintchip"], dict)
    assert "available" in report["mintchip"]
    assert isinstance(report["mcp"], dict)

    # Human-readable text output
    rc_txt = cli_main(["doctor", "--out", str(tmp_path)])
    assert rc_txt == 0
    txt = capsys.readouterr().out
    for label in (
        "detected surface:",
        "detected harness:",
        "graphics protocol:",
        "tmux passthrough:",
        "truecolor:",
        "braille support:",
        "mintchip:",
        "mcp hosts:",
        "inline image protocol:",
    ):
        assert label in txt


def test_cli_mcp_dispatch(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[list[str]] = []
    fake_mod = types.ModuleType("mintfig.mcp_server")

    def _fake_cli_mcp(argv: list[str]) -> int:
        captured.append(list(argv))
        return 0

    fake_mod.cli_mcp = _fake_cli_mcp  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "mintfig.mcp_server", fake_mod)

    rc = cli_main(["mcp", "--status"])
    assert rc == 0
    assert captured == [["--status"]]
