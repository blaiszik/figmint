"""Tufte word-sized micro-graphics and expandable evidence chips (``mint.inline``).

Public façade exposing all 17 dual-surface (Unicode/ASCII text + themed SVG)
inline components across five families, plus prose/document helpers and a
``CATALOG`` registry for discovery and review.
"""

from __future__ import annotations

from ._inline.change import delta, scatter, waterfall
from ._inline.composition import funnel, ratio, share
from ._inline.core import (
    InlineGraphic,
    bar,
    ci,
    dist,
    document,
    format_prose,
    shared_domain,
    spark,
    strip,
)
from ._inline.evidence import evidence, gauge, quantiles
from ._inline.structure import dual_spark, rank, timeline

CATALOG: tuple[dict[str, str], ...] = (
    # Core 5
    {"name": "spark", "family": "core", "question": "How did a value evolve over steps or time?"},
    {"name": "ci", "family": "core", "question": "What is the estimate and uncertainty vs. null?"},
    {"name": "dist", "family": "core", "question": "How are raw observations spread (skew & outliers)?"},
    {"name": "bar", "family": "core", "question": "How large is a ratio or score vs. baseline & target?"},
    {"name": "strip", "family": "core", "question": "Which seeds/checks passed, warned, failed, or shifted?"},
    # Change, Attribution & Tradeoffs
    {"name": "delta", "family": "change", "question": "How far and in what direction did a value move?"},
    {"name": "waterfall", "family": "change", "question": "Which positive and negative drivers summed to the net change?"},
    {"name": "scatter", "family": "change", "question": "How do two measures correlate or sit on a Pareto frontier?"},
    # Composition, Funnels & Natural Frequencies
    {"name": "share", "family": "composition", "question": "How is a whole divided across categories (never a pie)?"},
    {"name": "funnel", "family": "composition", "question": "Where did items drop off across sequential pipeline stages?"},
    {"name": "ratio", "family": "composition", "question": "What does a probability or count feel like in natural frequencies?"},
    # Operating Windows, Uncertainty & Evidence
    {"name": "gauge", "family": "evidence", "question": "Where does a reading sit inside normal and caution limits?"},
    {"name": "quantiles", "family": "evidence", "question": "What is the predictive probability mass relative to a threshold?"},
    {"name": "evidence", "family": "evidence", "question": "How strong is the statistical evidence given effect and n?"},
    # Timelines, Rankings & Dual Trajectories
    {"name": "timeline", "family": "structure", "question": "Where did wall-clock time go and which phase was the bottleneck?"},
    {"name": "rank", "family": "structure", "question": "Where does this entity sit in its cohort or leaderboard?"},
    {"name": "dual_spark", "family": "structure", "question": "How did two paired trajectories diverge or cross over time?"},
)

__all__ = [
    "CATALOG",
    "InlineGraphic",
    "bar",
    "ci",
    "delta",
    "dist",
    "document",
    "dual_spark",
    "evidence",
    "format_prose",
    "funnel",
    "gauge",
    "quantiles",
    "rank",
    "ratio",
    "scatter",
    "share",
    "shared_domain",
    "spark",
    "strip",
    "timeline",
    "waterfall",
]
