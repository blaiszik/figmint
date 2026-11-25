"""Tests for epistemic / slant auditing and four-level semantic narratives."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import numpy as np
import pytest

import figmint as fm
from figmint.epistemic import audit_epistemic, build_narrative
from figmint.explainer import _VISUAL_DEFECT_RULES

GALLERY_DIR = Path(__file__).resolve().parent.parent / "gallery"
GALLERY_MODULES = (
    "explain_chat_examples",
    "explain_science_examples",
    "explain_form_gallery",
    "explain_release_examples",
)


def _load_gallery_examples() -> list[tuple[str, Any]]:
    builders: list[tuple[str, Any]] = []
    for mod_name in GALLERY_MODULES:
        path = GALLERY_DIR / f"{mod_name}.py"
        spec = importlib.util.spec_from_file_location(f"_gallery_{mod_name}", path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        examples = module.EXAMPLES
        items = examples.items() if isinstance(examples, dict) else examples
        for name, fn in items:
            builders.append((f"{mod_name}.{name}", fn))
    return builders


# --------------------------------------------------------------------------- #
# Part 1: Four-Level Semantic Narrative (L1 / L2 / L3 / L4 + summary)
# --------------------------------------------------------------------------- #


class TestBuildNarrative:
    def test_compare_and_table_four_levels(self) -> None:
        rows = [
            {"Model": "Alpha-3", "GPQA": 86.4, "Cost": 2.50},
            {"Model": "Alpha-2", "GPQA": 77.1, "Cost": 3.00},
            {"Model": "Beta-Pro", "GPQA": 83.2, "Cost": 6.00},
        ]
        exp = fm.explain(
            "Alpha-3 leads GPQA while costing 17% less than Alpha-2",
            fm.compare(
                rows,
                name="Model",
                value="GPQA",
                label="Accuracy",
                unit="%",
                highlight="Alpha-3",
                baseline="Alpha-2",
            ),
            fm.table(
                rows,
                units={"GPQA": "%", "Cost": "$/M"},
                highlight="Alpha-3",
                baseline="Alpha-2",
            ),
            subtitle="Evaluation suite, Nov 2026",
            source="synthetic benchmark",
        )
        nar = build_narrative(
            exp.takeaway, exp.panels, subtitle=exp.subtitle, source=exp.source
        )
        assert set(nar) == {"L1", "L2", "L3", "L4", "summary"}
        assert nar["L1"] == "2 panels: compare (Accuracy, %); table (Model, GPQA, Cost)"
        assert isinstance(nar["L2"], list) and len(nar["L2"]) >= 3
        assert any("highest: Alpha-3 86.4%" in f for f in nar["L2"])
        assert any("GPQA: highest Alpha-3" in f for f in nar["L2"])
        assert isinstance(nar["L3"], list) and len(nar["L3"]) >= 1
        assert any("rank 1 of 3" in f for f in nar["L3"])
        assert "Alpha-3 leads GPQA" in nar["L4"]
        assert "Evaluation suite, Nov 2026" in nar["L4"]
        assert nar["summary"].startswith(nar["L4"])
        assert "Source: synthetic benchmark." in nar["summary"]

    def test_trend_events_and_crossings_classify_into_l3(self) -> None:
        exp = fm.explain(
            "Checkout regressed after the v2.3 deploy",
            fm.trend(
                list(range(1, 9)),
                {
                    "checkout": [540, 560, 550, 570, 980, 1400, 1700, 1840],
                    "search": [450, 470, 455, 465, 460, 450, 470, 460],
                },
                label="p99 latency",
                unit="ms",
                x_label="Week",
                highlight="checkout",
                events={4: "v2.3 deploy"},
            ),
        )
        nar = build_narrative(exp.takeaway, exp.panels)
        assert nar["L1"] == "1 panel: trend (p99 latency, ms vs Week)"
        assert any("v2.3 deploy" in f for f in nar["L3"])
        assert any("540 ms" in f and "1,840 ms" in f for f in nar["L3"])

    def test_relate_pareto_frontier_and_correlation_in_l3(self) -> None:
        rows = [
            {"model": "M1", "family": "A", "cost": 0.5, "score": 76.0},
            {"model": "M2", "family": "A", "cost": 2.0, "score": 86.0},
            {"model": "M3", "family": "A", "cost": 8.0, "score": 90.0},
            {"model": "N1", "family": "B", "cost": 1.0, "score": 72.0},
            {"model": "N2", "family": "B", "cost": 5.0, "score": 82.0},
        ]
        exp = fm.explain(
            "Family A defines the Pareto frontier across price tiers",
            fm.relate(
                "cost",
                "score",
                data=rows,
                names="model",
                groups="family",
                highlight="A",
                frontier=True,
                log_x=True,
                x_label="Cost ($/M)",
                y_label="Score (%)",
                unit="%",
            ),
        )
        nar = build_narrative(exp.takeaway, exp.panels)
        assert "relate (" in nar["L1"]
        assert "Pareto frontier" in nar["L1"]
        assert "log x" in nar["L1"]
        assert any("Pareto frontier" in f for f in nar["L3"])
        assert any("r =" in f for f in nar["L3"])

    def test_histogram_bimodal_and_matrix_and_change_forms(self) -> None:
        rng = np.random.default_rng(51)
        latencies = np.concatenate([rng.normal(18, 3, 120), rng.normal(44, 4, 80)]).round(1)
        exp_hist = fm.explain(
            "Latency splits into two modes near 18 ms and 44 ms",
            fm.histogram(
                latencies.tolist(),
                bins=16,
                reference=(35.0, "SLA"),
                label="Response time",
                unit="ms",
            ),
        )
        nar_hist = build_narrative(exp_hist.takeaway, exp_hist.panels)
        assert "histogram" in nar_hist["L1"]
        assert any("peak bin" in f for f in nar_hist["L3"])
        assert any("median" in f for f in nar_hist["L2"])

        exp_change = fm.explain(
            "Every benchmark improved after fine-tuning",
            fm.change(
                {"A": 40, "B": 60, "C": 70},
                {"A": 80, "B": 72, "C": 85},
                labels=("Base", "Tuned"),
                label="Accuracy",
                unit="%",
            ),
        )
        nar_change = build_narrative(exp_change.takeaway, exp_change.panels)
        assert "Base → Tuned" in nar_change["L1"]
        assert any("3 up, 0 down" in f for f in nar_change["L3"])

        exp_mat = fm.explain(
            "Rust perf is the lowest cell at 22%",
            fm.matrix(
                [[80, 90], [22, 75]],
                rows=["Python", "Rust"],
                cols=["perf", "docs"],
                label="Pass rate",
                unit="%",
            ),
        )
        nar_mat = build_narrative(exp_mat.takeaway, exp_mat.panels)
        assert "2×2" in nar_mat["L1"]
        assert any("lowest: Rust" in f for f in nar_mat["L2"])

    def test_accepts_plain_dict_panels(self) -> None:
        nar = build_narrative(
            "Service A leads latency",
            {
                "a": {
                    "kind": "compare",
                    "label": "Latency",
                    "unit": "ms",
                    "facts": ["highest: A 400 ms", "A is 2.0× the next highest (B 200 ms)"],
                    "spec": {"values": {"A": 400, "B": 200}},
                }
            },
        )
        assert nar["L1"] == "1 panel: compare (Latency, ms)"
        assert nar["L2"] == ["highest: A 400 ms"]
        assert nar["L3"] == ["A is 2.0× the next highest (B 200 ms)"]
        assert nar["L4"] == "Service A leads latency."


# --------------------------------------------------------------------------- #
# Part 2: Epistemic / Slant Audit — Positive Detections
# --------------------------------------------------------------------------- #


class TestAuditEpistemicDetections:
    def test_rules_are_advisory_and_never_in_visual_defect_rules(self) -> None:
        assert "claim_overstates_uncertainty" not in _VISUAL_DEFECT_RULES
        assert "claim_number_mismatch" not in _VISUAL_DEFECT_RULES

    @pytest.mark.parametrize(
        "takeaway",
        [
            "Treatment A is statistically significant over Control",
            "Treatment A conclusively outperforms Control",
            "Treatment A clearly beats Control across seeds",
            "Treatment A proves a gain over Control",
            "Treatment A gain is outside seed noise",
            "Treatment A unambiguously leads Control",
            "Treatment A decisively lowers error",
        ],
    )
    def test_catches_overclaiming_on_overlapping_cis(self, takeaway: str) -> None:
        panel = fm.compare(
            {"Treatment A": 0.78, "Control": 0.75},
            error={"Treatment A": (0.73, 0.83), "Control": (0.70, 0.80)},
            error_label="95% CI, 5 seeds",
            label="Accuracy",
            highlight="Treatment A",
        )
        issues = audit_epistemic(takeaway, {"a": panel})
        rules = [i["rule"] for i in issues]
        assert rules == ["claim_overstates_uncertainty"]
        assert issues[0]["severity"] == "warning"
        assert issues[0]["panel"] == "a"
        assert "note=" in issues[0]["fix_hint"] or "Hedge" in issues[0]["fix_hint"]

    def test_catches_overclaiming_on_small_n_rough_estimate(self) -> None:
        panel = fm.relate(
            [1.0, 2.0, 3.0, 1.5, 2.5, 3.5],
            [2.0, 4.1, 5.9, 1.0, 2.1, 3.2],
            groups=["A", "A", "A", "B", "B", "B"],
            x_label="Dose",
            y_label="Response",
        )
        assert any("rough estimate" in f for f in panel.facts)
        issues = audit_epistemic(
            "Dose conclusively proves a linear response", {"a": panel}
        )
        assert [i["rule"] for i in issues] == ["claim_overstates_uncertainty"]
        assert issues[0]["severity"] == "warning"

        dist_small = fm.distribution(
            {"A": [10.0, 12.0, 14.0], "B": [8.0, 9.0, 10.0]},
            stat="mean",
            label="Score",
        )
        assert any("rough estimate" in f for f in dist_small.facts)
        dist_issues = audit_epistemic("Group A clearly beats Group B", {"a": dist_small})
        assert [i["rule"] for i in dist_issues] == ["claim_overstates_uncertainty"]

    def test_catches_blatant_percentage_mismatch(self) -> None:
        panel = fm.compare({"before": 100.0, "after": 92.0}, label="Latency", unit="ms")
        issues = audit_epistemic("Latency fell with a 50% drop after rollout", {"a": panel})
        assert [i["rule"] for i in issues] == ["claim_number_mismatch"]
        assert issues[0]["severity"] == "warning"
        assert "50%" in issues[0]["message"]

    def test_catches_blatant_percentage_mismatch_on_trend(self) -> None:
        panel = fm.trend(
            [1, 2, 3, 4],
            {"latency": [100.0, 98.0, 95.0, 92.0]},
            label="Latency",
            unit="ms",
            x_label="Week",
        )
        issues = audit_epistemic("Latency saw a 50% drop from week 1 to week 4", {"a": panel})
        assert [i["rule"] for i in issues] == ["claim_number_mismatch"]
        assert issues[0]["severity"] == "warning"

    def test_catches_blatant_fold_mismatch(self) -> None:
        panel = fm.compare({"checkout": 120.0, "search": 100.0}, label="Latency", unit="ms")
        issues = audit_epistemic("Checkout is 8x slower than search", {"a": panel})
        assert [i["rule"] for i in issues] == ["claim_number_mismatch"]
        assert issues[0]["severity"] == "warning"
        assert "8x" in issues[0]["message"]


# --------------------------------------------------------------------------- #
# Part 3: Zero False Positives on Tricky Benign Cases + ALL Gallery Examples
# --------------------------------------------------------------------------- #


class TestAuditEpistemicZeroFalsePositives:
    def test_no_warning_when_cis_do_not_overlap(self) -> None:
        panel = fm.compare(
            {"full model": 0.82, "no retrieval": 0.74},
            error={"full model": (0.80, 0.84), "no retrieval": (0.71, 0.77)},
            error_label="95% CI, 5 seeds",
            label="Test accuracy",
            highlight="no retrieval",
        )
        issues = audit_epistemic(
            "Removing retrieval is outside seed noise and clearly lowers accuracy",
            {"a": panel},
        )
        assert issues == []

    def test_no_warning_when_overlapping_cis_have_hedged_takeaway(self) -> None:
        panel = fm.compare(
            {"Treatment A": 0.78, "Control": 0.75},
            error={"Treatment A": (0.73, 0.83), "Control": (0.70, 0.80)},
            error_label="95% CI, 5 seeds",
            label="Accuracy",
        )
        issues = audit_epistemic(
            "Treatment A edges ahead of Control, though 95% CIs overlap",
            {"a": panel},
        )
        assert issues == []

    @pytest.mark.parametrize(
        ("takeaway", "panel"),
        [
            # Years, versions, item counts
            (
                "In 2026, v2.3 leads all 4 benchmarks after the Q3 release",
                fm.compare({"A": 86, "B": 82, "C": 79, "D": 75}, label="Score", unit="%"),
            ),
            # Point deltas (0.08 -> 8 points, 0.13 -> 13 points)
            (
                "Removing retrieval costs 8 points of accuracy; removing fine-tuning costs 13",
                fm.compare(
                    {"full": 0.82, "no retrieval": 0.74, "no fine-tuning": 0.69},
                    label="Accuracy",
                ),
            ),
            # Unit conversions (0.01 uM -> 10 nM)
            (
                "BX-204 inhibits the kinase at 10 nM across replicates",
                fm.compare({"BX-204": 0.01, "BX-101": 0.08}, label="IC50", unit="µM"),
            ),
            # Hedged percentages and folds
            (
                "Checkout drops latency by ~20% across services",
                fm.compare({"before": 100.0, "after": 92.0}, label="Latency", unit="ms"),
            ),
            (
                "Migration falls by about 40% after knockout",
                fm.compare({"wt": 12.0, "ko": 10.0}, label="Distance", unit="µm"),
            ),
            (
                "Compound is roughly 5x more potent than control",
                fm.compare({"drug": 2.0, "ctrl": 1.0}, label="Potency"),
            ),
            (
                "Nearly 90% of requests stay under budget",
                fm.compare({"ok": 60.0, "slow": 40.0}, label="Count"),
            ),
            (
                "Over 50% of runs pass on the first try",
                fm.compare({"pass": 30.0, "fail": 70.0}, label="Count"),
            ),
            # Confidence interval label ("95% CI") should not be checked as a data value
            (
                "Effect size is 0.4 with narrow 95% CI",
                fm.compare({"A": 0.4, "B": 0.1}, label="Effect"),
            ),
            # Atomic percent ("2 at.%")
            (
                "Conductivity peaks at 2 at.% Li across all samples",
                fm.compare({"0 at.%": 1e-5, "2 at.%": 1e-2}, label="Conductivity", unit="S/cm"),
            ),
            # Small fold <= 1.2x ignored
            (
                "Model B is 1.1x faster than baseline",
                fm.compare({"A": 10.0, "B": 10.0}, label="Speed"),
            ),
            # Valid percentage change (8% drop on 100 -> 92)
            (
                "Latency fell by 8% after caching",
                fm.compare({"before": 100.0, "after": 92.0}, label="Latency", unit="ms"),
            ),
            # Valid fraction-to-percent match (0.82 -> 82%)
            (
                "Full model reaches 82% accuracy",
                fm.compare({"full": 0.82, "base": 0.74}, label="Accuracy"),
            ),
            # Valid fold ratio (1840 / 460 = 4x)
            (
                "Checkout p99 is 4x the next worst service",
                fm.compare({"checkout": 1840, "search": 460}, label="p99", unit="ms"),
            ),
            # Custom panel skipped completely
            (
                "Custom diagram illustrates a 50% drop and 9x speedup",
                fm.custom(lambda ax: ax.plot([0, 1], [100, 99]), title="Custom"),
            ),
        ],
    )
    def test_benign_cases_emit_zero_warnings(self, takeaway: str, panel: fm.Panel) -> None:
        assert audit_epistemic(takeaway, {"a": panel}) == []

    @pytest.mark.parametrize(("name", "builder"), _load_gallery_examples())
    def test_zero_false_positives_across_all_gallery_examples(
        self, name: str, builder: Any
    ) -> None:
        exp = builder()
        issues = audit_epistemic(exp.takeaway, exp.panels)
        assert issues == [], f"{name} emitted unexpected epistemic warnings: {issues}"
        nar = build_narrative(
            exp.takeaway, exp.panels, subtitle=exp.subtitle, source=exp.source
        )
        assert nar["L1"]
        assert nar["L4"]
        assert nar["summary"]
