"""Tests for Tufte word-sized micro-graphics and expandable evidence chips (mint.inline)."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

import mintfig as mint


def test_inline_spark_svg_unicode_and_auto_expand(tmp_path: Path) -> None:
    g = mint.inline.spark(
        [1.82, 1.31, 0.94, 0.72, 0.58, 0.49, 0.44],
        label="Val loss",
        band=(0.40, 0.55),
        reference=0.50,
        expand=True,
    )
    assert isinstance(g, mint.InlineGraphic)
    assert g.kind == "spark"
    assert g.svg.startswith("<svg ") and g.svg.endswith("</svg>")
    assert "<polyline" in g.svg
    assert "<rect" in g.svg  # reference band
    assert "0.44" in str(g)
    assert any("within band" in f for f in g.facts)
    assert g.expand_explanation is not None

    chip_html = g.html(show_label=True)
    assert "data-mf-chip=" in chip_html
    assert "↗" in chip_html
    assert g.markdown(mode="svg_uri").startswith("![")

    svg_path = tmp_path / "loss.svg"
    res = g.save(svg_path)
    assert svg_path.exists()
    assert res["expandable"] is True


def test_inline_spark_handles_gaps_and_flat_series() -> None:
    g = mint.inline.spark([2.0, 2.0, None, 2.0, 2.0])
    assert g.svg.count("<polyline") == 2
    assert "flat" in g.facts[0]

    with pytest.raises(mint.ExplainError):
        mint.inline.spark([1.0])


def test_inline_ci_epistemic_warning_and_reference_coloring() -> None:
    # Excludes reference (0) and names its uncertainty
    sig = mint.inline.ci(
        0.14,
        (0.06, 0.22),
        error_label="95% CI, 10 seeds",
        inner_error=(0.11, 0.17),
        reference=0.0,
        domain=(-0.10, 0.30),
        label="Δ accuracy",
        expand=True,
    )
    assert sig.warnings == []
    assert sig.data["excludes_reference"] is True
    assert any("excludes reference" in f for f in sig.facts)
    assert sig.theme.series_colors[0] in sig.svg
    assert "│" in sig.text and "●" in sig.text
    assert "|" in sig.ascii_text and "*" in sig.ascii_text
    assert sig.expand_explanation is not None

    # Crosses reference (0) and omits error_label -> muted hollow dot + advisory warning
    dom = mint.inline.shared_domain((0.06, 0.22), (-0.03, 0.07), reference=0.0)
    assert dom[0] < -0.03 and dom[1] > 0.22
    null_ci = mint.inline.ci(0.02, 0.05, reference=0.0, domain=dom)
    assert null_ci.data["excludes_reference"] is False
    assert "○" in null_ci.text
    assert "o" in null_ci.ascii_text
    assert any("Unnamed uncertainty" in w for w in null_ci.warnings)
    assert null_ci.theme.muted in null_ci.svg
    assert f'fill="{null_ci.theme.background}"' in null_ci.svg


def test_inline_dist_small_and_large_n() -> None:
    small = mint.inline.dist(
        [12.1, 12.4, 12.9, 13.0, 13.2, 13.5, 13.8, 28.4],
        label="Latency",
        unit="ms",
        reference=15.0,
        expand=True,
    )
    assert "<circle" in small.svg
    assert any("outlier" in f for f in small.facts)
    assert small.expand_explanation is not None

    # Large n switches cleanly to micro-histogram bars
    large = mint.inline.dist([float(i % 17) + 0.1 * (i // 17) for i in range(120)], expand=True)
    assert "<rect" in large.svg
    assert large.data["n"] == 120
    assert large.expand_explanation is not None


def test_inline_bar_and_strip_modes() -> None:
    b = mint.inline.bar(
        0.84, total=1.0, baseline=0.76, target=0.80, bands=(0.60, 0.80), label="Pass@1", expand=True
    )
    assert b.value_text == "84%"
    assert any("meets target" in f for f in b.facts)
    assert b.expand_explanation is not None

    status = mint.inline.strip(
        [True, True, False, True, "warn", "skip", True],
        labels=[f"seed_{i}" for i in range(7)],
        label="Seeds",
        expand=True,
    )
    assert "4/6 pass" in status.value_text
    assert any("seed_2" in f for f in status.facts)
    assert "<path" in status.svg  # redundant cross on fail cell
    assert "▄" in status.text and "□" in status.text
    assert status.expand_explanation is not None

    heat = mint.inline.strip([-0.8, -0.2, 0.0, 0.4, 0.9], diverging=True, label="Effect", expand=True)
    assert heat.data["numeric"] is True
    assert heat.svg.count("<rect") == 5
    assert heat.expand_explanation is not None


def test_custom_attached_explanation_and_document_escaping(tmp_path: Path) -> None:
    custom_fig = mint.explain(
        "Retrieval accounts for 8 points of accuracy",
        mint.compare({"full": 0.82, "no retrieval": 0.74}, label="Accuracy"),
    )
    chip = mint.inline.bar(0.82, baseline=0.74, label="<script>alert(1)</script>", expand=custom_fig)

    prose = mint.inline.format_prose(
        "Model reached {acc} with <unsafe> tags safely escaped.",
        acc=chip,
    )
    assert "&lt;unsafe&gt;" in prose
    assert "&lt;script&gt;" in prose
    assert "<script>alert(1)</script>" not in prose

    # Extract embedded JSON payload and ensure figure SVG is embedded cleanly
    m = re.search(r'data-mf-chip="([^"]+)"', prose)
    assert m is not None
    import html as html_lib

    payload = json.loads(html_lib.unescape(m.group(1)))
    assert payload["has_figure"] is True
    assert "<svg" in payload["figure_svg"]
    assert payload["figure_title"] == custom_fig.takeaway

    doc_html = mint.inline.document(
        "Ablation Note",
        [prose],
        subtitle="Click any inline chip to inspect the full figure",
        style="dark",
        palette="okabe_ito",
        source="pytest",
    )
    out = tmp_path / "note.html"
    out.write_text(doc_html, encoding="utf-8")
    assert "mf-modal-backdrop" in doc_html
    assert "color-scheme: dark" in doc_html

    # Plain-text prose rendering (verbose + compact)
    plain = mint.inline.format_prose("Accuracy: {acc}", mode="text", acc=chip)
    assert "82%" in plain
    assert "<button" not in plain

    ci_chip = mint.inline.ci(0.08, (0.05, 0.11), error_label="95% CI")
    compact_prose = mint.inline.format_prose("Gain {g}.", mode="text", compact=True, g=ci_chip)
    assert "[+0.05" not in compact_prose
    assert "+0.08 [" in compact_prose


def test_inline_catalog_exports_all_17_components() -> None:
    names = [entry["name"] for entry in mint.inline.CATALOG]
    assert len(names) == 17
    assert len(set(names)) == 17
    for name in names:
        fn = getattr(mint.inline, name)
        assert callable(fn)

