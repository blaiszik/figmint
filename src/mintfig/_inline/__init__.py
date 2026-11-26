"""Internal modules for ``mint.inline`` word-sized micro-graphics."""

from __future__ import annotations

from .change import delta, scatter, waterfall
from .composition import funnel, ratio, share
from .core import (
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
from .evidence import evidence, gauge, quantiles
from .structure import dual_spark, rank, timeline

__all__ = [
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
