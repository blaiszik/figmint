"""Visual surface themes and palettes for ``mint.explain``."""

from __future__ import annotations

import colorsys
import itertools
import json
from pathlib import Path

import matplotlib as mpl
import numpy as np
import pytest
from matplotlib.colors import to_hex, to_rgb
from matplotlib.text import Text

import mintfig as mint
from mintfig import explainer
from mintfig.cli import main as cli_main
from mintfig.palettes import simulate_cvd
from mintfig.themes import (
    EXPLAIN_PALETTES,
    THEMES,
    ExplainPalette,
    Theme,
    contrast_ratio,
    get_explain_palette,
    get_theme,
    register_palette,
    register_theme,
    resolve_default_palette,
    resolve_default_style,
)

SERVICES = {"checkout": 1840, "search": 460, "auth": 310, "catalog": 280, "cart": 240}
WEEKS = list(range(1, 9))
LATENCY = {
    "checkout": [540, 560, 550, 570, 980, 1400, 1700, 1840],
    "search": [450, 470, 455, 465, 460, 450, 470, 460],
    "auth": [300, 310, 305, 315, 300, 320, 305, 310],
}
TAKEAWAY = "Checkout is the slow service: its p99 is 4x the next worst"
ALL_STYLES = (
    "mintfig",
    "mint",
    "pine",
    "botanical",
    "bold",
    "editorial",
    "paper",
    "dark",
    "mono",
    "sketch",
)
ALL_PALETTES = (
    "default",
    "okabe_ito",
    "tol",
    "earth",
    "ocean",
    "berry",
    "mint",
    "spearmint",
    "matcha",
    "glacier",
    "mineral",
)
MINT_PALETTES = ("mint", "spearmint", "matcha", "glacier", "mineral")
MINT_STYLES = ("mint", "pine", "botanical")


def _all_forms() -> dict[str, mint.Panel]:
    rng = np.random.default_rng(7)
    return {
        "compare": mint.compare(SERVICES, label="p99 latency", unit="ms", highlight="checkout"),
        "compare_error": mint.compare(
            {"control": 4.1, "B": 5.2},
            error={"control": (3.8, 4.4), "B": (4.7, 5.7)},
            error_label="95% CI",
            unit="%",
            highlight="B",
        ),
        "share": mint.share(
            {f"stage {i}": v for i, v in enumerate([400, 380, 160, 60, 50, 40, 30, 9, 7])}
        ),
        "trend": mint.trend(WEEKS, LATENCY, label="p99 latency", unit="ms", x_label="Week", events={4: "v2.3"}),
        "trend_dates": mint.trend(
            ["2026-01-01", "2026-02-01", "2026-03-01", "2026-04-01"],
            {"A": [1, 2, 3, 5], "B": [2, 2, 2, 2]},
            band={"A": ([0.5, 1.5, 2.5, 4], [1.5, 2.5, 3.5, 6])},
            band_label="80% interval",
            reference=(3, "target"),
            label="Active teams",
            unit="thousands",
        ),
        "trend_highlight": mint.trend(
            WEEKS,
            {f"s{i}": rng.normal(i, 1, 8).tolist() for i in range(9)},
            highlight="s3",
            label="Score",
        ),
        "trend_facet": mint.trend(
            WEEKS,
            {f"s{i}": rng.normal(i, 1, 8).tolist() for i in range(6)},
            facet=True,
            label="Score",
        ),
        "change": mint.change(
            {"a": 10, "b": 30, "c": 55}, {"a": 40, "b": 28, "c": 60}, highlight="a", unit="%"
        ),
        "distribution": mint.distribution(
            {"before": rng.lognormal(3, 0.2, 60), "after": rng.lognormal(3.4, 0.5, 60)},
            unit="ms",
            highlight="after",
            reference=(40, "SLO"),
        ),
        "histogram_single": mint.histogram(
            rng.normal(50, 10, 120),
            bins=12,
            label="Score",
            unit="pts",
            reference=(65, "target"),
        ),
        "histogram_groups": mint.distribution(
            {"before": rng.lognormal(3.0, 0.25, 80), "after": rng.lognormal(3.4, 0.35, 80)},
            bins=14,
            label="Latency",
            unit="ms",
            baseline="before",
            highlight="after",
            reference=(40, "SLO"),
        ),
        "relate": mint.relate(
            np.arange(1.0, 31.0),
            np.arange(1.0, 31.0) * 3 + rng.normal(0, 4, 30),
            x_label="Batch size",
            y_label="Throughput (req/s)",
            names=[f"run{i}" for i in range(30)],
            highlight="run4",
            fit=True,
        ),
        "matrix": mint.matrix(
            rng.uniform(20, 95, (4, 5)).round(0).tolist(),
            rows=["Python", "Go", "Rust", "Java"],
            cols=["bugfix", "refactor", "tests", "docs", "perf"],
            unit="%",
            highlight=[("Rust", "perf")],
        ),
    }


def test_theme_aliases_and_unknown_style_rejection() -> None:
    assert get_theme("default").name == "mintfig"
    assert get_theme("bold").name == "bold"
    assert get_theme("newspaper").name == "editorial"
    assert get_theme("hand-drawn").name == "sketch"
    for retired in ("538", "nytimes", "xkcd", "fivethirtyeight", "nyt"):
        with pytest.raises(ValueError):
            get_theme(retired)
    with pytest.raises(mint.ExplainError) as err:
        mint.explain(TAKEAWAY, mint.compare(SERVICES, unit="ms"), style="bauhaus")
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
    result = mint.explain(
        TAKEAWAY,
        _all_forms()[form_name],
        source="synthetic example data",
        style=style_name,
    )
    summary = result.summary()
    assert summary["style"] == style_name
    # low_density is the only advisory allowed: a three-item slopegraph (6 values) at its
    # natural height always gets it; others may, depending on the host's font metrics
    # (DejaVu Sans on Linux CI makes the editorial and paper compare panels taller).
    advisories = {i["rule"] for i in summary.get("advisories", [])}
    assert summary["issues"] == []
    assert advisories <= {"low_density"}
    if form_name == "change":
        assert advisories == {"low_density"}
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
    original = mint.explain(
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
    if style_name == "mintfig":
        assert "style" not in spec
    else:
        assert spec["style"] == style_name
    mint.load(spec, out=tmp_path / "two.png")
    assert (tmp_path / "one.png").read_bytes() == (tmp_path / "two.png").read_bytes()


def test_bold_surface_tokens() -> None:
    result = mint.explain(
        TAKEAWAY,
        mint.trend(WEEKS, LATENCY, label="p99 latency", unit="ms", highlight="checkout"),
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
    result = mint.explain(
        TAKEAWAY,
        mint.trend(WEEKS, LATENCY, label="p99 latency", unit="ms", highlight="checkout"),
        source="synthetic",
        style="editorial",
    )
    assert result.issues == []
    title = result.fig.texts[0]
    assert getattr(title, "_mintfig_allow_serif", False) is True
    assert "serif" in title.get_fontfamily()
    assert set(title.get_fontfamily()) <= set(get_theme("editorial").title_family or ())
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
    measured = mint.explain(
        "Checkout dropped by 12.5 points after the change",
        mint.compare(long_names, label="Delta", unit="pts"),
        mint.compare(SERVICES, unit="ms"),
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
    illustrative = mint.explain(
        TAKEAWAY,
        mint.compare(SERVICES, label="p99 latency", unit="ms", highlight="checkout"),
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
        ["explain", str(spec_path), "--style", "newspaper", "--out", str(out_png), "--write-spec",
         "--summary", "full"]
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
    fig = mint.explain(
        TAKEAWAY,
        mint.compare(SERVICES, label="p99 latency", unit="ms", highlight="checkout"),
        mint.trend(WEEKS, LATENCY, label="p99 latency", unit="ms", x_label="Week"),
        source="synthetic",
        palette=palette_name,
    )
    summary = fig.summary()
    assert summary["ok"] is True
    assert summary["issues"] == []
    assert summary["palette"] == palette_name
    out = tmp_path / f"{palette_name}.png"
    fig.save(out, write_spec=True)
    spec = mint.load(out).to_spec()
    if palette_name == "default":
        assert "palette" not in spec
    else:
        assert spec["palette"] == palette_name
    rebuilt = mint.load(spec)
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
            "--summary",
            "full",
        ]
    )
    assert code == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["ok"] is True
    assert summary["style"] == "dark"
    assert summary["palette"] == "okabe_ito"
    assert summary["issues"] == []
    assert set(EXPLAIN_PALETTES) >= set(ALL_PALETTES)
    with pytest.raises(mint.ExplainError) as err:
        mint.explain(TAKEAWAY, mint.compare(SERVICES, unit="ms"), palette="rainbow_unicorn")
    assert err.value.rule == "unknown_palette"


def _is_yellow_or_amber(hex_color: str) -> bool:
    """True when a saturated color falls in the yellow/amber hue band (35–75 deg)."""
    r, g, b = to_rgb(hex_color)
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    hue_deg = h * 360.0
    return 35.0 <= hue_deg <= 75.0 and s >= 0.25 and v >= 0.35


@pytest.mark.parametrize("palette_name", MINT_PALETTES)
def test_mint_palettes_contain_zero_yellow_or_amber(palette_name: str) -> None:
    pal = get_explain_palette(palette_name)
    all_colors = (
        *pal.series_colors,
        *pal.accent_colors,
        *pal.seq_stops,
        *pal.div_low,
        *pal.div_high,
        pal.div_mid,
    )
    yellows = [c for c in all_colors if _is_yellow_or_amber(c)]
    assert yellows == [], f"{palette_name} contains yellow/amber colors: {yellows}"


@pytest.mark.parametrize("style_name", MINT_STYLES)
def test_mint_themes_contain_zero_yellow_or_amber(style_name: str) -> None:
    theme = get_theme(style_name)
    all_colors = (
        theme.background,
        theme.ink,
        theme.muted,
        *theme.series_colors,
        *theme.accent_colors,
        *theme.seq_stops,
        *theme.div_low,
        *theme.div_high,
        theme.div_mid,
    )
    yellows = [c for c in all_colors if _is_yellow_or_amber(c)]
    assert yellows == [], f"{style_name} contains yellow/amber colors: {yellows}"


def test_mint_theme_aliases_and_surface_tokens() -> None:
    assert get_theme("mint").name == "mint"
    assert get_theme("pine").name == "pine"
    assert get_theme("mint_dark").name == "pine"
    assert get_theme("mint-dark").name == "pine"
    assert get_theme("botanical").name == "botanical"

    mint_res = mint.explain(
        TAKEAWAY,
        mint.trend(WEEKS, LATENCY, label="p99 latency", unit="ms", highlight="checkout"),
        source="synthetic",
        style="mint",
    )
    assert mint_res.issues == []
    assert to_hex(mint_res.fig.get_facecolor()).upper() == "#F8FBFA"
    assert len(mint_res.fig.artists) == 2  # emerald top rule + subtle footer rule

    pine_res = mint.explain(
        TAKEAWAY,
        mint.trend(WEEKS, LATENCY, label="p99 latency", unit="ms", highlight="checkout"),
        source="synthetic",
        style="mint_dark",
    )
    assert pine_res.issues == []
    assert pine_res.summary()["style"] == "pine"
    assert to_hex(pine_res.fig.get_facecolor()).upper() == "#0F1715"
    for col in THEMES["pine"].series_colors:
        assert contrast_ratio(col, THEMES["pine"].background) >= 4.5

    bot_res = mint.explain(
        TAKEAWAY,
        mint.trend(WEEKS, LATENCY, label="p99 latency", unit="ms", highlight="checkout"),
        source="synthetic",
        style="botanical",
    )
    assert bot_res.issues == []
    assert to_hex(bot_res.fig.get_facecolor()).upper() == "#F5F8F4"
    title = bot_res.fig.texts[0]
    assert getattr(title, "_mintfig_allow_serif", False) is True
    assert "serif" in title.get_fontfamily()
    assert set(title.get_fontfamily()) <= set(get_theme("botanical").title_family or ())


def test_resolve_default_style_and_palette_precedence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("MINTFIG_STYLE", raising=False)
    monkeypatch.delenv("MINTFIG_PALETTE", raising=False)

    # Empty project with no pyproject.toml falls back to ("mintfig", None)
    empty_dir = tmp_path / "no_pyproject"
    empty_dir.mkdir()
    monkeypatch.chdir(empty_dir)
    assert resolve_default_style() == "mintfig"
    assert resolve_default_palette() is None

    # Nearest pyproject.toml [tool.mintfig] applies even from a nested subdirectory
    proj = tmp_path / "proj"
    nested = proj / "src" / "analysis"
    nested.mkdir(parents=True)
    (proj / "pyproject.toml").write_text(
        '[project]\nname = "demo"\n\n[tool.mintfig]\nstyle = "mint"\npalette = "glacier"\n',
        encoding="utf-8",
    )
    monkeypatch.chdir(nested)
    assert resolve_default_style() == "mint"
    assert resolve_default_palette() == "glacier"

    # Environment variables take precedence over pyproject.toml
    monkeypatch.setenv("MINTFIG_STYLE", "pine")
    monkeypatch.setenv("MINTFIG_PALETTE", "mineral")
    assert resolve_default_style() == "pine"
    assert resolve_default_palette() == "mineral"

    # Whitespace-only env vars fall through to pyproject.toml
    monkeypatch.setenv("MINTFIG_STYLE", "   ")
    monkeypatch.setenv("MINTFIG_PALETTE", "")
    assert resolve_default_style() == "mint"
    assert resolve_default_palette() == "glacier"

    # Malformed pyproject.toml falls back cleanly instead of raising
    broken = tmp_path / "broken"
    broken.mkdir()
    (broken / "pyproject.toml").write_text("[tool.mintfig\nstyle = ", encoding="utf-8")
    monkeypatch.delenv("MINTFIG_STYLE", raising=False)
    monkeypatch.delenv("MINTFIG_PALETTE", raising=False)
    monkeypatch.chdir(broken)
    assert resolve_default_style() == "mintfig"
    assert resolve_default_palette() is None


def test_register_theme_and_palette_helpers(monkeypatch: pytest.MonkeyPatch) -> None:
    custom_theme = Theme(name="custom_sage", description="Custom test theme.")
    custom_pal = ExplainPalette(
        name="custom_jade",
        description="Custom test palette.",
        series_colors=THEMES["mint"].series_colors,
        accent_colors=THEMES["mint"].accent_colors,
        seq_stops=THEMES["mint"].seq_stops,
        div_low=THEMES["mint"].div_low,
        div_high=THEMES["mint"].div_high,
        div_mid=THEMES["mint"].div_mid,
    )
    try:
        register_theme(custom_theme, aliases=("sage_alias",))
        register_palette(custom_pal)
        assert get_theme("custom_sage") is custom_theme
        assert get_theme("sage-alias") is custom_theme
        assert get_explain_palette("custom_jade") is custom_pal
        with pytest.raises(ValueError):
            register_theme(custom_theme)
        with pytest.raises(ValueError):
            register_palette(custom_pal)
    finally:
        THEMES.pop("custom_sage", None)
        from mintfig.themes import THEME_ALIASES

        THEME_ALIASES.pop("sage_alias", None)
        EXPLAIN_PALETTES.pop("custom_jade", None)


def test_cli_themes_list_json_and_swatch_card(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MINTFIG_STYLE", raising=False)
    monkeypatch.delenv("MINTFIG_PALETTE", raising=False)

    # Plain text listing
    assert cli_main(["themes"]) == 0
    text_out = capsys.readouterr().out
    for style_name in ALL_STYLES:
        assert style_name in text_out
    for pal_name in ALL_PALETTES:
        assert pal_name in text_out
    assert "mint_dark" in text_out

    # JSON output + visual swatch card rendering
    swatch_png = tmp_path / "themes_swatch.png"
    assert cli_main(["themes", "--json", "--out", str(swatch_png)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert set(ALL_STYLES) <= set(payload["styles"])
    assert set(ALL_PALETTES) <= set(payload["palettes"])
    assert payload["aliases"]["mint_dark"] == "pine"
    assert payload["out"] == str(swatch_png.resolve())
    assert swatch_png.is_file()
    assert swatch_png.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
