"""Density: ``explain(density="compact")``, the ``low_density`` advisory, and trend banking."""

from __future__ import annotations

import json

import matplotlib
import pytest

matplotlib.use("Agg")

import mintfig as mint
from mintfig._explain.core import MIN_TEXT_PX, _Measure, _Sizes
from mintfig.specs import get_spec

SERVICES = {"checkout": 1840, "search": 460, "auth": 310, "catalog": 280}
TAKEAWAY = "Checkout is 4x slower than the next service at p99"


def _four_bars(**kw: object) -> mint.Explanation:
    return mint.explain(
        TAKEAWAY,
        mint.compare(SERVICES, label="p99 latency", unit="ms", highlight="checkout"),
        **kw,
    )


def test_compact_four_bars_fit_in_190_px_and_keep_text_readable() -> None:
    regular, compact = _four_bars(), _four_bars(density="compact")
    tall = regular.summary()["display"]["height_px"]
    short = compact.summary()["display"]["height_px"]
    assert short <= 190 < tall
    assert compact.min_text_px >= MIN_TEXT_PX and compact.ship and compact.issues == []


def test_density_round_trips_and_is_checked() -> None:
    spec = _four_bars(density="compact").to_spec()
    assert spec["density"] == "compact"
    assert "density" not in _four_bars().to_spec()
    again = mint.load(json.loads(json.dumps(spec)))
    assert again.density == "compact" and again.to_spec() == spec
    with pytest.raises(mint.ExplainError, match="density"):
        _four_bars(density="dense")
    with mint.lenient():
        assert _four_bars(density="dense").density == "regular"


def test_low_density_warns_on_a_tall_sparse_figure_without_blocking_ship() -> None:
    sparse = mint.explain(
        "Math rose 30 points while reading and code held",
        mint.change({"math": 10, "code": 30, "reading": 55},
                    {"math": 40, "code": 28, "reading": 60}, unit="%", label="Pass rate",
                    highlight="math"),
        subtitle="Pass rate before and after the curriculum change, three subjects",
        note="One cohort; the other subjects are within a point of last term.",
        source="synthetic",
    )
    assert not [i for i in sparse.issues if i["rule"] == "low_density"]  # advisory, not an issue
    low = [i for i in sparse.advisories if i["rule"] == "low_density"]
    assert sparse.summary()["display"]["height_px"] > 320
    assert len(low) == 1 and low[0]["severity"] == "warning"
    assert 'density="compact"' in low[0]["fix_hint"] and "mint.table" in low[0]["fix_hint"]
    assert sparse.ship
    assert sparse.summary()["advisories"] == low
    # a distribution's observations count one by one
    many = mint.explain(
        "After the change most runs finish within the 40 ms SLO",
        mint.distribution({"before": [41, 44, 39, 47, 52, 45], "after": [33, 36, 38, 35, 41, 34]},
                          unit="ms", label="Latency", highlight="after"),
        subtitle="Six runs each", note="Synthetic.", source="synthetic",
    )
    assert not [i for i in many.advisories if i["rule"] == "low_density"]
    assert "advisories" not in many.summary()  # the key appears only when there is one


def _trend_height(series: dict[str, list[float]], **kw: object) -> float:
    panel = mint.trend(list(range(len(next(iter(series.values()))))), series, label="y", **kw)
    sizes = _Sizes.from_spec(get_spec("screen"))
    return panel._height_mm(132.0, _Measure(), sizes, mint.themes.MINTFIG_THEME)


def test_trend_is_banked_within_its_bounds() -> None:
    natural = min(54.0, max(36.0, 0.40 * 132.0))
    flat_noise = _trend_height({"s": [5, 5.1, 5, 5.2, 5.1, 5, 5.1, 5.2]})
    curve = _trend_height({"s": [i * i for i in range(8)]})
    steady = _trend_height({"s": [10, 14, 19, 23, 28, 31, 36, 40]})
    for h in (flat_noise, curve, steady):
        assert 0.8 * natural - 1e-6 <= h <= 1.15 * natural + 1e-6
    assert flat_noise < steady  # jagged segments are steep: a shorter plot banks them
    # small multiples (one row of four here) share one banked height, within the same bounds
    facets = {f"s{i}": [i + v * v for v in range(6)] for i in range(4)}
    assert 0.8 * 27.0 - 1e-6 <= _trend_height(facets, facet=True) <= 1.15 * 27.0 + 1e-6
