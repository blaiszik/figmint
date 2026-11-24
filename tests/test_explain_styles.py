"""Visual surface themes for ``fm.explain``: ``figmint``, ``bold``, ``editorial``, ``sketch``."""

from __future__ import annotations

import itertools
import json
from pathlib import Path

import matplotlib as mpl
import numpy as np
import pytest
from matplotlib.colors import to_hex, to_rgb
from matplotlib.text import Text

import figmint as fm
from figmint import explainer
from figmint.cli import main as cli_main
from figmint.palettes import simulate_cvd
from figmint.themes import EXPLAIN_PALETTES, THEMES, contrast_ratio, get_explain_palette, get_theme

SERVICES = {"checkout": 1840, "search": 460, "auth": 310, "catalog": 280, "cart": 240}
WEEKS = list(range(1, 9))
LATENCY = {
    "checkout": [540, 560, 550, 570, 980, 1400, 1700, 1840],
    "search": [450, 470, 455, 465, 460, 450, 470, 460],
    "auth": [300, 310, 305, 315, 300, 320, 305, 310],
}
TAKEAWAY = "Checkout is the slow service: its p99 is 4x the next worst"
ALL_STYLES = ("figmint", "bold", "editorial", "paper", "dark", "mono", "sketch")
ALL_PALETTES = ("default", "okabe_ito", "tol", "earth", "ocean", "berry")


def _all_forms() -> dict[str, fm.Panel]:
    rng = np.random.default_rng(7)
    return {
        "compare": fm.compare(SERVICES, label="p99 latency", unit="ms", highlight="checkout"),
        "compare_error": fm.compare(
            {"control": 4.1, "B": 5.2},
            error={"control": (3.8, 4.4), "B": (4.7, 5.7)},
            error_label="95% CI",
            unit="%",
            highlight="B",
        ),
        "share": fm.share(
            {f"stage {i}": v for i, v in enumerate([400, 380, 160, 60, 50, 40, 30, 9, 7])}
        ),
        "trend": fm.trend(WEEKS, LATENCY, label="p99 latency", unit="ms", x_label="Week", events={4: "v2.3"}),
        "trend_dates": fm.trend(
            ["2026-01-01", "2026-02-01", "2026-03-01", "2026-04-01"],
            {"A": [1, 2, 3, 5], "B": [2, 2, 2, 2]},
            band={"A": ([0.5, 1.5, 2.5, 4], [1.5, 2.5, 3.5, 6])},
            band_label="80% interval",
            reference=(3, "target"),
            label="Active teams",
            unit="thousands",
        ),
        "trend_highlight": fm.trend(
            WEEKS,
            {f"s{i}": rng.normal(i, 1, 8).tolist() for i in range(9)},
            highlight="s3",
            label="Score",
        ),
        "trend_facet": fm.trend(
            WEEKS,
            {f"s{i}": rng.normal(i, 1, 8).tolist() for i in range(6)},
            facet=True,
            label="Score",
        ),
        "change": fm.change(
            {"a": 10, "b": 30, "c": 55}, {"a": 40, "b": 28, "c": 60}, highlight="a", unit="%"
        ),
        "distribution": fm.distribution(
            {"before": rng.lognormal(3, 0.2, 60), "after": rng.lognormal(3.4, 0.5, 60)},
            unit="ms",
            highlight="after",
            reference=(40, "SLO"),
        ),
        "histogram_single": fm.histogram(
            rng.normal(50, 10, 120),
            bins=12,
            label="Score",
            unit="pts",
            reference=(65, "target"),
        ),
        "histogram_groups": fm.distribution(
            {"before": rng.lognormal(3.0, 0.25, 80), "after": rng.lognormal(3.4, 0.35, 80)},
            bins=14,
            label="Latency",
            unit="ms",
            baseline="before",
            highlight="after",
            reference=(40, "SLO"),
        ),
        "relate": fm.relate(
            np.arange(1.0, 31.0),
            np.arange(1.0, 31.0) * 3 + rng.normal(0, 4, 30),
            x_label="Batch size",
            y_label="Throughput (req/s)",
            names=[f"run{i}" for i in range(30)],
            highlight="run4",
            fit=True,
        ),
        "matrix": fm.matrix(
            rng.uniform(20, 95, (4, 5)).round(0).tolist(),
            rows=["Python", "Go", "Rust", "Java"],
            cols=["bugfix", "refactor", "tests", "docs", "perf"],
            unit="%",
            highlight=[("Rust", "perf")],
        ),
    }


def test_theme_aliases_and_unknown_style_rejection() -> None:
    assert get_theme("default").name == "figmint"
    assert get_theme("bold").name == "bold"
    assert get_theme("newspaper").name == "editorial"
    assert get_theme("hand-drawn").name == "sketch"
    for retired in ("538", "nytimes", "xkcd", "fivethirtyeight", "nyt"):
        with pytest.raises(ValueError):
            get_theme(retired)
    with pytest.raises(fm.ExplainError) as err:
        fm.explain(TAKEAWAY, fm.compare(SERVICES, unit="ms"), style="bauhaus")
    assert err.value.rule == "unknown_style"
    assert "editorial" in err.value.fix_hint and "bold" in err.value.fix_hint


@pytest.mark.parametrize("style_name", ALL_STYLES)
def test_every_theme_palette_separates_in_grayscale_and_cvd(style_name: str) -> None:
    theme = THEMES[style_name]
    assert len(theme.series_colors) == 4
    assert len(theme.accent_colors) == 3
    assert set(theme.accent_colors) <= set(theme.series_colors)

    rgb = np.array([to_rgb(c) for c in theme.series_colors])[np.newaxis]
    gray = simulate_cvd(rgb, "grayscale")[0, :, 0]
    deutan = simulate_cvd(rgb, "deuteranopia")[0]
    protan = simulate_cvd(rgb, "protanopia")[0]
    for i, j in itertools.combinations(range(len(theme.series_colors)), 2):
        assert abs(gray[i] - gray[j]) >= 0.05
        assert (
            min(np.linalg.norm(deutan[i] - deutan[j]), np.linalg.norm(protan[i] - protan[j]))
            >= 0.12
        )


@pytest.mark.parametrize("style_name", ALL_STYLES)
def test_every_theme_text_contrast_meets_wcag_aa_on_background(style_name: str) -> None:
    theme = THEMES[style_name]
    assert contrast_ratio(theme.ink, theme.background) >= 7.0
    assert contrast_ratio(theme.muted, theme.background) >= 4.5
    for color in theme.series_colors:
        adjusted = explainer._text_color(color, background=theme.background, ink=theme.ink)
        assert contrast_ratio(adjusted, theme.background) >= 4.5


@pytest.mark.parametrize("style_name", ALL_STYLES)
@pytest.mark.parametrize("form_name", list(_all_forms()))
def test_every_form_renders_clean_across_all_styles(style_name: str, form_name: str) -> None:
    result = fm.explain(
        TAKEAWAY,
        _all_forms()[form_name],
        source="synthetic example data",
        style=style_name,
    )
    summary = result.summary()
    assert summary["style"] == style_name
    assert summary["issues"] == []
    assert summary["ok"] is True
    assert result.width_mm == pytest.approx(140.0, abs=0.01)
    assert summary["display"]["min_text_px"] >= explainer.MIN_TEXT_PX
    rotated = [
        t.get_text()
        for t in result.fig.findobj(Text)
        if t.get_visible() and t.get_text().strip() and t.get_rotation() not in (0.0, 360.0)
    ]
    assert rotated == []


@pytest.mark.parametrize("style_name", ALL_STYLES)
def test_multi_panel_spec_round_trip_is_byte_identical_and_rcparams_clean(
    style_name: str, tmp_path: Path
) -> None:
    before = dict(mpl.rcParams)
    forms = _all_forms()
    original = fm.explain(
        TAKEAWAY,
        forms["compare"],
        forms["trend"],
        forms["change"],
        forms["matrix"],
        subtitle="Week of 16 Nov",
        note="Synthetic test data.",
        source="synthetic",
        style=style_name,
    )
    original.save(tmp_path / "one.png", write_spec=True)
    assert dict(mpl.rcParams) == before

    spec = json.loads((tmp_path / "one.json").read_text("utf-8"))
    if style_name == "figmint":
        assert "style" not in spec
    else:
        assert spec["style"] == style_name
    fm.explain_from_spec(spec, out=tmp_path / "two.png")
    assert (tmp_path / "one.png").read_bytes() == (tmp_path / "two.png").read_bytes()


def test_bold_surface_tokens() -> None:
    result = fm.explain(
        TAKEAWAY,
        fm.trend(WEEKS, LATENCY, label="p99 latency", unit="ms", highlight="checkout"),
        source="synthetic",
        style="bold",
    )
    assert to_hex(result.fig.get_facecolor()).upper() == "#F0F0F0"
    ax = result["a"]
    assert all(not sp.get_visible() for sp in ax.spines.values())
    assert any(gl.get_visible() for gl in ax.yaxis.get_gridlines())
    assert any(gl.get_visible() for gl in ax.xaxis.get_gridlines())
    assert len(result.fig.artists) == 1  # footer rule
    assert result.issues == []


def test_editorial_surface_tokens_serif_title_and_inline_y_ticks() -> None:
    result = fm.explain(
        TAKEAWAY,
        fm.trend(WEEKS, LATENCY, label="p99 latency", unit="ms", highlight="checkout"),
        source="synthetic",
        style="editorial",
    )
    assert result.issues == []
    title = result.fig.texts[0]
    assert getattr(title, "_figmint_allow_serif", False) is True
    assert "Georgia" in title.get_fontfamily()
    assert len(result.fig.artists) == 2  # crisp top rule + subtle footer rule
    ax = result["a"]
    # Traditional left y-tick labels are hidden in favour of inline above-gridline annotations
    assert all(not tick.label1.get_visible() for tick in ax.yaxis.get_major_ticks())
    inline_texts = [t.get_text() for t in ax.texts]
    assert any(txt.endswith(" ms") for txt in inline_texts)
    assert sum(1 for txt in inline_texts if txt.endswith(" ms")) == 1  # unit on top tick only


def test_sketch_surface_tokens_ascii_glyphs_and_honesty_warning() -> None:
    # Negative value + long truncated name verify ASCII minus and ASCII ellipsis
    long_names = {
        "payments end-to-end regression suite for checkout flow": -12.5,
        "auth": 4.0,
    }
    measured = fm.explain(
        "Checkout dropped by 12.5 points after the change",
        fm.compare(long_names, label="Delta", unit="pts"),
        fm.compare(SERVICES, unit="ms"),
        source="prod/latency.parquet",
        style="sketch",
    )
    rules = {i["rule"] for i in measured.issues}
    assert "sketch_on_measured_data" in rules
    assert measured.ok is True  # warning only

    rendered_texts = [t.get_text() for t in measured.fig.findobj(Text) if t.get_text().strip()]
    assert not any("\N{MINUS SIGN}" in s for s in rendered_texts)
    assert not any("\N{HORIZONTAL ELLIPSIS}" in s for s in rendered_texts)
    assert any("-" in s and "12.5" in s for s in rendered_texts)
    assert any("..." in s for s in rendered_texts)

    # Marking the data synthetic or illustrative silences the honesty warning
    illustrative = fm.explain(
        TAKEAWAY,
        fm.compare(SERVICES, label="p99 latency", unit="ms", highlight="checkout"),
        note="Illustrative concept sketch.",
        style="sketch",
    )
    assert illustrative.issues == []


def test_cli_explain_style_override(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli_main(["explain", "--example"]) == 0
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(capsys.readouterr().out, encoding="utf-8")

    out_png = tmp_path / "editorial.png"
    code = cli_main(
        ["explain", str(spec_path), "--style", "newspaper", "--out", str(out_png), "--write-spec"]
    )
    assert code == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["ok"] is True
    assert summary["style"] == "editorial"
    assert summary["issues"] == []
    saved_spec = json.loads(out_png.with_suffix(".json").read_text("utf-8"))
    assert saved_spec["style"] == "editorial"


@pytest.mark.parametrize("palette_name", ALL_PALETTES)
def test_every_explain_palette_separates_in_grayscale_and_cvd(palette_name: str) -> None:
    pal = get_explain_palette(palette_name)
    assert len(pal.series_colors) == 4
    assert len(pal.accent_colors) == 3
    assert set(pal.accent_colors) <= set(pal.series_colors)

    rgb = np.array([to_rgb(c) for c in pal.series_colors])[np.newaxis]
    gray = simulate_cvd(rgb, "grayscale")[0, :, 0]
    deutan = simulate_cvd(rgb, "deuteranopia")[0]
    protan = simulate_cvd(rgb, "protanopia")[0]
    for i, j in itertools.combinations(range(len(pal.series_colors)), 2):
        assert abs(gray[i] - gray[j]) >= 0.05
        assert (
            min(np.linalg.norm(deutan[i] - deutan[j]), np.linalg.norm(protan[i] - protan[j]))
            >= 0.12
        )
    for color in pal.series_colors:
        adjusted = explainer._text_color(color, background="#FFFFFF", ink="#1A1D21")
        assert contrast_ratio(adjusted, "#FFFFFF") >= 4.5


@pytest.mark.parametrize("palette_name", ALL_PALETTES)
def test_palette_renders_clean_and_roundtrips_via_spec(
    palette_name: str, tmp_path: Path
) -> None:
    fig = fm.explain(
        TAKEAWAY,
        fm.compare(SERVICES, label="p99 latency", unit="ms", highlight="checkout"),
        fm.trend(WEEKS, LATENCY, label="p99 latency", unit="ms", x_label="Week"),
        source="synthetic",
        palette=palette_name,
    )
    summary = fig.summary()
    assert summary["ok"] is True
    assert summary["issues"] == []
    assert summary["palette"] == palette_name
    out = tmp_path / f"{palette_name}.png"
    fig.save(out, write_spec=True)
    spec = fm.load(out).to_spec()
    if palette_name == "default":
        assert "palette" not in spec
    else:
        assert spec["palette"] == palette_name
    rebuilt = fm.explain_from_spec(spec)
    assert rebuilt.summary()["palette"] == palette_name


def test_dark_theme_and_palette_override_cli(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli_main(["explain", "--example"]) == 0
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(capsys.readouterr().out, encoding="utf-8")

    out_png = tmp_path / "dark_okabe.png"
    code = cli_main(
        [
            "explain",
            str(spec_path),
            "--style",
            "dark",
            "--palette",
            "okabe_ito",
            "--out",
            str(out_png),
            "--write-spec",
        ]
    )
    assert code == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["ok"] is True
    assert summary["style"] == "dark"
    assert summary["palette"] == "okabe_ito"
    assert summary["issues"] == []
    assert set(EXPLAIN_PALETTES) >= set(ALL_PALETTES)
    with pytest.raises(fm.ExplainError) as err:
        fm.explain(TAKEAWAY, fm.compare(SERVICES, unit="ms"), palette="rainbow_unicorn")
    assert err.value.rule == "unknown_palette"
