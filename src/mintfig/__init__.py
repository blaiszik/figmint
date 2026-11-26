"""mintfig — message-first figures for agents explaining results.

The top level holds what an agent calls to explain a result. Journal plates,
styling, annotation, export and preflight live in :mod:`mintfig.pub`; themes and
palettes in :mod:`mintfig.themes`; audits in :mod:`mintfig.audit`; skill install
in :mod:`mintfig.skill`.
"""

from __future__ import annotations

# Submodule homes for names that left the top level in 0.3.0 (reachable as mint.pub, ...).
from . import audit as audit
from . import inline
from . import interactive as interactive
from . import pub as pub
from . import skill as skill
from . import terminal as terminal
from . import themes as themes
from .brief import Brief, Session, brief
from .edit import edit
from .explainer import (
    ExplainError,
    Explanation,
    Panel,
    change,
    compare,
    custom,
    distribution,
    explain,
    flow,
    histogram,
    lenient,
    load,
    matrix,
    relate,
    share,
    table,
    timeline,
    trend,
    waterfall,
)
from .figcheck import check
from .inline import InlineGraphic
from .inspect_data import auto_panel, inspect_data, load_table_file
from .plate import Plate, figure

__version__ = "0.3.0"

__all__ = [
    "Brief",
    "ExplainError",
    "Explanation",
    "InlineGraphic",
    "Panel",
    "Plate",
    "Session",
    "__version__",
    "auto_panel",
    "brief",
    "change",
    "check",
    "compare",
    "custom",
    "distribution",
    "edit",
    "explain",
    "figure",
    "flow",
    "histogram",
    "inline",
    "inspect_data",
    "lenient",
    "load",
    "load_table_file",
    "matrix",
    "relate",
    "share",
    "table",
    "timeline",
    "trend",
    "waterfall",
]

# Names removed from the top level in 0.3.0 (clean break, no aliases) -> new home.
_MOVED: dict[str, str] = {
    **{name: f"mintfig.pub.{name}" for name in pub.__all__ if name not in {"Plate", "figure"}},
    **{
        name: f"mintfig.themes.{name}"
        for name in (
            "THEMES",
            "Theme",
            "get_theme",
            "EXPLAIN_PALETTES",
            "ExplainPalette",
            "get_explain_palette",
        )
    },
    **{name: f"mintfig.audit.{name}" for name in audit.__all__},
    **{
        name: f"mintfig.skill.{name}"
        for name in ("install_skill", "get_skill_markdown", "get_agents_snippet", "VALID_TARGETS")
    },
    "render_html": "mintfig.interactive.render_html",
    "render_terminal": "mintfig.terminal.render_terminal",
    "show_in_terminal": "mintfig.terminal.show_in_terminal",
    "explain_from_spec": "mintfig.load",
    "panel_from_spec": "mintfig.explainer.panel_from_spec",
}

_HINTS: dict[str, str] = {
    "render_html": "; or call fig.to_html()",
    "render_terminal": "; or call fig.to_text()",
    "show_in_terminal": "; or call fig.show()",
    "explain_from_spec": " (pass the spec dict: mintfig.load(spec))",
}


def __getattr__(name: str) -> object:
    new_home = _MOVED.get(name)
    if new_home is not None:
        raise AttributeError(
            f"mintfig.{name} moved to {new_home} in 0.3.0{_HINTS.get(name, '')}"
        )
    raise AttributeError(f"module 'mintfig' has no attribute {name!r}")
