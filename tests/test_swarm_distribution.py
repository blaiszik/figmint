"""Tests for deterministic beeswarm (mode="swarm") and tabular right-aligned readouts on distribution()."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pytest
from matplotlib.collections import LineCollection, PathCollection

import mintfig as mint
from mintfig import ExplainError
from mintfig._explain.distribution import _beeswarm_pack
from mintfig.audit import audit_figure


def _latency_groups(n: int = 65) -> dict[str, list[float]]:
    rng = np.random.default_rng(17)
    return {
        "before": np.round(rng.lognormal(mean=6.15, sigma=0.22, size=n), 1).tolist(),
        "after": np.round(rng.lognormal(mean=7.12, sigma=0.45, size=n), 1).tolist(),
    }


def _rendered_offsets_pt(exp: mint.Explanation, key: str = "a") -> list[tuple[np.ndarray, float]]:
    """Return ``(xy_pt, diameter_pt)`` for every scatter PathCollection on ``exp[key]``."""
    ax = exp[key]
    fig = exp.fig
    pt_per_px = 72.0 / float(fig.dpi)
    out: list[tuple[np.ndarray, float]] = []
    for coll in ax.collections:
        if isinstance(coll, PathCollection):
            data_xy = np.asarray(coll.get_offsets(), dtype=float)
            disp_px = ax.transData.transform(data_xy)
            disp_pt = disp_px * pt_per_px
            sizes = np.asarray(coll.get_sizes(), dtype=float)
            d_pt = float(np.sqrt(sizes[0])) if sizes.size else 0.0
            out.append((disp_pt, d_pt))
    return out


def _min_pairwise_distance(xy_pt: np.ndarray) -> float:
    if xy_pt.shape[0] < 2:
        return float("inf")
    diff = xy_pt[:, None, :] - xy_pt[None, :, :]
    dist = np.hypot(diff[:, :, 0], diff[:, :, 1])
    np.fill_diagonal(dist, np.inf)
    return float(dist.min())


def test_beeswarm_pack_helper_exact_symmetry_and_zero_overlap() -> None:
    # Identical values pack symmetrically around 0 with exact separation.
    tied = np.full(9, 40.0)
    v_tied = _beeswarm_pack(tied, 5.0)
    assert v_tied[0] == pytest.approx(0.0)
    assert np.mean(v_tied) == pytest.approx(0.0, abs=1e-4)
    xy_tied = np.column_stack([tied, v_tied])
    assert _min_pairwise_distance(xy_tied) >= 5.0 - 1e-6

    # Gaussian cluster packs deterministically with zero pairwise overlap.
    rng = np.random.default_rng(4)
    u = rng.normal(120.0, 28.0, size=100)
    v1 = _beeswarm_pack(u, 4.0)
    v2 = _beeswarm_pack(u, 4.0)
    assert np.array_equal(v1, v2)
    assert _min_pairwise_distance(np.column_stack([u, v1])) >= 4.0 - 1e-6


def test_swarm_determinism_zero_overlap_and_summary_overlay(tmp_path: Path) -> None:
    groups = {
        "control": [42, 45, 44, 47, 46, 48, 43, 45, 46, 49, 44, 46, 47, 45, 48, 46, 45, 44, 47, 46],
        "variant A": [51, 54, 52, 56, 55, 53, 54, 57, 52, 55, 54, 53, 56, 55, 54, 58, 53, 55, 54, 56],
        "variant B": [60, 62, 61, 64, 63, 65, 62, 64, 63, 66, 61, 63, 64, 62, 65, 63, 64, 62, 63, 67],
    }

    def _build() -> mint.Explanation:
        return mint.explain(
            "Variant B raises throughput without overlapping control",
            mint.distribution(
                groups,
                mode="swarm",
                label="Throughput",
                unit="req/s",
                baseline="control",
                highlight="variant B",
                reference=(58.0, "target"),
            ),
            source="synthetic benchmark",
        )

    exp1 = _build()
    exp2 = _build()
    try:
        assert exp1.ship is True
        assert exp1.issues == []
        assert exp1.panels["a"].spec["mode"] == "swarm"
        assert "Beeswarm" in exp1.panels["a"].describe

        # Existing facts (medians, superiority, reference exceedance) all present.
        joined = "\n".join(exp1.panels["a"].facts)
        assert "P(variant B > control) = 100%" in joined
        assert "above 58 req/s (target)" in joined

        # Audit confirms zero overlaps / text faults / struck text.
        with exp1.theme.rc_context(exp1.spec):
            aud = audit_figure(exp1.fig)
        assert aud["overlaps"] == []
        assert aud["struck"] == []
        assert aud["text_faults"] == []

        # Bit-for-bit deterministic coordinates across independent runs.
        scatters1 = [c for c in exp1["a"].collections if isinstance(c, PathCollection)]
        scatters2 = [c for c in exp2["a"].collections if isinstance(c, PathCollection)]
        assert len(scatters1) == len(groups)
        for s1, s2, (nm, vals) in zip(scatters1, scatters2, groups.items(), strict=True):
            off1 = np.asarray(s1.get_offsets(), dtype=float)
            off2 = np.asarray(s2.get_offsets(), dtype=float)
            assert np.array_equal(off1, off2), f"Non-deterministic swarm for {nm}"
            # Exact x values preserved (no horizontal jitter).
            assert np.allclose(off1[:, 0], np.asarray(vals, dtype=float))

        # Zero pairwise dot overlap in rendered display points & strict lane containment.
        rendered = _rendered_offsets_pt(exp1, "a")
        for row, ((xy_pt, d_pt), sc) in enumerate(zip(rendered, scatters1, strict=True)):
            min_d = _min_pairwise_distance(xy_pt)
            assert min_d >= d_pt * 0.99, f"Row {row} overlap: min_d={min_d:.2f} < d_pt={d_pt:.2f}"
            ys_data = np.asarray(sc.get_offsets(), dtype=float)[:, 1]
            assert ys_data.min() >= row - 0.45 and ys_data.max() <= row + 0.45

        # Haloed median ticks (3) and IQR lines (3, since every group has n >= 5) on top.
        lines = [c for c in exp1["a"].collections if isinstance(c, LineCollection)]
        horizontal = [c for c in lines if np.ptp(c.get_segments()[0][:, 1]) == 0]
        vertical = [c for c in lines if np.ptp(c.get_segments()[0][:, 0]) == 0]
        assert len(horizontal) == 3
        assert len(vertical) == 3

        # PNG & dict round-trip via mint.load(), plus text/html surfaces.
        png = tmp_path / "swarm.png"
        summary = exp1.save(png)
        assert summary["ship"] is True
        assert summary["issues"] == []
        assert "variant B" in exp1.to_text()
        assert "variant B" in exp1.to_html()

        from_dict = mint.load(exp1.to_spec())
        from_png = mint.load(png)
        try:
            for reloaded in (from_dict, from_png):
                assert reloaded.ship is True
                assert reloaded.issues == []
                assert reloaded.panels["a"].spec["mode"] == "swarm"
                sc_r = [c for c in reloaded["a"].collections if isinstance(c, PathCollection)]
                for orig, rel in zip(scatters1, sc_r, strict=True):
                    assert np.allclose(orig.get_offsets(), rel.get_offsets())
        finally:
            plt.close(from_dict.fig)
            plt.close(from_png.fig)
    finally:
        plt.close(exp1.fig)
        plt.close(exp2.fig)


def test_swarm_log_scale_and_mean_stat() -> None:
    groups = _latency_groups(n=55)
    exp = mint.explain(
        "Request latency tripled after deploy with a heavier upper tail",
        mint.distribution(
            groups,
            mode="swarm",
            log=True,
            stat="mean",
            baseline="before",
            highlight="after",
            reference=(1000.0, "1s SLO"),
            label="Request time",
            unit="ms",
        ),
        source="synthetic telemetry",
    )
    try:
        assert exp.ship is True
        assert exp.issues == []
        assert exp["a"].get_xscale() == "log"
        rendered = _rendered_offsets_pt(exp, "a")
        for row, (xy_pt, d_pt) in enumerate(rendered):
            min_d = _min_pairwise_distance(xy_pt)
            assert min_d >= d_pt * 0.99, f"Log swarm row {row} overlap: {min_d:.2f} < {d_pt:.2f}"
    finally:
        plt.close(exp.fig)


def test_swarm_large_n_and_constant_spike_stay_in_lane() -> None:
    rng = np.random.default_rng(99)
    large_groups = {
        "fast": rng.normal(42.0, 5.0, size=220).tolist(),
        "medium": rng.normal(58.0, 7.5, size=220).tolist(),
        "slow": rng.normal(75.0, 9.0, size=220).tolist(),
    }
    exp_large = mint.explain(
        "Large cohorts keep distinct beeswarm lanes without colliding",
        mint.distribution(
            large_groups,
            mode="swarm",
            label="Latency",
            unit="ms",
            highlight="fast",
        ),
        source="synthetic benchmark",
    )
    try:
        assert exp_large.ship is True
        assert exp_large.issues == []
        scatters = [c for c in exp_large["a"].collections if isinstance(c, PathCollection)]
        assert len(scatters) == 3
        for row, sc in enumerate(scatters):
            ys = np.asarray(sc.get_offsets(), dtype=float)[:, 1]
            assert ys.size == 220
            assert ys.min() >= row - 0.45 and ys.max() <= row + 0.45
    finally:
        plt.close(exp_large.fig)

    # Degenerate spike of 60 identical observations softly clamps inside its lane.
    exp_spike = mint.explain(
        "Identical observations clamp safely inside the row lane",
        mint.distribution(
            {"constant": [10.0] * 60, "spread": np.linspace(8.0, 12.0, 40).tolist()},
            mode="swarm",
            label="Score",
        ),
        source="synthetic",
    )
    try:
        assert exp_spike.ship is True
        assert exp_spike.issues == []
        scatters = [c for c in exp_spike["a"].collections if isinstance(c, PathCollection)]
        for row, sc in enumerate(scatters):
            ys = np.asarray(sc.get_offsets(), dtype=float)[:, 1]
            assert ys.min() >= row - 0.45 and ys.max() <= row + 0.45
    finally:
        plt.close(exp_spike.fig)


def test_swarm_single_unnamed_series_and_validation_errors() -> None:
    rng = np.random.default_rng(3)
    exp = mint.explain(
        "Single unnamed distribution renders cleanly as a beeswarm",
        mint.distribution(rng.normal(25.0, 4.0, size=35).tolist(), mode="swarm", label="Score", unit="pts"),
        source="synthetic",
    )
    try:
        assert exp.ship is True
        assert exp.issues == []
    finally:
        plt.close(exp.fig)

    vals = {"a": [1.0, 2.0, 3.0, 4.0, 5.0]}
    with pytest.raises(ExplainError, match="bins"):
        mint.distribution(vals, mode="swarm", bins="auto")
    with pytest.raises(ExplainError, match="facet"):
        mint.distribution({"f1": vals, "f2": vals}, mode="swarm", facet=True)


@pytest.mark.parametrize("mode", ["dots", "swarm", "quantile"])
@pytest.mark.parametrize("unit", ["ms", "%", None])
def test_distribution_readout_column_is_right_aligned_on_shared_rail(
    mode: str, unit: str | None
) -> None:
    groups = _latency_groups(n=45)
    exp = mint.explain(
        "After deploy median latency rises sharply above baseline",
        mint.distribution(
            groups,
            mode=mode,
            label="Request time",
            unit=unit,
            highlight="after",
            baseline="before",
        ),
        source="synthetic telemetry",
    )
    try:
        assert exp.ship is True
        assert exp.issues == []
        ax = exp["a"]
        renderer = exp.fig.canvas.get_renderer()
        frame = ax.get_window_extent(renderer)

        # Collect header ("median") and all right-column readout annotations.
        right_texts = [
            t
            for t in ax.texts
            if t.get_visible()
            and t.get_text().strip()
            and t.get_window_extent(renderer).x0 >= frame.x1 - 1.0
        ]
        assert len(right_texts) == 3, [t.get_text() for t in right_texts]
        assert any(t.get_text() == "median" for t in right_texts)

        for t in right_texts:
            assert t.get_horizontalalignment() == "right", (
                f"Expected ha='right' for {t.get_text()!r}, got {t.get_horizontalalignment()!r}"
            )

        right_edges = [t.get_window_extent(renderer).x1 for t in right_texts]
        assert max(right_edges) - min(right_edges) <= 2.0, (
            f"Right rail ragged across {[t.get_text() for t in right_texts]}: {right_edges}"
        )

        # Ensure every readout stays inside canvas and has zero text overlaps.
        fig_w = exp.fig.bbox.width
        assert max(right_edges) <= fig_w - 0.5
        with exp.theme.rc_context(exp.spec):
            aud = audit_figure(exp.fig)
        assert aud["overlaps"] == []
    finally:
        plt.close(exp.fig)
