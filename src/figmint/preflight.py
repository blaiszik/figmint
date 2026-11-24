"""Automated preflight compliance linter for Matplotlib figures and exported PDFs."""

from __future__ import annotations

import contextlib
import re
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import matplotlib.pyplot as plt
import numpy as np
from matplotlib import font_manager
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.cm import ScalarMappable
from matplotlib.collections import Collection, LineCollection, PolyCollection
from matplotlib.colors import to_hex, to_rgb, to_rgba
from matplotlib.container import BarContainer
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.spines import Spine
from matplotlib.text import Text
from pypdf import PdfReader

from .palettes import BANNED_COLORMAPS, simulate_cvd
from .specs import MM_PER_INCH, JournalSpec, get_spec, in_to_mm

CheckStatus = Literal["pass", "warn", "fail"]
CheckSeverity = Literal["ok", "warning", "error"]

_SERIF_SUBSTRINGS = (
    "times",
    "georgia",
    "palatino",
    "garamond",
    "cambria",
    "baskerville",
    "bookman",
    "charter",
    "century",
    "minion",
    "caslon",
    "hoefler",
    "didot",
    "bodoni",
    "computer modern",
    "stixgeneral",
    "dejavuserif",
    "liberationserif",
    "notoserif",
    "sourceserif",
    "ptserif",
    "nimbusrom",
    "urwbookman",
)

_SERIF_TOKEN_RE = re.compile(
    r"(?:^|[^a-z])(cmr|cmmi|cmsy|cmex|cmti|cmbx|cmsl|cmtt|stix|serif)(?:[^a-z]|$)",
    re.IGNORECASE,
)

_CANONICAL_WIDTH_PRIORITY = ("single", "mid", "double", "full", "1.5col", "2col", "3col")


@dataclass
class CheckResult:
    """Result of a single preflight compliance check."""

    rule: str
    status: CheckStatus
    message: str
    details: dict[str, Any] = field(default_factory=dict)
    panel: str | None = None
    elements: list[str] = field(default_factory=list)
    fix_hint: str | None = None
    panels: list[str] = field(default_factory=list)
    element_locations: list[dict[str, str | None]] = field(default_factory=list)

    @property
    def severity(self) -> CheckSeverity:
        """Return v0.2 severity level ('error', 'warning', or 'ok')."""
        if self.status == "fail":
            return "error"
        if self.status == "warn":
            return "warning"
        return "ok"

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable dictionary representation."""
        return {
            "rule": self.rule,
            "status": self.status,
            "severity": self.severity,
            "panel": self.panel,
            "panels": list(self.panels),
            "elements": list(self.elements),
            "element_locations": [dict(loc) for loc in self.element_locations],
            "message": self.message,
            "fix_hint": self.fix_hint,
            "details": self.details,
        }

    def to_issue_dict(self) -> dict[str, Any]:
        """Return the concise v0.2 agent issue payload for non-passing checks."""
        return {
            "rule": self.rule,
            "severity": self.severity,
            "panel": self.panel,
            "panels": list(self.panels),
            "elements": list(self.elements),
            "element_locations": [dict(loc) for loc in self.element_locations],
            "message": self.message,
            "fix_hint": self.fix_hint,
        }


@dataclass
class PreflightReport:
    """Aggregated compliance report for a figure or PDF against a journal spec."""

    journal: str
    checks: list[CheckResult]
    width_mm: float
    height_mm: float
    spec_version: str = ""
    spec_source_url: str = ""
    recommended_max_loops: int = 2

    @property
    def passed(self) -> bool:
        """Return True if no check failed."""
        return not any(check.status == "fail" for check in self.checks)

    @property
    def warnings(self) -> list[CheckResult]:
        """Return all checks with warning status."""
        return [check for check in self.checks if check.status == "warn"]

    @property
    def failures(self) -> list[CheckResult]:
        """Return all checks with fail status."""
        return [check for check in self.checks if check.status == "fail"]

    @property
    def issues(self) -> list[CheckResult]:
        """Return all failing and warning checks (errors first)."""
        return [*self.failures, *self.warnings]

    def summary(self) -> str:
        """Render a crisp, readable scorecard string."""
        try:
            display = get_spec(self.journal).display_name
        except (KeyError, ValueError):
            display = self.journal

        overall = "PASS" if self.passed else "FAIL"
        header = (
            f"figmint preflight — {display} "
            f"({self.width_mm:.1f} × {self.height_mm:.1f} mm) — {overall}"
        )
        rule_width = max((len(c.rule) for c in self.checks), default=14)
        divider = "─" * max(len(header), 64)
        lines = [header, divider]

        tag_map = {"pass": "[PASS]", "warn": "[WARN]", "fail": "[FAIL]"}
        for check in self.checks:
            tag = tag_map[check.status]
            if len(check.panels) > 1:
                panel_note = f" [panels {', '.join(check.panels)}]"
            else:
                panel_note = f" [panel {check.panel}]" if check.panel else ""
            lines.append(f"{tag} {check.rule:<{rule_width}}  {check.message}{panel_note}")

        n_pass = sum(1 for c in self.checks if c.status == "pass")
        n_warn = len(self.warnings)
        n_fail = len(self.failures)
        lines.append(divider)
        lines.append(f"Summary: {n_pass} passed, {n_warn} warnings, {n_fail} failures")
        return "\n".join(lines)

    def to_agent_dict(
        self,
        *,
        artifacts: dict[str, str | None] | None = None,
    ) -> dict[str, Any]:
        """Return the structured v0.2 agent-consumable JSON contract."""
        return {
            "schema_version": "0.2",
            "ok": self.passed,
            "journal": self.journal,
            "spec_version": self.spec_version,
            "spec_source_url": self.spec_source_url,
            "dimensions_mm": {
                "width": round(float(self.width_mm), 2),
                "height": round(float(self.height_mm), 2),
            },
            "summary": {
                "errors": len(self.failures),
                "warnings": len(self.warnings),
                "passed": sum(1 for c in self.checks if c.status == "pass"),
            },
            "recommended_max_loops": self.recommended_max_loops,
            "issues": [check.to_issue_dict() for check in self.issues],
            "artifacts": dict(artifacts) if artifacts is not None else {},
        }

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable dictionary preserving v0.1 + v0.2 fields."""
        agent_payload = self.to_agent_dict()
        return {
            **agent_payload,
            "width_mm": round(float(self.width_mm), 3),
            "height_mm": round(float(self.height_mm), 3),
            "passed": self.passed,
            "num_passed": agent_payload["summary"]["passed"],
            "num_warnings": agent_payload["summary"]["warnings"],
            "num_failures": agent_payload["summary"]["errors"],
            "checks": [c.to_dict() for c in self.checks],
        }


def _is_serif_font_name(name: str) -> bool:
    """Return True if a font name or file stem indicates a serif typeface."""
    if not name:
        return False
    # Strip PDF subset prefix like "ABCDEF+Helvetica"
    cleaned = re.sub(r"^[A-Z]{6}\+", "", name.strip())
    low = cleaned.lower()
    compact = re.sub(r"[\s_\-]+", "", low)

    if "sans" in compact:
        return False

    if any(sub in compact or sub in low for sub in _SERIF_SUBSTRINGS):
        return True

    # Computer Modern PDF/Type1 font names like CMR10, CMMI7, CMSY10
    if re.match(r"^(cmr|cmmi|cmsy|cmex|cmti|cmbx|cmsl)\d*", compact):
        return True

    return bool(_SERIF_TOKEN_RE.search(low))


def _canonical_preset_for_width(spec: JournalSpec, width_mm: float) -> tuple[str, float]:
    """Return the nearest canonical (preset_name, target_width_mm) for ``width_mm``."""
    order = {name: i for i, name in enumerate(_CANONICAL_WIDTH_PRIORITY)}
    candidates = sorted(
        spec.widths_mm.items(),
        key=lambda kv: (abs(width_mm - kv[1]), order.get(kv[0], 99), kv[0]),
    )
    return candidates[0]


def _build_axes_panel_map(fig: Figure) -> dict[int, str]:
    """Map axes ``id(ax)`` to a panel key (``_figmint_panel_key`` or ``ax{idx}``)."""
    mapping: dict[int, str] = {}
    has_plate_keys = False
    for ax in fig.axes:
        key = getattr(ax, "_figmint_panel_key", None)
        if key is not None:
            mapping[id(ax)] = str(key)
            has_plate_keys = True

    if len(fig.axes) > 1:
        for idx, ax in enumerate(fig.axes):
            if id(ax) not in mapping:
                # Colorbars / insets on a Plate still get a deterministic fallback key
                parent = getattr(ax, "_parent_axes", None)
                if has_plate_keys and parent is not None and id(parent) in mapping:
                    mapping[id(ax)] = mapping[id(parent)]
                else:
                    mapping[id(ax)] = f"ax{idx}"
    return mapping


def _artist_panel(artist: Any, panel_map: dict[int, str]) -> str | None:
    """Resolve the panel key owning ``artist``, or ``None`` for figure-level artists."""
    ax = getattr(artist, "axes", None)
    if ax is None:
        return None
    key = getattr(ax, "_figmint_panel_key", None)
    if key is not None:
        return str(key)
    return panel_map.get(id(ax))


def _distinct_panels(panels: Any) -> list[str]:
    """Return distinct non-empty panel keys in first-seen order."""
    out: list[str] = []
    for panel in panels:
        if panel and panel not in out:
            out.append(str(panel))
    return out


def _locate(pairs: Any) -> list[dict[str, str | None]]:
    """Build ``element_locations`` entries from ``(element, panel)`` pairs."""
    return [{"element": element, "panel": panel} for element, panel in pairs]


def _check_dimensions(
    width_mm: float,
    height_mm: float,
    spec: JournalSpec,
    *,
    tol_mm: float = 0.5,
) -> CheckResult:
    """Validate physical figure width and height against journal column specs."""
    nearest_preset, nearest_width = _canonical_preset_for_width(spec, width_mm)
    width_ok = abs(width_mm - nearest_width) <= tol_mm
    matched_preset = nearest_preset if width_ok else None
    matched_width = nearest_width if width_ok else None

    unique_widths = sorted(set(spec.widths_mm.values()))

    height_status: CheckStatus
    if height_mm > spec.max_page_height_mm + tol_mm:
        height_status = "fail"
        height_note = (
            f"height {height_mm:.1f} mm exceeds max page height "
            f"{spec.max_page_height_mm:.1f} mm"
        )
    elif height_mm > spec.max_height_mm + tol_mm:
        height_status = "warn"
        height_note = (
            f"height {height_mm:.1f} mm exceeds standard {spec.max_height_mm:.1f} mm "
            f"(within page max {spec.max_page_height_mm:.1f} mm)"
        )
    else:
        height_status = "pass"
        height_note = f"height {height_mm:.1f} mm <= {spec.max_height_mm:.1f} mm"

    if width_ok and matched_width is not None:
        width_note = f"width {width_mm:.1f} mm matches '{matched_preset}' ({matched_width:.1f} mm)"
    else:
        allowed_str = ", ".join(f"{w:.0f}" for w in unique_widths)
        width_note = (
            f"width {width_mm:.1f} mm does not match allowed {spec.name} widths "
            f"[{allowed_str}] mm (±{tol_mm:.1f} mm)"
        )

    if not width_ok or height_status == "fail":
        status: CheckStatus = "fail"
    elif height_status == "warn":
        status = "warn"
    else:
        status = "pass"

    elements: list[str] = []
    fix_hint: str | None = None
    if status != "pass":
        elements = [f"{width_mm:.1f}x{height_mm:.1f}mm"]
        suggested_h = min(round(height_mm, 1), spec.max_height_mm)
        if not width_ok and height_status == "fail":
            fix_hint = (
                f"Use fm.Plate(journal={spec.name!r}, width={nearest_preset!r}, "
                f"height_mm={spec.max_height_mm:.0f}) to match {nearest_width:.1f} mm "
                f"width and keep height <= {spec.max_height_mm:.0f} mm."
            )
        elif not width_ok:
            fix_hint = (
                f"Use fm.Plate(journal={spec.name!r}, width={nearest_preset!r}, "
                f"height_mm={suggested_h:.1f}) (target {nearest_width:.1f} mm)."
            )
        elif height_status == "fail":
            fix_hint = (
                f"Reduce height_mm from {height_mm:.1f} mm to <= {spec.max_height_mm:.0f} mm "
                f"(e.g. fm.Plate(journal={spec.name!r}, width={nearest_preset!r}, "
                f"height_mm={spec.max_height_mm:.0f}))."
            )
        else:
            fix_hint = (
                f"Reduce height_mm from {height_mm:.1f} mm to <= {spec.max_height_mm:.0f} mm "
                "to leave space for the figure caption."
            )

    return CheckResult(
        rule="dimensions",
        status=status,
        message=f"{width_note}; {height_note}",
        details={
            "width_mm": round(width_mm, 3),
            "height_mm": round(height_mm, 3),
            "matched_preset": matched_preset,
            "nearest_preset": nearest_preset,
            "nearest_width_mm": nearest_width,
            "allowed_widths_mm": unique_widths,
            "max_height_mm": spec.max_height_mm,
            "max_page_height_mm": spec.max_page_height_mm,
        },
        panel=None,
        elements=elements,
        fix_hint=fix_hint,
    )


@dataclass(frozen=True)
class _TextRecord:
    """Measured visible Text artist with bounding box, panel, and semantic role."""

    artist: Text
    bbox: Any
    text: str
    panel: str | None
    role: Literal["tick", "legend", "title", "axis_label", "panel_label", "annotation"]


def _iter_visible_texts(
    fig: Figure,
    renderer: Any,
    panel_map: dict[int, str],
) -> list[_TextRecord]:
    """Collect visible, non-empty, actually rendered Text artists and their pixel bboxes."""
    all_tick_label_ids: set[int] = set()
    active_tick_label_ids: set[int] = set()
    inactive_offset_ids: set[int] = set()
    axis_label_ids: set[int] = set()
    title_ids: set[int] = set()
    legend_text_ids: set[int] = set()
    hidden_legend_text_ids: set[int] = set()

    for ax in fig.axes:
        ax_visible = ax.get_visible()
        ax_axis_on = bool(getattr(ax, "axison", True))
        axis_label_ids.add(id(ax.xaxis.label))
        axis_label_ids.add(id(ax.yaxis.label))
        title_ids.add(id(ax.title))
        for attr in ("_left_title", "_right_title"):
            sub_title = getattr(ax, attr, None)
            if sub_title is not None:
                title_ids.add(id(sub_title))

        for axis in (ax.xaxis, ax.yaxis):
            axis_visible = ax_visible and ax_axis_on and axis.get_visible()
            v0, v1 = axis.get_view_interval()
            lo, hi = (v0, v1) if v0 <= v1 else (v1, v0)
            span = abs(hi - lo)
            # Relative tolerance only: an absolute floor would count off-view ticks as
            # active on axes whose data are tiny (1e-13 A leakage currents).
            eps = span * 1e-6 if span > 0 else 1e-12 * max(abs(lo), 1e-300)

            if not axis_visible:
                inactive_offset_ids.add(id(axis.get_offset_text()))
                inactive_offset_ids.add(id(axis.label))

            ticks = list(axis.get_major_ticks()) + list(axis.get_minor_ticks())
            for tick in ticks:
                all_tick_label_ids.add(id(tick.label1))
                all_tick_label_ids.add(id(tick.label2))
                if not axis_visible or not tick.get_visible():
                    continue
                loc = tick.get_loc()
                if not np.isfinite(loc) or loc < lo - eps or loc > hi + eps:
                    continue
                if tick.label1.get_visible() and tick.label1.get_text().strip():
                    active_tick_label_ids.add(id(tick.label1))
                if tick.label2.get_visible() and tick.label2.get_text().strip():
                    active_tick_label_ids.add(id(tick.label2))

    for leg in list(fig.legends) + [ax.get_legend() for ax in fig.axes]:
        if leg is None:
            continue
        leg_visible = leg.get_visible()
        for t in leg.get_texts():
            legend_text_ids.add(id(t))
            if not leg_visible:
                hidden_legend_text_ids.add(id(t))
        leg_title = leg.get_title()
        legend_text_ids.add(id(leg_title))
        if not leg_visible:
            hidden_legend_text_ids.add(id(leg_title))

    results: list[_TextRecord] = []
    seen_ids: set[int] = set()

    for text_artist in fig.findobj(Text):
        tid = id(text_artist)
        if tid in seen_ids:
            continue
        seen_ids.add(tid)

        if tid in hidden_legend_text_ids or tid in inactive_offset_ids:
            continue
        if tid in all_tick_label_ids and tid not in active_tick_label_ids:
            continue

        if not text_artist.get_visible():
            continue
        alpha = text_artist.get_alpha()
        if alpha is not None and alpha <= 0:
            continue
        if text_artist.axes is not None and not text_artist.axes.get_visible():
            continue

        content = text_artist.get_text()
        if not content or not content.strip():
            continue

        try:
            bbox = text_artist.get_window_extent(renderer=renderer)
        except (RuntimeError, ValueError):
            continue

        if not np.all(np.isfinite([bbox.x0, bbox.y0, bbox.x1, bbox.y1])):
            continue
        if bbox.width <= 0.5 or bbox.height <= 0.5:
            continue

        # If artist is clipped to an axes/clip_box and lies completely outside it, skip.
        if text_artist.get_clip_on():
            clip_box = text_artist.get_clip_box()
            if clip_box is not None and not bbox.overlaps(clip_box):
                continue

        if bool(getattr(text_artist, "_figmint_panel_label", False)):
            role: Literal[
                "tick", "legend", "title", "axis_label", "panel_label", "annotation"
            ] = "panel_label"
        elif tid in active_tick_label_ids:
            role = "tick"
        elif tid in legend_text_ids:
            role = "legend"
        elif tid in title_ids:
            role = "title"
        elif tid in axis_label_ids:
            role = "axis_label"
        else:
            role = "annotation"

        label = content.strip().replace("\n", " ")[:48]
        results.append(
            _TextRecord(
                artist=text_artist,
                bbox=bbox,
                text=label,
                panel=_artist_panel(text_artist, panel_map),
                role=role,
            )
        )

    return results


def _check_font_sizes(
    visible_texts: list[_TextRecord],
    spec: JournalSpec,
) -> CheckResult:
    """Verify all visible text artists respect journal minimum and maximum font sizes."""
    if not visible_texts:
        return CheckResult(
            rule="font_sizes",
            status="pass",
            message="No visible text artists found",
            details={"count": 0},
        )

    too_small: list[dict[str, Any]] = []
    too_large: list[dict[str, Any]] = []
    sizes: list[float] = []

    for rec in visible_texts:
        pt = float(rec.artist.get_fontsize())
        sizes.append(pt)
        is_panel = rec.role == "panel_label"
        max_pt = (spec.panel_label_pt + 0.5) if is_panel else (spec.font_max_pt + 0.5)

        if pt < spec.font_min_pt - 0.1:
            too_small.append(
                {
                    "text": rec.text,
                    "size_pt": round(pt, 2),
                    "panel": rec.panel,
                    "role": rec.role,
                }
            )
        elif pt > max_pt:
            too_large.append(
                {
                    "text": rec.text,
                    "size_pt": round(pt, 2),
                    "panel": rec.panel,
                    "is_panel_label": is_panel,
                    "role": rec.role,
                }
            )

    min_obs = min(sizes)
    max_obs = max(sizes)

    if too_small or too_large:
        small_elems = [f"{item['text']} ({item['size_pt']} pt)" for item in too_small[:6]]
        large_elems = [f"{item['text']} ({item['size_pt']} pt)" for item in too_large[:6]]
        elements = small_elems + large_elems
        located = [*too_small[:6], *too_large[:6]]
        offenders = [*too_small, *too_large]
        panels = _distinct_panels(item["panel"] for item in offenders)

        parts: list[str] = []
        hints: list[str] = []
        if too_small:
            sample = ", ".join(
                f"'{item['text']}' ({item['size_pt']} pt)" for item in too_small[:4]
            )
            parts.append(
                f"{len(too_small)} text artist(s) below {spec.font_min_pt:.1f} pt minimum: "
                f"{sample}"
            )
            hints.append(
                f"Increase font size of {small_elems[0]} to >= {spec.font_min_pt:.1f} pt "
                f"(recommended body={spec.body_pt:.1f} pt, ticks={spec.tick_pt:.1f} pt) "
                f"or remove tiny fontsize overrides."
            )
        if too_large:
            sample = ", ".join(
                f"'{item['text']}' ({item['size_pt']} pt)" for item in too_large[:4]
            )
            parts.append(
                f"{len(too_large)} text artist(s) above {spec.font_max_pt:.1f} pt maximum: "
                f"{sample}"
            )
            hints.append(
                f"Reduce font size to <= {spec.font_max_pt:.1f} pt (body={spec.body_pt:.1f} pt) "
                f"by building inside fm.Plate(journal={spec.name!r}) or fm.use({spec.name!r})."
            )

        # The first offender's panel: too-small text first (it drives the error).
        panel = next((item["panel"] for item in offenders if item["panel"]), None)
        return CheckResult(
            rule="font_sizes",
            status="fail" if too_small else "warn",
            message="; ".join(parts),
            details={
                "count": len(visible_texts),
                "min_pt": round(min_obs, 2),
                "max_pt": round(max_obs, 2),
                "too_small": too_small[:20],
                "too_large": too_large[:20],
            },
            panel=panel,
            elements=elements,
            fix_hint=" Also: ".join(hints),
            panels=panels,
            element_locations=_locate(
                zip(elements, (item["panel"] for item in located), strict=True)
            ),
        )

    return CheckResult(
        rule="font_sizes",
        status="pass",
        message=(
            f"All {len(visible_texts)} text artists in range "
            f"({min_obs:.1f}–{max_obs:.1f} pt; min {spec.font_min_pt:.1f} pt)"
        ),
        details={
            "count": len(visible_texts),
            "min_pt": round(min_obs, 2),
            "max_pt": round(max_obs, 2),
        },
    )


def _check_font_family(
    visible_texts: list[_TextRecord],
    spec: JournalSpec,
) -> CheckResult:
    """Verify sans-serif font usage across visible text artists and mathtext."""
    serif_hits: list[dict[str, Any]] = []
    resolved_fonts: set[str] = set()

    for rec in visible_texts:
        if getattr(rec.artist, "_figmint_allow_serif", False):
            continue
        families = rec.artist.get_fontfamily()
        if isinstance(families, str):
            families = [families]

        font_name = rec.artist.get_fontname()
        try:
            font_path = font_manager.findfont(
                rec.artist.get_fontproperties(), fallback_to_default=True
            )
            font_stem = Path(font_path).stem
        except (RuntimeError, ValueError):
            font_stem = font_name

        resolved_fonts.add(font_stem)

        flagged_font: str | None = None
        for candidate in (*families, font_name, font_stem):
            if _is_serif_font_name(str(candidate)):
                flagged_font = str(candidate)
                break

        # Mathtext font set is captured per artist (FontProperties.math_fontfamily,
        # taken from rcParams when the Text was created) and used at draw time, so
        # read it from the artist rather than from the live global rcParams.
        mathtext_fontset = ""
        if flagged_font is None and rec.text.count("$") >= 2:
            try:
                mathtext_fontset = str(
                    rec.artist.get_fontproperties().get_math_fontfamily()
                ).lower()
            except AttributeError:
                mathtext_fontset = str(plt.rcParams.get("mathtext.fontset", "")).lower()
        if flagged_font is None and mathtext_fontset in {"cm", "stix"}:
            flagged_font = f"mathtext:{mathtext_fontset}"

        if flagged_font is not None:
            serif_hits.append(
                {"text": rec.text, "font": flagged_font, "panel": rec.panel}
            )

    if serif_hits:
        unique_bad = sorted({hit["font"] for hit in serif_hits})
        sample = ", ".join(unique_bad[:4])
        panel = next((hit["panel"] for hit in serif_hits if hit["panel"]), None)
        elements = [f"{hit['text']} ({hit['font']})" for hit in serif_hits[:6]]
        family_panels = _distinct_panels(hit["panel"] for hit in serif_hits)
        family_locations = _locate(
            zip(elements, (hit["panel"] for hit in serif_hits[:6]), strict=True)
        )
        return CheckResult(
            rule="font_family",
            status="warn",
            message=(
                f"Detected serif font(s) on {len(serif_hits)} text artist(s): {sample} "
                "(sans-serif required)"
            ),
            details={"serif_hits": serif_hits[:20], "resolved_fonts": sorted(resolved_fonts)},
            panel=panel,
            elements=elements,
            fix_hint=(
                f"Remove explicit serif font overrides and wrap plotting in fm.use({spec.name!r}) "
                f"or fm.Plate(journal={spec.name!r}) to enforce sans-serif ({spec.font_family[0]}/Arial) "
                "text and mathtext."
            ),
            panels=family_panels,
            element_locations=family_locations,
        )

    fonts_str = ", ".join(sorted(resolved_fonts)[:4]) if resolved_fonts else "sans-serif"
    return CheckResult(
        rule="font_family",
        status="pass",
        message=f"All text artists use sans-serif typography ({fonts_str})",
        details={"resolved_fonts": sorted(resolved_fonts)},
    )


def _overlap_fix_hint(role_a: str, role_b: str, panel: str | None) -> str:
    """Return a context-aware fix hint for an overlapping pair of text roles."""
    roles = {role_a, role_b}
    where = f" in panel '{panel}'" if panel else ""
    if roles == {"tick"}:
        return (
            f"Reduce tick density{where} with ax.xaxis.set_major_locator(MaxNLocator(4)), "
            "rotate tick labels (rotation=30, ha='right'), or increase figure width/gap_mm."
        )
    if "legend" in roles:
        return (
            f"Replace the overlapping legend{where} with fm.direct_labels(ax), "
            "move it with loc='best' / bbox_to_anchor outside the data, or expand ylim."
        )
    if "panel_label" in roles:
        return (
            f"Increase Plate margin_mm or gap_mm{where} and call plate.label_panels() "
            "after setting titles and axis labels."
        )
    if roles & {"axis_label", "title"}:
        return (
            f"Increase Plate gap_mm (e.g. gap_mm=8.0) or height_mm{where}, "
            "or shorten axis labels/titles."
        )
    return (
        f"Reposition colliding annotations{where} to non-overlapping coordinates, "
        "use fm.direct_labels(ax), or increase ylim/xlim padding."
    )


def _overlap_elements(
    pairs: list[dict[str, Any]],
) -> tuple[list[str], list[dict[str, str | None]], list[str]]:
    """Return (elements, element_locations, panels) for overlapping text pairs."""
    elements: list[str] = []
    located: list[tuple[str, str | None]] = []
    for item in pairs[:3]:
        for txt, pnl in ((item["text_a"], item["panel_a"]), (item["text_b"], item["panel_b"])):
            if txt not in elements:
                elements.append(txt)
                located.append((txt, pnl))
    panels = _distinct_panels(
        pnl for item in pairs for pnl in (item["panel"], item["panel_a"], item["panel_b"])
    )
    return elements, _locate(located), panels


def _check_text_overlaps(visible_texts: list[_TextRecord]) -> CheckResult:
    """Detect colliding visible Text artists with high precision (zero grazing FPs)."""
    severe: list[dict[str, Any]] = []
    moderate: list[dict[str, Any]] = []

    n = len(visible_texts)
    for i in range(n):
        rec_a = visible_texts[i]
        ba = rec_a.bbox
        ax0, ay0, ax1, ay1 = float(ba.x0), float(ba.y0), float(ba.x1), float(ba.y1)
        area_a = max(0.0, ax1 - ax0) * max(0.0, ay1 - ay0)
        if area_a <= 0.0:
            continue

        for j in range(i + 1, n):
            rec_b = visible_texts[j]
            if rec_a.artist is rec_b.artist:
                continue
            bb = rec_b.bbox
            bx0, by0, bx1, by1 = float(bb.x0), float(bb.y0), float(bb.x1), float(bb.y1)
            area_b = max(0.0, bx1 - bx0) * max(0.0, by1 - by0)
            if area_b <= 0.0:
                continue

            iw = min(ax1, bx1) - max(ax0, bx0)
            ih = min(ay1, by1) - max(ay0, by0)
            if iw < 3.0 or ih < 3.0:
                continue

            inter_area = iw * ih
            min_area = min(area_a, area_b)
            ratio = inter_area / min_area if min_area > 0.0 else 0.0
            if ratio < 0.20:
                continue

            panel = rec_a.panel if rec_a.panel == rec_b.panel else (rec_a.panel or rec_b.panel)
            entry = {
                "text_a": rec_a.text,
                "text_b": rec_b.text,
                "role_a": rec_a.role,
                "role_b": rec_b.role,
                "panel": panel,
                "panel_a": rec_a.panel,
                "panel_b": rec_b.panel,
                "overlap_ratio": round(ratio, 3),
                "intersect_px": [round(iw, 1), round(ih, 1)],
            }
            if ratio >= 0.35:
                severe.append(entry)
            else:
                moderate.append(entry)

    severe.sort(key=lambda item: item["overlap_ratio"], reverse=True)
    moderate.sort(key=lambda item: item["overlap_ratio"], reverse=True)

    if severe:
        worst = severe[0]
        pairs = ", ".join(
            f"'{o['text_a']}' vs '{o['text_b']}'" for o in severe[:4]
        )
        extra = f" (+{len(severe) - 4} more)" if len(severe) > 4 else ""
        elements, locations, panels = _overlap_elements(severe)
        return CheckResult(
            rule="text_overlaps",
            status="fail",
            message=f"{len(severe)} severe overlapping text pair(s): {pairs}{extra}",
            details={"overlaps": severe[:20], "moderate_overlaps": moderate[:20]},
            panel=worst["panel"],
            elements=elements,
            fix_hint=_overlap_fix_hint(worst["role_a"], worst["role_b"], worst["panel"]),
            panels=panels,
            element_locations=locations,
        )

    if moderate:
        worst = moderate[0]
        pairs = ", ".join(
            f"'{o['text_a']}' vs '{o['text_b']}'" for o in moderate[:4]
        )
        elements, locations, panels = _overlap_elements(moderate)
        return CheckResult(
            rule="text_overlaps",
            status="warn",
            message=f"{len(moderate)} moderate text overlap(s) (20–35%): {pairs}",
            details={"overlaps": [], "moderate_overlaps": moderate[:20]},
            panel=worst["panel"],
            elements=elements,
            fix_hint=_overlap_fix_hint(worst["role_a"], worst["role_b"], worst["panel"]),
            panels=panels,
            element_locations=locations,
        )

    return CheckResult(
        rule="text_overlaps",
        status="pass",
        message=f"No text collisions across {len(visible_texts)} visible text artists",
        details={"checked_count": len(visible_texts)},
    )


def _check_canvas_clipping(
    fig: Figure,
    visible_texts: list[_TextRecord],
    *,
    margin_px: float = 2.5,
) -> CheckResult:
    """Flag visible text artists extending outside the figure canvas bounds."""
    fig_w_px = float(fig.bbox.width)
    fig_h_px = float(fig.bbox.height)
    clipped: list[dict[str, Any]] = []

    for rec in visible_texts:
        bbox = rec.bbox
        edges: list[tuple[str, float]] = [
            ("left", max(0.0, -float(bbox.x0))),
            ("bottom", max(0.0, -float(bbox.y0))),
            ("right", max(0.0, float(bbox.x1) - fig_w_px)),
            ("top", max(0.0, float(bbox.y1) - fig_h_px)),
        ]
        bad_edges = [(edge, ov) for edge, ov in edges if ov > margin_px]
        if bad_edges:
            worst_edge, max_overflow = max(bad_edges, key=lambda pair: pair[1])
            clipped.append(
                {
                    "text": rec.text,
                    "panel": rec.panel,
                    "edges": [e for e, _ in bad_edges],
                    "worst_edge": worst_edge,
                    "overflow_px": round(max_overflow, 1),
                }
            )

    if clipped:
        sample = ", ".join(
            f"'{c['text']}' ({c['worst_edge']} +{c['overflow_px']} px)" for c in clipped[:4]
        )
        panel = next((c["panel"] for c in clipped if c["panel"]), None)
        elements = [c["text"] for c in clipped[:6]]
        all_edges = sorted({e for c in clipped for e in c["edges"]})
        edges_str = "/".join(all_edges)
        if set(all_edges) & {"top", "bottom"}:
            extra_hint = "increase height_mm or margin_mm, wrap/shorten axis labels, or enable layout='constrained' (fm.Plate)."
        else:
            extra_hint = "move out-of-bounds annotations inside axes, shorten/wrap labels, or enable layout='constrained' (fm.Plate) with larger margin_mm."
        return CheckResult(
            rule="canvas_clipping",
            status="fail",
            message=f"{len(clipped)} text artist(s) clipped at {edges_str} edge: {sample}",
            details={
                "clipped": clipped[:20],
                "canvas_px": [round(fig_w_px, 1), round(fig_h_px, 1)],
            },
            panel=panel,
            elements=elements,
            fix_hint=f"Text clipped at {edges_str} edge: {extra_hint}",
            panels=_distinct_panels(c["panel"] for c in clipped),
            element_locations=_locate((c["text"], c["panel"]) for c in clipped[:6]),
        )

    return CheckResult(
        rule="canvas_clipping",
        status="pass",
        message="All visible text artists fit cleanly inside canvas bounds",
        details={"canvas_px": [round(fig_w_px, 1), round(fig_h_px, 1)]},
    )


def _has_visible_rgba(color: Any) -> bool:
    """Return True if a Matplotlib color specification has non-zero alpha."""
    if color is None:
        return False
    if isinstance(color, str) and color.lower() in {"none", ""}:
        return False
    try:
        rgba = to_rgba(color)
        return float(rgba[3]) > 0.0
    except (TypeError, ValueError):
        return True


def _check_hairline_strokes(
    fig: Figure,
    spec: JournalSpec,
    panel_map: dict[int, str],
) -> CheckResult:
    """Detect visible non-zero strokes thinner than the journal minimum linewidth.

    Skips invisible artists, zero-alpha or zero-linewidth strokes, and scatter
    ``PathCollection`` marker outlines to avoid false positives.
    """
    min_lw = spec.min_linewidth_pt
    eps = 1e-6
    violations: list[dict[str, Any]] = []

    # 1. Spines
    for ax in fig.axes:
        if not ax.get_visible():
            continue
        panel = _artist_panel(ax, panel_map)
        for name, spine in ax.spines.items():
            if not isinstance(spine, Spine) or not spine.get_visible():
                continue
            alpha = spine.get_alpha()
            if alpha is not None and alpha <= 0:
                continue
            if not _has_visible_rgba(spine.get_edgecolor()):
                continue
            lw = float(spine.get_linewidth())
            if 0.0 < lw < min_lw - eps:
                violations.append(
                    {
                        "artist": f"spine:{name}",
                        "linewidth_pt": round(lw, 3),
                        "panel": panel,
                    }
                )

    # 2. Line2D artists (data lines, errorbars, ticks, brackets)
    for line in fig.findobj(Line2D):
        if not line.get_visible():
            continue
        if line.axes is not None and not line.axes.get_visible():
            continue
        alpha = line.get_alpha()
        if alpha is not None and alpha <= 0:
            continue
        ls = line.get_linestyle()
        if ls in ("None", "none", "", " "):
            continue
        if not _has_visible_rgba(line.get_color()):
            continue
        xdata = line.get_xdata(orig=False)
        if xdata is not None and len(xdata) == 0:
            continue
        lw = float(line.get_linewidth())
        if 0.0 < lw < min_lw - eps:
            label = line.get_label()
            desc = f"Line2D({label})" if label and not label.startswith("_") else "Line2D"
            violations.append(
                {
                    "artist": desc,
                    "linewidth_pt": round(lw, 3),
                    "panel": _artist_panel(line, panel_map),
                }
            )

    # 3. LineCollection and PolyCollection strokes (explicitly excluding PathCollection scatter)
    for col in fig.findobj(Collection):
        if not isinstance(col, (LineCollection, PolyCollection)):
            continue
        if not col.get_visible():
            continue
        if col.axes is not None and not col.axes.get_visible():
            continue
        alpha = col.get_alpha()
        if alpha is not None and alpha <= 0:
            continue

        if isinstance(col, LineCollection):
            colors = col.get_colors()
            has_stroke_color = len(colors) > 0 and bool(np.any(colors[:, 3] > 0))
        else:
            edgecolors = col.get_edgecolors()
            has_stroke_color = len(edgecolors) > 0 and bool(np.any(edgecolors[:, 3] > 0))

        if not has_stroke_color:
            continue

        lws = col.get_linewidths()
        for lw_val in np.atleast_1d(lws):
            lw = float(lw_val)
            if 0.0 < lw < min_lw - eps:
                violations.append(
                    {
                        "artist": type(col).__name__,
                        "linewidth_pt": round(lw, 3),
                        "panel": _artist_panel(col, panel_map),
                    }
                )
                break

    if violations:
        min_found = min(v["linewidth_pt"] for v in violations)
        sample = ", ".join(
            f"{v['artist']} ({v['linewidth_pt']} pt)" for v in violations[:4]
        )
        panel = next((v["panel"] for v in violations if v["panel"]), None)
        elements = [f"{v['artist']} ({v['linewidth_pt']} pt)" for v in violations[:6]]
        return CheckResult(
            rule="hairline_strokes",
            status="warn",
            message=(
                f"{len(violations)} stroke(s) below {min_lw:.2f} pt minimum "
                f"(thinnest {min_found:.2f} pt): {sample}"
            ),
            details={"min_linewidth_pt": min_lw, "violations": violations[:20]},
            panel=panel,
            elements=elements,
            fix_hint=(
                f"Increase linewidth from {min_found:.2f} pt to >= {min_lw:.2f} pt "
                f"(recommended axes={spec.axes_linewidth_pt:.2f} pt, "
                f"data={spec.data_linewidth_pt:.2f} pt)."
            ),
            panels=_distinct_panels(v["panel"] for v in violations),
            element_locations=_locate(
                zip(elements, (v["panel"] for v in violations[:6]), strict=True)
            ),
        )

    return CheckResult(
        rule="hairline_strokes",
        status="pass",
        message=f"All visible strokes meet >= {min_lw:.2f} pt print minimum",
        details={"min_linewidth_pt": min_lw},
    )


def _maps_data_to_color(mappable: ScalarMappable) -> bool:
    """Return True if ``mappable`` actually maps scalar data through its colormap.

    A ScalarMappable always carries a colormap (``rcParams['image.cmap']`` by
    default), even a solid-colour ``scatter(color=...)`` or an RGB(A) ``imshow``
    whose colormap is never drawn. Only artists with a non-empty scalar data
    array use the colormap.
    """
    try:
        arr = mappable.get_array()
    except (AttributeError, TypeError, ValueError):
        return False
    if arr is None:
        return False
    size = int(np.size(arr))
    if size == 0:
        return False
    if np.ndim(arr) >= 3:
        # RGB(A) image data is drawn directly; the colormap is not applied.
        return False
    # A fully masked array draws nothing through the colormap.
    return not (np.ma.isMaskedArray(arr) and bool(np.ma.getmaskarray(arr).all()))


def _check_colormaps(fig: Figure, panel_map: dict[int, str]) -> CheckResult:
    """Reject banned non-perceptual colormap names (jet, rainbow, hsv, etc.).

    Only artists that map data to colour are considered. This is a name check
    against a blocklist; it does not measure perceptual uniformity.
    """
    found_cmaps: set[str] = set()
    banned_hits: list[dict[str, Any]] = []

    seen_ids: set[int] = set()
    mappables: list[ScalarMappable] = list(
        fig.findobj(lambda artist: isinstance(artist, ScalarMappable))
    )
    for ax in fig.axes:
        for obj in list(ax.images) + list(ax.collections):
            if isinstance(obj, ScalarMappable):
                mappables.append(obj)

    for mappable in mappables:
        mid = id(mappable)
        if mid in seen_ids:
            continue
        seen_ids.add(mid)
        if hasattr(mappable, "get_visible") and not mappable.get_visible():
            continue
        if not _maps_data_to_color(mappable):
            continue

        cmap = mappable.get_cmap()
        if cmap is None:
            continue
        cmap_name = str(cmap.name)
        base_name = cmap_name.removesuffix("_r")
        found_cmaps.add(cmap_name)

        if base_name.lower() in BANNED_COLORMAPS:
            banned_hits.append(
                {
                    "artist": type(mappable).__name__,
                    "colormap": cmap_name,
                    "panel": _artist_panel(mappable, panel_map),
                }
            )

    if banned_hits:
        bad_names = sorted({h["colormap"] for h in banned_hits})
        panel = next((h["panel"] for h in banned_hits if h["panel"]), None)
        # One location per distinct (colormap, panel) pair, in element order.
        located: list[tuple[str, str | None]] = []
        for name in bad_names:
            for hit in banned_hits:
                pair = (name, hit["panel"])
                if hit["colormap"] == name and pair not in located:
                    located.append(pair)
        return CheckResult(
            rule="colormaps",
            status="fail",
            message=(
                f"Banned non-perceptual colormap(s) detected: {', '.join(bad_names)} "
                "(use viridis, magma, cividis, or plasma)"
            ),
            details={"banned": banned_hits, "colormaps": sorted(found_cmaps)},
            panel=panel,
            elements=bad_names,
            fix_hint=(
                f"Replace cmap={bad_names[0]!r} with 'viridis', 'magma', or 'cividis'."
            ),
            panels=_distinct_panels(h["panel"] for h in banned_hits),
            element_locations=_locate(located),
        )

    if found_cmaps:
        msg = (
            f"Name check only: no banned rainbow colormap among {len(found_cmaps)} in use "
            f"({', '.join(sorted(found_cmaps))}); perceptual uniformity not measured"
        )
    else:
        msg = "No colormapped data artists found (pass)"

    return CheckResult(
        rule="colormaps",
        status="pass",
        message=msg,
        details={"colormaps": sorted(found_cmaps), "method": "name_blocklist"},
    )


def _check_vector_fonts(spec: JournalSpec, fig: Figure | None = None) -> CheckResult:
    """Predict, from the *current* rcParams, whether a plain save emits editable fonts.

    This is only a prediction about a future ``fig.savefig``: ``pdf.fonttype`` and
    ``svg.fonttype`` are read at save time, and figmint's own exporters
    (``fm.save_figure``, ``plate.save``, ``figmint run --bundle``) always force
    ``pdf.fonttype=42`` / ``svg.fonttype='none'``. The authoritative check is
    :func:`preflight_pdf` on the exported file.

    * rcParams already editable -> pass.
    * Figure built by figmint (``fm.Plate`` / ``fm.figure``, tagged with
      ``_figmint_journal``) -> pass: its export path forces Type 42, so a warning
      would only send an agent chasing a non-problem.
    * Any other figure -> warn, because a plain ``fig.savefig`` with these
      rcParams really would embed Type 3 / outlined text.
    """
    pdf_ft = plt.rcParams.get("pdf.fonttype")
    svg_ft = plt.rcParams.get("svg.fonttype")
    issues: list[str] = []
    if pdf_ft != 42:
        issues.append(f"pdf.fonttype={pdf_ft!r} (expected 42)")
    if svg_ft != "none":
        issues.append(f"svg.fonttype={svg_ft!r} (expected 'none')")

    details: dict[str, Any] = {
        "pdf.fonttype": pdf_ft,
        "svg.fonttype": svg_ft,
        "basis": "current_rcparams",
        "authoritative": False,
    }

    if not issues:
        return CheckResult(
            rule="vector_fonts",
            status="pass",
            message="Editable vector fonts active (pdf.fonttype=42, svg.fonttype='none')",
            details=details,
        )

    figmint_journal = getattr(fig, "_figmint_journal", None) if fig is not None else None
    if figmint_journal:
        details["basis"] = "figmint_export"
        return CheckResult(
            rule="vector_fonts",
            status="pass",
            message=(
                "figmint-built figure: fm.save_figure / plate.save / figmint run --bundle "
                "force pdf.fonttype=42 and svg.fonttype='none' "
                f"(current rcParams: {'; '.join(issues)} only affect a raw fig.savefig)"
            ),
            details=details,
        )

    return CheckResult(
        rule="vector_fonts",
        status="warn",
        message=(
            f"Current rcParams would embed non-editable text on a plain fig.savefig: "
            f"{'; '.join(issues)}. Exports through fm.save_figure / plate.save / "
            "figmint run --bundle force Type 42 regardless; preflight_pdf on the "
            "exported PDF is authoritative"
        ),
        details=details,
        panel=None,
        elements=issues,
        fix_hint=(
            "No plotting change needed if you export with fm.save_figure(...), plate.save(...) "
            "or figmint run --bundle (they force pdf.fonttype=42). If you save with plain "
            f"fig.savefig, call fm.apply({spec.name!r}) or set "
            "plt.rcParams['pdf.fonttype'] = 42 and plt.rcParams['svg.fonttype'] = 'none' "
            "before saving."
        ),
    )


_LAYOUT_COLLAPSE_PATTERNS = (
    "constrained_layout not applied",
    "collapsed to zero",
    "tight_layout not applied",
)

_LINESTYLE_CANON = {
    "-": "-",
    "solid": "-",
    "--": "--",
    "dashed": "--",
    ":": ":",
    "dotted": ":",
    "-.": "-.",
    "dashdot": "-.",
}


def _normalize_linestyle(ls: Any) -> str:
    if isinstance(ls, tuple):
        return str(ls)
    return _LINESTYLE_CANON.get(str(ls).strip().lower(), str(ls))


def _normalize_marker(marker: Any) -> str:
    if marker is None:
        return ""
    s = str(marker).strip()
    return "" if s in {"", "None", "none", " "} else s


def _check_layout_collapse(
    fig: Figure,
    layout_warnings: list[str],
    panel_map: dict[int, str],
) -> CheckResult:
    """Detect collapsed constrained/tight layouts or zero-size visible axes."""
    collapsed_axes: list[dict[str, Any]] = []
    for ax in fig.axes:
        if not ax.get_visible():
            continue
        bbox = ax.bbox
        w_px = float(bbox.width)
        h_px = float(bbox.height)
        if not (np.isfinite(w_px) and np.isfinite(h_px)) or w_px < 4.0 or h_px < 4.0:
            panel = _artist_panel(ax, panel_map)
            collapsed_axes.append(
                {
                    "panel": panel,
                    "width_px": round(w_px, 1) if np.isfinite(w_px) else None,
                    "height_px": round(h_px, 1) if np.isfinite(h_px) else None,
                }
            )

    if layout_warnings or collapsed_axes:
        panels = _distinct_panels(item["panel"] for item in collapsed_axes)
        elements: list[str] = []
        located: list[tuple[str, str | None]] = []
        for item in collapsed_axes[:6]:
            desc = (
                f"{item['panel'] or 'axes'} ({item['width_px']}x{item['height_px']} px)"
            )
            elements.append(desc)
            located.append((desc, item["panel"]))
        for msg in layout_warnings[:3]:
            short = msg.strip().replace("\n", " ")[:72]
            if short not in elements:
                elements.append(short)
                located.append((short, panels[0] if panels else None))

        reasons: list[str] = []
        if layout_warnings:
            reasons.append(f"{len(layout_warnings)} layout-collapse warning(s)")
        if collapsed_axes:
            reasons.append(f"{len(collapsed_axes)} collapsed axes (< 4 px)")
        return CheckResult(
            rule="layout_collapse",
            status="fail",
            message=f"Layout engine failed to fit panels: {', '.join(reasons)}",
            details={
                "warnings": layout_warnings[:10],
                "collapsed_axes": collapsed_axes[:10],
            },
            panel=panels[0] if panels else None,
            elements=elements,
            fix_hint=(
                "Matplotlib could not fit constrained_layout (axes collapsed). "
                "Use uniform mosaic column splits, reduce gap_mm, shorten long y-axis "
                "labels, or increase Plate(..., height_mm=...)."
            ),
            panels=panels,
            element_locations=_locate(located),
        )

    return CheckResult(
        rule="layout_collapse",
        status="pass",
        message="All visible panels laid out without constrained_layout collapse",
        details={"axes_count": sum(1 for ax in fig.axes if ax.get_visible())},
    )


def _check_color_separation(
    fig: Figure,
    panel_map: dict[int, str],
) -> CheckResult:
    """Clarity warning: flag same-style labeled series indistinguishable in CVD/grayscale."""
    confusable: list[dict[str, Any]] = []

    for ax in fig.axes:
        if not ax.get_visible() or getattr(ax, "_colorbar", None) is not None:
            continue
        series: list[tuple[str, str, str, str, np.ndarray]] = []
        seen_labels: set[str] = set()
        for line in ax.get_lines():
            if not line.get_visible():
                continue
            alpha = line.get_alpha()
            if alpha is not None and alpha <= 0:
                continue
            ls = _normalize_linestyle(line.get_linestyle())
            if ls in {"none", "", " "}:
                continue
            label = str(line.get_label() or "").strip()
            if not label or label.startswith("_") or label in seen_labels:
                continue
            try:
                rgb = np.array(to_rgb(line.get_color()), dtype=np.float64)
                hex_c = to_hex(rgb)
            except (TypeError, ValueError):
                continue
            seen_labels.add(label)
            series.append((label, hex_c, ls, _normalize_marker(line.get_marker()), rgb))

        if len(series) < 2:
            continue

        panel = _artist_panel(ax, panel_map)
        rgb_stack = np.stack([item[4] for item in series], axis=0)[np.newaxis, :, :]
        gray = simulate_cvd(rgb_stack, "grayscale")[0, :, 0]
        deut = simulate_cvd(rgb_stack, "deuteranopia")[0]
        prot = simulate_cvd(rgb_stack, "protanopia")[0]

        for i in range(len(series)):
            for j in range(i + 1, len(series)):
                lbl_a, hex_a, ls_a, mk_a, _ = series[i]
                lbl_b, hex_b, ls_b, mk_b, _ = series[j]
                # Skip when lines already carry distinct linestyle or marker encoding.
                if ls_a != ls_b or mk_a != mk_b:
                    continue
                gray_diff = float(abs(gray[i] - gray[j]))
                deut_dist = float(np.linalg.norm(deut[i] - deut[j]))
                prot_dist = float(np.linalg.norm(prot[i] - prot[j]))
                min_cvd = min(deut_dist, prot_dist)
                if gray_diff < 0.05 or min_cvd < 0.12:
                    confusable.append(
                        {
                            "panel": panel,
                            "series_a": lbl_a,
                            "hex_a": hex_a,
                            "series_b": lbl_b,
                            "hex_b": hex_b,
                            "gray_delta": round(gray_diff, 3),
                            "min_cvd_dist": round(min_cvd, 3),
                        }
                    )

    if confusable:
        first = confusable[0]
        sample = ", ".join(
            f"'{c['series_a']}' ({c['hex_a']}) vs '{c['series_b']}' ({c['hex_b']})"
            for c in confusable[:3]
        )
        elements = [f"{c['series_a']} vs {c['series_b']}" for c in confusable[:6]]
        panels = _distinct_panels(c["panel"] for c in confusable)
        where = f" in panel '{first['panel']}'" if first["panel"] else ""
        return CheckResult(
            rule="color_separation",
            status="warn",
            message=(
                f"{len(confusable)} same-style series pair(s) have low CVD/grayscale "
                f"separation: {sample}"
            ),
            details={"confusable_pairs": confusable[:20]},
            panel=first["panel"],
            elements=elements,
            fix_hint=(
                f"Distinguish '{first['series_a']}' and '{first['series_b']}'{where} "
                "using a dashed linestyle (ls='--'), distinct marker, or high-contrast "
                "palette (palette='okabe_ito')."
            ),
            panels=panels,
            element_locations=_locate(
                zip(elements, (c["panel"] for c in confusable[:6]), strict=True)
            ),
        )

    return CheckResult(
        rule="color_separation",
        status="pass",
        message="Labeled line series are distinguishable under CVD and grayscale",
        details={},
    )


def _check_clarity_metadata(
    fig: Figure,
    panel_map: dict[int, str],
) -> CheckResult:
    """Clarity warning: flag colormapped panels without colorbars or completely unlabeled axes."""
    missing_cbars: list[dict[str, Any]] = []
    unlabeled_axes: list[dict[str, Any]] = []

    for ax in fig.axes:
        if not ax.get_visible():
            continue
        if getattr(ax, "_colorbar", None) is not None or ax.get_label() == "<colorbar>":
            continue
        if getattr(ax, "_figmint_decorative", False):
            continue
        pos = ax.get_position()
        is_inset = getattr(ax, "_parent_axes", None) is not None
        panel = _artist_panel(ax, panel_map)

        # 1. Colormapped data panel missing a colorbar (skip thin decorative strips & insets).
        if not is_inset and pos.height >= 0.12 and pos.width >= 0.08:
            scalar_mappables = [
                obj
                for obj in list(ax.images) + list(ax.collections)
                if isinstance(obj, ScalarMappable)
                and obj.get_visible()
                and _maps_data_to_color(obj)
            ]
            if scalar_mappables and all(
                getattr(m, "colorbar", None) is None for m in scalar_mappables
            ):
                missing_cbars.append(
                    {
                        "panel": panel,
                        "colormap": str(scalar_mappables[0].get_cmap().name),
                    }
                )

        # 2. Primary quantitative plot axes missing BOTH xlabel and ylabel.
        if (
            not is_inset
            and ax.axison
            and not ax.images
            and not getattr(ax, "_figmint_has_scalebar", False)
            and (ax.lines or ax.collections or ax.patches)
        ):
            # A hidden axis draws no tick labels even though each label still
            # reports itself visible, so it cannot count as an unlabeled scale.
            has_xticks = ax.xaxis.get_visible() and any(
                t.label1.get_visible() and t.label1.get_text().strip()
                for t in ax.xaxis.get_major_ticks()
            )
            has_yticks = ax.yaxis.get_visible() and any(
                t.label1.get_visible() and t.label1.get_text().strip()
                for t in ax.yaxis.get_major_ticks()
            )
            # fm.explain() names the measure in a horizontal line above the
            # plot instead of a rotated axis label.
            named_above = bool(getattr(ax, "_figmint_measure_label", None))
            if (
                has_xticks
                and has_yticks
                and not named_above
                and not ax.get_xlabel().strip()
                and not ax.get_ylabel().strip()
            ):
                unlabeled_axes.append({"panel": panel})

    if missing_cbars or unlabeled_axes:
        parts: list[str] = []
        hints: list[str] = []
        elements: list[str] = []
        located: list[tuple[str, str | None]] = []

        if missing_cbars:
            c_panels = ", ".join(c["panel"] or "axes" for c in missing_cbars[:4])
            parts.append(
                f"{len(missing_cbars)} colormapped panel(s) lack a colorbar ({c_panels})"
            )
            hints.append(
                "Add a colorbar via cbar = fig.colorbar(im, ax=ax); fm.style_colorbar(cbar, label='...')."
            )
            for c in missing_cbars[:4]:
                el = f"missing colorbar ({c['colormap']})"
                elements.append(el)
                located.append((el, c["panel"]))

        if unlabeled_axes:
            u_panels = ", ".join(u["panel"] or "axes" for u in unlabeled_axes[:4])
            parts.append(
                f"{len(unlabeled_axes)} data panel(s) have neither xlabel nor ylabel ({u_panels})"
            )
            hints.append(
                "Add descriptive axis labels with units via ax.set_xlabel(...) and ax.set_ylabel(...)."
            )
            for u in unlabeled_axes[:4]:
                el = f"missing axis labels ({u['panel'] or 'axes'})"
                elements.append(el)
                located.append((el, u["panel"]))

        all_panels = _distinct_panels(
            [c["panel"] for c in missing_cbars] + [u["panel"] for u in unlabeled_axes]
        )
        return CheckResult(
            rule="clarity_metadata",
            status="warn",
            message="; ".join(parts),
            details={
                "missing_colorbars": missing_cbars,
                "unlabeled_axes": unlabeled_axes,
            },
            panel=all_panels[0] if all_panels else None,
            elements=elements,
            fix_hint=" ".join(hints),
            panels=all_panels,
            element_locations=_locate(located),
        )

    return CheckResult(
        rule="clarity_metadata",
        status="pass",
        message="Data panels include axis labels and colorbars where colormapped",
        details={},
    )


def _check_bar_baseline_nonzero(
    fig: Figure,
    panel_map: dict[int, str],
) -> CheckResult:
    """Tufte lie-factor guard: warn when positive bar charts truncate the zero baseline."""
    truncated: list[dict[str, Any]] = []

    for ax in fig.axes:
        if not ax.get_visible() or getattr(ax, "_colorbar", None) is not None:
            continue
        bar_containers = [c for c in ax.containers if isinstance(c, BarContainer)]
        if not bar_containers:
            continue

        orientation = getattr(bar_containers[0], "orientation", "vertical")
        values: list[float] = []
        bases: list[float] = []
        for bc in bar_containers:
            for rect in bc.patches:
                if not rect.get_visible():
                    continue
                if orientation == "horizontal":
                    values.append(float(rect.get_width()))
                    bases.append(float(rect.get_x()))
                else:
                    values.append(float(rect.get_height()))
                    bases.append(float(rect.get_y()))

        if not values:
            continue
        # Only apply to non-negative bars anchored at 0 (skip diverging +/- or stacked offsets)
        if min(values) < 0.0 or max(values) <= 0.0 or min(bases) < -1e-9:
            continue

        scale = ax.get_xscale() if orientation == "horizontal" else ax.get_yscale()
        if scale == "log":
            continue

        lo, hi = ax.get_xlim() if orientation == "horizontal" else ax.get_ylim()
        axis_min = min(float(lo), float(hi))
        max_val = max(values)
        if axis_min > 0.01 * max_val:
            panel = _artist_panel(ax, panel_map)
            truncated.append(
                {
                    "panel": panel,
                    "axis": "x" if orientation == "horizontal" else "y",
                    "baseline": round(axis_min, 3),
                    "max_bar": round(max_val, 3),
                }
            )

    if truncated:
        first = truncated[0]
        panels = _distinct_panels(t["panel"] for t in truncated)
        elements = [
            f"{t['panel'] or 'axes'} ({t['axis']}_min={t['baseline']})" for t in truncated[:6]
        ]
        where = f" in panel '{first['panel']}'" if first["panel"] else ""
        setter = "set_xlim(left=0)" if first["axis"] == "x" else "set_ylim(bottom=0)"
        return CheckResult(
            rule="bar_baseline_nonzero",
            status="warn",
            message=(
                f"{len(truncated)} positive bar panel(s) truncate the zero baseline: "
                + ", ".join(elements[:4])
            ),
            details={"truncated_bars": truncated},
            panel=first["panel"],
            elements=elements,
            fix_hint=(
                f"Call ax.{setter}{where} so bar length stays proportional to magnitude "
                "(or switch to a dot/range plot if zero is outside the meaningful scale)."
            ),
            panels=panels,
            element_locations=_locate(
                zip(elements, (t["panel"] for t in truncated[:6]), strict=True)
            ),
        )

    return CheckResult(
        rule="bar_baseline_nonzero",
        status="pass",
        message="Bar chart baselines include zero (no truncated-axis lie factor)",
        details={},
    )


def _check_chartjunk_hints(
    fig: Figure,
    panel_map: dict[int, str],
) -> CheckResult:
    """Tufte data-ink guard: warn on boxed legends, heavy grids, or spaghetti crowding."""
    boxed_legends: list[dict[str, Any]] = []
    heavy_grids: list[dict[str, Any]] = []
    spaghetti_axes: list[dict[str, Any]] = []

    for ax in fig.axes:
        if not ax.get_visible() or getattr(ax, "_colorbar", None) is not None:
            continue
        panel = _artist_panel(ax, panel_map)

        # 1. Boxed legend frame (allow borderless pure-white readability halos over images)
        leg = ax.get_legend()
        if leg is not None and leg.get_visible() and leg.get_frame_on():
            frame = leg.get_frame()
            ec = frame.get_edgecolor()
            fc = frame.get_facecolor()
            lw = float(frame.get_linewidth())
            has_visible_border = (
                lw > 0
                and _has_visible_rgba(ec)
                and min(to_rgb(ec)) < 0.94
            )
            has_tinted_fill = (
                _has_visible_rgba(fc)
                and float(to_rgba(fc)[3]) > 0.15
                and min(to_rgb(fc)) < 0.94
            )
            if has_visible_border or has_tinted_fill:
                boxed_legends.append({"panel": panel})

        # 2. Heavy dark gridlines (ignore white heatmap cell dividers!)
        for axis in (ax.xaxis, ax.yaxis):
            for gl in axis.get_gridlines():
                if not gl.get_visible():
                    continue
                alpha = gl.get_alpha()
                if alpha is not None and alpha <= 0:
                    continue
                lw = float(gl.get_linewidth())
                if lw <= 0.65:
                    continue
                try:
                    rgb = to_rgb(gl.get_color())
                except (TypeError, ValueError):
                    continue
                # Skip crisp white cell dividers drawn by style_heatmap()
                if min(rgb) > 0.94:
                    continue
                heavy_grids.append({"panel": panel, "linewidth_pt": round(lw, 2)})
                break

        # 3. Spaghetti crowding: >= 6 distinct labeled data series on a single axes
        labeled_series: set[str] = set()
        for line in ax.get_lines():
            if not line.get_visible():
                continue
            ls = _normalize_linestyle(line.get_linestyle())
            if ls in {"none", "", " "}:
                continue
            lbl = str(line.get_label() or "").strip()
            if lbl and not lbl.startswith("_"):
                labeled_series.add(lbl)
        if len(labeled_series) >= 6:
            spaghetti_axes.append({"panel": panel, "series_count": len(labeled_series)})

    if boxed_legends or heavy_grids or spaghetti_axes:
        parts: list[str] = []
        hints: list[str] = []
        elements: list[str] = []
        located: list[tuple[str, str | None]] = []

        if boxed_legends:
            parts.append(f"{len(boxed_legends)} boxed legend frame(s)")
            hints.append("Remove legend boxes (frameon=False) or use fm.direct_labels(ax).")
            for b in boxed_legends[:4]:
                el = f"boxed legend ({b['panel'] or 'axes'})"
                elements.append(el)
                located.append((el, b["panel"]))

        if heavy_grids:
            parts.append(f"{len(heavy_grids)} heavy gridline axes (> 0.65 pt)")
            hints.append("Use fm.subtle_grid(ax, lw=0.45) instead of heavy dark gridlines.")
            for g in heavy_grids[:4]:
                el = f"heavy grid ({g['linewidth_pt']} pt)"
                elements.append(el)
                located.append((el, g["panel"]))

        if spaghetti_axes:
            parts.append(
                f"{len(spaghetti_axes)} crowded panel(s) with >=6 labeled curves"
            )
            hints.append(
                "Split crowded spaghetti lines into shared-axis small multiples with fm.ghost_context(...)."
            )
            for s in spaghetti_axes[:4]:
                el = f"{s['series_count']} curves ({s['panel'] or 'axes'})"
                elements.append(el)
                located.append((el, s["panel"]))

        all_panels = _distinct_panels(
            [b["panel"] for b in boxed_legends]
            + [g["panel"] for g in heavy_grids]
            + [s["panel"] for s in spaghetti_axes]
        )
        return CheckResult(
            rule="chartjunk_hints",
            status="warn",
            message=f"Tufte data-ink hint(s): {'; '.join(parts)}",
            details={
                "boxed_legends": boxed_legends,
                "heavy_grids": heavy_grids,
                "spaghetti_axes": spaghetti_axes,
            },
            panel=all_panels[0] if all_panels else None,
            elements=elements,
            fix_hint=" ".join(hints),
            panels=all_panels,
            element_locations=_locate(located),
        )

    return CheckResult(
        rule="chartjunk_hints",
        status="pass",
        message="Clean data-ink ratio (no boxed legends, heavy grids, or spaghetti crowding)",
        details={},
    )


def _check_text_on_data(
    fig: Figure,
    visible_texts: list[_TextRecord],
    panel_map: dict[int, str],
) -> CheckResult:
    """Clarity warning: detect in-axes annotations/legends printed over foreground data ink."""
    candidates: list[_TextRecord] = []
    for rec in visible_texts:
        if rec.role not in {"annotation", "legend"}:
            continue
        artist = rec.artist
        ax = getattr(artist, "axes", None)
        if ax is None or not ax.get_visible():
            continue
        if getattr(ax, "_colorbar", None) is not None or ax.images:
            continue
        if getattr(artist, "_figmint_scalebar", False) or getattr(
            artist, "_figmint_heatmap_text", False
        ):
            continue
        # Skip text explicitly shielded by a background halo / pill patch
        if artist.get_bbox_patch() is not None:
            continue
        # Only inspect text positioned inside the plot data box
        if not rec.bbox.overlaps(ax.bbox):
            continue
        candidates.append(rec)

    if not candidates or fig.canvas is None:
        return CheckResult(
            rule="text_on_data",
            status="pass",
            message="No in-axes annotations or legends collide with foreground data ink",
            details={"checked_count": len(candidates)},
        )

    # Temporarily hide candidate text and legend internals (without hiding the Legend
    # container itself so constrained_layout geometry never shifts), draw once, copy
    # the pixel buffer, and restore before inspecting foreground ink.
    to_hide: list[Any] = [rec.artist for rec in candidates]
    for leg in list(fig.legends) + [ax.get_legend() for ax in fig.axes]:
        if leg is not None and leg.get_visible():
            to_hide.extend(leg.get_texts())
            to_hide.append(leg.get_title())
            frame = leg.get_frame()
            if frame is not None:
                to_hide.append(frame)
            handles = getattr(leg, "legend_handles", None) or getattr(leg, "legendHandles", [])
            for h in handles:
                if h is not None and hasattr(h, "get_visible") and hasattr(h, "set_visible"):
                    to_hide.append(h)

    seen_hide: set[int] = set()
    saved_vis: list[tuple[Any, bool]] = []
    for obj in to_hide:
        oid = id(obj)
        if oid not in seen_hide:
            seen_hide.add(oid)
            saved_vis.append((obj, bool(obj.get_visible())))

    try:
        for obj, _ in saved_vis:
            obj.set_visible(False)
        fig.canvas.draw()
        # Copy the buffer before finally() redraws the text back into Agg's live memory.
        buf = np.asarray(fig.canvas.buffer_rgba())[..., :3].copy()
    except Exception:  # noqa: BLE001
        return CheckResult(
            rule="text_on_data",
            status="pass",
            message="Skipped pixel text-on-data check on non-Agg canvas",
            details={},
        )
    finally:
        for obj, vis in saved_vis:
            obj.set_visible(vis)
        with contextlib.suppress(Exception):
            fig.canvas.draw()

    img_h, img_w = buf.shape[:2]
    sx = img_w / max(float(fig.bbox.width), 1.0)
    sy = img_h / max(float(fig.bbox.height), 1.0)
    hits: list[dict[str, Any]] = []
    for rec in candidates:
        ax = rec.artist.axes
        if ax is None:
            continue
        # Intersect text bbox with the axes plot area (shrink 1 px to ignore edge touches)
        ix0 = max(int(np.floor(max(rec.bbox.x0, ax.bbox.x0) * sx)) + 1, 0)
        ix1 = min(int(np.ceil(min(rec.bbox.x1, ax.bbox.x1) * sx)) - 1, img_w)
        # Matplotlib display y=0 is bottom; buffer row 0 is top
        iy0 = max(int(np.floor(img_h - min(rec.bbox.y1, ax.bbox.y1) * sy)) + 1, 0)
        iy1 = min(int(np.ceil(img_h - max(rec.bbox.y0, ax.bbox.y0) * sy)) - 1, img_h)
        if ix1 - ix0 < 4 or iy1 - iy0 < 4:
            continue

        patch = buf[iy0:iy1, ix0:ix1]
        # Count saturated foreground data ink (ignore pale CI ribbons/gridlines/pastel fills >= 185)
        dark_mask = np.min(patch, axis=2) < 185
        ink_frac = float(np.mean(dark_mask))
        if ink_frac > 0.22:
            hits.append(
                {
                    "text": rec.text,
                    "panel": rec.panel or _artist_panel(ax, panel_map),
                    "ink_fraction": round(ink_frac, 3),
                }
            )

    if hits:
        hits.sort(key=lambda h: h["ink_fraction"], reverse=True)
        first = hits[0]
        sample = ", ".join(f"'{h['text']}' ({int(h['ink_fraction'] * 100)}% ink)" for h in hits[:4])
        elements = [h["text"] for h in hits[:6]]
        panels = _distinct_panels(h["panel"] for h in hits)
        where = f" in panel '{first['panel']}'" if first["panel"] else ""
        return CheckResult(
            rule="text_on_data",
            status="warn",
            message=f"{len(hits)} annotation/legend text(s) overlap foreground data: {sample}",
            details={"overlaps": hits[:20]},
            panel=first["panel"],
            elements=elements,
            fix_hint=(
                f"Move '{first['text']}'{where} into open whitespace, use fm.direct_labels(ax), "
                "or add a subtle white bbox halo."
            ),
            panels=panels,
            element_locations=_locate((h["text"], h["panel"]) for h in hits[:6]),
        )

    return CheckResult(
        rule="text_on_data",
        status="pass",
        message=f"All {len(candidates)} in-axes annotation/legend text(s) sit clear of data ink",
        details={"checked_count": len(candidates)},
    )


def _safe_draw_and_collect_texts(
    fig: Figure,
    panel_map: dict[int, str],
) -> tuple[list[_TextRecord], list[str]]:
    """Draw the figure canvas, capture layout-collapse warnings, and collect visible texts.

    On macOS, FreeType can raise ``RuntimeError: failed to load glyph`` for
    sub-5 pt text rendered with ``Helvetica.ttc``. When that happens, we
    temporarily substitute ``Arial``/``DejaVu Sans`` for sub-5 pt artists
    strictly during layout/bbox measurement and immediately restore their
    original font properties so every check inspects the true artist state.
    """
    if fig.canvas is None:
        FigureCanvasAgg(fig)

    def _draw_capturing_warnings() -> list[str]:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            fig.canvas.draw()
        collapse_msgs: list[str] = []
        for w in caught:
            msg = str(w.message)
            low = msg.lower()
            if any(pat in low for pat in _LAYOUT_COLLAPSE_PATTERNS):
                collapse_msgs.append(msg)
        return collapse_msgs

    try:
        layout_warnings = _draw_capturing_warnings()
        renderer = fig.canvas.get_renderer()
        return _iter_visible_texts(fig, renderer, panel_map), layout_warnings
    except RuntimeError:
        saved_families: list[tuple[Text, list[str]]] = []
        for text_artist in fig.findobj(Text):
            if float(text_artist.get_fontsize()) < 5.0:
                orig = list(text_artist.get_fontfamily())
                saved_families.append((text_artist, orig))
                text_artist.set_fontfamily(["Arial", "DejaVu Sans"])
        try:
            layout_warnings = _draw_capturing_warnings()
            renderer = fig.canvas.get_renderer()
            return _iter_visible_texts(fig, renderer, panel_map), layout_warnings
        finally:
            for text_artist, orig in saved_families:
                text_artist.set_fontfamily(orig)


def preflight_figure(
    fig: Figure,
    journal: str | JournalSpec = "nature",
    *,
    strict: bool = False,
) -> PreflightReport:
    """Run all automated publication-compliance and clarity checks on a Matplotlib Figure."""
    spec = get_spec(journal)
    panel_map = _build_axes_panel_map(fig)
    visible_texts, layout_warnings = _safe_draw_and_collect_texts(fig, panel_map)

    width_mm = in_to_mm(float(fig.get_figwidth()))
    height_mm = in_to_mm(float(fig.get_figheight()))

    checks = [
        _check_dimensions(width_mm, height_mm, spec),
        _check_layout_collapse(fig, layout_warnings, panel_map),
        _check_font_sizes(visible_texts, spec),
        _check_font_family(visible_texts, spec),
        _check_text_overlaps(visible_texts),
        _check_canvas_clipping(fig, visible_texts),
        _check_hairline_strokes(fig, spec, panel_map),
        _check_colormaps(fig, panel_map),
        _check_vector_fonts(spec, fig),
        _check_color_separation(fig, panel_map),
        _check_clarity_metadata(fig, panel_map),
        _check_bar_baseline_nonzero(fig, panel_map),
        _check_chartjunk_hints(fig, panel_map),
        _check_text_on_data(fig, visible_texts, panel_map),
    ]

    report = PreflightReport(
        journal=spec.name,
        checks=checks,
        width_mm=width_mm,
        height_mm=height_mm,
        spec_version=getattr(spec, "spec_version", ""),
        spec_source_url=getattr(spec, "source_url", ""),
    )

    if strict and not report.passed:
        raise ValueError(report.summary())

    return report


def _resolve_pdf_obj(obj: Any) -> Any:
    """Safely dereference pypdf IndirectObjects."""
    if hasattr(obj, "get_object"):
        return obj.get_object()
    return obj


def _collect_pdf_fonts(
    resources: Any,
    seen: set[int],
    fonts_out: list[dict[str, str]],
) -> None:
    """Recursively collect /Font dictionaries from a PDF /Resources dict (including XObjects)."""
    res = _resolve_pdf_obj(resources)
    if not isinstance(res, dict):
        return

    res_id = id(res)
    if res_id in seen:
        return
    seen.add(res_id)

    font_dict = _resolve_pdf_obj(res.get("/Font"))
    if isinstance(font_dict, dict):
        for font_key, font_ref in font_dict.items():
            font_obj = _resolve_pdf_obj(font_ref)
            if not isinstance(font_obj, dict):
                continue
            subtype = str(_resolve_pdf_obj(font_obj.get("/Subtype", "")))
            basefont = str(_resolve_pdf_obj(font_obj.get("/BaseFont", "")))
            fonts_out.append(
                {
                    "key": str(font_key),
                    "subtype": subtype,
                    "basefont": basefont.lstrip("/"),
                }
            )

    xobjects = _resolve_pdf_obj(res.get("/XObject"))
    if isinstance(xobjects, dict):
        for xobj_ref in xobjects.values():
            xobj = _resolve_pdf_obj(xobj_ref)
            if isinstance(xobj, dict) and "/Resources" in xobj:
                _collect_pdf_fonts(xobj["/Resources"], seen, fonts_out)


def preflight_pdf(
    path: str | Path,
    journal: str | JournalSpec = "nature",
) -> PreflightReport:
    """Inspect an exported PDF directly for physical dimensions, fonts, and file size."""
    pdf_path = Path(path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    spec = get_spec(journal)
    reader = PdfReader(str(pdf_path))
    if not reader.pages:
        raise ValueError(f"PDF contains no pages: {pdf_path}")

    first_page = reader.pages[0]
    mediabox = first_page.mediabox
    width_pt = float(mediabox.width)
    height_pt = float(mediabox.height)
    width_mm = width_pt * MM_PER_INCH / 72.0
    height_mm = height_pt * MM_PER_INCH / 72.0

    # Collect all fonts across all pages
    fonts: list[dict[str, str]] = []
    seen: set[int] = set()
    for page in reader.pages:
        if "/Resources" in page:
            _collect_pdf_fonts(page["/Resources"], seen, fonts)

    # 1. Dimensions check
    dim_check = _check_dimensions(width_mm, height_mm, spec)

    # 2. Type 3 font check (canonical rule name: vector_fonts)
    type3_fonts = [f for f in fonts if f["subtype"] == "/Type3"]
    if type3_fonts:
        keys = [f["key"] for f in type3_fonts[:6]]
        type3_check = CheckResult(
            rule="vector_fonts",
            status="fail",
            message=(
                f"Found {len(type3_fonts)} Type 3 outlined font(s) ({', '.join(keys)}); "
                "export with pdf.fonttype=42 for editable TrueType fonts"
            ),
            details={"type3_fonts": type3_fonts, "all_fonts": fonts},
            panel=None,
            elements=keys,
            fix_hint=(
                "Export via fm.save_figure(...) or set plt.rcParams['pdf.fonttype'] = 42 "
                "to embed editable TrueType fonts instead of Type 3 outlines."
            ),
        )
    else:
        unique_names = sorted({f["basefont"] or f["subtype"] for f in fonts})
        names_str = ", ".join(unique_names[:5]) if unique_names else "none"
        type3_check = CheckResult(
            rule="vector_fonts",
            status="pass",
            message=f"Zero Type 3 fonts; {len(fonts)} editable font ref(s) ({names_str})",
            details={"all_fonts": fonts},
        )

    # 3. Serif font name check
    serif_fonts = [
        f for f in fonts if f["basefont"] and _is_serif_font_name(f["basefont"])
    ]
    if serif_fonts:
        bad = sorted({f["basefont"] for f in serif_fonts})
        family_check = CheckResult(
            rule="font_family",
            status="warn",
            message=f"Serif font(s) embedded in PDF: {', '.join(bad)} (sans-serif required)",
            details={"serif_fonts": bad},
            panel=None,
            elements=bad[:6],
            fix_hint=(
                f"Build the figure inside fm.use({spec.name!r}) or fm.Plate(journal={spec.name!r}) "
                "so embedded PDF fonts are sans-serif."
            ),
        )
    else:
        unique_clean = sorted(
            {re.sub(r"^[A-Z]{6}\+", "", f["basefont"]) for f in fonts if f["basefont"]}
        )
        names_str = ", ".join(unique_clean[:4]) if unique_clean else "none"
        family_check = CheckResult(
            rule="font_family",
            status="pass",
            message=f"All embedded PDF fonts are sans-serif ({names_str})",
            details={"fonts": unique_clean},
        )

    # 4. File size check
    size_bytes = pdf_path.stat().st_size
    size_mb = size_bytes / (1024.0 * 1024.0)
    if size_mb > 10.0:
        size_check = CheckResult(
            rule="file_size",
            status="warn",
            message=(
                f"PDF file size {size_mb:.2f} MB exceeds 10.0 MB recommendation "
                "(use rasterize_heavy for dense data)"
            ),
            details={"size_bytes": size_bytes, "size_mb": round(size_mb, 3)},
            panel=None,
            elements=[f"{size_mb:.2f} MB"],
            fix_hint=(
                "Pass rasterize_above=10_000 to plate.save(...) / fm.save_figure(...) "
                "to rasterize dense scatter/heatmap layers while keeping text vector."
            ),
        )
    else:
        size_kb = size_bytes / 1024.0
        size_check = CheckResult(
            rule="file_size",
            status="pass",
            message=f"PDF file size {size_kb:.1f} KB ({size_mb:.2f} MB) <= 10.0 MB",
            details={"size_bytes": size_bytes, "size_mb": round(size_mb, 3)},
        )

    return PreflightReport(
        journal=spec.name,
        checks=[dim_check, type3_check, family_check, size_check],
        width_mm=width_mm,
        height_mm=height_mm,
        spec_version=getattr(spec, "spec_version", ""),
        spec_source_url=getattr(spec, "source_url", ""),
    )
