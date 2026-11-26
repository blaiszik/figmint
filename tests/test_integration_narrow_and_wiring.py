"""Integration tests for width='narrow', HTML/terminal wiring, narrative, epistemic audit, and exports."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

import mintfig as mint
import mintfig.explainer as explainer_mod


def _sample_two_panel(*, width: str | float = "chat", style: str = "mintfig") -> mint.Explanation:
    return mint.explain(
        "Checkout p99 is 4x the next slowest service",
        mint.compare(
            {"checkout": 1840, "search": 460, "auth": 310, "cart": 240},
            label="p99 latency",
            unit="ms",
            title="Checkout stands alone",
            highlight="checkout",
        ),
        mint.trend(
            [1, 2, 3, 4, 5, 6],
            {
                "checkout": [540, 560, 980, 1400, 1700, 1840],
                "search": [450, 470, 455, 465, 460, 460],
            },
            label="p99 latency",
            unit="ms",
            x_label="Week",
            title="Regressed after week 2",
            highlight="checkout",
        ),
        subtitle="API latency across core services",
        source="synthetic telemetry",
        width=width,
        style=style,
    )


def test_narrow_spec_and_auto_stack_legibility(tmp_path: Path) -> None:
    spec = mint.pub.get_spec("screen")
    assert spec.resolve_width_mm("narrow") == 92.0

    fig = _sample_two_panel(width="narrow")
    assert fig.width_mm == 92.0
    assert fig.display_width_px == 450
    assert fig.layout == [["a"], ["b"]]
    assert fig.min_text_px >= 11.0
    assert fig.ok is True
    assert fig.ship is True
    assert fig.issues == []

    summary = fig.save(tmp_path / "narrow.png")
    assert summary["display"]["width_px"] == 450
    assert summary["display"]["min_text_px"] >= 11.0
    assert summary["size_px"] is not None
    # 450 px * scale=2.0 = 900 px wide (within rounding)
    assert abs(summary["size_px"][0] - 900) <= 4

    rebuilt = mint.load(tmp_path / "narrow.png")
    assert rebuilt.to_spec()["width"] == "narrow"
    assert rebuilt.layout == [["a"], ["b"]]
    assert rebuilt.display_width_px == 450


def test_narrow_auto_stacks_three_panels_and_respects_explicit_layout() -> None:
    p1 = mint.compare({"a": 10, "b": 4}, label="Score", unit="%", title="Panel A")
    p2 = mint.compare({"c": 8, "d": 2}, label="Score", unit="%", title="Panel B")
    p3 = mint.compare({"e": 9, "f": 5}, label="Score", unit="%", title="Panel C")

    stacked = mint.explain("Panel A leads with 10% across all checks", p1, p2, p3, width="narrow")
    assert stacked.layout == [["a"], ["b"], ["c"]]
    assert stacked.min_text_px >= 11.0

    explicit = mint.explain(
        "Panel A leads with 10% across two groups",
        p1,
        p2,
        layout=[["a", "b"]],
        width="narrow",
    )
    assert explicit.layout == [["a", "b"]]


def test_explanation_save_html_and_repr_html(tmp_path: Path) -> None:
    fig = _sample_two_panel()
    html_path = tmp_path / "review.html"
    summary = fig.save(html_path, write_spec=True)

    assert html_path.exists()
    assert (tmp_path / "review.json").exists()
    assert summary["rendered"] is True
    assert summary["path"] == str(html_path.resolve())
    assert summary["size_px"] is None
    assert summary["ok"] is True

    content = html_path.read_text(encoding="utf-8")
    assert "<!DOCTYPE html>" in content
    assert "<svg" in content
    assert "Checkout p99 is 4x the next slowest service" in content

    htm_path = tmp_path / "review.htm"
    summary_htm = fig.save(htm_path)
    assert htm_path.exists()
    assert summary_htm["rendered"] is True

    static_html = fig.to_html(interactive=False)
    assert "<!DOCTYPE html>" in static_html
    assert "<svg" in static_html

    frag = fig._repr_html_()
    assert "<!DOCTYPE html>" not in frag
    assert "<svg" in frag


def test_explanation_to_terminal() -> None:
    fig = _sample_two_panel()
    uni = fig.to_terminal(width=78, color=False, ascii_only=False)
    assert "Checkout p99 is 4x the next slowest service" in uni
    assert "checkout" in uni

    asc = fig.to_terminal(width=78, color=False, ascii_only=True)
    assert asc.isascii()
    assert "checkout" in asc


def test_summary_includes_four_level_narrative() -> None:
    fig = _sample_two_panel()
    summary = fig.summary()
    assert "narrative" in summary
    nar = summary["narrative"]
    assert set(nar.keys()) >= {"L1", "L2", "L3", "L4", "summary"}
    assert "compare" in nar["L1"] and "trend" in nar["L1"]
    assert isinstance(nar["L2"], list) and nar["L2"]
    assert isinstance(nar["L3"], list) and nar["L3"]
    assert "Checkout p99 is 4x the next slowest service" in nar["L4"]
    assert "Checkout p99 is 4x the next slowest service" in nar["summary"]
    # Serializes cleanly to JSON
    encoded = json.dumps(summary)
    assert '"narrative"' in encoded


def test_epistemic_audit_wired_into_explain_as_advisory() -> None:
    # 1) Overclaiming with overlapping CIs triggers advisory warning without blocking ship
    fig_over = mint.explain(
        "Model A clearly outperforms Model B at 82%",
        mint.compare(
            {"Model A": 82, "Model B": 79},
            error={"Model A": (77, 87), "Model B": (74, 84)},
            error_label="95% CI",
            label="Accuracy",
            unit="%",
            title="Intervals overlap",
            highlight="Model A",
        ),
    )
    rules_over = [i["rule"] for i in fig_over.issues]
    assert "claim_overstates_uncertainty" in rules_over
    assert all(
        i["severity"] == "warning"
        for i in fig_over.issues
        if i["rule"] == "claim_overstates_uncertainty"
    )
    assert fig_over.ok is True
    assert fig_over.ship is True

    # In lenient mode, advisory epistemic warnings move to summary["advisories"]
    fig_lenient = mint.explain(
        "Model A clearly outperforms Model B at 82%",
        mint.compare(
            {"Model A": 82, "Model B": 79},
            error={"Model A": (77, 87), "Model B": (74, 84)},
            error_label="95% CI",
            label="Accuracy",
            unit="%",
            title="Intervals overlap",
            highlight="Model A",
        ),
        strict=False,
    )
    assert fig_lenient.ship is True
    assert any(i["rule"] == "claim_overstates_uncertainty" for i in fig_lenient.advisories)

    # 2) Blatant number mismatch emits advisory claim_number_mismatch
    fig_mis = mint.explain(
        "Latency dropped 50% after the update",
        mint.compare(
            {"Before": 100, "After": 92},
            label="Latency",
            unit="ms",
            title="Only an 8% drop",
            highlight="After",
        ),
    )
    assert "claim_number_mismatch" in [i["rule"] for i in fig_mis.issues]
    assert fig_mis.ship is True


def test_public_exports_on_package_and_explainer() -> None:
    expected = {
        "render_html": mint.interactive,
        "render_terminal": mint.terminal,
        "show_in_terminal": mint.terminal,
        "build_narrative": mint.audit,
        "audit_epistemic": mint.audit,
    }
    for name, home in expected.items():
        assert hasattr(home, name), f"{home.__name__} missing export {name}"
        assert hasattr(explainer_mod, name), f"mintfig.explainer missing export {name}"
        assert name in explainer_mod.__all__
        assert getattr(home, name) is getattr(explainer_mod, name)


def test_narrow_with_new_visual_science_forms() -> None:
    rng = np.random.default_rng(7)
    fig = mint.explain(
        "Treated samples beat control by +9 points with 90% above target",
        mint.distribution(
            {
                "treated": rng.normal(62, 6, 40),
                "control": rng.normal(53, 6, 40),
            },
            mode="quantile",
            quantiles=20,
            baseline="control",
            reference=(52, "target"),
            highlight="treated",
            label="Score",
            unit="%",
            title="Quantile dotplot (5% per dot)",
        ),
        mint.compare(
            {"treated": 62.0, "control": 53.0},
            error={"treated": 3.5, "control": 3.2},
            inner_error={"treated": 1.7, "control": 1.5},
            error_label="50% / 95% CI",
            baseline="control",
            show_delta=True,
            highlight="treated",
            label="Mean score",
            unit="%",
            title="Nested intervals with inline delta",
        ),
        width="narrow",
        source="synthetic study",
    )
    assert fig.layout == [["a"], ["b"]]
    assert fig.min_text_px >= 11.0
    assert fig.ship is True
    assert fig.issues == []
