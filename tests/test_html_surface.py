"""The HTML surface: responsive layouts, light/dark from one file, details on demand."""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET

import matplotlib

matplotlib.use("Agg")

import numpy as np
import pytest

import mintfig as mint
from mintfig._explain import marks as marks_mod
from mintfig.interactive import _render_svg, render_html, render_html_fragment

XMLNS = {"http://www.w3.org/2000/svg", "http://www.w3.org/1999/xlink"}


def _ablation(**kw: object) -> mint.Explanation:
    return mint.explain(
        "Removing retrieval costs 8 points of accuracy; removing fine-tuning costs 13",
        mint.compare(
            {"full model": 0.82, "no retrieval": 0.74, "no fine-tuning": 0.69},
            error={"full model": (0.80, 0.84), "no retrieval": (0.71, 0.77),
                   "no fine-tuning": (0.66, 0.72)},
            error_label="95% CI, 5 seeds",
            title="Both losses are outside seed noise",
            label="Test accuracy",
            highlight=["no retrieval", "no fine-tuning"],
        ),
        mint.trend(
            [0, 500, 1000, 1500, 2000],
            {"full model": [0.02, 0.61, 0.76, 0.80, 0.82],
             "no retrieval": [0.02, 0.52, 0.67, 0.72, 0.74],
             "no fine-tuning": [0.01, 0.44, 0.60, 0.66, 0.69]},
            title="The gap opens in the first 500 steps",
            label="Validation accuracy",
            x_label="Training step",
        ),
        source="runs/ablation_2026-11 (5 seeds per variant)",
        **kw,
    )


def _marks_map(doc: str) -> dict[str, dict[str, object]]:
    return json.loads(re.search(r"var M=(\{.*?\}),SPEC=", doc, re.DOTALL).group(1))


def _dark_block(doc: str) -> str:
    return re.search(r"@media \(prefers-color-scheme:dark\)\{(#[\w-]+\{[^}]*\})", doc).group(1)


@pytest.fixture(scope="module")
def ablation_doc() -> str:
    return render_html(_ablation())


def test_layouts_switched_by_container_query(ablation_doc: str) -> None:
    assert ablation_doc.count('<div class="mf-v mf-v') == 3
    assert 'data-mf-layouts="360 450 700"' in ablation_doc
    root = re.search(r'<figure id="([\w-]+)"', ablation_doc).group(1)
    assert f"container:{root}/inline-size" in ablation_doc
    assert f"@container {root} (min-width:450px)" in ablation_doc
    assert f"@container {root} (min-width:700px)" in ablation_doc
    widths = [float(w) for w in re.findall(r'<svg[^>]* width="([\d.]+)pt"', ablation_doc)]
    assert len(widths) == 3 and widths[0] < widths[1] < widths[2]  # small, narrow, chat

    narrow = render_html(_ablation(width="narrow"))
    assert narrow.count('<div class="mf-v mf-v') == 2
    assert 'data-mf-layouts="360 450"' in narrow


def test_slide_embeds_small_narrow_chat_and_slide() -> None:
    doc = render_html_fragment(_ablation(width="slide"))
    assert doc.count('<div class="mf-v mf-v') == 4
    assert "(min-width:700px)" in doc and "(min-width:1280px)" in doc


def test_every_theme_variable_has_a_dark_value(ablation_doc: str) -> None:
    used = set(re.findall(r"var\(--mf-([\w-]+), #[0-9a-fA-F]{6}\)", ablation_doc))
    assert {"bg", "ink", "muted"} <= used
    dark = _dark_block(ablation_doc)
    for name in used:
        assert f"--mf-{name}:" in dark
    assert '[data-mf-scheme="dark"]' in ablation_doc
    assert '[data-mf-scheme="light"]' in ablation_doc
    # The light figure's surface is the default style's; the dark one the dark style's.
    assert "--mf-bg:#14181f;" in dark


def test_explicit_style_does_not_auto_switch() -> None:
    doc = render_html_fragment(_ablation(style="dark"))
    assert "prefers-color-scheme" not in doc
    assert "var(--mf-" not in re.sub(r"<style>.*?</style>", "", doc, flags=re.DOTALL)


def test_standalone_svg_parses_with_fallback_hex(ablation_doc: str) -> None:
    svg = re.search(r"<svg.*?</svg>", ablation_doc, re.DOTALL).group(0)
    root = ET.fromstring(svg)
    assert root.tag.endswith("svg")
    styles = " ".join(el.get("style", "") for el in root.iter())
    assert "var(--mf-ink, #1a1d21)" in styles
    for var in re.findall(r"var\([^)]*\)", styles):
        assert re.fullmatch(r"var\(--mf-[\w-]+, #[0-9a-fA-F]{6}\)", var)


def test_marks_carry_values_and_citation_parts(tmp_path: object) -> None:
    exp = _ablation()
    exp.save(tmp_path / "ablation.png")  # type: ignore[operator]
    doc = render_html(exp)
    data = _marks_map(doc)
    keys = set(re.findall(r'data-mf="([^"]+)"', doc))
    assert keys <= set(data)
    assert {"name": "no retrieval", "x": "500", "value": 0.52} in [
        {k: v for k, v in rec.items() if k != "panel"} for rec in data.values()
        if rec["panel"] == "b"
    ]
    dots = [rec for rec in data.values() if rec["panel"] == "a"]
    assert {"name": "full model", "value": 0.82, "lo": 0.8, "hi": 0.84, "panel": "a"} in dots
    assert 'FILE="ablation.png"' in doc
    assert "Critique" not in doc and "toolbar" not in doc


KIND_FIGURES = [
    lambda: mint.explain(
        "Checkout is the slowest service and the share of time it takes is largest",
        mint.compare({"checkout": 1840, "search": 460, "auth": 310}, label="p99", unit="ms"),
        mint.share({"checkout": 52, "search": 30, "auth": 18}, label="Time"),
        mint.waterfall({"+Retrieval": 8.2, "+Reranker": 3.4, "Quant": -1.5},
                       start=("Base", 69.0), unit="%"),
        mint.flow([("Visits", 1000), ("Carts", 400), ("Orders", 120)]),
    ),
    lambda: mint.explain(
        "Alpha improves on every view of the evaluation after the 2.0 release",
        mint.trend([1, 2, 3, 4], {"alpha": [1, 2, 3, 5], "beta": [1, 1.5, 2, 2.2]}, label="Score"),
        mint.change({"alpha": 70, "beta": 68}, {"alpha": 82, "beta": 71}, label="Score"),
        mint.relate([1, 2, 3, 4, 5], [2.1, 3.9, 6.2, 8.1, 9.8], x_label="Size", y_label="Score"),
        mint.timeline([("build", 0, 4), ("test", 4, 9), ("deploy", 9, 11)], unit="min"),
    ),
    lambda: mint.explain(
        "Alpha leads the scorecard and its runs are the fastest and tightest of all",
        mint.table([{"Model": "Alpha", "Acc": 92.4}, {"Model": "Beta", "Acc": 87.1}]),
        mint.matrix([[1.0, 0.4], [0.4, 1.0]], rows=["a", "b"], cols=["a", "b"], label="r"),
        mint.distribution({"alpha": [1, 2, 2, 3, 4, 2.5], "beta": [3, 4, 4, 5, 6, 4.5]},
                          label="Latency", unit="ms"),
        mint.histogram(list(np.linspace(0, 10, 40)), bins=5, label="Latency", unit="ms"),
    ),
    lambda: mint.explain(
        "Alpha wins both benchmarks, and its interval clears the baseline on each",
        mint.compare({"GPQA": {"alpha": 86, "beta": 77}, "SWE": {"alpha": 74, "beta": 58}},
                     label="Score", unit="%"),
        mint.compare({"alpha": 0.8, "beta": 0.7}, error={"alpha": (0.78, 0.82),
                     "beta": (0.66, 0.74)}, error_label="95% CI", label="Acc"),
    ),
]


@pytest.mark.parametrize("build", KIND_FIGURES)
def test_every_panel_kind_has_tagged_marks(build: object) -> None:
    exp = build()  # type: ignore[operator]
    svg, data = _render_svg(exp)
    tagged = set(re.findall(r'data-mf="([^"]+)"', svg))
    for key, panel in exp.panels.items():
        own = [k for k in tagged if data[k]["panel"] == key]
        assert own, f"panel {key} ({panel.kind}) has no tagged mark"
        assert all("value" in data[k] for k in own)


def test_no_external_requests(ablation_doc: str) -> None:
    assert set(re.findall(r"https?://[^\s\"')<>]+", ablation_doc)) <= XMLNS
    assert "@import" not in ablation_doc
    assert not re.search(r"<(script|link|img)\b[^>]+(src|href)=", ablation_doc)


def test_two_fragments_on_one_page_keep_ids_apart() -> None:
    exp = _ablation()
    page = render_html_fragment(exp) + render_html_fragment(exp)
    roots = re.findall(r'<figure id="([\w-]+)"', page)
    assert len(roots) == 2 and roots[0] != roots[1]
    ids = re.findall(r' id="([^"]+)"', page)
    assert len(ids) == len(set(ids))


def test_tagging_leaves_the_raster_render_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    def pixels(exp: mint.Explanation) -> bytes:
        with exp.theme.rc_context(exp.spec):
            exp.fig.canvas.draw()
        return bytes(exp.fig.canvas.buffer_rgba())

    tagged = pixels(_ablation())
    monkeypatch.setattr(marks_mod, "_claim", lambda ctx, artist: False)
    untagged_exp = _ablation()
    assert not marks_mod.tagged(untagged_exp.fig)
    assert pixels(untagged_exp) == tagged


def test_small_layout_keeps_text_at_11px_at_360() -> None:
    from matplotlib.text import Text

    from mintfig.interactive import _small_layout

    small = _small_layout(_ablation())
    assert small is not None and small.layout == [["a"], ["b"]]
    sizes = [t.get_fontsize() for t in small.fig.findobj(Text) if t.get_visible() and t.get_text().strip()]
    assert min(sizes) * 360 / (small.fig.get_figwidth() * 72) >= 11


def test_small_layout_falls_back_to_narrow_when_it_cannot_fit() -> None:
    row = {"Model": "Alpha-3 Max"} | {f"Bench {i}": 86.4 + i for i in range(5)}
    wide = mint.explain(
        "Alpha-3 Max leads every benchmark we ran",
        mint.table([row, {**row, "Model": "Beta"}]),
    )
    assert 'data-mf-layouts="450 700"' in render_html_fragment(wide)


def test_svg_style_is_scoped_to_its_own_svg(ablation_doc: str) -> None:
    assert '<style type="text/css">*{' not in ablation_doc
    svg_ids = re.findall(r'<svg id="([\w-]+)"', ablation_doc)
    assert svg_ids
    for svg_id in svg_ids:
        assert f'<style type="text/css">#{svg_id} *{{stroke-linejoin' in ablation_doc


def test_dense_relate_gets_one_mark_per_group() -> None:
    rng = np.random.default_rng(0)
    x = rng.normal(size=400)
    exp = mint.explain(
        "Score rises with size in both groups",
        mint.relate(list(x), list(x + rng.normal(size=400)), groups=["a", "b"] * 200,
                    x_label="Size", y_label="Score"),
    )
    svg, data = _render_svg(exp)
    assert 'class="mf-hits"' not in svg
    groups = [rec for rec in data.values() if rec.get("x") == "median, range"]
    assert {rec["name"] for rec in groups} == {"a", "b"}
    assert sum(rec["n"] for rec in groups) == 400
    assert all(rec["lo"] <= rec["value"] <= rec["hi"] for rec in groups)


def test_focusable_marks_are_named_by_their_tooltip(ablation_doc: str) -> None:
    focusable = re.findall(r'<(?:g|circle|rect)\b[^>]*tabindex="0"[^>]*>', ablation_doc)
    assert focusable and all('aria-label="' in tag for tag in focusable)
    assert 'aria-label="no retrieval @ 500 = 0.52"' in ablation_doc
    assert 'aria-label="full model = 0.82  [0.8, 0.84]"' in ablation_doc


def test_width_in_mm_embeds_its_own_layout_and_the_smaller_ones() -> None:
    doc = render_html_fragment(_ablation(width=100.0, layout=[["a"], ["b"]]))  # 500 px at chat scale
    assert 'data-mf-layouts="360 450 500"' in doc
    assert "max-width:500px" in doc
    wide = render_html_fragment(_ablation(width=180.0))
    assert 'data-mf-layouts="360 450 700 900"' in wide


def test_fragment_options_for_pages_with_several_figures() -> None:
    exp = _ablation()
    plain = render_html_fragment(exp, facts=False, caption="Both drops exceed the seed CI.")
    drawer = plain.split('<div class="mf-data"', 1)[1]
    assert 'class="mf-facts"' not in drawer and 'class="mf-data-table"' in drawer
    assert plain.index('class="mf-cap">Both drops') < plain.index('class="mf-foot"')

    thumb = render_html_fragment(exp, interactive=False, responsive=False)
    assert thumb.count('<div class="mf-v mf-v') == 1 and "@container" not in thumb
    assert 'data-mf-layouts="700"' in thumb and "var(--mf-" in thumb  # still light and dark
    assert "<script" not in thumb and 'class="mf-foot"' not in thumb
