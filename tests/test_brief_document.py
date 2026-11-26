"""mint.brief as a document: prose between figures, overview first, one caption per
figure, facts out of the way, shared-scale advice, page scheme, print and CLI."""

from __future__ import annotations

import html
import json
import re
from pathlib import Path

import pytest

import mintfig as mint
from mintfig.cli import main as cli_main


def _accuracy(takeaway: str, values: dict[str, float], unit: str = "%") -> mint.Explanation:
    return mint.explain(
        takeaway,
        mint.compare(values, label="Accuracy", unit=unit, title="Test accuracy"),
        source="ablation runs",
    )


@pytest.fixture(scope="module")
def figs() -> tuple[mint.Explanation, mint.Explanation, mint.Explanation]:
    f1 = _accuracy("Removing retrieval costs 8 points", {"full": 82.0, "no retrieval": 74.0})
    f2 = mint.explain(
        "The gap opens in the first 500 steps",
        mint.trend([0, 500, 1000], {"full": [2, 78, 82], "no retrieval": [2, 68, 74]},
                   label="Accuracy", unit="%", title="Validation accuracy"),
        source="ablation runs",
    )
    f3 = mint.explain(
        "The full model leads on both benchmarks",
        mint.table([{"Model": "full", "QA": 82.0, "Code": 64.1},
                    {"Model": "no retrieval", "QA": 74.0, "Code": 63.5}],
                   units={"QA": "%", "Code": "%"}, title="Scorecard"),
        source="held-out benchmarks",
    )
    return f1, f2, f3


def _document(figs: tuple[mint.Explanation, ...], **kw: object) -> mint.Brief:
    f1, f2, f3 = figs
    return mint.brief(
        "Ablation <study>",
        "We removed one component at a time & retrained.",
        f1,
        f2,
        "## Beyond the main task",
        "The ranking holds on held-out benchmarks.",
        f3,
        **kw,
    )


def test_markdown_reads_as_a_document(figs: tuple[mint.Explanation, ...], tmp_path: Path) -> None:
    b = _document(figs)
    assert len(b.figures) == 3
    meta = b.save(tmp_path / "brief.md")
    md = (tmp_path / "brief.md").read_text(encoding="utf-8")
    caption = figs[0].summary()["deliver"]["caption"]

    # Overview: numbered takeaways linking to the finding headings.
    assert "1. [Removing retrieval costs 8 points](#removing-retrieval-costs-8-points)" in md
    assert "3. [The full model leads on both benchmarks](#the-full-model-leads-on-both-benchmarks)" in md
    # A finding is heading, image, caption in italics, source; nothing else.
    block = md.split("## Removing retrieval costs 8 points\n", 1)[1].split("\n## ", 1)[0]
    assert block.strip().split("\n\n") == [
        "![Removing retrieval costs 8 points](brief_figures/fig_01.png)",
        f"*{caption}*",
        "Source: ablation runs",
    ]
    assert not re.search(r"^- ", md, re.MULTILINE)  # no fact bullets
    # Prose and section heading stay in place; findings after a section go one level down.
    assert md.index("We removed one component") < md.index("## Removing retrieval")
    assert md.index("## Beyond the main task") < md.index("### The full model leads")
    assert "| Model" in md  # table panels stay
    assert len(meta["assets"]) == 3


def test_html_overview_captions_and_collapsed_numbers(figs: tuple[mint.Explanation, ...]) -> None:
    text = _document(figs).to_html()
    assert "Ablation &lt;study&gt;" in text and "component at a time &amp; retrained" in text
    assert "<script src=" not in text and "<link " not in text and "url(http" not in text
    ids = re.findall(r' id="([^"]+)"', text)
    assert len(ids) == len(set(ids))

    assert "fm-" not in text
    nav = text.split('<nav class="mf-bthumbs"', 1)[1].split("</nav>", 1)[0]
    assert [f'href="#fig-{i}"' in nav for i in (1, 2, 3)] == [True] * 3
    assert '<script' not in nav and 'class="mf-foot"' not in nav and 'class="mf-tip"' not in nav
    assert nav.count('class="mf-tk"') == 3
    # Thumbnails are static, one layout each: no hidden layouts for the page CSS to undo.
    assert nav.count('<div class="mf-v mf-v') == 3 and "mf-v1" not in nav
    assert "last-child" not in text

    finding = text.split('<section id="fig-1"', 1)[1].split("</section>", 1)[0]
    # The heading stays in the outline but is hidden: the figure draws the takeaway.
    assert '<h2 id="fig-1-h" class="mf-sr-only">Removing retrieval costs 8 points</h2>' in finding
    caption = figs[0].summary()["deliver"]["caption"]
    plain = finding.replace("&#x27;", "'")
    assert f'<p class="mf-cap">{caption}</p>' in plain
    # The caption sits under the figure, above its data line; the source is drawn in it.
    assert plain.index('class="mf-stage"') < plain.index('class="mf-cap"') < plain.index('class="mf-foot"')
    assert "mf-bsrc" not in finding
    # The facts appear once: in the numbers block, not again in the figure's data drawer.
    assert "<summary>Numbers behind this figure</summary>" in finding
    numbers = finding.split("<summary>Numbers behind this figure</summary>", 1)[1]
    assert all(html.escape(fact) in numbers for fact in figs[0].panels["a"].facts[:2])
    assert 'class="mf-facts"' not in finding and 'class="mf-data-table"' in finding
    assert '<h3 id="fig-3-h" class="mf-sr-only">' in text  # after the section heading
    assert '<h2 class="mf-bh">Beyond the main task</h2>' in text


def test_page_scheme_and_print(figs: tuple[mint.Explanation, ...]) -> None:
    auto = _document(figs).to_html()
    assert re.search(r'<html lang="en">', auto)  # follows the reader
    assert "@media (prefers-color-scheme:dark){:root{--mf-page-bg:" in auto
    dark = _document(figs, style="dark").to_html()
    assert '<html lang="en" data-mf-scheme="dark">' in dark  # pins the figures too
    assert "color-scheme: dark" in dark and "prefers-color-scheme:dark){:root" not in dark

    print_css = auto.split("@media print{", 1)[1]
    assert ".mf-bpage{break-before:page}" in print_css
    assert "break-inside:avoid" in print_css
    assert ".mf-bnums" in print_css.split("display:none", 1)[0]  # collapsed numbers omitted


def test_scales_differ_advice(figs: tuple[mint.Explanation, ...], tmp_path: Path) -> None:
    log_fig = mint.explain(
        "Accuracy climbs by orders of magnitude",
        mint.trend([1, 2, 3], {"full": [1, 10, 100]}, label="Accuracy", unit="%", log=True),
    )
    other_unit = _accuracy("Same label, other unit", {"full": 0.82, "no retrieval": 0.74}, unit="pts")
    hard_split = _accuracy("Half as accurate on the hard split", {"full": 41.0, "no retrieval": 37.0})
    meta = mint.brief("Scales", figs[0], hard_split, figs[1], log_fig, other_unit).save(
        tmp_path / "s.html"
    )
    pairs = {(tuple(p["figure"] for p in d["panels"]), d["issue"]) for d in meta["scales_differ"]}
    assert ((1, 2), "range") in pairs  # two bar panels, bars of different length per point
    assert ((3, 4), "log_vs_linear") in pairs
    # Labelled bars have no drawn axis, so they are not measured against a line panel.
    assert not any(figs_ in {(1, 3), (2, 3)} for figs_, _ in pairs)
    assert not any(5 in figs_ for figs_, _ in pairs)
    first = meta["scales_differ"][0]
    assert first["label"] == "Accuracy" and first["unit"] == "%" and first["hint"]


def test_items_validation(figs: tuple[mint.Explanation, ...], tmp_path: Path) -> None:
    png = tmp_path / "f1.png"
    figs[0].save(png)
    b = mint.brief("Paths", str(png), "A paragraph that mentions f1.png in passing.", *["note"] * 13)
    assert len(b.figures) == 1  # strings are prose; the limit counts figures only
    with pytest.raises(mint.ExplainError, match="does not exist"):
        mint.brief("Typo", "missing_fig.png")
    with pytest.raises(mint.ExplainError, match="at least one figure"):
        mint.brief("Prose only", "Just words.")
    with pytest.raises(mint.ExplainError, match="13 figures"):
        mint.brief("Too many", *[tmp_path / f"f{i}.png" for i in range(13)])


def test_markdown_wraps_image_paths_with_spaces(figs: tuple[mint.Explanation, ...]) -> None:
    md = mint.brief("Paths", figs[0]).to_markdown(image_paths=["my figs/fig (1).png"])
    assert "![Removing retrieval costs 8 points](<my figs/fig (1).png>)" in md


def test_session_brief_with_prose() -> None:
    s = mint.Session()
    s.explain("Checkout p99 is 4x search", mint.compare({"checkout": 1840, "search": 460}, unit="ms"))
    md = s.brief("Latency", "Traces from one day.").to_markdown()
    assert md.index("Traces from one day.") < md.index("## Checkout p99 is 4x search")


def test_cli_brief_intro(figs: tuple[mint.Explanation, ...], tmp_path: Path,
                         capsys: pytest.CaptureFixture[str]) -> None:
    png1, png2 = tmp_path / "a.png", tmp_path / "b.png"
    figs[0].save(png1)
    _accuracy("Half as accurate on the hard split", {"full": 41.0, "no retrieval": 37.0}).save(png2)
    out = tmp_path / "report.md"
    rc = cli_main(["brief", str(png1), str(png2), "--title", "CLI brief",
                   "--intro", "Why we ran this.", "--out", str(out)])
    assert rc == 0
    meta = json.loads(capsys.readouterr().out)
    assert meta["figure_count"] == 2 and meta["scales_differ"]
    md = out.read_text(encoding="utf-8")
    assert md.index("2. [") < md.index("Why we ran this.") < md.index("## Removing retrieval")
