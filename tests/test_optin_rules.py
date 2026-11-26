"""Tests for Phase 3 opt-in rules: share(kind="pie" | "donut") and legend=True."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from matplotlib.patches import Wedge

import mintfig as mint
from mintfig.audit import audit_figure

TAKEAWAY_SHARE = "Compute accounts for 55% of total cloud spend across regions"
TAKEAWAY_TREND = "Checkout latency tripled to 1,840 ms after week 4 deploy"
TAKEAWAY_RELATE = "Group B reaches higher efficiency across every batch size tested"
TAKEAWAY_GROUPED = "Model A leads 3 of 3 benchmarks by up to 8 points"


def _assert_clean_ship(exp: mint.Explanation) -> None:
    summary = exp.summary()
    assert summary["ok"] is True, f"Expected ok=True, issues={summary['issues']}"
    assert summary["ship"] is True, f"Expected ship=True, issues={summary['issues']}"
    assert summary["display"]["min_text_px"] >= 11.0, (
        f"Text too small: {summary['display']['min_text_px']} px"
    )
    with exp.theme.rc_context(exp.spec):
        audit = audit_figure(exp.fig, allow_ascii_minus=(exp.theme.minus_sign == "-"))
    assert audit["overlaps"] == [], f"Overlaps: {audit['overlaps']}"
    assert audit["struck"] == [], f"Struck lines: {audit['struck']}"
    assert audit["text_faults"] == [], f"Text faults: {audit['text_faults']}"


# --------------------------------------------------------------------------- #
# 1. share(kind="pie" | "donut")
# --------------------------------------------------------------------------- #


class TestSharePieAndDonut:
    def test_pie_and_donut_ship_cleanly_with_wedges_and_labels(self, tmp_path: Path) -> None:
        parts = {"Compute": 550, "Storage": 300, "Network": 150}
        for kind in ("pie", "donut"):
            exp = mint.explain(
                TAKEAWAY_SHARE,
                mint.share(parts, label="Cloud spend", unit="$", highlight="Compute", kind=kind),
            )
            _assert_clean_ship(exp)
            assert exp.issues == []
            ax = exp["a"]
            wedges = [p for p in ax.patches if isinstance(p, Wedge)]
            assert len(wedges) == 3
            texts = [t.get_text() for t in ax.texts if t.get_visible() and t.get_text().strip()]
            joined = " | ".join(texts)
            assert "Compute" in joined and "55%" in joined
            assert "Storage" in joined and "30%" in joined
            assert "Network" in joined and "15%" in joined

            if kind == "donut":
                # Donut ring leaves a center hole and renders a central readout.
                assert all(w.width is not None and w.width < w.r for w in wedges)
                assert any("55%" in t for t in texts)
            else:
                assert all(w.width is None for w in wedges)

            # Round-trip via spec and PNG preserves kind and panel.kind == "share"
            spec = exp.to_spec()
            assert spec["panels"][0]["kind"] == "share"
            assert spec["panels"][0]["share_kind"] == kind
            rebuilt = mint.load(spec)
            assert rebuilt.to_spec() == spec
            _assert_clean_ship(rebuilt)

            png = tmp_path / f"share_{kind}.png"
            exp.save(png)
            from_png = mint.load(png)
            assert from_png.to_spec() == spec
            _assert_clean_ship(from_png)

    def test_donut_central_total_readout_without_highlight(self) -> None:
        parts = {"Compute": 550, "Storage": 300, "Network": 150}
        exp = mint.explain(
            TAKEAWAY_SHARE,
            mint.share(parts, label="Cloud spend", unit="$", kind="donut"),
        )
        _assert_clean_ship(exp)
        texts = [t.get_text().replace("\\", "") for t in exp["a"].texts if t.get_visible()]
        assert any("$1,000" in t for t in texts)
        assert any(t == "total" for t in texts)

    def test_pie_five_parts_and_top_folding(self) -> None:
        six_parts = {"Alpha": 42, "Beta": 24, "Gamma": 14, "Delta": 9, "Epsilon": 6, "Zeta": 5}
        with pytest.raises(mint.ExplainError) as err:
            mint.share(six_parts, label="Traffic", kind="pie")
        assert err.value.rule == "too_many_items"
        assert (
            err.value.fix_hint
            == "Use kind='bars' for more than 5 parts, or set top=4 to fold the rest into Other."
        )

        # Folding to top=4 yields 5 slices (4 + Other (2)) and ships cleanly.
        exp = mint.explain(
            "Alpha carries 42% of total traffic across six services",
            mint.share(six_parts, label="Traffic", top=4, kind="donut"),
        )
        _assert_clean_ship(exp)
        wedges = [p for p in exp["a"].patches if isinstance(p, Wedge)]
        assert len(wedges) == 5

    def test_pie_close_slices_advisory_never_blocks_ship(self) -> None:
        close_parts = {"Compute": 36, "Storage": 33, "Network": 21, "Support": 10}
        exp = mint.explain(
            "Compute leads Storage by 3 points at 36% of total spend",
            mint.share(close_parts, label="Spend", kind="pie"),
        )
        _assert_clean_ship(exp)
        rules = [i["rule"] for i in exp.issues]
        assert "pie_close_slices" in rules
        advisory = next(i for i in exp.issues if i["rule"] == "pie_close_slices")
        assert advisory["severity"] == "warning"
        assert "bars" in advisory["message"].lower()

        # In lenient mode, pie_close_slices moves to advisories while ship stays True.
        exp_lenient = mint.explain(
            "Compute leads Storage by 3 points at 36% of total spend",
            mint.share(close_parts, label="Spend", kind="donut"),
            strict=False,
        )
        summary = exp_lenient.summary()
        assert summary["ship"] is True
        assert any(i["rule"] == "pie_close_slices" for i in summary["advisories"])

    def test_pie_preserves_computed_facts_and_shared_entity_colors(self) -> None:
        parts = {"Compute": 550, "Storage": 300, "Network": 150}
        bars = mint.share(parts, label="Spend", unit="$", highlight="Compute")
        pie = mint.share(parts, label="Spend", unit="$", highlight="Compute", kind="pie")
        donut = mint.share(parts, label="Spend", unit="$", highlight="Compute", kind="donut")
        assert pie.facts == bars.facts
        assert donut.facts == bars.facts

        # Side-by-side with a trend sharing the same entity names ships cleanly and shares colors.
        exp = mint.explain(
            "Compute is 55% of spend and climbed to 550 dollars in Q4",
            mint.share(parts, title="Share of spend", label="Spend", unit="$", kind="donut"),
            mint.trend(
                [1, 2, 3, 4],
                {
                    "Compute": [380, 420, 490, 550],
                    "Storage": [290, 295, 300, 300],
                    "Network": [140, 145, 148, 150],
                },
                title="Quarterly spend",
                label="Spend",
                unit="$",
                x_label="Quarter",
            ),
        )
        _assert_clean_ship(exp)
        assert "Compute" in exp.entity_colors and "Storage" in exp.entity_colors

    def test_share_invalid_kind_and_top_level_pie_still_rejected(self) -> None:
        with pytest.raises(mint.ExplainError, match="'bars', 'pie', or 'donut'"):
            mint.share({"A": 60, "B": 40}, kind="waffle")
        with pytest.raises(mint.ExplainError, match="Unknown panel kind"):
            mint.load({"takeaway": TAKEAWAY_SHARE, "panels": [{"kind": "pie"}]})

    @pytest.mark.parametrize("style", ["mintfig", "dark", "editorial", "bold"])
    def test_donut_works_across_styles(self, style: str) -> None:
        parts = {"Compute": 55, "Storage": 30, "Network": 15}
        exp = mint.explain(
            TAKEAWAY_SHARE,
            mint.share(parts, label="Spend", kind="donut"),
            style=style,
        )
        _assert_clean_ship(exp)


# --------------------------------------------------------------------------- #
# 2. Opt-in legend=True on trend, relate, and grouped compare
# --------------------------------------------------------------------------- #


class TestOptInLegends:
    def test_trend_legend_true_ships_and_round_trips(self, tmp_path: Path) -> None:
        x = [1, 2, 3, 4, 5, 6, 7, 8]
        series = {
            "checkout": [540, 560, 550, 570, 980, 1400, 1700, 1840],
            "search": [450, 470, 455, 465, 460, 450, 470, 460],
            "auth": [300, 310, 305, 315, 300, 320, 305, 310],
        }
        exp = mint.explain(
            TAKEAWAY_TREND,
            mint.trend(
                x,
                series,
                label="p99 latency",
                unit="ms",
                x_label="Week",
                highlight="checkout",
                events={4: "v2.3 deploy"},
                reference=(500, "SLO"),
                legend=True,
            ),
        )
        _assert_clean_ship(exp)
        ax = exp["a"]
        leg = ax.get_legend()
        assert leg is not None
        assert leg.get_frame_on() is False
        leg_labels = [t.get_text() for t in leg.get_texts()]
        assert leg_labels == ["checkout", "search", "auth"]
        # Direct end-of-line annotations must be omitted when legend=True.
        direct_texts = [t.get_text() for t in ax.texts]
        assert not any("1,840" in txt for txt in direct_texts)

        spec = exp.to_spec()
        assert spec["panels"][0]["legend"] is True
        rebuilt = mint.load(spec)
        assert rebuilt.to_spec() == spec
        assert rebuilt["a"].get_legend() is not None
        _assert_clean_ship(rebuilt)

        png = tmp_path / "trend_legend.png"
        exp.save(png)
        from_png = mint.load(png)
        assert from_png["a"].get_legend() is not None
        _assert_clean_ship(from_png)

    def test_trend_legend_with_many_context_series(self) -> None:
        x = [1, 2, 3, 4, 5]
        series = {f"svc-{i}": [10 + i * 2 + t for t in x] for i in range(10)}
        series["svc-0"] = [15, 22, 35, 55, 80]
        exp = mint.explain(
            "Service svc-0 jumped to 80 ms while 9 others stayed flat",
            mint.trend(x, series, label="Latency", unit="ms", highlight="svc-0", legend=True),
        )
        _assert_clean_ship(exp)
        leg = exp["a"].get_legend()
        assert leg is not None
        labels = [t.get_text() for t in leg.get_texts()]
        assert labels == ["svc-0", "9 others"]

    def test_relate_legend_true_ships_and_round_trips(self, tmp_path: Path) -> None:
        rng = np.random.default_rng(7)
        x = np.concatenate([rng.uniform(1, 5, 10), rng.uniform(1, 5, 10), rng.uniform(1, 5, 10)])
        y = np.concatenate([10 * x[:10] + 4, 18 * x[10:20] + 2, 13 * x[20:] + 3])
        groups = ["Group A"] * 10 + ["Group B"] * 10 + ["Group C"] * 10
        exp = mint.explain(
            TAKEAWAY_RELATE,
            mint.relate(
                x,
                y,
                groups=groups,
                fit=True,
                highlight="Group B",
                x_label="Batch size",
                y_label="Throughput (req/s)",
                legend=True,
            ),
        )
        _assert_clean_ship(exp)
        ax = exp["a"]
        leg = ax.get_legend()
        assert leg is not None
        assert leg.get_frame_on() is False
        assert [t.get_text() for t in leg.get_texts()] == ["Group A", "Group B", "Group C"]
        # Direct right-end group annotations omitted; per-group fit lines still drawn.
        direct_texts = [t.get_text() for t in ax.texts]
        assert "Group A" not in direct_texts and "Group B" not in direct_texts
        assert len([ln for ln in ax.lines if ln.get_label() == "_fit"]) == 3

        spec = exp.to_spec()
        assert spec["panels"][0]["legend"] is True
        rebuilt = mint.load(spec)
        assert rebuilt.to_spec() == spec
        assert rebuilt["a"].get_legend() is not None
        _assert_clean_ship(rebuilt)

        png = tmp_path / "relate_legend.png"
        exp.save(png)
        from_png = mint.load(png)
        assert from_png["a"].get_legend() is not None
        _assert_clean_ship(from_png)

    def test_grouped_compare_legend_true_bars_dots_and_round_trip(self, tmp_path: Path) -> None:
        nested = {
            "MMLU": {"Model A": 86.2, "Model B": 81.4, "Baseline": 78.0},
            "GSM8K": {"Model A": 92.5, "Model B": 88.1, "Baseline": 84.5},
            "HumanEval": {"Model A": 79.0, "Model B": 74.2, "Baseline": 71.0},
        }
        # Bar mode with reference line and legend=True
        exp = mint.explain(
            TAKEAWAY_GROUPED,
            mint.compare(
                nested,
                label="Accuracy",
                unit="%",
                highlight="Model A",
                baseline="Baseline",
                reference=(80, "target"),
                legend=True,
            ),
        )
        _assert_clean_ship(exp)
        ax = exp["a"]
        leg = ax.get_legend()
        assert leg is not None
        assert leg.get_frame_on() is False
        assert [t.get_text() for t in leg.get_texts()] == ["Model A", "Model B", "Baseline"]

        spec = exp.to_spec()
        assert spec["panels"][0]["legend"] is True
        rebuilt = mint.load(spec)
        assert rebuilt.to_spec() == spec
        assert rebuilt["a"].get_legend() is not None
        _assert_clean_ship(rebuilt)

        png = tmp_path / "grouped_legend.png"
        exp.save(png)
        from_png = mint.load(png)
        assert from_png["a"].get_legend() is not None
        _assert_clean_ship(from_png)

        # Dot mode (zero=False) with tidy rows (group=) and legend=True
        rows = [
            {"bench": b, "model": m, "score": v}
            for b, scores in nested.items()
            for m, v in scores.items()
        ]
        exp_dots = mint.explain(
            TAKEAWAY_GROUPED,
            mint.compare(
                rows,
                name="bench",
                group="model",
                value="score",
                label="Accuracy",
                unit="%",
                zero=False,
                legend=True,
            ),
        )
        _assert_clean_ship(exp_dots)
        assert exp_dots["a"].get_legend() is not None

    def test_specific_hint_updates_for_legend(self) -> None:
        with pytest.raises(mint.ExplainError) as err_other:
            mint.distribution({"a": [1.0, 2.0, 3.0]}, legend=True)
        assert "There are no legends" not in err_other.value.fix_hint
        assert "legend=True" in err_other.value.fix_hint
        assert "trend()" in err_other.value.fix_hint

        with pytest.raises(mint.ExplainError) as err_alias:
            mint.trend([1, 2, 3], {"a": [1, 2, 3]}, show_legend=True)
        assert "There are no legends" not in err_alias.value.fix_hint
        assert "pass legend=True" in err_alias.value.fix_hint

    def test_non_bool_legend_raises_explain_error(self) -> None:
        with pytest.raises(mint.ExplainError, match="True or False"):
            mint.trend([1, 2, 3], {"a": [1, 2, 3]}, legend="upper right")  # type: ignore[arg-type]
        with pytest.raises(mint.ExplainError, match="True or False"):
            mint.relate([1, 2, 3], [1, 2, 3], x_label="x", y_label="y", legend="top")  # type: ignore[arg-type]
        with pytest.raises(mint.ExplainError, match="True or False"):
            mint.compare({"a": 1, "b": 2}, legend="top")  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# 3. Defaults remain strictly unchanged & SKILL.md byte budget
# --------------------------------------------------------------------------- #


class TestDefaultsAndSkillDoc:
    def test_defaults_unchanged_for_share_trend_relate_and_grouped_compare(self) -> None:
        # share default is bars (no share_kind in spec, no wedges)
        exp_share = mint.explain(
            TAKEAWAY_SHARE,
            mint.share({"Compute": 55, "Storage": 30, "Network": 15}, label="Spend"),
        )
        assert "share_kind" not in exp_share.to_spec()["panels"][0]
        assert not any(isinstance(p, Wedge) for p in exp_share["a"].patches)

        # trend default has no legend and direct end labels
        exp_trend = mint.explain(
            TAKEAWAY_TREND,
            mint.trend([1, 2, 3], {"checkout": [500, 1200, 1840], "auth": [300, 305, 310]}, unit="ms"),
        )
        assert exp_trend["a"].get_legend() is None
        assert "legend" not in exp_trend.to_spec()["panels"][0]

        # relate(groups=) default has no legend and direct group labels
        exp_rel = mint.explain(
            TAKEAWAY_RELATE,
            mint.relate(
                [1, 2, 3, 1, 2, 3],
                [2, 4, 6, 5, 8, 11],
                groups=["A", "A", "A", "B", "B", "B"],
                x_label="x",
                y_label="y",
            ),
        )
        assert exp_rel["a"].get_legend() is None
        assert "legend" not in exp_rel.to_spec()["panels"][0]

        # grouped compare default has no Matplotlib legend (uses inline strip)
        exp_grp = mint.explain(
            TAKEAWAY_GROUPED,
            mint.compare(
                {"B1": {"Model A": 86, "Model B": 81}, "B2": {"Model A": 92, "Model B": 88}},
                label="Score",
                unit="%",
            ),
        )
        assert exp_grp["a"].get_legend() is None
        assert "legend" not in exp_grp.to_spec()["panels"][0]

    def test_skill_chat_section_under_12000_bytes(self) -> None:
        skill = (Path(mint.__file__).parent / "assets" / "SKILL.md").read_text(encoding="utf-8")
        section = skill[skill.index("## Explain in a Conversation") : skill.index("## Publication Figures")]
        assert len(section.encode("utf-8")) < 12_000
        assert "legend=False" in section
        assert 'kind="bars"' in section
