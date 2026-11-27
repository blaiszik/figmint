"""Tests for Universal Surface Auto-Router (mintfig.surface) and Ghostty/WezTerm/tmux passthrough."""

from __future__ import annotations

import base64
import dataclasses
import json
import re
import subprocess
import sys
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import pytest

matplotlib.use("Agg")

import mintfig as mint
from mintfig.explainer import EXAMPLE_SPEC
from mintfig.surface import (
    VALID_HARNESSES,
    VALID_SURFACES,
    SurfaceInfo,
    deliver_for_surface,
    detect_surface,
)
from mintfig.terminal import (
    detect_graphics_protocol,
    encode_iterm2_png,
    encode_kitty_png,
    show_in_terminal,
    wrap_tmux_passthrough,
)

_BRAILLE_RE = re.compile(r"[\u2801-\u28ff]")


def _unwrap_tmux_passthrough(wrapped: str) -> str:
    """Inverse of wrap_tmux_passthrough for round-trip verification."""
    assert wrapped.startswith("\x1bPtmux;")
    assert wrapped.endswith("\x1b\\")
    inner = wrapped[len("\x1bPtmux;") : -2]
    return inner.replace("\x1b\x1b", "\x1b")


def _sample_exp() -> mint.Explanation:
    return mint.explain(
        "Spearmint clears the 0.85 accuracy target while Baseline stalls at 0.72",
        mint.trend(
            [0, 500, 1000, 1500, 2000],
            {
                "Spearmint": [0.35, 0.68, 0.82, 0.89, 0.93],
                "Baseline": [0.35, 0.54, 0.64, 0.70, 0.72],
            },
            title="Validation curve",
            label="Accuracy",
            x_label="Step",
            highlight="Spearmint",
            reference=(0.85, "target"),
        ),
        style="pine",
    )


class TestGhosttyWezTermAndTmuxPassthrough:
    @pytest.mark.parametrize(
        ("env", "expected"),
        [
            ({"GHOSTTY_RESOURCES_DIR": "/Applications/Ghostty.app/Contents/Resources/ghostty"}, "kitty"),
            ({"TERM": "xterm-ghostty"}, "kitty"),
            ({"TERM_PROGRAM": "ghostty"}, "kitty"),
            ({"KITTY_WINDOW_ID": "7"}, "kitty"),
            ({"TERM": "xterm-kitty"}, "kitty"),
            ({"WEZTERM_EXECUTABLE": "/Applications/WezTerm.app/Contents/MacOS/wezterm-gui"}, "iterm2"),
            ({"WEZTERM_PANE": "0"}, "iterm2"),
            ({"TERM_PROGRAM": "WezTerm"}, "iterm2"),
            ({"ITERM_SESSION_ID": "w0t0p0:ABC-123"}, "iterm2"),
            ({"TERM_PROGRAM": "iTerm.app"}, "iterm2"),
            ({"LC_TERMINAL": "iTerm2"}, "iterm2"),
            ({"WT_SESSION": "guid-123"}, "unicode"),
            ({"TERM": "xterm-256color"}, "unicode"),
            ({}, "unicode"),
        ],
    )
    def test_detect_graphics_protocol_and_surface_parity(
        self, env: dict[str, str], expected: str
    ) -> None:
        assert detect_graphics_protocol(env) == expected
        assert detect_surface(env).protocol == expected

    def test_wrap_tmux_passthrough_round_trip_kitty_and_iterm2(self) -> None:
        assert wrap_tmux_passthrough("") == ""

        # Multi-chunk Kitty APC payload
        large_png = b"\x89PNG\r\n\x1a\n" + bytes(range(256)) * 32
        kitty_seq = encode_kitty_png(large_png)
        wrapped_kitty = wrap_tmux_passthrough(kitty_seq)
        assert wrapped_kitty.startswith("\x1bPtmux;\x1b\x1b_Ga=T,f=100,m=1;")
        assert wrapped_kitty.endswith("\x1b\x1b\\\x1b\\")
        # Inner body must never contain an unescaped single ESC
        inner_kitty = wrapped_kitty[len("\x1bPtmux;") : -2]
        assert "\x1b" not in inner_kitty.replace("\x1b\x1b", "")
        assert _unwrap_tmux_passthrough(wrapped_kitty) == kitty_seq

        # iTerm2 OSC 1337 payload
        small_png = b"\x89PNG\r\n\x1a\n" + b"MINTFIG"
        iterm_seq = encode_iterm2_png(small_png)
        wrapped_iterm = wrap_tmux_passthrough(iterm_seq)
        assert wrapped_iterm.startswith("\x1bPtmux;\x1b\x1b]1337;File=inline=1;")
        assert wrapped_iterm.endswith("\x07\x1b\\")
        assert _unwrap_tmux_passthrough(wrapped_iterm) == iterm_seq

        # Decode base64 back to exact bytes after unwrap
        unwrapped_b64 = _unwrap_tmux_passthrough(wrapped_iterm).split(":", 1)[1][:-1]
        assert base64.b64decode(unwrapped_b64) == small_png

    def test_show_in_terminal_tmux_passthrough_auto_explicit_and_opt_out(self) -> None:
        exp = _sample_exp()
        try:
            # Ghostty + TMUX auto mode -> Kitty APC wrapped in tmux DCS passthrough
            ghostty_tmux = show_in_terminal(
                exp,
                mode="auto",
                env={
                    "GHOSTTY_RESOURCES_DIR": "/usr/share/ghostty",
                    "TMUX": "/tmp/tmux-1000/default,1234,0",
                },
            )
            assert ghostty_tmux.startswith("\x1bPtmux;\x1b\x1b_Ga=T,f=100,")
            assert _unwrap_tmux_passthrough(ghostty_tmux).startswith("\x1b_Ga=T,f=100,")

            # WezTerm + TMUX auto mode -> iTerm2 OSC 1337 wrapped in tmux DCS passthrough
            wezterm_tmux = show_in_terminal(
                exp,
                mode="auto",
                env={
                    "WEZTERM_EXECUTABLE": "/usr/bin/wezterm",
                    "TMUX": "/tmp/tmux-1000/default,1234,0",
                },
            )
            assert wezterm_tmux.startswith("\x1bPtmux;\x1b\x1b]1337;File=inline=1;")
            assert _unwrap_tmux_passthrough(wezterm_tmux).startswith("\x1b]1337;File=inline=1;")

            # Explicit kitty/iterm2 modes inside TMUX default to passthrough=True
            explicit_kitty_tmux = show_in_terminal(
                exp,
                mode="kitty",
                env={"TMUX": "/tmp/tmux-1000/default,9,0"},
            )
            assert explicit_kitty_tmux.startswith("\x1bPtmux;")

            explicit_iterm_tmux = show_in_terminal(
                exp,
                mode="iterm2",
                env={"TMUX": "/tmp/tmux-1000/default,9,0"},
            )
            assert explicit_iterm_tmux.startswith("\x1bPtmux;")

            # passthrough=False disables tmux wrapping even when TMUX is set
            unwrapped = show_in_terminal(
                exp,
                mode="kitty",
                env={"TMUX": "/tmp/tmux-1000/default,9,0"},
                passthrough=False,
            )
            assert unwrapped.startswith("\x1b_Ga=T,f=100,")
            assert not unwrapped.startswith("\x1bPtmux;")

            # No TMUX -> raw Ghostty/WezTerm sequences
            ghostty_direct = show_in_terminal(
                exp,
                mode="auto",
                env={"GHOSTTY_RESOURCES_DIR": "/usr/share/ghostty"},
            )
            assert ghostty_direct.startswith("\x1b_Ga=T,f=100,")
        finally:
            plt.close(exp.fig)


class TestSurfaceDetection:
    def test_surface_info_frozen_and_json_serializable(self) -> None:
        info = detect_surface({"GHOSTTY_RESOURCES_DIR": "/usr/share/ghostty", "TMUX": "/tmp/tmux,1,0"})
        assert isinstance(info, SurfaceInfo)
        assert dataclasses.is_dataclass(info)
        with pytest.raises(dataclasses.FrozenInstanceError):
            info.surface = "ci_plain"  # type: ignore[misc]

        as_dict = info.to_dict()
        expected_keys = {
            "surface",
            "harness",
            "protocol",
            "color",
            "truecolor",
            "in_tmux",
            "width_cols",
            "prefers_dark",
            "supports_images",
            "supports_html",
            "reason",
        }
        assert set(as_dict) == expected_keys
        # Round-trips cleanly through json.dumps
        assert json.loads(json.dumps(as_dict)) == as_dict

    @pytest.mark.parametrize(
        ("env", "expected_harness", "expected_surface", "expected_protocol"),
        [
            ({"CLAUDECODE": "1"}, "claude_code", "terminal_braille", "unicode"),
            ({"CLAUDE_CODE_ENTRYPOINT": "cli"}, "claude_code", "terminal_braille", "unicode"),
            ({"ANTIGRAVITY_SESSION": "abc"}, "antigravity", "ide_chat", "unicode"),
            ({"AGY_WORKSPACE": "/tmp/ws"}, "antigravity", "ide_chat", "unicode"),
            ({"CURSOR_TRACE_ID": "xyz"}, "cursor", "ide_chat", "unicode"),
            ({"CODEX_SANDBOX": "seatbelt"}, "codex", "terminal_braille", "unicode"),
            ({"GEMINI_CLI": "1"}, "gemini_cli", "terminal_braille", "unicode"),
            ({"COLAB_RELEASE_TAG": "release-2026"}, "colab", "notebook_html", "unicode"),
            ({"JPY_PARENT_PID": "9999"}, "jupyter", "notebook_html", "unicode"),
            ({"MARIMO_RUNTIME_DIR": "/tmp/marimo"}, "marimo", "notebook_html", "unicode"),
            ({"GITHUB_ACTIONS": "true"}, "github_actions", "ci_plain", "unicode"),
            (
                {"GITHUB_ACTIONS": "true", "GITHUB_EVENT_NAME": "pull_request"},
                "github_actions",
                "github_pr",
                "unicode",
            ),
            (
                {"GITHUB_ACTIONS": "true", "GITHUB_STEP_SUMMARY": "/tmp/summary.md"},
                "github_actions",
                "github_pr",
                "unicode",
            ),
            ({"MINTFIG_MCP": "1"}, "unknown", "mcp", "unicode"),
            ({"MINTFIG_MCP": "1", "AGY_SESSION": "1"}, "antigravity", "mcp", "unicode"),
            ({"KITTY_WINDOW_ID": "3"}, "kitty", "terminal_image", "kitty"),
            ({"GHOSTTY_RESOURCES_DIR": "/usr/share/ghostty"}, "ghostty", "terminal_image", "kitty"),
            ({"TERM": "xterm-ghostty"}, "ghostty", "terminal_image", "kitty"),
            ({"ITERM_SESSION_ID": "w0t0p0:1"}, "iterm2", "terminal_image", "iterm2"),
            ({"WEZTERM_EXECUTABLE": "/usr/bin/wezterm"}, "wezterm", "terminal_image", "iterm2"),
            ({"WT_SESSION": "abc-def"}, "windows_terminal", "terminal_braille", "unicode"),
            ({"TERM": "xterm-256color"}, "terminal", "terminal_braille", "unicode"),
            ({"TERM": "dumb"}, "terminal", "terminal_ascii", "unicode"),
            ({"CI": "true"}, "unknown", "ci_plain", "unicode"),
            ({}, "unknown", "ci_plain", "unicode"),
        ],
    )
    def test_detect_every_harness_and_surface(
        self,
        env: dict[str, str],
        expected_harness: str,
        expected_surface: str,
        expected_protocol: str,
    ) -> None:
        info = detect_surface(env)
        assert info.harness == expected_harness
        assert info.surface == expected_surface
        assert info.protocol == expected_protocol
        assert info.harness in VALID_HARNESSES
        assert info.surface in VALID_SURFACES
        assert info.reason.strip() != ""

    def test_agent_harness_takes_precedence_over_outer_graphics_terminal(self) -> None:
        # Claude Code running inside Ghostty should not emit raw Kitty escapes
        info = detect_surface(
            {
                "CLAUDECODE": "1",
                "GHOSTTY_RESOURCES_DIR": "/Applications/Ghostty.app/Contents/Resources/ghostty",
                "TERM": "xterm-ghostty",
            }
        )
        assert info.harness == "claude_code"
        assert info.surface == "terminal_braille"
        assert info.protocol == "kitty"
        assert info.width_cols == 72
        assert info.supports_images is False

    def test_no_color_force_color_colorterm_and_tty_rules(self) -> None:
        # NO_COLOR disables color & truecolor everywhere
        no_color = detect_surface(
            {"TERM": "xterm-256color", "COLORTERM": "truecolor", "NO_COLOR": "1"}
        )
        assert no_color.color is False
        assert no_color.truecolor is False

        # NO_COLOR beats FORCE_COLOR
        both = detect_surface({"TERM": "xterm-256color", "NO_COLOR": "1", "FORCE_COLOR": "1"})
        assert both.color is False
        assert both.truecolor is False

        # FORCE_COLOR enables color even when is_tty=False
        forced = detect_surface(
            {"TERM": "xterm-256color", "COLORTERM": "24bit", "FORCE_COLOR": "1"},
            is_tty=False,
        )
        assert forced.color is True
        assert forced.truecolor is True
        assert forced.surface == "terminal_braille"

        # Non-TTY Kitty avoids emitting raw image escape sequences
        piped_kitty = detect_surface({"KITTY_WINDOW_ID": "1"}, is_tty=False)
        assert piped_kitty.surface == "terminal_ascii"
        assert piped_kitty.supports_images is False
        assert piped_kitty.color is False

        # COLORTERM=truecolor vs plain xterm-256color
        plain_256 = detect_surface({"TERM": "xterm-256color"}, is_tty=True)
        assert plain_256.color is True
        assert plain_256.truecolor is False

        tc = detect_surface({"TERM": "xterm-256color", "COLORTERM": "truecolor"}, is_tty=True)
        assert tc.color is True
        assert tc.truecolor is True

    def test_width_clamping_and_prefers_dark_heuristics(self) -> None:
        # Terminal width clamped to 56..132
        assert detect_surface({"TERM": "xterm-256color", "COLUMNS": "30"}).width_cols == 56
        assert detect_surface({"TERM": "xterm-256color", "COLUMNS": "96"}).width_cols == 96
        assert detect_surface({"TERM": "xterm-256color", "COLUMNS": "250"}).width_cols == 132

        # Chat / IDE / CI / Notebook default to 72 regardless of terminal COLUMNS
        assert detect_surface({"CLAUDECODE": "1", "COLUMNS": "140"}).width_cols == 72
        assert detect_surface({"ANTIGRAVITY_ENV": "1", "COLUMNS": "140"}).width_cols == 72
        assert detect_surface({"GITHUB_ACTIONS": "true", "COLUMNS": "140"}).width_cols == 72
        assert detect_surface({"COLAB_RELEASE_TAG": "1", "COLUMNS": "140"}).width_cols == 72

        # COLORFGBG detection (15;0 -> dark, 0;15 -> light)
        assert detect_surface({"TERM": "xterm-256color", "COLORFGBG": "15;0"}).prefers_dark is True
        assert detect_surface({"TERM": "xterm-256color", "COLORFGBG": "0;15"}).prefers_dark is False
        assert detect_surface({"TERM_PROGRAM": "Apple_Terminal"}).prefers_dark is False
        assert detect_surface({"GHOSTTY_RESOURCES_DIR": "/usr/share/ghostty"}).prefers_dark is True
        assert detect_surface({"JPY_PARENT_PID": "123"}).prefers_dark is False

    def test_surface_module_import_is_pure_stdlib(self) -> None:
        code = (
            "import sys; "
            "from mintfig.surface import detect_surface; "
            "info = detect_surface({'GHOSTTY_RESOURCES_DIR': '/usr/share/ghostty'}); "
            "heavy = [m for m in ('matplotlib', 'numpy', 'PIL') if m in sys.modules]; "
            "print(info.surface, info.harness, ','.join(heavy))"
        )
        proc = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True, check=True
        )
        assert proc.stdout.strip() == "terminal_image ghostty"


class TestDeliverForSurface:
    def test_deliver_terminal_image_ghostty_tmux_and_direct(self, tmp_path: Path) -> None:
        exp = _sample_exp()
        out_png = tmp_path / "curve.png"
        try:
            # Ghostty inside tmux -> inline_escape wrapped with wrap_tmux_passthrough
            res_tmux = deliver_for_surface(
                exp,
                out=out_png,
                env={
                    "GHOSTTY_RESOURCES_DIR": "/usr/share/ghostty",
                    "TMUX": "/tmp/tmux-1000/default,77,0",
                },
            )
            assert res_tmux["surface"] == "terminal_image"
            assert res_tmux["harness"] == "ghostty"
            assert res_tmux["mode"] == "kitty"
            assert res_tmux["image_path"] == str(out_png.resolve())
            assert out_png.exists()
            assert res_tmux["html"] is None
            assert res_tmux["inline_escape"] is not None
            assert res_tmux["inline_escape"].startswith("\x1bPtmux;\x1b\x1b_Ga=T,f=100,")
            assert _unwrap_tmux_passthrough(res_tmux["inline_escape"]).startswith("\x1b_Ga=T,f=100,")
            assert f"({out_png.resolve()})" in res_tmux["markdown"]
            assert res_tmux["caption"]

            # Direct WezTerm (no tmux) -> raw OSC 1337 iTerm2 sequence
            res_wez = deliver_for_surface(
                exp,
                env={"WEZTERM_EXECUTABLE": "/usr/bin/wezterm"},
            )
            assert res_wez["surface"] == "terminal_image"
            assert res_wez["harness"] == "wezterm"
            assert res_wez["mode"] == "iterm2"
            assert res_wez["inline_escape"].startswith("\x1b]1337;File=inline=1;")
            assert not res_wez["inline_escape"].startswith("\x1bPtmux;")
            assert res_wez["image_path"] is None
        finally:
            plt.close(exp.fig)

    def test_deliver_braille_ascii_and_no_color(self) -> None:
        exp = _sample_exp()
        try:
            braille = deliver_for_surface(exp, env={"CLAUDECODE": "1"})
            assert braille["surface"] == "terminal_braille"
            assert braille["harness"] == "claude_code"
            assert braille["mode"] == "braille"
            assert braille["inline_escape"] is None
            assert braille["html"] is None
            assert _BRAILLE_RE.search(braille["text"])
            assert "\x1b[" in braille["text"]
            assert "\x1b[" not in braille["markdown"]

            braille_no_color = deliver_for_surface(
                exp, env={"CLAUDECODE": "1", "NO_COLOR": "1"}
            )
            assert braille_no_color["surface"] == "terminal_braille"
            assert _BRAILLE_RE.search(braille_no_color["text"])
            assert "\x1b[" not in braille_no_color["text"]

            ci = deliver_for_surface(exp, env={"GITHUB_ACTIONS": "true"})
            assert ci["surface"] == "ci_plain"
            assert ci["harness"] == "github_actions"
            assert ci["mode"] == "ascii"
            assert ci["text"].isascii()
            assert "\x1b[" not in ci["text"]

            forced_ascii = deliver_for_surface(exp, surface="terminal_ascii")
            assert forced_ascii["surface"] == "terminal_ascii"
            assert forced_ascii["mode"] == "ascii"
            assert forced_ascii["text"].isascii()
        finally:
            plt.close(exp.fig)

    def test_deliver_notebook_ide_chat_github_pr_mcp_and_spec_dict(self, tmp_path: Path) -> None:
        # Works directly on a spec dict (EXAMPLE_SPEC)
        nb = deliver_for_surface(EXAMPLE_SPEC, env={"COLAB_RELEASE_TAG": "2026"})
        assert nb["surface"] == "notebook_html"
        assert nb["harness"] == "colab"
        assert nb["mode"] == "html"
        assert nb["html"] is not None
        assert "<figure" in nb["html"] and "<svg" in nb["html"]
        assert "<!DOCTYPE html>" not in nb["html"]  # fragment for notebooks

        ide = deliver_for_surface(EXAMPLE_SPEC, env={"ANTIGRAVITY_ENV": "1"})
        assert ide["surface"] == "ide_chat"
        assert ide["harness"] == "antigravity"
        assert ide["mode"] == "html"
        assert ide["html"] is not None
        assert ide["html"].startswith("<!DOCTYPE html>")
        assert "<svg" in ide["html"]
        assert "\x1b[" not in ide["text"]

        pr_png = tmp_path / "pr_fig.png"
        pr = deliver_for_surface(
            EXAMPLE_SPEC,
            out=pr_png,
            env={"GITHUB_ACTIONS": "true", "GITHUB_EVENT_NAME": "pull_request"},
        )
        assert pr["surface"] == "github_pr"
        assert pr["harness"] == "github_actions"
        assert pr["mode"] == "markdown"
        assert pr["html"] is None
        assert pr["image_path"] == str(pr_png.resolve())
        assert "<details>" in pr["markdown"]
        assert "Computed facts" in pr["markdown"]
        assert f"({pr_png.resolve()})" in pr["markdown"]

        mcp = deliver_for_surface(EXAMPLE_SPEC, surface="mcp", env={"CURSOR_AGENT": "1"})
        assert mcp["surface"] == "mcp"
        assert mcp["harness"] == "cursor"
        assert mcp["mode"] == "mcp"
        assert mcp["html"] is not None
        assert "<svg" in mcp["html"]

        out_html = tmp_path / "out.html"
        html_saved = deliver_for_surface(EXAMPLE_SPEC, surface="ide_chat", out=out_html)
        assert out_html.exists()
        assert html_saved["image_path"] == str(out_html.resolve())
        assert html_saved["html"] is not None and html_saved["html"].startswith("<!DOCTYPE html>")

    def test_deliver_for_surface_errors(self) -> None:
        with pytest.raises(ValueError, match="Unknown surface"):
            deliver_for_surface(EXAMPLE_SPEC, surface="hologram")
        with pytest.raises(TypeError):
            deliver_for_surface("not-a-figure")
