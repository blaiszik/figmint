"""Epistemic / slant auditing and four-level semantic narratives for ``mint.explain``.

Implements:
- Four-level semantic narrative (Lundgard & Satyanarayan, IEEE VIS 2021):
  :func:`build_narrative` produces structured L1 (encoded construction), L2
  (statistical facts), L3 (perceptual/pattern facts), L4 (domain takeaway),
  and a compact reader-first ``summary`` string.
- Tightly scoped epistemic / slant audit (Kong, Liu & Karahalios, CHI 2018):
  :func:`audit_epistemic` emits advisory ``severity="warning"`` issues only for
  two high-precision failure modes (``claim_overstates_uncertainty`` and
  ``claim_number_mismatch``) with near-zero false positives.
"""

from __future__ import annotations

import math
import numbers
import re
from collections.abc import Mapping, Sequence
from typing import Any

# --------------------------------------------------------------------------- #
# Panel accessors (work with both Panel instances and plain dict specs/summaries)
# --------------------------------------------------------------------------- #


def _pget(panel: Any, key: str, default: Any = None) -> Any:
    if isinstance(panel, Mapping):
        return panel.get(key, default)
    return getattr(panel, key, default)


def _pspec(panel: Any) -> Mapping[str, Any]:
    spec = _pget(panel, "spec")
    if isinstance(spec, Mapping):
        return spec
    if isinstance(panel, Mapping):
        return panel
    return {}


def _pfacts(panel: Any) -> list[str]:
    facts = _pget(panel, "facts") or []
    return [str(f) for f in facts if isinstance(f, str) and f.strip()]


def _is_finite_number(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, numbers.Real):
        return math.isfinite(float(value))
    # Support numpy scalar types without importing numpy
    cls_name = type(value).__module__
    if cls_name.startswith("numpy") and not isinstance(value, (str, bytes)):
        try:
            fval = float(value)
            return math.isfinite(fval)
        except (TypeError, ValueError):
            return False
    return False


# --------------------------------------------------------------------------- #
# Part 1: Four-Level Semantic Narrative (Lundgard & Satyanarayan, VIS 2021)
# --------------------------------------------------------------------------- #

# Patterns classifying computed panel facts into L3 (perceptual/cognitive patterns)
# vs L2 (concrete statistical facts).
_L3_PATTERN_RE = re.compile(
    r"(?:"
    r"\N{RIGHTWARDS ARROW}|"  # trajectory / before->after shift
    r"\bbefore\s+.+\bfrom it on\b|"
    r"\bcrosses?\b|"
    r"\bstay(?:s)?\s+(?:above|below)\b|"
    r"\bPareto frontier\b|"
    r"\bleads\s+\d+\s+of\s+\d+|"
    r"\bleader\b|"
    r"\bnext highest\b|"
    r"\bnext lowest\b|"
    r"\brank\s+1\s+of\b|"
    r"\bfar from the rest\b|"
    r"\bpeak bin\b|"
    r"\boverlaps?\b|"
    r"\bdoes not overlap\b|"
    r"\bevery\s+.+\s+value\s+is\s+(?:above|below)\b|"
    r"\ball but\s+\d+\s+of\s+\d+\s+.+\s+lie\s+(?:above|below)\b|"
    r"\bPearson r\s*=|"
    r"\br\s*=\s*[\-\N{MINUS SIGN}]?\d|"
    r"\bfitted line\b|"
    r"\blog\N{SUBSCRIPT ONE}\N{SUBSCRIPT ZERO}\s+slope\b|"
    r"y\s*\N{PROPORTIONAL TO}\s*x|"
    r"\bpooled across groups\b|"
    r"\bstrongest off-diagonal\b|"
    r"\blargest off-diagonal\b|"
    r"\blargest change:|"
    r"\blargest\s+.+\s+gain:|"
    r"\blargest\s+(?:positive\s+driver|negative\s+drag|drop):|"
    r"\blongest\s+stage:|"
    r"\blinear\s+fit\s+slope\b|"
    r"\bpeak\s+\d+\s+stages\s+overlapping\b|"
    r"\b\d+\s+up,\s+\d+\s+down\b|"
    r"\bchange(?:s)?\s+by\s+.+\s+from first to last\b|"
    r"\bend at\s+.+\s+their first values\b|"
    r"\bpeak within\s+.+\s+of their own medians\b|"
    r"\btop\s+\d+\s+together:|"
    r"\btogether:\s+\d+(?:\.\d+)?%"
    r")",
    re.IGNORECASE,
)

# Metadata/housekeeping facts that belong in L2 but are skipped in the compact summary
# when higher-signal facts exist.
_META_FACT_RE = re.compile(
    r"^(?:"
    r"intervals read as\b|"
    r"bands read as\b|"
    r"binned into\b|"
    r"\d+\s+(?:rows|categories)\s*\N{MULTIPLICATION SIGN}\s*\d+\s+(?:columns|series)$|"
    r"diagonal is\b|"
    r"\d+\s+empty cell|"
    r"\d+\s+of\s+\d+\s+cells empty"
    r")",
    re.IGNORECASE,
)


def _label_has_unit(label: str, unit: str) -> bool:
    u = unit.strip()
    if not u:
        return True
    return bool(re.search(rf"[(\[]\s*{re.escape(u)}\s*[)\]]\s*$", label.strip()))


def _table_columns(spec: Mapping[str, Any]) -> list[str]:
    """The columns a table shows: ``interval={col: ("lo", "hi")}`` bound columns are hidden."""
    hidden: set[str] = set()
    interval = spec.get("interval")
    if isinstance(interval, Mapping):
        for bounds in interval.values():
            if (
                isinstance(bounds, Sequence)
                and not isinstance(bounds, (str, bytes))
                and len(bounds) == 2
                and all(isinstance(b, str) for b in bounds)
            ):
                hidden.update(bounds)
    found: list[str] = []
    cols = spec.get("columns")
    rows = spec.get("rows")
    if isinstance(cols, Sequence) and not isinstance(cols, (str, bytes)):
        found = [str(c) for c in cols if str(c).strip()]
    elif isinstance(rows, Mapping):
        found = [str(k) for k in rows]
    elif isinstance(rows, Sequence) and not isinstance(rows, (str, bytes)) and rows:
        first = rows[0]
        if isinstance(first, Mapping):
            found = [str(k) for k in first]
    return [c for c in found if c not in hidden]


def _describe_panel_l1(panel: Any) -> str:
    kind = str(_pget(panel, "kind", "panel") or "panel")
    label = _pget(panel, "label")
    unit = _pget(panel, "unit")
    spec = _pspec(panel)

    parts: list[str] = []
    if kind == "table":
        cols = _table_columns(spec)
        if cols:
            shown = cols[:4]
            if len(cols) > 4:
                shown.append(f"+{len(cols) - 4} more")
            parts.append(", ".join(shown))
        elif label:
            parts.append(str(label))
    elif kind == "relate":
        x_label = spec.get("x_label")
        y_label = spec.get("y_label") or label
        if x_label and y_label:
            parts.append(f"{x_label} vs {y_label}")
        elif y_label:
            parts.append(str(y_label))
        elif x_label:
            parts.append(str(x_label))
        if spec.get("log_x") and spec.get("log_y"):
            parts.append("log-log")
        elif spec.get("log_x"):
            parts.append("log x")
        elif spec.get("log_y"):
            parts.append("log y")
        if spec.get("frontier"):
            parts.append("Pareto frontier")
        if spec.get("facet"):
            parts.append("faceted")
    elif kind == "trend":
        if label:
            parts.append(str(label))
            if unit and not _label_has_unit(str(label), str(unit)):
                parts.append(str(unit))
        elif unit:
            parts.append(str(unit))
        x_label = spec.get("x_label")
        if x_label:
            if parts:
                parts[-1] = f"{parts[-1]} vs {x_label}"
            else:
                parts.append(str(x_label))
        if spec.get("log") and spec.get("log_x"):
            parts.append("log-log")
        elif spec.get("log"):
            parts.append("log y")
        elif spec.get("log_x"):
            parts.append("log x")
        if spec.get("facet"):
            parts.append("faceted")
    elif kind == "matrix":
        if label:
            parts.append(str(label))
        if unit and (not label or not _label_has_unit(str(label), str(unit))):
            parts.append(str(unit))
        rows = spec.get("rows")
        cols = spec.get("cols")
        if isinstance(rows, Sequence) and isinstance(cols, Sequence):
            parts.append(f"{len(rows)}\N{MULTIPLICATION SIGN}{len(cols)}")
        tri = spec.get("triangle")
        if isinstance(tri, str) and tri:
            parts.append(f"{tri} triangle")
    elif kind == "change":
        if label:
            parts.append(str(label))
        if unit and (not label or not _label_has_unit(str(label), str(unit))):
            parts.append(str(unit))
        pair_labels = spec.get("labels")
        if (
            isinstance(pair_labels, Sequence)
            and not isinstance(pair_labels, (str, bytes))
            and len(pair_labels) == 2
        ):
            parts.append(f"{pair_labels[0]} \N{RIGHTWARDS ARROW} {pair_labels[1]}")
    elif kind == "distribution":
        if label:
            parts.append(str(label))
        if unit and (not label or not _label_has_unit(str(label), str(unit))):
            parts.append(str(unit))
        if spec.get("bins") is not None:
            parts.append("histogram")
        if spec.get("log"):
            parts.append("log scale")
        if spec.get("facet"):
            parts.append("faceted")
    elif kind == "waterfall":
        if label:
            parts.append(str(label))
        if unit and (not label or not _label_has_unit(str(label), str(unit))):
            parts.append(str(unit))
        steps = spec.get("steps")
        if isinstance(steps, Mapping):
            parts.append(f"{len(steps)} steps")
    elif kind == "timeline":
        x_label = spec.get("x_label") or label
        tl_unit = unit or spec.get("unit")
        if x_label:
            parts.append(str(x_label))
        if tl_unit and (not x_label or not _label_has_unit(str(x_label), str(tl_unit))):
            parts.append(str(tl_unit))
        spans = spec.get("spans")
        if isinstance(spans, Sequence) and not isinstance(spans, (str, bytes)):
            parts.append(f"{len(spans)} stages")
    elif kind == "flow":
        if label:
            parts.append(str(label))
        if unit and (not label or not _label_has_unit(str(label), str(unit))):
            parts.append(str(unit))
        stages = spec.get("stages")
        if isinstance(stages, Sequence) and not isinstance(stages, (str, bytes)):
            parts.append(f"{len(stages)} stages")
    elif kind == "custom":
        desc = _pget(panel, "describe")
        if label:
            parts.append(str(label))
        if unit and (not label or not _label_has_unit(str(label), str(unit))):
            parts.append(str(unit))
        if not parts and desc:
            parts.append(str(desc))
    else:
        # compare, share, or unknown future form
        if label:
            parts.append(str(label))
        if unit and (not label or not _label_has_unit(str(label), str(unit))):
            parts.append(str(unit))
        if spec.get("log"):
            parts.append("log scale")
        if spec.get("facet"):
            parts.append("faceted")

    if not parts:
        desc = _pget(panel, "describe")
        if desc:
            parts.append(str(desc))
    return f"{kind} ({', '.join(parts)})" if parts else kind


def build_narrative(
    takeaway: str,
    panels: Mapping[str, Any],
    *,
    subtitle: str | None = None,
    source: str | None = None,
) -> dict[str, Any]:
    """Build a four-level semantic narrative (Lundgard & Satyanarayan, IEEE VIS 2021).

    Returns a dict with keys:
    - ``"L1"``: concise structural construction summary (panel count, kinds, labels/units)
    - ``"L2"``: ``list[str]`` of concrete statistical facts (extrema, ranges, CIs, counts, deltas)
    - ``"L3"``: ``list[str]`` of perceptual/pattern facts (trends, crossings, shifts, leaders,
      Pareto frontier, correlations, overlap/clusters)
    - ``"L4"``: domain takeaway sentence (+ subtitle scope if present)
    - ``"summary"``: compact reader-first string prioritizing L4 + top L3/L2 facts
    """
    n_panels = len(panels)
    panel_noun = "panel" if n_panels == 1 else "panels"
    l1_descs = [_describe_panel_l1(p) for p in panels.values()]
    l1 = f"{n_panels} {panel_noun}: {'; '.join(l1_descs)}" if l1_descs else "0 panels"

    l2: list[str] = []
    l3: list[str] = []
    multi = n_panels > 1
    for key, panel in panels.items():
        prefix = f"[{key}] " if multi else ""
        for fact in _pfacts(panel):
            tagged = f"{prefix}{fact}"
            if _L3_PATTERN_RE.search(fact):
                l3.append(tagged)
            else:
                l2.append(tagged)

    clean_takeaway = " ".join(str(takeaway).split()).strip()
    l4_parts: list[str] = []
    if clean_takeaway:
        l4_parts.append(clean_takeaway.rstrip(".") + ".")
    if subtitle and str(subtitle).strip():
        clean_sub = " ".join(str(subtitle).split()).strip()
        l4_parts.append(clean_sub.rstrip(".") + ".")
    l4 = " ".join(l4_parts)

    # Compact reader-first summary: L4 + up to 3 high-signal facts (L3 first, then L2) + source.
    summary_parts: list[str] = []
    if l4:
        summary_parts.append(l4)

    def _strip_prefix(text: str) -> str:
        return re.sub(r"^\[[^\]]+\]\s*", "", text)

    top_l3 = [f for f in l3 if not _META_FACT_RE.search(_strip_prefix(f))][:2]
    top_l2 = [f for f in l2 if not _META_FACT_RE.search(_strip_prefix(f))][:2]
    highlights = [*top_l3, *top_l2][:3]
    if not highlights:
        highlights = (l3 + l2)[:2]
    for fact in highlights:
        summary_parts.append(fact.rstrip(".") + ".")
    if source and str(source).strip():
        clean_src = " ".join(str(source).split()).strip().rstrip(".")
        summary_parts.append(f"Source: {clean_src}.")

    return {
        "L1": l1,
        "L2": l2,
        "L3": l3,
        "L4": l4,
        "summary": " ".join(summary_parts),
    }


# --------------------------------------------------------------------------- #
# Part 2: Tightly Scoped Epistemic / Slant Audit (Kong et al., CHI 2018)
# --------------------------------------------------------------------------- #


def _advisory(
    rule: str,
    message: str,
    fix_hint: str,
    *,
    panel: str | None = None,
) -> dict[str, Any]:
    return {
        "rule": rule,
        "severity": "warning",
        "panel": panel,
        "message": message,
        "fix_hint": fix_hint,
    }


# Tight allowlist of explicit strong certainty / significance claims.
_STRONG_CERTAINTY_RE = re.compile(
    r"\b("
    r"statistically\s+significant|"
    r"proves|proven|disproves|disproven|"
    r"conclusively|conclusive|"
    r"unambiguously|unambiguous|"
    r"decisively|decisive|"
    r"definitively|definitive|"
    r"clearly\s+(?:beats?|outperforms?|hurts?|lower|higher|better|worse|exceeds?|leads?|wins?|reduces?|increases?|improves?|cuts?|drops?)|"
    r"outside\s+(?:seed\s+)?noise|"
    r"beyond\s+(?:seed\s+)?noise|"
    r"beyond\s+doubt"
    r")\b",
    re.IGNORECASE,
)

_OVERLAP_WORD_RE = re.compile(r"\boverlaps?\b", re.IGNORECASE)
_OVERLAP_NEGATED_RE = re.compile(
    r"\b(?:no|not|never|non|do\s+not|does\s+not|did\s+not|without)\s+overlaps?\b"
    r"|\bclear\s+of\b"
    r"|\boutside\b",
    re.IGNORECASE,
)
_SMALL_N_CAUTION_RE = re.compile(
    r"\b(?:rough\s+estimate|small\s+n|quartiles\s+are\s+not\s+meaningful)\b",
    re.IGNORECASE,
)


def _fact_has_conflicting_uncertainty(fact: str) -> str | None:
    """Return a concise reason string if ``fact`` reports overlapping intervals or small-n caution."""
    if _SMALL_N_CAUTION_RE.search(fact):
        return "small-n rough estimate"
    for clause in fact.split(";"):
        if _OVERLAP_WORD_RE.search(clause) and not _OVERLAP_NEGATED_RE.search(clause):
            return "overlapping intervals"
    return None


def _check_overstates_uncertainty(
    takeaway: str,
    panels: Mapping[str, Any],
) -> list[dict[str, Any]]:
    match = _STRONG_CERTAINTY_RE.search(takeaway)
    if match is None:
        return []
    phrase = match.group(0)

    conflicts: list[tuple[str, str, str]] = []
    for key, panel in panels.items():
        for fact in _pfacts(panel):
            reason = _fact_has_conflicting_uncertainty(fact)
            if reason is not None:
                conflicts.append((str(key), reason, fact))
                break

    if not conflicts:
        return []

    reasons = list(dict.fromkeys(r for _, r, _ in conflicts))
    panel_keys = [k for k, _, _ in conflicts]
    panel_ref = panel_keys[0] if len(panel_keys) == 1 else None
    sample_fact = conflicts[0][2]
    reason_text = " and ".join(reasons)
    return [
        _advisory(
            "claim_overstates_uncertainty",
            f"Takeaway uses strong certainty wording ({phrase!r}), while panel facts indicate "
            f"{reason_text} ({sample_fact}).",
            "Hedge the takeaway wording to match the overlapping intervals or small n "
            "(e.g. 'tends to', 'suggests', or state the observed difference directly), "
            "or report the formal statistical test and p-value in note=.",
            panel=panel_ref,
        )
    ]


# Hedge markers in takeaway: if present, skip claim_number_mismatch completely.
_HEDGE_RE = re.compile(
    r"[~≈]"
    r"|\b(?:about|approx\.?|approximately|roughly|nearly|around|almost|over|under)\b",
    re.IGNORECASE,
)

# Change verbs: used only to avoid bogus 2-item 50/50 share matching on relative-drop claims.
_CHANGE_CLAIM_RE = re.compile(
    r"\b(?:drop(?:s|ped)?|cut(?:s)?|fell|fall(?:s)?|decline(?:s|d)?|decreas(?:e|es|ed)|"
    r"reduc(?:e|es|ed|tion)|less|lower|below|gain(?:s|ed)?|rise(?:s)?|rose|"
    r"increas(?:e|es|ed)|higher|more|above|faster|slower|up|down)\b",
    re.IGNORECASE,
)

# Explicit percentage claim (excludes confidence/interval level descriptors like "95% CI").
_PCT_CLAIM_RE = re.compile(
    r"(?<![A-Za-z0-9_.~≈<>≤≥±/])"
    r"(?P<num>\d+(?:,\d{3})*(?:\.\d+)?)\s*%"
    r"(?!\s*(?:CI\b|confidence\b|credible\b|prediction\b|interval\b|quantile\b|percentile\b|IQR\b))",
    re.IGNORECASE,
)

# Explicit fold/ratio claim ("4x", "2.3×") with value > 1.2 (excludes "10×10", "GPT-4x", "v2x").
_FOLD_CLAIM_RE = re.compile(
    r"(?<![A-Za-z0-9_.~≈<>≤≥±/])"
    r"(?<![A-Za-z]-)"
    r"(?P<num>\d+(?:,\d{3})*(?:\.\d+)?)\s*[x\N{MULTIPLICATION SIGN}]"
    r"(?![A-Za-z0-9_])",
    re.IGNORECASE,
)

_SUP_TRANS = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹⁻⁺", "0123456789-+")
_FACT_SCI_RE = re.compile(
    r"[\-\N{MINUS SIGN}+]?(\d+(?:,\d{3})*(?:\.\d+)?)\s*\N{MULTIPLICATION SIGN}\s*10([⁻⁺]?[⁰¹²³⁴⁵⁶⁷⁸⁹]+)"
)
_FACT_NUM_RE = re.compile(
    r"(?<![A-Za-z_])[\-\N{MINUS SIGN}+]?(\d+(?:,\d{3})*(?:\.\d+)?)(?:[eE]([+\-]?\d+))?"
)


def _parse_fact_numbers(facts: Sequence[str]) -> list[float]:
    out: list[float] = []
    for text in facts:
        cleaned = text
        for m in _FACT_SCI_RE.finditer(text):
            try:
                mant = float(m.group(1).replace(",", ""))
                exp = int(m.group(2).translate(_SUP_TRANS))
                val = mant * (10.0**exp)
                if math.isfinite(val):
                    out.append(abs(val))
            except ValueError:
                pass
        cleaned = _FACT_SCI_RE.sub(" ", cleaned)
        for m in _FACT_NUM_RE.finditer(cleaned):
            try:
                num_str = m.group(1).replace(",", "")
                if m.group(2):
                    num_str = f"{num_str}e{m.group(2)}"
                val = float(num_str)
                if math.isfinite(val):
                    out.append(abs(val))
            except ValueError:
                pass
    return out


def _dedup_sample(values: Sequence[float], limit: int = 80) -> list[float]:
    """Deduplicate finite numbers and downsample evenly if very large."""
    uniq = sorted({round(v, 10) for v in values if math.isfinite(v)})
    if len(uniq) <= limit:
        return uniq
    # Always preserve extremes + evenly spaced quantiles
    idxs = [round(i * (len(uniq) - 1) / (limit - 1)) for i in range(limit)]
    return [uniq[i] for i in dict.fromkeys(idxs)]


def _extract_numeric_seq(obj: Any) -> list[float]:
    if isinstance(obj, Sequence) and not isinstance(obj, (str, bytes)):
        return [float(v) for v in obj if _is_finite_number(v)]
    return []


def _stats_summary(vals: Sequence[float]) -> list[float]:
    if not vals:
        return []
    s = sorted(vals)
    n = len(s)
    mid = s[n // 2] if n % 2 else 0.5 * (s[n // 2 - 1] + s[n // 2])
    mean = sum(s) / n
    out = [s[0], s[-1], mid, mean]
    if n >= 4:
        out.extend([s[n // 4], s[(3 * n) // 4]])
    return out


def _collect_panel_groups(
    panel: Any,
) -> tuple[list[float], list[list[float]], list[list[float]], list[float]]:
    """Return ``(direct_values, metric_groups, ratio_only_groups, share_candidates)``.

    - ``direct_values``: all individual finite magnitudes from spec + parsed facts.
    - ``metric_groups``: same-unit numeric groups from panel data (for pairwise diffs,
      percentage changes, sums, and ratios).
    - ``ratio_only_groups``: auxiliary numeric sets (parsed fact numbers such as fitted
      slopes, and numeric x axes) used for fold/ratio matching without conflating mixed
      units into bogus percentage-change pairs.
    - ``share_candidates``: explicit percentage shares (0..100) for share/part-to-whole
      panels and reference-threshold splits.
    """
    kind = str(_pget(panel, "kind", "") or "")
    spec = _pspec(panel)
    direct: list[float] = []
    groups: list[list[float]] = []
    ratio_groups: list[list[float]] = []
    shares: list[float] = []

    fact_nums = _parse_fact_numbers(_pfacts(panel))
    direct.extend(fact_nums)
    if fact_nums:
        ratio_groups.append(_dedup_sample(fact_nums, limit=60))

    # Reference value if present
    ref = spec.get("reference")
    ref_val: float | None = None
    if _is_finite_number(ref):
        ref_val = float(ref)
        direct.append(abs(ref_val))
    elif (
        isinstance(ref, Sequence)
        and not isinstance(ref, (str, bytes))
        and ref
        and _is_finite_number(ref[0])
    ):
        ref_val = float(ref[0])
        direct.append(abs(ref_val))

    if kind == "compare":
        vals = spec.get("values")
        boost = spec.get("boost")
        if isinstance(vals, Mapping):
            # Single-series or grouped compare
            flat: list[float] = []
            for k, v in vals.items():
                if _is_finite_number(v):
                    fv = float(v)
                    flat.append(fv)
                    direct.append(abs(fv))
                    if isinstance(boost, Mapping) and _is_finite_number(boost.get(k)):
                        bv = float(boost[k])
                        direct.append(abs(bv))
                        direct.append(abs(fv + bv))
                        flat.append(fv + bv)
                elif isinstance(v, Mapping):
                    sub = [float(sv) for sv in v.values() if _is_finite_number(sv)]
                    if sub:
                        groups.append(sub)
                        flat.extend(sub)
                        direct.extend(abs(sv) for sv in sub)
            if flat:
                groups.append(flat)
                # Also collect error bounds
        err = spec.get("error")
        if isinstance(err, Mapping) and spec.get("facet"):
            # compare(facet=True): {category: {item: interval}}, one level deeper
            err = {
                f"{k}/{sk}": sv
                for k, v in err.items()
                if isinstance(v, Mapping)
                for sk, sv in v.items()
            }
        if isinstance(err, Mapping):
            for ev in err.values():
                if _is_finite_number(ev):
                    direct.append(abs(float(ev)))
                elif isinstance(ev, Sequence) and not isinstance(ev, (str, bytes)):
                    direct.extend(abs(float(x)) for x in ev if _is_finite_number(x))

    elif kind == "share":
        parts = spec.get("parts")
        if isinstance(parts, Mapping):
            pvals = [float(v) for v in parts.values() if _is_finite_number(v) and float(v) >= 0]
            if pvals:
                total = sum(pvals)
                direct.extend(pvals)
                direct.append(total)
                groups.append(pvals)
                if total > 0:
                    for v in pvals:
                        shares.append(100.0 * v / total)
                    desc = sorted(pvals, reverse=True)
                    running = 0.0
                    for v in desc:
                        running += v
                        shares.append(100.0 * running / total)
                    hl = spec.get("highlight")
                    hl_list = [hl] if isinstance(hl, str) else (list(hl) if isinstance(hl, Sequence) else [])
                    hl_sum = sum(
                        float(parts[k])
                        for k in hl_list
                        if k in parts and _is_finite_number(parts[k])
                    )
                    if hl_sum > 0:
                        shares.append(100.0 * hl_sum / total)

    elif kind == "change":
        before = spec.get("before")
        after = spec.get("after")
        if isinstance(before, Mapping) and isinstance(after, Mapping):
            all_v: list[float] = []
            for k in before:
                bv, av = before.get(k), after.get(k)
                if _is_finite_number(bv) and _is_finite_number(av):
                    fb, fa = float(bv), float(av)
                    groups.append([fb, fa])
                    all_v.extend([fb, fa])
                    direct.extend([abs(fb), abs(fa), abs(fa - fb)])
            if all_v:
                groups.append(all_v)

    elif kind == "trend":
        series = spec.get("series")
        all_ends: list[float] = []
        if isinstance(series, Mapping):
            for seq in series.values():
                nums = _extract_numeric_seq(seq)
                if nums:
                    stats = _stats_summary(nums)
                    sample = _dedup_sample([*nums, *stats], limit=40)
                    groups.append(sample)
                    direct.extend(abs(v) for v in sample)
                    all_ends.extend([nums[0], nums[-1]])
        points = spec.get("points")
        if isinstance(points, Mapping):
            for x_groups in points.values():
                if isinstance(x_groups, Sequence) and not isinstance(x_groups, (str, bytes)):
                    means: list[float] = []
                    for bucket in x_groups:
                        bnums = _extract_numeric_seq(bucket)
                        if bnums:
                            means.append(sum(bnums) / len(bnums))
                    if means:
                        groups.append(means)
                        direct.extend(abs(v) for v in means)
                        all_ends.extend([means[0], means[-1]])
        if all_ends:
            groups.append(all_ends)
        xs = _extract_numeric_seq(spec.get("x"))
        if xs:
            x_sample = _dedup_sample(xs, limit=30)
            direct.extend(abs(v) for v in x_sample)
            ratio_groups.append(x_sample)
        band = spec.get("band")
        if isinstance(band, Mapping):
            for bv in band.values():
                if _is_finite_number(bv):
                    direct.append(abs(float(bv)))
                elif isinstance(bv, Sequence) and not isinstance(bv, (str, bytes)):
                    for item in bv:
                        if _is_finite_number(item):
                            direct.append(abs(float(item)))
                        else:
                            direct.extend(abs(v) for v in _extract_numeric_seq(item))

    elif kind == "distribution":
        grp_map = spec.get("groups")
        if isinstance(grp_map, Mapping) and spec.get("facet") and spec.get("bins") is None:
            # distribution(facet=...): {facet: {group: [obs]}}, one level deeper
            grp_map = {
                f"{k}/{g}": obs
                for k, v in grp_map.items()
                if isinstance(v, Mapping)
                for g, obs in v.items()
            }
        if isinstance(grp_map, Mapping):
            centers: list[float] = []
            for seq in grp_map.values():
                nums = _extract_numeric_seq(seq)
                if nums:
                    stats = _stats_summary(nums)
                    direct.extend(abs(v) for v in stats)
                    centers.extend(stats)
                    groups.append(_dedup_sample([*nums, *stats], limit=40))
                    if ref_val is not None:
                        above_pct = 100.0 * sum(1 for v in nums if v > ref_val) / len(nums)
                        below_pct = 100.0 * sum(1 for v in nums if v < ref_val) / len(nums)
                        shares.extend([above_pct, below_pct])
            if centers:
                groups.append(centers)

    elif kind == "relate":
        xs = _extract_numeric_seq(spec.get("x"))
        ys = _extract_numeric_seq(spec.get("y"))
        for arr in (xs, ys):
            if arr:
                sample = _dedup_sample([*arr, *_stats_summary(arr)], limit=45)
                groups.append(sample)
                direct.extend(abs(v) for v in sample)

    elif kind == "matrix":
        mat = spec.get("values")
        if isinstance(mat, Sequence) and not isinstance(mat, (str, bytes)):
            flat_m: list[float] = []
            for row in mat:
                rnums = _extract_numeric_seq(row)
                if rnums:
                    flat_m.extend(rnums)
                    direct.append(abs(sum(rnums) / len(rnums)))
            if flat_m:
                sample = _dedup_sample(flat_m, limit=50)
                groups.append(sample)
                direct.extend(abs(v) for v in sample)

    elif kind == "table":
        rows = spec.get("rows")
        col_buckets: dict[str, list[float]] = {}
        if isinstance(rows, Sequence) and not isinstance(rows, (str, bytes)):
            for row in rows:
                if isinstance(row, Mapping):
                    for ck, cv in row.items():
                        if _is_finite_number(cv):
                            col_buckets.setdefault(str(ck), []).append(float(cv))
                elif isinstance(row, Sequence) and not isinstance(row, (str, bytes)):
                    for idx, cv in enumerate(row):
                        if _is_finite_number(cv):
                            col_buckets.setdefault(str(idx), []).append(float(cv))
        elif isinstance(rows, Mapping):
            for ck, seq in rows.items():
                nums = _extract_numeric_seq(seq)
                if nums:
                    col_buckets[str(ck)] = nums
        for col_nums in col_buckets.values():
            groups.append(col_nums)
            direct.extend(abs(v) for v in col_nums)

    elif kind == "waterfall":
        steps = spec.get("steps")
        if isinstance(steps, Mapping):
            s_val = 0.0
            start_raw = spec.get("start")
            if _is_finite_number(start_raw):
                s_val = float(start_raw)
                direct.append(abs(s_val))
            elif (
                isinstance(start_raw, Sequence)
                and not isinstance(start_raw, (str, bytes))
                and len(start_raw) == 2
                and _is_finite_number(start_raw[1])
            ):
                s_val = float(start_raw[1])
                direct.append(abs(s_val))
            deltas = [float(v) for v in steps.values() if _is_finite_number(v)]
            if deltas:
                running = s_val
                levels = [s_val] if start_raw is not None else [0.0]
                for d in deltas:
                    running += d
                    levels.append(running)
                    direct.append(abs(d))
                    direct.append(abs(running))
                net = sum(deltas)
                direct.extend([abs(net), abs(running)])
                groups.append([abs(d) for d in deltas])
                groups.append(levels)
                pos_sum = sum(d for d in deltas if d > 0)
                neg_sum = sum(-d for d in deltas if d < 0)
                abs_sum = sum(abs(d) for d in deltas)
                for denom in (abs(net), pos_sum, neg_sum, abs_sum, abs(s_val)):
                    if denom > 0:
                        for d in deltas:
                            shares.append(100.0 * abs(d) / denom)
                        shares.append(100.0 * abs(net) / denom)

    elif kind == "timeline":
        spans = spec.get("spans")
        if isinstance(spans, Sequence) and not isinstance(spans, (str, bytes)):
            starts: list[float] = []
            ends: list[float] = []
            durs: list[float] = []
            by_group: dict[str, float] = {}
            for item in spans:
                if (
                    isinstance(item, Sequence)
                    and not isinstance(item, (str, bytes))
                    and len(item) >= 3
                    and _is_finite_number(item[1])
                    and _is_finite_number(item[2])
                ):
                    sv, ev = float(item[1]), float(item[2])
                    dv = max(0.0, ev - sv)
                    starts.append(sv)
                    ends.append(ev)
                    durs.append(dv)
                    direct.extend([abs(sv), abs(ev), dv])
                    if len(item) >= 4 and item[3] is not None:
                        gk = str(item[3])
                        by_group[gk] = by_group.get(gk, 0.0) + dv
            if durs:
                wall = max(ends) - min(starts)
                total_w = sum(durs)
                direct.extend([wall, total_w, *by_group.values()])
                groups.append([*durs, wall, total_w])
                if by_group:
                    groups.append(list(by_group.values()))
                for denom in (wall, total_w):
                    if denom > 0:
                        for d in durs:
                            shares.append(100.0 * d / denom)
                        for gd in by_group.values():
                            shares.append(100.0 * gd / denom)

    elif kind == "flow":
        stages = spec.get("stages")
        if isinstance(stages, Sequence) and not isinstance(stages, (str, bytes)):
            fvals: list[float] = []
            for st in stages:
                if (
                    isinstance(st, Sequence)
                    and not isinstance(st, (str, bytes))
                    and len(st) >= 2
                    and _is_finite_number(st[1])
                ):
                    fvals.append(float(st[1]))
            if fvals:
                direct.extend(abs(v) for v in fvals)
                groups.append(fvals)
                start_v = fvals[0]
                if start_v > 0:
                    for v in fvals:
                        shares.append(100.0 * v / start_v)
                        shares.append(100.0 * abs(start_v - v) / start_v)
                for idx_s in range(1, len(fvals)):
                    prev_v = fvals[idx_s - 1]
                    drop_v = abs(prev_v - fvals[idx_s])
                    direct.append(drop_v)
                    if prev_v > 0:
                        shares.append(100.0 * drop_v / prev_v)
                        shares.append(100.0 * fvals[idx_s] / prev_v)

    return direct, groups, ratio_groups, shares


def pair_derivations(a: float, b: float, claim_kind: str) -> list[tuple[str, float]]:
    """What a claim about two values ``a`` and ``b`` may state, as ``(derivation, value)``.

    Always the difference. A percent claim may also be the difference in points
    (fractions x100: 0.08 -> "8%") or the change relative to either value ("relative:b"
    is relative to ``b``); any other claim may be the ratio. ``claim_number_mismatch``
    and the compare brackets share it.
    """
    diff = abs(a - b)
    out = [("difference", diff)]
    if claim_kind == "percent":
        if diff <= 1.0:
            out.append(("points", diff * 100.0))
        if abs(b) > 0:
            out.append(("relative:b", 100.0 * diff / abs(b)))
        if abs(a) > 0:
            out.append(("relative:a", 100.0 * diff / abs(a)))
    elif abs(a) > 0 and abs(b) > 0:
        out.append(("ratio", max(abs(a), abs(b)) / min(abs(a), abs(b))))
    return out


#: A number stated as a difference in points ("8 points", "8.2 pts", "3 pp").
_POINTS_TAIL_RE = re.compile(r"\s*(?:percentage[- ]points?|points?|pts?|pp)\b", re.IGNORECASE)
#: Any unsigned number not glued to a word, version, date or range ("GPT-4", "v2.3", "p99").
_ANY_NUM_RE = re.compile(r"(?<![\w.=/^~≈±])(?<!\w-)(?P<num>\d+(?:,\d{3})*(?:\.\d+)?)(?![\w.]*\d)")
_PLAIN_END_RE = re.compile(r"\s*(?:[,;:)!?]|\.(?!\d)|$)")


def claim_numbers(takeaway: str, unit: str | None = None) -> list[tuple[str, float, str]]:
    """Numbers the takeaway states, in order, as ``(kind, value, text)``.

    ``kind`` is "percent" ("12%", not "95% CI"), "fold" ("4x", "2.3×"), "points"
    ("8 points", "3 pp") or "plain": a bare number that ends a clause ("costs 13") or
    carries ``unit`` ("12 ms"). Counts of things ("5 seeds") and years are left out.
    """
    if not isinstance(takeaway, str):
        return []
    found: list[tuple[int, str, float, str]] = []
    taken: list[tuple[int, int]] = []
    for kind, rx in (("percent", _PCT_CLAIM_RE), ("fold", _FOLD_CLAIM_RE)):
        for m in rx.finditer(takeaway):
            val = float(m.group("num").replace(",", ""))
            if math.isfinite(val) and (kind == "percent" or val > 1.0):
                found.append((m.start(), kind, val, m.group(0).strip()))
                taken.append(m.span())
    for m in _ANY_NUM_RE.finditer(takeaway):
        if any(s <= m.start() < e for s, e in taken):
            continue
        text, rest = m.group("num"), takeaway[m.end() :]
        if rest[:1] in {"%", "x", "\N{MULTIPLICATION SIGN}"}:
            continue
        val = float(text.replace(",", ""))
        tail = _POINTS_TAIL_RE.match(rest)
        if tail:
            found.append((m.start(), "points", val, text + tail.group(0)))
            continue
        if re.fullmatch(r"(1[89]|20)\d\d", text):
            continue  # a year
        unit_tail = unit and re.match(rf"\s*{re.escape(unit.strip())}(?!\w)", rest)
        if unit_tail or _PLAIN_END_RE.match(rest):
            found.append((m.start(), "plain", val, text))
    return [(kind, val, text) for _, kind, val, text in sorted(found)]


def stated_match(claim: float, text: str, candidate: float) -> bool:
    """True when ``candidate`` rounds to ``claim`` as written ("8" is 7.5..8.5, "8.2" is
    8.15..8.25): tighter than the mismatch audit, for marks drawn on the strength of it."""
    digits = re.search(r"\.(\d+)", text)
    half = 0.5 * 10.0 ** -(len(digits.group(1)) if digits else 0)
    return math.isfinite(candidate) and abs(abs(candidate) - claim) <= half * (1 + 1e-9)


def claimed_pairs(
    claim: tuple[str, float, str], values: Mapping[str, float], *, percent_unit: bool = False
) -> list[tuple[str, str, str]]:
    """Pairs of ``values`` whose difference (or ratio, or change) is the claimed number.

    Returns ``(a, b, derivation)`` for every pair that matches; a claim that equals an
    item's own value (or that value x100) is a level, not a difference, and matches none.
    On a "%" quantity (``percent_unit``) a percent claim is read as a difference in
    points only: a relative change of a percentage would be a second, ambiguous reading.
    """
    kind, val, text = claim
    for v in values.values():
        if stated_match(val, text, v) or (abs(v) <= 1 and stated_match(val, text, 100 * v)):
            return []
    wanted = {
        "percent": {"difference"} if percent_unit else {"difference", "points", "relative"},
        "fold": {"ratio"},
    }.get(kind, {"difference", "points"})
    names = list(values)
    out: list[tuple[str, str, str]] = []
    for i, a in enumerate(names):
        for b in names[i + 1 :]:
            derivs = pair_derivations(values[a], values[b], "fold" if kind == "fold" else "percent")
            for how, v in derivs:
                if how.split(":")[0] in wanted and stated_match(val, text, v):
                    out.append((a, b, how))
                    break
    return out


def fact_states(claim: tuple[str, float, str], fact: str) -> bool:
    """True when a fact (or fact segment) prints the claimed number, as is or x100
    (a fraction stated in points or percent)."""
    kind, val, text = claim
    for num in _parse_fact_numbers([fact]):
        if stated_match(val, text, num):
            return True
        if kind != "fold" and num <= 1 and stated_match(val, text, 100 * num):
            return True
    return False


def _approx_match(claim: float, candidate: float) -> bool:
    if not math.isfinite(candidate) or candidate < 0:
        return False
    return abs(claim - candidate) <= 1.0 or (
        candidate > 0 and abs(claim - candidate) / candidate <= 0.15
    )


def _matches_any_derivation(
    claim: float,
    *,
    claim_kind: str,
    takeaway: str,
    all_direct: Sequence[float],
    all_groups: Sequence[Sequence[float]],
    all_ratio_groups: Sequence[Sequence[float]],
    all_shares: Sequence[float],
    compare_share_groups: Sequence[Sequence[float]],
) -> bool:
    # 1. Direct values + 100x / 0.01x / 1000x / 0.001x scaled values
    for v in all_direct:
        if _approx_match(claim, v):
            return True
        for scale in (100.0, 0.01, 1000.0, 0.001):
            if _approx_match(claim, v * scale):
                return True

    # 2. Explicit share candidates (from share panels & distribution reference splits)
    if claim_kind == "percent":
        for s in all_shares:
            if _approx_match(claim, s):
                return True
        # Allow a/total on compare panels with >= 3 positive values when not a change claim
        if not _CHANGE_CLAIM_RE.search(takeaway):
            for grp in compare_share_groups:
                pos = [v for v in grp if v > 0]
                if len(pos) >= 3:
                    total = sum(pos)
                    if total > 0:
                        for v in pos:
                            if _approx_match(claim, 100.0 * v / total):
                                return True

    # 3. Same-unit group sums, pairwise differences, percentage changes, and ratios
    for grp in all_groups:
        nums = list(grp)
        if not nums:
            continue
        grp_sum = abs(sum(nums))
        if _approx_match(claim, grp_sum):
            return True
        if len(nums) < 2:
            continue
        pos = [abs(v) for v in nums if abs(v) > 0]
        if len(pos) >= 2 and _approx_match(claim, max(pos) / min(pos)):
            return True
        for i in range(len(nums)):
            for j in range(i + 1, len(nums)):
                if any(
                    _approx_match(claim, v) for _, v in pair_derivations(nums[i], nums[j], claim_kind)
                ):
                    return True

    # 4. Auxiliary ratio-only groups (e.g. fitted slopes parsed from facts, log-x doses)
    if claim_kind == "fold":
        for grp in all_ratio_groups:
            pos = [abs(v) for v in grp if abs(v) > 0]
            if len(pos) < 2:
                continue
            if _approx_match(claim, max(pos) / min(pos)):
                return True
            for i in range(len(pos)):
                for j in range(i + 1, len(pos)):
                    ratio = max(pos[i], pos[j]) / min(pos[i], pos[j])
                    if _approx_match(claim, ratio):
                        return True
    return False


def _check_number_mismatch(
    takeaway: str,
    panels: Mapping[str, Any],
) -> list[dict[str, Any]]:
    if not panels:
        return []
    # Skip completely if any panel is custom or takeaway is hedged
    if any(str(_pget(p, "kind", "")) == "custom" for p in panels.values()):
        return []
    if _HEDGE_RE.search(takeaway):
        return []

    claims: list[tuple[str, float, str]] = []
    for m in _PCT_CLAIM_RE.finditer(takeaway):
        val = float(m.group("num").replace(",", ""))
        if math.isfinite(val):
            claims.append(("percent", val, m.group(0).strip()))
    for m in _FOLD_CLAIM_RE.finditer(takeaway):
        val = float(m.group("num").replace(",", ""))
        if math.isfinite(val) and val > 1.2:
            claims.append(("fold", val, m.group(0).strip()))

    if not claims:
        return []

    all_direct: list[float] = []
    all_groups: list[list[float]] = []
    all_ratio_groups: list[list[float]] = []
    all_shares: list[float] = []
    compare_share_groups: list[list[float]] = []

    for panel in panels.values():
        direct, groups, ratio_groups, shares = _collect_panel_groups(panel)
        all_direct.extend(direct)
        all_groups.extend(groups)
        all_ratio_groups.extend(ratio_groups)
        all_shares.extend(shares)
        if str(_pget(panel, "kind", "")) == "compare":
            vals = _pspec(panel).get("values")
            if isinstance(vals, Mapping):
                flat = [float(v) for v in vals.values() if _is_finite_number(v)]
                if flat:
                    compare_share_groups.append(flat)

    # Require actual numeric evidence in the panels before flagging anything
    if not all_direct and not all_groups:
        return []

    # Cross-panel ratios (e.g. dose IC50 in panel a vs toxicity in panel b)
    if len(panels) > 1 and all_direct:
        all_ratio_groups.append(_dedup_sample(all_direct, limit=60))

    mismatched: list[str] = []
    for claim_kind, val, raw in claims:
        if (
            not _matches_any_derivation(
                val,
                claim_kind=claim_kind,
                takeaway=takeaway,
                all_direct=all_direct,
                all_groups=all_groups,
                all_ratio_groups=all_ratio_groups,
                all_shares=all_shares,
                compare_share_groups=compare_share_groups,
            )
            and raw not in mismatched
        ):
            mismatched.append(raw)

    if not mismatched:
        return []

    listed = ", ".join(repr(m) for m in mismatched[:3])
    return [
        _advisory(
            "claim_number_mismatch",
            f"Takeaway cites {listed}, which does not match any value, difference, "
            "percentage change, share, or ratio computed from the panel data.",
            "Verify the number in the takeaway against summary['panels'][...]['facts'], "
            "or qualify approximate figures with '~' / 'about' and explain external baselines in note=.",
            panel=None,
        )
    ]


def audit_epistemic(takeaway: str, panels: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Run tightly scoped advisory epistemic checks on ``takeaway`` vs ``panels``.

    Emits ``severity="warning"`` issues only (never errors, never blocks ``ship``)
    for:
    - ``claim_overstates_uncertainty``: strong certainty wording in ``takeaway``
      paired with overlapping intervals or small-n rough-estimate warnings in panel facts.
    - ``claim_number_mismatch``: explicit unhedged percentage or fold (>1.2x) claim in
      ``takeaway`` that matches no plausible derivation from the panel data or facts.
    """
    if not isinstance(takeaway, str) or not takeaway.strip() or not panels:
        return []
    issues: list[dict[str, Any]] = []
    issues.extend(_check_overstates_uncertainty(takeaway, panels))
    issues.extend(_check_number_mismatch(takeaway, panels))
    return issues


__all__ = [
    "audit_epistemic",
    "build_narrative",
]
