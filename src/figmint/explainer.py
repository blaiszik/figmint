"""Message-first figures for conversations.

Public facade re-exporting all forms, layout, and helpers from
``figmint._explain``.
"""

from __future__ import annotations

from typing import Any

from ._explain import (
    change as _change,
)
from ._explain import (
    compare as _compare,
)
from ._explain import (
    core as _core,
)
from ._explain import (
    distribution as _distribution,
)
from ._explain import (
    layout as _layout,
)
from ._explain import (
    matrix as _matrix,
)
from ._explain import (
    relate as _relate,
)
from ._explain import (
    trend as _trend,
)
from ._explain.change import change
from ._explain.compare import compare, share
from ._explain.core import (
    _VISUAL_DEFECT_RULES,
    ACCENT_COLORS,
    AXIS,
    COMFORTABLE_COMPARE_ITEMS,
    COMFORTABLE_PANELS,
    CONTEXT_FILL,
    CONTEXT_LINE,
    DISPLAY_WIDTH_PX,
    GRID,
    INK,
    KINDS,
    MAX_CHANGE_ITEMS,
    MAX_COLORED_SERIES,
    MAX_COMPARE_ITEMS,
    MAX_FACETS,
    MAX_GROUPS,
    MAX_HIGHLIGHTS,
    MAX_MATRIX_COLS,
    MAX_MATRIX_ROWS,
    MAX_PANELS,
    MIN_TEXT_PX,
    MUTED,
    PT_TO_MM,
    SERIES_COLORS,
    ExplainError,
    Panel,
    lenient,
)
from ._explain.distribution import MAX_HIST_GROUPS, distribution, histogram
from ._explain.layout import (
    COLOR_SLOTS,
    EXAMPLE_SPEC,
    NARROW_DISPLAY_WIDTH_PX,
    SLIDE_DISPLAY_WIDTH_PX,
    Explanation,
    Summary,
    custom,
    explain,
    explain_from_spec,
    load,
    panel_from_spec,
    read_png_text,
    table,
)
from ._explain.matrix import matrix
from ._explain.relate import relate
from ._explain.trend import trend
from .epistemic import audit_epistemic, build_narrative
from .interactive import render_html
from .terminal import render_terminal, show_in_terminal

_SUBMODULES = (
    _core,
    _layout,
    _compare,
    _trend,
    _change,
    _distribution,
    _relate,
    _matrix,
)


def __getattr__(name: str) -> Any:
    """Forward legacy internal attribute lookups to the split ``_explain`` submodules."""
    for mod in _SUBMODULES:
        if hasattr(mod, name):
            return getattr(mod, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "ACCENT_COLORS",
    "AXIS",
    "COLOR_SLOTS",
    "COMFORTABLE_COMPARE_ITEMS",
    "COMFORTABLE_PANELS",
    "CONTEXT_FILL",
    "CONTEXT_LINE",
    "DISPLAY_WIDTH_PX",
    "EXAMPLE_SPEC",
    "GRID",
    "INK",
    "KINDS",
    "MAX_CHANGE_ITEMS",
    "MAX_COLORED_SERIES",
    "MAX_COMPARE_ITEMS",
    "MAX_FACETS",
    "MAX_GROUPS",
    "MAX_HIGHLIGHTS",
    "MAX_HIST_GROUPS",
    "MAX_MATRIX_COLS",
    "MAX_MATRIX_ROWS",
    "MAX_PANELS",
    "MIN_TEXT_PX",
    "MUTED",
    "NARROW_DISPLAY_WIDTH_PX",
    "PT_TO_MM",
    "SERIES_COLORS",
    "SLIDE_DISPLAY_WIDTH_PX",
    "_VISUAL_DEFECT_RULES",
    "ExplainError",
    "Explanation",
    "Panel",
    "Summary",
    "audit_epistemic",
    "build_narrative",
    "change",
    "compare",
    "custom",
    "distribution",
    "explain",
    "explain_from_spec",
    "histogram",
    "lenient",
    "load",
    "matrix",
    "panel_from_spec",
    "read_png_text",
    "relate",
    "render_html",
    "render_terminal",
    "share",
    "show_in_terminal",
    "table",
    "trend",
]
