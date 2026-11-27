"""Tests for SummaryCard.to_terminal(), Explanation.to_text()/show(), CLI --braille, and mintfig watch."""

from __future__ import annotations

import io
import json
import os
import re
import shutil
from pathlib import Path
from typing import Any

import matplotlib
import matplotlib.pyplot as plt
import pytest

matplotlib.use("Agg")

import mintfig as mint
from mintfig.card import EXAMPLE_CARD_SPEC, card, cli_card
from mintfig.cli import main as cli_main
from mintfig.explainer import EXAMPLE_SPEC

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
_BRAILLE_RE = re.compile(r"[\u2801-\u28ff]")


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


def _rgb_seq(hex_color: str) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"38;2;{r};{g};{b}m"


@pytest.fixture(autouse=True)
def _close_figs() -> Any:
    yield
    plt.close("all")


def _sample_metrics() -> list[dict[str, Any]]:
    return [
        {
            "label": "p99 latency",
            "value": "248 ms",
            "delta": "-38%",
            "good": True,
            "spark": [410, 405, 398, 390, 310, 265, 248],
            "note": "vs 400 ms base",
        },
        {
            "label": "Availability",
            "value": "99.94%",
            "delta": "+0.02 pts",
            "good": True,
            "spark": [99.91, 99.92, 99.92, 99.93, 99.93, 99.94, 99.94],
        },
        {
            "label": "Error rate",
            "value": "0.06%",
            "delta": "-0.04 pts",
            "good": True,
            "spark": [0.11, 0.10, 0.10, 0.09, 0.08, 0.07, 0.06],
        },
        {
            "label": "Peak RSS",
            "value": "412 MB",
            "delta": "+18 MB",
            "good": False,
            "spark": [392, 394, 395, 394, 406, 410, 412],
            "note": "cache warm-up",
        },
    ]


# --------------------------------------------------------------------------- #
# 1. SummaryCard.to_terminal() & mintfig card --terminal
# --------------------------------------------------------------------------- #


class TestSummaryCardToTerminal:
    def test_unicode_box_tiles_braille_sparklines_and_alignment(self) -> None:
        c = card(
            "PR #418 cuts checkout p99 latency 38% while holding 99.94% availability",
            _sample_metrics(),
            subtitle="checkout-service canary · 7-day window",
            source="perf-canary 2026-11",
        )
        rendered = c.to_terminal(width=76, color=True)
        plain = _strip_ansi(rendered)
        lines = plain.splitlines()

        # Header accent bar, takeaway, subtitle, footer source
        assert lines[0].startswith("━") and "─" in lines[0]
        assert len(lines[0]) == 76
        assert "PR #418 cuts checkout p99 latency 38%" in plain
        assert "checkout-service canary" in plain
        assert "Source: perf-canary 2026-11" in plain

        # Crisp Unicode rounded box tiles arranged horizontally (4 tiles on one row)
        top_edges = [ln for ln in lines if "╭" in ln and "╮" in ln]
        bot_edges = [ln for ln in lines if "╰" in ln and "╯" in ln]
        assert len(top_edges) == 1
        assert len(bot_edges) == 1
        assert top_edges[0].count("╭") == 4
        assert bot_edges[0].count("╰") == 4

        # Every line inside the KPI tile block has the exact same visible width
        tile_start = lines.index(top_edges[0])
        tile_end = lines.index(bot_edges[0])
        tile_widths = {len(lines[i]) for i in range(tile_start, tile_end + 1)}
        assert len(tile_widths) == 1
        assert next(iter(tile_widths)) <= 76

        # Native monospace block sparklines inside boxed tiles + semantic ANSI delta colors
        assert any(ch in plain for ch in "▁▂▃▄▅▆▇█")
        assert "\x1b[" in rendered
        assert _rgb_seq("#0F8B6D") in rendered  # good=True green/emerald
        assert _rgb_seq("#C93B2B") in rendered  # good=False crimson
        assert "248 ms" in plain
        assert "412 MB" in plain
        assert "vs 400 ms base" in plain

    def test_narrow_width_wraps_tiles_into_two_rows(self) -> None:
        c = card("Release v2.4 trims latency across all clusters", _sample_metrics())
        plain = _strip_ansi(c.to_terminal(width=48, color=False))
        assert "\x1b" not in c.to_terminal(width=48, color=False)
        lines = plain.splitlines()

        top_edges = [ln for ln in lines if "╭" in ln and "╮" in ln]
        bot_edges = [ln for ln in lines if "╰" in ln and "╯" in ln]
        assert len(top_edges) == 2
        assert len(bot_edges) == 2
        assert top_edges[0].count("╭") == 2
        assert top_edges[1].count("╭") == 2
        assert all(len(ln) <= 48 for ln in lines)

    def test_attached_panel_renders_underneath_and_style_override(self) -> None:
        panel = mint.trend(
            [1, 2, 3, 4, 5, 6, 7],
            {
                "canary": [405, 398, 390, 310, 278, 258, 248],
                "control": [402, 408, 399, 404, 401, 405, 400],
            },
            title="Daily p99 trajectory",
            label="p99 latency",
            unit="ms",
            x_label="Day",
            highlight="canary",
        )
        c = card(
            "Canary cuts p99 latency 38% after Day 3 rollout",
            _sample_metrics(),
            panel=panel,
            source="telemetry 2026-11",
        )
        out = c.to_terminal(width=80, color=True, style="pine")
        plain = _strip_ansi(out)

        assert "MINTFIGCARDPANEL" not in plain
        assert "Daily p99 trajectory" in plain
        assert "canary" in plain
        assert "control" in plain
        assert "Source: telemetry 2026-11" in plain
        assert _rgb_seq("#38DDA9") in out  # pine emerald

    def test_ascii_only_and_no_color_and_auto_width(self, monkeypatch: pytest.MonkeyPatch) -> None:
        c = card(
            "Canary cuts p99 latency 38% across 5 clusters",
            _sample_metrics(),
            panel=mint.compare(
                {"checkout": 248, "payment": 195, "cart": 142},
                title="Endpoint p99",
                label="p99 latency",
                unit="ms",
            ),
            source="perf-canary",
        )
        asc = c.to_terminal(width=76, color=False, ascii_only=True)
        assert asc.isascii()
        assert "\x1b" not in asc
        assert "+-" in asc and "|" in asc
        assert "╭" not in asc
        assert not _BRAILLE_RE.search(asc)

        monkeypatch.setenv("NO_COLOR", "1")
        no_col = c.to_terminal(width=76, color=None)
        assert "\x1b" not in no_col

        monkeypatch.setattr(
            shutil, "get_terminal_size", lambda fallback=(80, 24): os.terminal_size((92, 30))
        )
        auto_out = _strip_ansi(c.to_terminal(width="auto", color=False))
        assert len(auto_out.splitlines()[0]) == 92

    def test_cli_card_example_pipe_to_terminal(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        # `mintfig card --example` -> stdout JSON
        assert cli_main(["card", "--example"]) == 0
        example_json = capsys.readouterr().out
        parsed = json.loads(example_json)
        assert parsed["takeaway"] == EXAMPLE_CARD_SPEC["takeaway"]

        # Pipe JSON into `mintfig card - --terminal`
        monkeypatch.delenv("NO_COLOR", raising=False)
        monkeypatch.setattr("sys.stdin", io.StringIO(example_json))
        rc = cli_main(["card", "-", "--terminal", "--width", "76"])
        out = capsys.readouterr().out
        assert rc == 0
        assert "╭" in out
        assert any(ch in out for ch in "▁▂▃▄▅▆▇█")
        assert "\x1b[" in out
        assert "p99 latency by endpoint" in _strip_ansi(out)

        # File path with --no-color and --ascii
        spec_file = tmp_path / "card.json"
        spec_file.write_text(example_json, encoding="utf-8")
        rc_plain = cli_card([str(spec_file), "--terminal", "--width", "68", "--no-color"])
        out_plain = capsys.readouterr().out
        assert rc_plain == 0
        assert "\x1b" not in out_plain
        assert "╭" in out_plain

        rc_ascii = cli_card([str(spec_file), "--terminal", "--no-color", "--ascii"])
        out_ascii = capsys.readouterr().out
        assert rc_ascii == 0
        assert out_ascii.isascii()


# --------------------------------------------------------------------------- #
# 2. Explanation.to_text(...) & Explanation.show(...) ergonomics
# --------------------------------------------------------------------------- #


class TestExplanationTerminalErgonomics:
    def _trend_exp(self) -> mint.Explanation:
        return mint.explain(
            "Spearmint clears the 0.85 target while Baseline stalls at 0.72",
            mint.trend(
                [0, 250, 500, 750, 1000],
                {
                    "Spearmint": [0.32, 0.58, 0.76, 0.88, 0.93],
                    "Baseline": [0.31, 0.49, 0.60, 0.68, 0.72],
                },
                title="Validation accuracy",
                label="Accuracy",
                x_label="Step",
                highlight="Spearmint",
            ),
            style="pine",
        )

    def test_to_text_default_is_backwards_compatible(self) -> None:
        exp = self._trend_exp()
        plain = exp.to_text()
        assert "\x1b" not in plain
        assert not _BRAILLE_RE.search(plain)
        assert all(len(ln) <= 72 for ln in plain.splitlines())

        # Positional width/ascii_only remain supported
        asc = exp.to_text(68, True)
        assert asc.isascii()
        assert all(len(ln) <= 68 for ln in asc.splitlines())

    def test_to_text_braille_ascii_auto_width_and_no_color(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        exp = self._trend_exp()
        monkeypatch.delenv("NO_COLOR", raising=False)

        braille = exp.to_text(mode="braille")
        assert _BRAILLE_RE.search(braille)
        assert "\x1b[" in braille

        braille_plain = exp.to_text(mode="braille", color=False)
        assert _BRAILLE_RE.search(braille_plain)
        assert "\x1b[" not in braille_plain

        monkeypatch.setenv("NO_COLOR", "1")
        braille_nocolor_env = exp.to_text(mode="braille")
        assert _BRAILLE_RE.search(braille_nocolor_env)
        assert "\x1b[" not in braille_nocolor_env
        # Explicit color=True overrides NO_COLOR
        assert "\x1b[" in exp.to_text(mode="braille", color=True)

        asc = exp.to_text(mode="ascii")
        assert asc.isascii()
        assert not _BRAILLE_RE.search(asc)

        monkeypatch.setattr(
            shutil, "get_terminal_size", lambda fallback=(80, 24): os.terminal_size((96, 24))
        )
        auto_txt = exp.to_text(width="auto", mode="braille", color=False)
        assert _BRAILLE_RE.search(auto_txt)
        assert max(len(ln) for ln in auto_txt.splitlines()) <= 96

        with pytest.raises(ValueError, match="Unknown text mode"):
            exp.to_text(mode="bogus")

    def test_show_accepts_braille_and_ascii_modes(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        exp = self._trend_exp()
        monkeypatch.delenv("NO_COLOR", raising=False)

        exp.show(mode="braille", width=78)
        out = capsys.readouterr().out
        assert _BRAILLE_RE.search(out)
        assert "\x1b[" in out

        exp.show(mode="braille", width=78, color=False)
        out_plain = capsys.readouterr().out
        assert _BRAILLE_RE.search(out_plain)
        assert "\x1b[" not in out_plain

        exp.show(mode="ascii")
        out_asc = capsys.readouterr().out
        assert out_asc.isascii()


# --------------------------------------------------------------------------- #
# 3. One-flag --braille CLI shortcuts (plot, show, explain, diff)
# --------------------------------------------------------------------------- #


class TestCliBrailleShortcuts:
    def test_cli_plot_braille_without_out_kind_or_takeaway(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.delenv("NO_COLOR", raising=False)
        csv_path = tmp_path / "metrics.csv"
        csv_path.write_text(
            "step,model,accuracy\n"
            "0,Spearmint,0.35\n"
            "500,Spearmint,0.72\n"
            "1000,Spearmint,0.88\n"
            "1500,Spearmint,0.93\n"
            "0,Baseline,0.34\n"
            "500,Baseline,0.58\n"
            "1000,Baseline,0.68\n"
            "1500,Baseline,0.72\n",
            encoding="utf-8",
        )

        rc = cli_main(["plot", str(csv_path), "--braille", "--style", "pine"])
        out = capsys.readouterr().out
        assert rc == 0
        assert _BRAILLE_RE.search(out)
        assert "\x1b[" in out
        assert "Spearmint" in _strip_ansi(out)

        # --no-color disables ANSI while keeping Braille
        rc2 = cli_main(["plot", str(csv_path), "--braille", "--no-color"])
        out2 = capsys.readouterr().out
        assert rc2 == 0
        assert _BRAILLE_RE.search(out2)
        assert "\x1b[" not in out2

    def test_cli_show_braille_on_png_and_spec(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.delenv("NO_COLOR", raising=False)
        fig = mint.explain(
            "Spearmint rises from 0.40 to 0.93 across 5 epochs",
            mint.trend(
                [1, 2, 3, 4, 5],
                {"Spearmint": [0.40, 0.58, 0.74, 0.86, 0.93], "Base": [0.40, 0.46, 0.52, 0.57, 0.60]},
                label="Accuracy",
                x_label="Epoch",
                highlight="Spearmint",
            ),
        )
        png_path = tmp_path / "fig.png"
        fig.save(png_path, write_spec=True)

        rc_png = cli_main(["show", str(png_path), "--braille", "--style", "pine"])
        out_png = capsys.readouterr().out
        assert rc_png == 0
        assert _BRAILLE_RE.search(out_png)
        assert "\x1b[" in out_png
        assert "Spearmint" in _strip_ansi(out_png)

        rc_json = cli_main(["show", str(png_path.with_suffix(".json")), "--braille", "--no-color"])
        out_json = capsys.readouterr().out
        assert rc_json == 0
        assert _BRAILLE_RE.search(out_json)
        assert "\x1b[" not in out_json

    def test_cli_explain_braille_without_out(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.delenv("NO_COLOR", raising=False)
        spec_path = tmp_path / "spec.json"
        spec_path.write_text(json.dumps(EXAMPLE_SPEC), encoding="utf-8")

        rc = cli_main(["explain", str(spec_path), "--braille", "--style", "pine"])
        out = capsys.readouterr().out
        assert rc == 0
        assert _BRAILLE_RE.search(out)
        assert "\x1b[" in out
        assert "Checkout" in _strip_ansi(out)

    def test_cli_diff_braille(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.delenv("NO_COLOR", raising=False)
        base_path = tmp_path / "base.json"
        head_path = tmp_path / "head.json"
        base_path.write_text(
            json.dumps(
                [
                    {"name": "parse", "latency_ms": 120.0},
                    {"name": "encode", "latency_ms": 84.0},
                    {"name": "route", "latency_ms": 42.0},
                ]
            ),
            encoding="utf-8",
        )
        head_path.write_text(
            json.dumps(
                [
                    {"name": "parse", "latency_ms": 92.0},
                    {"name": "encode", "latency_ms": 79.0},
                    {"name": "route", "latency_ms": 68.0},
                ]
            ),
            encoding="utf-8",
        )

        rc = cli_main(["diff", str(base_path), str(head_path), "--braille", "--style", "pine"])
        out = capsys.readouterr().out
        assert rc == 0
        assert "\x1b[" in out
        plain = _strip_ansi(out)
        assert "parse" in plain and "route" in plain

        # --fail-on-regression still enforces exit code 1 with --braille
        rc_fail = cli_main(
            [
                "diff",
                str(base_path),
                str(head_path),
                "--braille",
                "--lower-is-better",
                "--fail-on-regression",
                "10",
            ]
        )
        _ = capsys.readouterr().out
        assert rc_fail == 1


# --------------------------------------------------------------------------- #
# 4. mintfig watch subcommand
# --------------------------------------------------------------------------- #


class TestCliWatch:
    def test_watch_once_csv_and_jsonl_and_ascii(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.delenv("NO_COLOR", raising=False)
        csv_path = tmp_path / "train.csv"
        csv_path.write_text(
            "step,loss\n0,2.40\n100,1.65\n200,1.12\n300,0.78\n400,0.54\n",
            encoding="utf-8",
        )

        rc = cli_main(
            [
                "watch",
                str(csv_path),
                "--once",
                "--braille",
                "--style",
                "pine",
                "--width",
                "80",
            ]
        )
        out = capsys.readouterr().out
        assert rc == 0
        assert _BRAILLE_RE.search(out)
        assert "\x1b[" in out

        # JSONL with explicit takeaway and --width auto
        monkeypatch.setattr(
            shutil, "get_terminal_size", lambda fallback=(80, 24): os.terminal_size((84, 24))
        )
        jsonl_path = tmp_path / "bench.jsonl"
        jsonl_path.write_text(
            "\n".join(
                json.dumps(r)
                for r in [
                    {"service": "checkout", "p99_ms": 248},
                    {"service": "payment", "p99_ms": 195},
                    {"service": "cart", "p99_ms": 142},
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        rc_j = cli_main(
            [
                "watch",
                str(jsonl_path),
                "--once",
                "--kind",
                "auto",
                "--takeaway",
                "Checkout p99 leads at 248 ms across services",
                "--width",
                "auto",
            ]
        )
        out_j = capsys.readouterr().out
        assert rc_j == 0
        assert "Checkout p99 leads at 248 ms" in _strip_ansi(out_j)

        # --ascii mode produces pure ASCII
        rc_a = cli_main(["watch", str(csv_path), "--once", "--ascii"])
        out_a = capsys.readouterr().out
        assert rc_a == 0
        assert out_a.isascii()

        # Missing file -> exit 2
        rc_miss = cli_main(["watch", str(tmp_path / "nope.csv"), "--once"])
        err_miss = capsys.readouterr().err
        assert rc_miss == 2
        assert "does not exist" in err_miss

    def test_watch_loop_clears_screen_on_file_update_and_handles_ctrl_c(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        import time

        monkeypatch.delenv("NO_COLOR", raising=False)
        csv_path = tmp_path / "live.csv"
        csv_path.write_text("step,loss\n0,2.4\n100,1.5\n200,0.9\n", encoding="utf-8")

        ticks = {"n": 0}

        def _fake_sleep(_sec: float) -> None:
            ticks["n"] += 1
            if ticks["n"] == 1:
                # Append a new row to trigger mtime/size change and re-render
                csv_path.write_text(
                    "step,loss\n0,2.4\n100,1.5\n200,0.9\n300,0.42\n", encoding="utf-8"
                )
                return
            raise KeyboardInterrupt

        monkeypatch.setattr(time, "sleep", _fake_sleep)
        rc = cli_main(["watch", str(csv_path), "--braille", "--interval", "0.1", "--width", "76"])
        out = capsys.readouterr().out

        assert rc == 0
        # Screen cleared cleanly twice (initial draw + post-update draw)
        assert out.count("\x1b[H\x1b[2J") == 2
        assert _BRAILLE_RE.search(out)
