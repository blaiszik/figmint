"""Small multiples on compare, distribution, histogram and relate, and ``scales_differ``."""

from __future__ import annotations

import numpy as np
import pytest
from matplotlib.colors import to_rgb
from matplotlib.patches import Rectangle

import mintfig as mint
from mintfig._explain.marks import MARKS_ATTR
from mintfig.interactive import _render_svg
from mintfig.terminal import audit_text_surface

NESTED = {
    "Reasoning": {"model A": 71.2, "model B": 64.8, "model C": 58.3},
    "Coding": {"model A": 62.5, "model B": 66.1, "model C": 49.7},
    "Math": {"model A": 80.4, "model B": 74.9, "model C": 61.0},
    "Long context": {"model A": 55.0, "model B": 52.3, "model C": 57.8},
}


def _facets(fig: mint.Explanation) -> list:
    return [ax for ax in fig.fig.axes if ax.get_title(loc="left")]


def _records(fig: mint.Explanation) -> list[dict]:
    out = []
    for artist in fig.fig.findobj(lambda a: bool(getattr(a, MARKS_ATTR, None))):
        out.extend(rec for _xy, rec in getattr(artist, MARKS_ATTR))
    return out


def _check(fig: mint.Explanation) -> None:
    assert fig.ok and fig.ship, fig.issues
    assert fig.min_text_px >= 11.0
    assert audit_text_surface(fig) == []
    again = mint.load(fig.to_spec())
    assert again.to_spec() == fig.to_spec()
    assert [p.facts for p in again.panels.values()] == [p.facts for p in fig.panels.values()]


def test_compare_facets_share_one_axis_and_keep_items_in_order() -> None:
    fig = mint.explain(
        "Model A leads three of four benchmarks; model C wins long context",
        mint.compare(NESTED, facet=True, label="Accuracy", unit="%"),
    )
    _check(fig)
    facets = _facets(fig)
    assert [ax.get_title(loc="left") for ax in facets] == list(NESTED)
    assert len({tuple(np.round(ax.get_xlim(), 6)) for ax in facets}) == 1
    for ax in facets:
        assert [t.label1.get_text() for t in ax.yaxis.get_major_ticks()] == ["model A", "model B", "model C"]
        assert len([t for t in ax.texts if t.get_text()]) == 3  # every value labelled
    facts = fig.panels["a"].facts
    assert facts[0].startswith("ranking differs from the usual (model A > model B > model C)")
    assert any(f.startswith("Coding: highest model B 66.1%") for f in facts)
    names = {(r["name"], r["x"]) for r in _records(fig)}
    assert ("model C", "Long context") in names and len(names) == 12
    text = fig.to_text()
    for cat in NESTED:
        assert f"  {cat}" in text


def test_compare_facets_with_intervals_from_tidy_rows() -> None:
    rows = [
        {"bench": c, "model": m, "acc": v, "ci": 2.0}
        for c, per in NESTED.items()
        for m, v in per.items()
    ]
    fig = mint.explain(
        "Model A leads three of four benchmarks; model C wins long context",
        mint.compare(rows, name="bench", group="model", value="acc", facet=True,
                     error="ci", error_label="95% CI", label="Accuracy", unit="%"),
    )
    _check(fig)
    assert "Reasoning: highest model A 71.2% (69.2–73.2%)" in fig.panels["a"].facts[1]
    assert "intervals: 95% CI" in fig.to_text()


@pytest.mark.parametrize(
    ("kwargs", "needle"),
    [
        ({"values": {"a": 1.0, "b": 2.0}}, "nested values"),
        ({"values": NESTED, "boost": {"model A": 1.0}}, "boost"),
        ({"values": NESTED, "error": {"model A": 1.0}}, "shaped like values"),
        ({"values": {f"c{i}": {"x": 1.0, "y": 2.0} for i in range(13)}}, "13 categories"),
    ],
)
def test_compare_facet_misuse_names_the_limit(kwargs: dict, needle: str) -> None:
    values = kwargs.pop("values")
    with pytest.raises(mint.ExplainError) as err:
        mint.compare(values, facet=True, **kwargs)
    assert needle in str(err.value) and err.value.fix_hint


def test_compare_facets_trim_to_twelve_when_lenient() -> None:
    many = {f"bench {i}": {"x": float(i), "y": float(i + 1)} for i in range(14)}
    with mint.lenient():
        fig = mint.explain("Model y beats model x on all fourteen benchmarks",
                           mint.compare(many, facet=True, label="Score", unit="pts"), strict=False)
    assert len(_facets(fig)) == 12
    assert any("trimmed 14 facets to first 12" in a for a in fig.adjustments)


def test_distribution_facets_from_rows_and_nested_mapping() -> None:
    rng = np.random.default_rng(3)
    rows = [
        {"site": site, "arm": arm, "score": float(v)}
        for site, shift in (("Site A", 0.0), ("Site B", 0.8), ("Site C", -0.4))
        for arm, eff in (("control", 0.0), ("treated", 1.1))
        for v in rng.normal(5 + shift + eff, 0.9, 20)
    ]
    panel = mint.distribution(rows, group="arm", value="score", facet="site",
                              label="Score", unit="points", highlight="treated")
    fig = mint.explain("Treatment raises the score at every site, by about one point", panel)
    _check(fig)
    facets = _facets(fig)
    assert [ax.get_title(loc="left") for ax in facets] == ["Site A", "Site B", "Site C"]
    assert len({tuple(np.round(ax.get_xlim(), 6)) for ax in facets}) == 1
    assert panel.facts[0] == "same order of medians (highest first) in all 3 facets: treated > control"
    nested = panel.spec["groups"]
    again = mint.distribution(nested, facet=True, label="Score", unit="points", highlight="treated")
    assert again.facts == panel.facts
    with pytest.raises(mint.ExplainError, match="names a column"):
        mint.distribution(nested, facet="site")
    with pytest.raises(mint.ExplainError, match="quantile"):
        mint.distribution(nested, facet=True, mode="quantile")


def test_histogram_facets_share_bins_and_count_axis() -> None:
    rng = np.random.default_rng(1)
    groups = {f"group {i + 1}": rng.lognormal(3 + 0.15 * i, 0.4, 120) for i in range(6)}
    fig = mint.explain("Latency shifts right from group 1 to group 6",
                       mint.histogram(groups, facet=True, label="Latency", unit="ms"))
    _check(fig)
    facets = _facets(fig)
    assert len(facets) == 6
    assert len({tuple(np.round(ax.get_xlim(), 6)) for ax in facets}) == 1
    assert len({tuple(np.round(ax.get_ylim(), 6)) for ax in facets}) == 1
    widths = {round(p.get_width(), 9) for ax in facets for p in ax.patches}
    assert len(widths) == 1  # the same bins in every facet
    assert fig.panels["a"].facts[0].startswith("median highest in group 6")
    # Without facet= three groups still stack as before.
    stacked = mint.histogram({k: groups[k] for k in list(groups)[:3]}, label="Latency", unit="ms")
    assert "facet" not in stacked.spec
    with pytest.raises(mint.ExplainError, match="2-12"):
        mint.histogram({"only": groups["group 1"]}, facet=True)


def _relate_data(n_groups: int) -> tuple[list[float], list[float], list[str]]:
    rng = np.random.default_rng(7)
    xs, ys, gs = [], [], []
    for i in range(n_groups):
        x = rng.uniform(0, 10, 15)
        xs += list(x)
        ys += list(5 + (1.5 - 0.4 * i) * x + rng.normal(0, 1.5, x.size))
        gs += [f"line {i + 1}"] * x.size
    return xs, ys, gs


def test_relate_facets_fit_each_group_on_shared_axes() -> None:
    xs, ys, gs = _relate_data(6)
    fig = mint.explain(
        "Response rises with dose in lines 1 to 3 and falls in lines 5 and 6",
        mint.relate(xs, ys, groups=gs, facet=True, fit=True, x_label="Dose (mg)",
                    y_label="Response", unit="AU"),
    )
    _check(fig)
    facets = _facets(fig)
    assert len(facets) == 6
    assert len({(tuple(np.round(ax.get_xlim(), 6)), tuple(np.round(ax.get_ylim(), 6))) for ax in facets}) == 1
    assert all(len([ln for ln in ax.lines if ln.get_label() == "_fit"]) == 1 for ax in facets)
    assert all(len(ax.collections) == 2 for ax in facets)  # grey context, then the group
    assert "the fitted slope is positive in" in fig.panels["a"].facts[0]


def test_relate_facet_limits() -> None:
    xs, ys, gs = _relate_data(13)
    with pytest.raises(mint.ExplainError, match="13 groups"):
        mint.relate(xs, ys, groups=gs, facet=True, x_label="Dose", y_label="Response")
    with mint.lenient():
        panel = mint.relate(xs, ys, groups=gs, facet=True, x_label="Dose", y_label="Response")
    assert len(set(panel.spec["groups"])) == 12
    with pytest.raises(mint.ExplainError, match="label_all"):
        mint.relate(xs, ys, groups=gs[:], names=[str(i) for i in range(len(xs))],
                    facet=True, label_all=True, x_label="Dose", y_label="Response")
    with pytest.raises(mint.ExplainError, match="groups="):
        mint.relate(xs, ys, facet=True, x_label="Dose", y_label="Response")


def test_facet_colours_follow_the_figure_registry() -> None:
    fig = mint.explain(
        "Model A leads three of four benchmarks and improves fastest",
        mint.compare(NESTED, facet=True, label="Accuracy", unit="%"),
        mint.trend([1, 2, 3], {"model A": [50, 60, 71], "model B": [55, 60, 65]},
                   label="Accuracy over training", unit="%"),
    )
    bar = next(
        p for p in fig.fig.findobj(Rectangle)
        if (getattr(p, MARKS_ATTR, None) or [(None, {})])[0][1].get("name") == "model A"
    )
    line = next(ln for ax in fig.fig.axes for ln in ax.lines if ln.get_label() == "model A")
    assert np.allclose(bar.get_facecolor()[:3], to_rgb(line.get_color()))


def test_scales_differ_is_advice_only() -> None:
    x = [1, 2, 3, 4]
    fig = mint.explain(
        "Latency rose in both regions after the deploy",
        mint.trend(x, {"east": [100, 120, 180, 240]}, label="p99", unit="ms"),
        mint.trend(x, {"west": [300, 310, 420, 520]}, label="p99", unit="ms"),
    )
    hits = [i for i in fig.issues if i["rule"] == "scales_differ"]
    assert len(hits) == 1 and hits[0]["severity"] == "warning"
    assert "Panels a and b" in hits[0]["message"] and "facet" in hits[0]["fix_hint"]
    assert fig.ship
    logged = mint.explain(
        "Latency rose in both regions after the deploy",
        mint.trend(x, {"east": [100, 120, 180, 240]}, label="p99", unit="ms"),
        mint.trend(x, {"west": [100, 120, 180, 240]}, label="p99", unit="ms", log=True),
    )
    assert any("log axis" in i["message"] for i in logged.issues if i["rule"] == "scales_differ")
    same = mint.explain(
        "Latency rose in both regions after the deploy",
        mint.trend(x, {"east": [100, 120, 180, 240]}, label="p99", unit="ms"),
        mint.trend(x, {"west": [100, 120, 180, 240]}, label="p99", unit="ms"),
        mint.trend(x, {"west": [1, 2, 3, 4]}, label="errors", unit="%"),
    )
    assert not [i for i in same.issues if i["rule"] == "scales_differ"]
    # Labelled bars hide their axis: measured against other bars, not against a line.
    bars_line = mint.explain(
        "Latency rose in both regions after the deploy",
        mint.compare({"east": 240, "west": 520}, label="p99", unit="ms"),
        mint.trend(x, {"west": [300, 310, 420, 520]}, label="p99", unit="ms"),
    )
    assert not [i for i in bars_line.issues if i["rule"] == "scales_differ"]
    two_bars = mint.explain(
        "Latency rose in both regions after the deploy",
        mint.compare({"east": 240, "west": 520}, label="p99", unit="ms"),
        mint.compare({"north": 90, "south": 130}, label="p99", unit="ms"),
    )
    assert [i["rule"] for i in two_bars.issues].count("scales_differ") == 1


def test_faceted_panels_keep_html_marks() -> None:
    fig = mint.explain(
        "Model A leads three of four benchmarks; model C wins long context",
        mint.compare(NESTED, facet=True, label="Accuracy", unit="%"),
    )
    _svg, marks = _render_svg(fig)
    own = [m for m in marks.values() if m["panel"] == "a"]
    assert len(own) == 12 and {m["x"] for m in own} == set(NESTED)
