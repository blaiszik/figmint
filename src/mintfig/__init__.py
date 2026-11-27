"""mintfig — message-first figures for agents explaining results.

The top level holds what an agent calls to explain a result. Journal plates,
styling, annotation, export and preflight live in :mod:`mintfig.pub`; themes and
palettes in :mod:`mintfig.themes`; audits in :mod:`mintfig.audit`; skill install
in :mod:`mintfig.skill`.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def _ensure_writable_mplconfigdir() -> None:
    """Point Matplotlib at a persistent writable temp cache when ``~/.matplotlib`` is read-only.

    Avoids Matplotlib rebuilding its font cache into a fresh random temp directory
    on every invocation inside sandboxed agent/CI environments (~6-8 s saved per cold run).
    """
    if os.environ.get("MPLCONFIGDIR"):
        return
    home = Path.home()
    mpl_dir = home / ".matplotlib"
    probe = mpl_dir if mpl_dir.exists() else home
    if os.access(probe, os.W_OK):
        return
    fallback = Path(tempfile.gettempdir()) / "mintfig-mpl"
    try:
        fallback.mkdir(parents=True, exist_ok=True)
        os.environ["MPLCONFIGDIR"] = str(fallback)
    except OSError:
        pass


_ensure_writable_mplconfigdir()

# Submodule homes for names that left the top level in 0.3.0 (reachable as mint.pub, ...).
from . import audit as audit
from . import byo as byo
from . import inline
from . import interactive as interactive
from . import notebook as notebook
from . import pub as pub
from . import skill as skill
from . import terminal as terminal
from . import themes as themes
from .brief import Brief, Session, brief
from .byo import (
    load_ipython_extension as load_ipython_extension,
)
from .byo import (
    style,
)
from .byo import (
    unload_ipython_extension as unload_ipython_extension,
)
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
    "notebook",
    "relate",
    "share",
    "style",
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
