"""Tests for Bet 1: Harness-Adaptive Delivery (interactive HTML, terminal, CLI show)."""

from __future__ import annotations

import base64
import io
import json
import re
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import pytest
from PIL import Image

matplotlib.use("Agg")

import mintfig as mint
from mintfig.cli import main as cli_main
from mintfig.explainer import EXAMPLE_SPEC
from mintfig.interactive import render_html, render_html_fragment
from mintfig.terminal import (
    detect_graphics_protocol,
    encode_iterm2_png,
    encode_kitty_png,
    render_terminal,
    show_in_terminal,
)


def _close(exp: mint.Explanation) -> None:
    plt.close(exp.fig)


def _sample_multi_panel_exp(*, style: str = "mintfig") -> mint.Explanation:
    return mint.explain(
        "Checkout is the slow service: p99 reached 1,840 ms after v2.3",
        mint.compare(
            {"checkout": 1840, "search": 460, "auth": 310, "profile": 120},
            title="Checkout stands alone",
            label="p99 latency",
            unit="ms",
            highlight="checkout",
        ),
        mint.trend(
            [1, 2, 3, 4, 5, 6],
            {
                "checkout": [540, 560, 580, 980, 1400, 1840],
                "search": [450, 460, 455, 465, 450, 460],
            },
            title="Regressed after v2.3 deploy",
            label="p99 latency",
            unit="ms",
            x_label="Week",
            highlight="checkout",
            events={3: "v2.3"},
        ),
        subtitle="API p99 latency across services, week of 16 Nov",
        source="synthetic telemetry",
        note="n = 50k requests per service",
        style=style,
    )


class TestInteractiveHtml:
    def test_render_html_from_explanation_and_spec_dict(self) -> None:
        exp = _sample_multi_panel_exp()
        try:
            doc = render_html(exp)
        finally:
            _close(exp)

        assert doc.startswith("<!DOCTYPE html>")
        assert "<html lang=\"en\">" in doc
        assert "</html>" in doc
        assert "<svg" in doc
        assert "viewBox=" in doc
        for action in ("data", "svg", "spec"):
            assert f'data-mf-act="{action}"' in doc
        assert "Critique / Ask Agent" not in doc

        # Zero external CDN or remote asset references
        assert not re.search(
            r"<(script|link)\b[^>]+(src|href)=[\"']https?://", doc, re.IGNORECASE
        )
        assert "@import" not in doc

        # Also works directly from a spec dict
        doc_from_spec = render_html(EXAMPLE_SPEC)
        assert "<!DOCTYPE html>" in doc_from_spec
        assert "<svg" in doc_from_spec
        assert "Checkout stands alone" in doc_from_spec

    def test_render_html_fragment_for_jupyter(self) -> None:
        exp = _sample_multi_panel_exp()
        try:
            frag = render_html_fragment(exp)
        finally:
            _close(exp)

        assert "<!DOCTYPE html>" not in frag
        assert "<html" not in frag
        assert "<figure" in frag
        assert "<svg" in frag
        assert 'class="mf-data" hidden' in frag
        assert "Critique" not in frag

    def test_render_html_noninteractive_mode(self) -> None:
        exp = _sample_multi_panel_exp()
        try:
            static_doc = render_html(exp, interactive=False)
        finally:
            _close(exp)

        assert "<!DOCTYPE html>" in static_doc
        assert "<svg" in static_doc
        assert "<script>" not in static_doc
        assert "data-mf-act" not in static_doc

    def test_light_and_dark_theme_surface_matching(self) -> None:
        light_exp = _sample_multi_panel_exp(style="mintfig")
        dark_exp = _sample_multi_panel_exp(style="dark")
        try:
            light_html = render_html(light_exp)
            dark_html = render_html(dark_exp)
        finally:
            _close(light_exp)
            _close(dark_exp)

        assert 'data-mf-theme="mintfig"' in light_html
        assert 'data-mf-mode="light"' in light_html
        assert light_exp.theme.background in light_html
        assert light_exp.theme.ink in light_html

        assert 'data-mf-theme="dark"' in dark_html
        assert 'data-mf-mode="dark"' in dark_html
        assert dark_exp.theme.background in dark_html
        assert dark_exp.theme.ink in dark_html

    def test_facts_drawer_covers_table_matrix_and_other_forms(self) -> None:
        exp = mint.explain(
            "Model A leads on accuracy while maintaining compact latency",
            mint.table(
                [
                    {"Model": "Alpha", "Accuracy": 92.4, "Latency": 18},
                    {"Model": "Beta", "Accuracy": 87.1, "Latency": 24},
                ],
                title="Benchmark table",
            ),
            mint.matrix(
                [[1.0, 0.42], [0.42, 1.0]],
                rows=["Acc", "Lat"],
                cols=["Acc", "Lat"],
                title="Metric correlation",
                label="Correlation",
            ),
            mint.change(
                {"Alpha": 84.0, "Beta": 82.0},
                {"Alpha": 92.4, "Beta": 87.1},
                title="Before vs after tuning",
                label="Accuracy",
                unit="%",
            ),
            mint.relate(
                [10, 20, 30, 40],
                [80, 85, 89, 93],
                x_label="Params (M)",
                y_label="Score",
                title="Scaling relation",
            ),
            source="internal eval",
        )
        try:
            doc = render_html(exp)
        finally:
            _close(exp)

        assert "Benchmark table" in doc
        assert "Alpha" in doc
        assert "92.4" in doc
        assert "Metric correlation" in doc
        assert "0.42" in doc
        assert "Before vs after tuning" in doc
        assert "Scaling relation" in doc
        assert "<table class=\"mf-data-table\">" in doc

    def test_xss_and_script_breakout_escaping(self) -> None:
        payload = '</script><script>alert("xss")</script>'
        img_xss = '<img src=x onerror=alert(1)>'
        exp = mint.explain(
            f"Latency spiked 3x {payload}",
            mint.compare(
                {img_xss: 90, "safe": 30},
                title=f"Title {img_xss}",
                label="Score",
                unit="ms",
            ),
            subtitle=f"Sub {payload}",
            source=f"Src {img_xss}",
            note=f"Note {payload}",
        )
        try:
            doc = render_html(exp)
        finally:
            _close(exp)

        # No injected script breakout or raw unescaped HTML elements
        assert '</script><script>alert("xss")</script>' not in doc
        assert "<img src=x onerror=alert(1)>" not in doc
        assert "&lt;img src=x onerror=alert(1)&gt;" in doc
        assert "\\u003c/script\\u003e" in doc

    def test_invalid_input_raises_type_error(self) -> None:
        with pytest.raises(TypeError):
            render_html("not-an-explanation")  # type: ignore[arg-type]

    def test_trend_points_replicates_align_with_x_and_means(self) -> None:
        exp = mint.explain(
            "Core suite runtime fell 40% from 31.0 s to 18.7 s across 3 releases",
            mint.trend(
                ["v1", "v2", "v3"],
                points={
                    "Core": [[30.0, 32.0, 31.0], [], [18.0, 19.0, 19.0]],
                    "Aux": [[10.0, 12.0], [11.0, 13.0], [12.0, 14.0]],
                },
                x_label="Release",
                label="Runtime",
                unit="s",
                title="Replicate runtimes",
                highlight="Core",
            ),
        )
        try:
            doc = render_html(exp)
            term = render_terminal(exp, width=78, color=False, ascii_only=False)
        finally:
            _close(exp)

        # HTML drawer table shows x labels and per-x replicate means (not pt[0]/pt[1])
        assert "<th>Release</th>" in doc
        assert "<td>v1</td>" in doc
        assert "<td>v2</td>" in doc
        assert "<td>v3</td>" in doc
        assert "31" in doc
        assert "18.67" in doc
        assert '<td class="mf-num">—</td>' in doc  # empty replicate bucket handled cleanly
        assert "per-x replicate means" in doc

        # Terminal sparkline summary matches per-x replicate means (31 s -> 18.7 s, -40%)
        assert "31 s → 18.7 s (-40%)" in term
        assert "11 s → 13 s (+18%)" in term

    def test_narrow_width_html_stays_compact(self) -> None:
        exp = mint.explain(
            "Checkout is 4x slower than search at 1,840 ms",
            mint.compare(
                {"checkout": 1840, "search": 460, "auth": 310},
                label="p99 latency",
                unit="ms",
                highlight="checkout",
            ),
            width="narrow",
        )
        try:
            doc = render_html(exp)
        finally:
            _close(exp)

        assert "max-width:450px;" in doc
        assert "max-width:700px;" not in doc


class TestTerminalProtocolAndEncoding:
    @pytest.mark.parametrize(
        ("env", "expected"),
        [
            ({"KITTY_WINDOW_ID": "1"}, "kitty"),
            ({"TERM": "xterm-kitty"}, "kitty"),
            ({"TERM": "xterm-ghostty"}, "kitty"),
            ({"TERM_PROGRAM": "ghostty"}, "kitty"),
            ({"TERM_PROGRAM": "iTerm.app"}, "iterm2"),
            ({"TERM_PROGRAM": "WezTerm"}, "iterm2"),
            ({"LC_TERMINAL": "iTerm2"}, "iterm2"),
            ({"TERM": "xterm-256color"}, "unicode"),
            ({}, "unicode"),
        ],
    )
    def test_detect_graphics_protocol(self, env: dict[str, str], expected: str) -> None:
        assert detect_graphics_protocol(env) == expected

    def test_encode_kitty_png_single_and_multi_chunk(self) -> None:
        small = b"\x89PNG\r\n\x1a\n" + b"A" * 64
        seq_small = encode_kitty_png(small)
        assert seq_small.startswith("\x1b_Ga=T,f=100,m=0;")
        assert seq_small.endswith("\x1b\\")
        payload_b64 = seq_small.split(";", 1)[1][:-2]
        assert base64.b64decode(payload_b64) == small

        # Large payload forces multiple 4096-byte chunks
        large = b"\x89PNG\r\n\x1a\n" + bytes(range(256)) * 40
        seq_large = encode_kitty_png(large)
        frames = [f for f in seq_large.split("\x1b\\") if f]
        assert len(frames) > 2
        assert frames[0].startswith("\x1b_Ga=T,f=100,m=1;")
        assert frames[-1].startswith("\x1b_Gm=0;")
        reconstructed = "".join(f.split(";", 1)[1] for f in frames)
        assert base64.b64decode(reconstructed) == large

        with pytest.raises(ValueError):
            encode_kitty_png(b"")

    def test_encode_iterm2_png(self) -> None:
        raw = b"\x89PNG\r\n\x1a\n" + b"XYZ123"
        seq = encode_iterm2_png(raw)
        assert seq.startswith(f"\x1b]1337;File=inline=1;size={len(raw)}:")
        assert seq.endswith("\x07")
        b64_part = seq.split(":", 1)[1][:-1]
        assert base64.b64decode(b64_part) == raw

        with pytest.raises(ValueError):
            encode_iterm2_png(b"")


class TestTerminalRendering:
    def test_render_terminal_compare_and_trend_unicode_and_ascii(self) -> None:
        exp = _sample_multi_panel_exp()
        try:
            uni_color = render_terminal(exp, width=78, color=True, ascii_only=False)
            uni_plain = render_terminal(exp, width=78, color=False, ascii_only=False)
            asc_plain = render_terminal(exp, width=78, color=False, ascii_only=True)
        finally:
            _close(exp)

        # Color vs no-color ANSI check
        assert "\x1b[" in uni_color
        assert "\x1b[" not in uni_plain
        assert "\x1b[" not in asc_plain

        # Headline, subtitle, source, note present
        assert "Checkout is the slow service" in uni_plain
        assert "week of 16 Nov" in uni_plain
        assert "Source: synthetic telemetry" in uni_plain
        assert "Note: n = 50k requests" in uni_plain

        # Unicode compare bars & trend sparklines
        assert "█" in uni_plain
        assert "1,840 ms" in uni_plain
        assert any(ch in uni_plain for ch in "▁▂▃▄▅▆▇█")
        assert "→" in uni_plain

        # Sorted descending: checkout appears before search before profile
        assert uni_plain.index("checkout") < uni_plain.index("search") < uni_plain.index("profile")

        # ASCII-only strictly ASCII with # bars and -> arrows
        assert asc_plain.isascii()
        assert "#" in asc_plain
        assert "->" in asc_plain

    def test_render_terminal_table_share_matrix_distribution_change_relate(self) -> None:
        exp = mint.explain(
            "Model Alpha leads accuracy by 5.3 pts with balanced share and tight spread",
            mint.table(
                [
                    {"Model": "Alpha", "Acc": 92.4, "Cost": 1.2},
                    {"Model": "Beta", "Acc": 87.1, "Cost": 2.4},
                ],
                title="Scorecard",
                highlight="Alpha",
            ),
            mint.share({"Compute": 65, "Storage": 25, "Network": 10}, title="Spend share"),
            mint.matrix(
                [[1.0, 0.3], [0.3, 1.0]],
                rows=["A", "B"],
                cols=["A", "B"],
                title="Correlations",
                label="r",
            ),
            mint.distribution(
                {"Alpha": [91, 92, 92.5, 93, 93.5], "Beta": [85, 86, 87, 88, 89]},
                title="Run spread",
                label="Acc",
                unit="%",
            ),
            style="mintfig",
        )
        try:
            uni = render_terminal(exp, width=78, color=False, ascii_only=False)
            asc = render_terminal(exp, width=78, color=False, ascii_only=True)
        finally:
            _close(exp)

        # Box-drawn table in Unicode and ASCII
        assert "┌" in uni and "│" in uni and "└" in uni
        assert "Alpha" in uni and "92.4" in uni
        assert "65.0%" in uni
        assert "Correlations" in uni
        assert "median" in uni

        assert asc.isascii()
        assert "+" in asc and "|" in asc and "-" in asc

    def test_show_in_terminal_modes_and_inputs(self, tmp_path: Path) -> None:
        exp = _sample_multi_panel_exp()
        png_path = tmp_path / "figure.png"
        spec_path = tmp_path / "spec.json"
        try:
            exp.save(png_path, write_spec=True)
        finally:
            _close(exp)
        spec_path.write_text(json.dumps(EXAMPLE_SPEC), encoding="utf-8")

        # Auto mode with kitty env -> Kitty APC
        kitty_out = show_in_terminal(spec_path, mode="auto", env={"KITTY_WINDOW_ID": "42"})
        assert kitty_out.startswith("\x1b_Ga=T,f=100,")

        # Auto mode with iTerm2 env -> OSC 1337
        iterm_out = show_in_terminal(png_path, mode="auto", env={"TERM_PROGRAM": "iTerm.app"})
        assert iterm_out.startswith("\x1b]1337;File=inline=1;size=")

        # Auto mode with plain terminal -> Unicode text rendered from embedded PNG spec
        text_out = show_in_terminal(png_path, mode="auto", color=False, env={"TERM": "xterm-256color"})
        assert "Checkout is the slow service" in text_out
        assert "█" in text_out

        # Explicit ascii mode from dict
        ascii_out = show_in_terminal(EXAMPLE_SPEC, mode="ascii", color=False)
        assert ascii_out.isascii()
        assert "#" in ascii_out

        # Plain PNG without embedded mintfig spec falls back gracefully in unicode mode
        plain_png = tmp_path / "plain.png"
        img_buf = io.BytesIO()
        Image.new("RGB", (32, 24), color=(10, 20, 30)).save(img_buf, format="PNG")
        plain_png.write_bytes(img_buf.getvalue())
        plain_out = show_in_terminal(plain_png, mode="unicode", color=False)
        assert "plain.png" in plain_out
        assert "32x24" in plain_out

        with pytest.raises(ValueError, match="Unknown terminal mode"):
            show_in_terminal(EXAMPLE_SPEC, mode="sixel")


class TestCliShowAndExplainHtml:
    def test_cli_show_json_png_and_stdin(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        spec_path = tmp_path / "spec.json"
        spec_path.write_text(json.dumps(EXAMPLE_SPEC), encoding="utf-8")

        code = cli_main(["show", str(spec_path), "--mode", "unicode", "--width", "72", "--no-color"])
        assert code == 0
        out = capsys.readouterr().out
        assert "Checkout is the slow service" in out
        assert "█" in out
        assert "\x1b[" not in out

        # ASCII mode
        code_ascii = cli_main(["show", str(spec_path), "--mode", "ascii", "--no-color"])
        assert code_ascii == 0
        out_ascii = capsys.readouterr().out
        assert out_ascii.isascii()
        assert "#" in out_ascii

        # Stdin '-'
        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(EXAMPLE_SPEC)))
        code_stdin = cli_main(["show", "-", "--mode", "unicode", "--no-color"])
        assert code_stdin == 0
        out_stdin = capsys.readouterr().out
        assert "Checkout stands alone" in out_stdin

        # Missing file -> non-zero exit code
        code_err = cli_main(["show", str(tmp_path / "missing.json"), "--mode", "unicode"])
        assert code_err != 0
        err = capsys.readouterr().err
        assert "Error:" in err

    def test_cli_explain_out_html(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        spec_path = tmp_path / "spec.json"
        spec_path.write_text(json.dumps(EXAMPLE_SPEC), encoding="utf-8")
        out_html = tmp_path / "out.html"

        code = cli_main(["explain", str(spec_path), "--out", str(out_html), "--write-spec"])
        assert code == 0
        stdout = capsys.readouterr().out
        summary = json.loads(stdout)
        assert summary["ok"] is True
        assert summary["deliver"]["html"] is not None
        assert Path(summary["path"]) == out_html.resolve()

        content = out_html.read_text(encoding="utf-8")
        assert content.startswith("<!DOCTYPE html>")
        assert "<svg" in content
        assert 'data-mf-act="data"' in content
        assert out_html.with_suffix(".json").exists()
