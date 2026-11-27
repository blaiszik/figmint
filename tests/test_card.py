"""Unit tests for general-purpose PR & release summary cards (``mintfig.card``)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import matplotlib
import pytest

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from PIL import Image

import mintfig as mint
from mintfig.card import (
    DEFAULT_ACCENT_DARK,
    DEFAULT_ACCENT_LIGHT,
    EXAMPLE_CARD_SPEC,
    SummaryCard,
    card,
    card_from_json,
    cli_card,
)
from mintfig.explainer import ExplainError, read_png_text
from mintfig.themes import contrast_ratio


@pytest.fixture(autouse=True)
def _defaults_and_close():
    """Reset Matplotlib rcParams and close figures after each test."""
    with matplotlib.rc_context():
        matplotlib.rcdefaults()
        matplotlib.use("Agg")
        yield
    plt.close("all")


def _corner_luminance(png_path: Path) -> float:
    with Image.open(png_path) as im:
        rgb = im.convert("RGB")
        r, g, b = rgb.getpixel((4, 4))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _sample_metrics(*, with_spark: bool = True) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = [
        {
            "label": "p99 latency",
            "value": "248 ms",
            "delta": "-38%",
            "good": True,
            "note": "vs 400 ms base",
        },
        {
            "label": "Availability",
            "value": "99.94%",
            "delta": "+0.02 pts",
            "good": True,
        },
        {
            "label": "Error rate",
            "value": "0.06%",
            "delta": "-0.04 pts",
            "good": True,
        },
        {
            "label": "Peak RSS",
            "value": "412 MB",
            "delta": "+18 MB",
            "good": False,
            "note": "cache warm-up",
        },
    ]
    if with_spark:
        sparks = [
            [410, 405, 398, 390, 310, 265, 248],
            [99.91, 99.92, 99.92, 99.93, 99.93, 99.94, 99.94],
            [0.11, 0.10, 0.10, 0.09, 0.08, 0.07, 0.06],
            [392, 394, 395, 394, 406, 410, 412],
        ]
        for item, sp in zip(items, sparks, strict=True):
            item["spark"] = sp
    return items


# --------------------------------------------------------------------------- #
# KPI-only cards & mint.check legibility
# --------------------------------------------------------------------------- #


class TestKpiOnlyCard:
    def test_kpi_only_card_defaults_and_mint_check_ship(self, tmp_path: Path) -> None:
        c = card(
            "PR #418 cuts checkout p99 latency 38% while holding 99.94% availability",
            _sample_metrics(with_spark=False),
            subtitle="checkout-service canary · 7-day window (n = 1.2M req)",
            source="perf-canary 2026-11",
        )
        assert isinstance(c, SummaryCard)
        assert c.ok is True
        assert c.ship is True
        assert c.style == "mintfig"
        assert c.resolved_accent.upper() == DEFAULT_ACCENT_LIGHT
        assert c.panel is None
        assert c.min_text_px >= 11.0

        # Passes mint.check legibility gate at reading width!
        chk = mint.check(c.fig, claim="", width="chat")
        assert chk["ship"] is True, chk["issues"]
        assert chk["display"]["min_text_px"] >= 11.0
        assert not [
            i
            for i in chk["issues"]
            if i["rule"]
            in {"text_too_small", "text_overlaps", "text_struck_by_line", "text_clipped", "text_malformed"}
        ]

        out = tmp_path / "kpi_only.png"
        summary = c.save(out)
        assert out.is_file()
        assert out.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
        assert summary["path"] == str(out.resolve())
        assert summary["ship"] is True
        assert summary["issues"] == []
        assert summary["metrics_count"] == 4
        assert summary["has_panel"] is False

        meta = read_png_text(out)
        assert "mintfig:card_spec" in meta
        assert meta["mintfig:takeaway"] == c.takeaway

    def test_five_tiles_and_numeric_values_and_narrow_slide_widths(self) -> None:
        metrics = [
            {"label": "Throughput", "value": 14200, "delta": 2150, "good": True},
            {"label": "p50", "value": 18.4, "delta": -3.2, "good": True},
            {"label": "p99", "value": 248, "delta": -152, "good": True},
            {"label": "CPU", "value": "61%", "delta": 0, "good": None},
            {"label": "Memory", "value": "412 MB", "delta": "+18 MB", "good": False},
        ]
        for width in ("chat", "narrow", "slide"):
            c = card("Release v2.4 lifts throughput 18% across 5 clusters", metrics, width=width)
            assert c.ship is True, f"width={width}: {c.issues}"
            assert c.min_text_px >= 11.0
            chk = mint.check(c.fig, claim="", width=width)
            assert chk["ship"] is True, f"mint.check width={width}: {chk['issues']}"

    def test_sparklines_in_tiles_including_edge_cases(self, tmp_path: Path) -> None:
        metrics = [
            {
                "label": "p99 latency",
                "value": "248 ms",
                "delta": "-38%",
                "good": True,
                "spark": [410, 390, 310, 265, 248],
            },
            {
                "label": "Flat SLA",
                "value": "99.9%",
                "delta": "0.0 pts",
                "good": None,
                "spark": [99.9, 99.9, 99.9, 99.9],
            },
            {
                "label": "Single point",
                "value": "42",
                "spark": [42.0],
            },
            {
                "label": "Peak RSS",
                "value": "412 MB",
                "delta": "+18 MB",
                "good": False,
                "spark": [392, 395, 406, 412],
            },
        ]
        c = card("Sparkline tiles render trends cleanly inside each KPI tile", metrics)
        assert c.ship is True
        # 4 sparkline inset axes created, all axis_off so mint.check never flags unlabelled axes.
        assert len(c.fig.axes) == 4
        assert all(not ax.axison for ax in c.fig.axes)

        chk = mint.check(c.fig, claim="", width="chat")
        assert chk["ship"] is True, chk["issues"]
        assert not [i for i in chk["issues"] if i["rule"] == "axis_unlabelled"]

        svg_path = tmp_path / "spark_card.svg"
        res = c.save(svg_path)
        assert svg_path.is_file()
        assert "<svg" in svg_path.read_text(encoding="utf-8")
        assert res["ship"] is True
        assert res["metrics_count"] == 4


# --------------------------------------------------------------------------- #
# KPI + Panel cards (compare & trend)
# --------------------------------------------------------------------------- #


class TestKpiWithPanel:
    def test_kpi_plus_compare_panel(self, tmp_path: Path) -> None:
        panel = mint.compare(
            {"checkout": 248, "payment": 195, "cart": 142, "catalog": 98, "health": 24},
            title="p99 latency by endpoint",
            label="p99 latency",
            unit="ms",
            highlight="checkout",
        )
        c = card(
            "Checkout p99 drops to 248 ms but still leads payment (195 ms)",
            _sample_metrics(with_spark=True),
            panel=panel,
            subtitle="Canary vs baseline · 7 days",
            source="perf-canary 2026-11",
        )
        assert c.ok is True
        assert c.ship is True, c.issues
        assert c.panel is panel
        assert c.panel_axes is not None

        chk = mint.check(c.fig, claim="", width="chat")
        assert chk["ship"] is True, chk["issues"]
        assert chk["display"]["min_text_px"] >= 11.0

        out = tmp_path / "compare_card.png"
        summary = c.save(out)
        assert summary["ship"] is True
        assert summary["has_panel"] is True
        assert len(summary["panel_facts"]) >= 1
        assert _corner_luminance(out) > 220.0

    def test_kpi_plus_trend_panel_and_dark_theme(self, tmp_path: Path) -> None:
        panel = mint.trend(
            [1, 2, 3, 4, 5, 6, 7],
            {
                "canary": [405, 398, 390, 310, 278, 258, 248],
                "control": [402, 408, 399, 404, 401, 405, 400],
            },
            title="Daily p99 latency trajectory",
            label="p99 latency",
            unit="ms",
            x_label="Day",
            highlight="canary",
        )
        c = card(
            "Canary cuts p99 latency from 405 ms to 248 ms after Day 3 rollout",
            _sample_metrics(with_spark=True),
            panel=panel,
            style="dark",
            source="telemetry 2026-11",
        )
        assert c.ship is True, c.issues
        assert c.style == "dark"
        assert c.resolved_accent.upper() == DEFAULT_ACCENT_DARK
        assert contrast_ratio(c.resolved_accent, c.theme.background) >= 4.5

        chk = mint.check(c.fig, claim="", width="chat")
        assert chk["ship"] is True, chk["issues"]

        out = tmp_path / "trend_dark.png"
        res = c.save(out)
        assert res["ship"] is True
        assert _corner_luminance(out) < 50.0


# --------------------------------------------------------------------------- #
# save_pair() light + dark + GitHub <picture> Markdown
# --------------------------------------------------------------------------- #


class TestSavePair:
    def test_save_pair_stem_and_picture_markdown(self, tmp_path: Path) -> None:
        panel = mint.compare(
            {"v2.4": 248, "v2.3": 400, "v2.2": 435},
            title="Release p99 comparison",
            label="p99 latency",
            unit="ms",
            highlight="v2.4",
            baseline="v2.3",
        )
        c = card(
            "v2.4 trims p99 latency 38% vs v2.3 across all regions",
            _sample_metrics(with_spark=True),
            panel=panel,
            source="release-bench",
        )
        pair = c.save_pair(tmp_path / "release", repo_prefix="docs/cards/")

        assert pair["ok"] is True
        assert pair["ship"] is True
        light_png = Path(pair["light"])
        dark_png = Path(pair["dark"])
        assert light_png.name == "release_light.png"
        assert dark_png.name == "release_dark.png"
        assert light_png.is_file()
        assert dark_png.is_file()
        assert _corner_luminance(light_png) > 220.0
        assert _corner_luminance(dark_png) < 50.0

        md = pair["markdown"]
        assert "<picture>" in md
        assert "</picture>" in md
        assert 'media="(prefers-color-scheme: dark)"' in md
        assert 'media="(prefers-color-scheme: light)"' in md
        assert 'srcset="docs/cards/release_dark.png"' in md
        assert 'srcset="docs/cards/release_light.png"' in md
        assert 'src="docs/cards/release_light.png"' in md
        assert 'width="700"' in md
        assert "<details>" in md
        assert "p99 latency" in md

    def test_save_pair_directory_and_dark_card_input(self, tmp_path: Path) -> None:
        c = card(
            "Dark-origin card pairs cleanly with light mintfig variant",
            _sample_metrics(with_spark=False),
            style="dark",
        )
        out_dir = tmp_path / "pair_dir"
        out_dir.mkdir()
        pair = c.save_pair(out_dir)

        assert pair["light_style"] == "mintfig"
        assert pair["dark_style"] == "dark"
        assert Path(pair["light"]).name == "card_light.png"
        assert Path(pair["dark"]).name == "card_dark.png"
        assert _corner_luminance(Path(pair["light"])) > 220.0
        assert _corner_luminance(Path(pair["dark"])) < 50.0


# --------------------------------------------------------------------------- #
# to_html() & to_markdown()
# --------------------------------------------------------------------------- #


class TestHtmlAndMarkdown:
    def test_to_html_responsive_light_dark_with_panel_and_zero_yellow(self, tmp_path: Path) -> None:
        panel = mint.compare(
            {"checkout": 248, "payment": 195, "cart": 142},
            title="Endpoint p99",
            label="p99 latency",
            unit="ms",
            highlight="checkout",
        )
        c = card(
            'Release "v2.4" <fast> & clean cuts p99 latency 38%',
            _sample_metrics(with_spark=True),
            panel=panel,
            subtitle="7-day canary",
            source="telemetry",
        )
        html_doc = c.to_html()
        assert html_doc.startswith("<!DOCTYPE html>")
        assert "prefers-color-scheme:dark" in html_doc
        assert DEFAULT_ACCENT_LIGHT in html_doc
        assert DEFAULT_ACCENT_DARK in html_doc
        assert "<svg" in html_doc
        assert 'class="mf-spark"' in html_doc
        assert 'class="mf-panel-light"' in html_doc
        assert 'class="mf-panel-dark"' in html_doc
        # Proper HTML escaping
        assert "&quot;v2.4&quot;" in html_doc
        assert "&lt;fast&gt;" in html_doc
        assert "&amp;" in html_doc
        # Zero yellow hexes in default mintfig card tokens
        for yellow in ("#F6DF78", "#CC8800", "#E6AF00", "#FFFF00", "#FFD700"):
            assert yellow not in html_doc.upper()

        # Also works via .save("card.html")
        html_path = tmp_path / "summary.html"
        res = c.save(html_path)
        assert html_path.is_file()
        assert res["path"] == str(html_path.resolve())
        assert "<!DOCTYPE html>" in html_path.read_text(encoding="utf-8")

    def test_to_markdown_table_with_spark_and_panel_facts(self) -> None:
        panel = mint.compare(
            {"checkout": 248, "payment": 195, "cart": 142},
            title="Endpoint p99",
            label="p99 latency",
            unit="ms",
        )
        c = card(
            "PR #418 cuts p99 latency 38%",
            _sample_metrics(with_spark=True),
            panel=panel,
            subtitle="7-day canary",
            source="perf-canary",
        )
        md = c.to_markdown()
        assert "**PR #418 cuts p99 latency 38%**" in md
        assert "*7-day canary*" in md
        assert "| Metric" in md
        assert "Delta" in md
        assert "Trend" in md
        assert "Note" in md
        assert "**248 ms**" in md
        assert "▲ −38%" in md
        assert "▼ +18 MB" in md
        assert "*Source: perf-canary*" in md
        assert "**Endpoint p99:**" in md

        md_ascii = c.to_markdown(ascii_only=True)
        assert "▲" not in md_ascii
        assert "▼" not in md_ascii
        assert "▁" not in md_ascii


# --------------------------------------------------------------------------- #
# card_from_json() & cli_card()
# --------------------------------------------------------------------------- #


class TestJsonAndCli:
    def test_card_from_json_dict_string_file_and_roundtrip(self, tmp_path: Path) -> None:
        c1 = card_from_json(EXAMPLE_CARD_SPEC)
        assert c1.ship is True
        assert c1.panel is not None
        assert len(c1.metrics) == 4

        spec_roundtrip = c1.to_spec()
        c2 = card_from_json(json.dumps(spec_roundtrip))
        assert c2.takeaway == c1.takeaway
        assert len(c2.metrics) == len(c1.metrics)
        assert c2.panel is not None and c2.panel.kind == "compare"

        spec_path = tmp_path / "card_spec.json"
        spec_path.write_text(json.dumps(EXAMPLE_CARD_SPEC), encoding="utf-8")
        c3 = card_from_json(spec_path)
        assert c3.ship is True

    def test_cli_card_out_pair_markdown_html_and_example(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # --example
        assert cli_card(["--example"]) == 0
        ex = json.loads(capsys.readouterr().out)
        assert "takeaway" in ex and "metrics" in ex

        spec_path = tmp_path / "spec.json"
        spec_path.write_text(json.dumps(EXAMPLE_CARD_SPEC), encoding="utf-8")

        # --out card.png
        out_png = tmp_path / "card.png"
        rc = cli_card([str(spec_path), "--out", str(out_png)])
        out = json.loads(capsys.readouterr().out)
        assert rc == 0
        assert out["ship"] is True
        assert out_png.is_file()

        # --out stem.png --pair
        stem_png = tmp_path / "pr_summary.png"
        rc_pair = cli_card([str(spec_path), "--out", str(stem_png), "--pair"])
        pair_out = json.loads(capsys.readouterr().out)
        assert rc_pair == 0
        assert pair_out["ship"] is True
        assert (tmp_path / "pr_summary_light.png").is_file()
        assert (tmp_path / "pr_summary_dark.png").is_file()
        assert "<picture>" in pair_out["markdown"]

        # --markdown
        assert cli_card([str(spec_path), "--markdown"]) == 0
        md_out = capsys.readouterr().out
        assert "| Metric" in md_out

        # --html
        assert cli_card([str(spec_path), "--html"]) == 0
        html_out = capsys.readouterr().out
        assert "<!DOCTYPE html>" in html_out

        # missing args -> exit code 2
        assert cli_card([str(spec_path)]) == 2
        err_out = json.loads(capsys.readouterr().out)
        assert err_out["ok"] is False


# --------------------------------------------------------------------------- #
# Validation & error handling
# --------------------------------------------------------------------------- #


class TestValidation:
    def test_invalid_inputs_raise_explain_error(self) -> None:
        with pytest.raises(ExplainError):
            card("", [{"label": "A", "value": "1"}])
        with pytest.raises(ExplainError):
            card("Headline", [])
        with pytest.raises(ExplainError):
            card("Headline", [{"label": "", "value": "1"}])
        with pytest.raises(ExplainError):
            card("Headline", [{"label": "A"}])
        with pytest.raises(ExplainError):
            card("Headline", [{"label": "A", "value": "1", "good": "yes"}])
        with pytest.raises(ExplainError):
            card("Headline", [{"label": "A", "value": "1", "spark": ["bad"]}])
        with pytest.raises(ExplainError):
            card("Headline", [{"label": "A", "value": "1"}], style="nonexistent")
        with pytest.raises(ExplainError):
            card("Headline", [{"label": "A", "value": "1"}], accent="not-a-color")
        with pytest.raises(ExplainError):
            card_from_json({"takeaway": "Hi", "metrics": [{"label": "A", "value": 1}], "bogus": 1})
