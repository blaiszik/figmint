"""mintfig — message-first figures for agents explaining results.

The top level holds what an agent calls to explain a result. Journal plates,
styling, annotation, export and preflight live in :mod:`mintfig.pub`; themes and
palettes in :mod:`mintfig.themes`; audits in :mod:`mintfig.audit`; skill install
in :mod:`mintfig.skill`.
"""

from __future__ import annotations

import importlib
import os
import sys
import tempfile
import types
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
    candidates = (
        Path(tempfile.gettempdir()) / "mintfig-mpl",
        Path("/tmp") / "mintfig-mpl",
    )
    seen: set[Path] = set()
    for cand in candidates:
        if cand in seen:
            continue
        seen.add(cand)
        try:
            cand.mkdir(parents=True, exist_ok=True)
            # Verify actual writability with a real create+unlink probe (handles
            # read-only dirs and macOS sandbox denials where os.access may mislead).
            probe_file = cand / f".mintfig-probe-{os.getpid()}"
            probe_file.write_bytes(b"")
            probe_file.unlink(missing_ok=True)
            os.environ["MPLCONFIGDIR"] = str(cand)
            return
        except OSError:
            continue


_ensure_writable_mplconfigdir()

__version__ = "0.3.1"

__all__ = [
    "Brief",
    "ExplainError",
    "Explanation",
    "InlineGraphic",
    "Panel",
    "Plate",
    "Session",
    "SummaryCard",
    "__version__",
    "auto_panel",
    "brief",
    "card",
    "change",
    "check",
    "compare",
    "custom",
    "distribution",
    "edit",
    "explain",
    "figure",
    "flow",
    "forest",
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

# Submodule homes (lazily imported via __getattr__ so CLI no-ops stay pure stdlib).
_LAZY_SUBMODULES: frozenset[str] = frozenset(
    {
        "audit",
        "byo",
        "inline",
        "interactive",
        "notebook",
        "pub",
        "skill",
        "terminal",
        "themes",
    }
)

# Top-level re-exports loaded on first access so `import mintfig` does not eagerly
# pull in matplotlib, numpy, or PIL.
_LAZY_ATTRS: dict[str, tuple[str, str]] = {
    "Brief": (".brief", "Brief"),
    "Session": (".brief", "Session"),
    "SummaryCard": (".card", "SummaryCard"),
    "brief": (".brief", "brief"),
    "card": (".card", "card"),
    "load_ipython_extension": (".byo", "load_ipython_extension"),
    "style": (".byo", "style"),
    "unload_ipython_extension": (".byo", "unload_ipython_extension"),
    "edit": (".edit", "edit"),
    "ExplainError": (".explainer", "ExplainError"),
    "Explanation": (".explainer", "Explanation"),
    "Panel": (".explainer", "Panel"),
    "change": (".explainer", "change"),
    "compare": (".explainer", "compare"),
    "custom": (".explainer", "custom"),
    "distribution": (".explainer", "distribution"),
    "explain": (".explainer", "explain"),
    "flow": (".explainer", "flow"),
    "forest": (".explainer", "forest"),
    "histogram": (".explainer", "histogram"),
    "lenient": (".explainer", "lenient"),
    "load": (".explainer", "load"),
    "matrix": (".explainer", "matrix"),
    "relate": (".explainer", "relate"),
    "share": (".explainer", "share"),
    "table": (".explainer", "table"),
    "timeline": (".explainer", "timeline"),
    "trend": (".explainer", "trend"),
    "waterfall": (".explainer", "waterfall"),
    "check": (".figcheck", "check"),
    "InlineGraphic": (".inline", "InlineGraphic"),
    "auto_panel": (".inspect_data", "auto_panel"),
    "inspect_data": (".inspect_data", "inspect_data"),
    "load_table_file": (".inspect_data", "load_table_file"),
    "Plate": (".plate", "Plate"),
    "figure": (".plate", "figure"),
}

_PUB_MOVED: tuple[str, ...] = (
    "BANNED_COLORMAPS",
    "EDITORIAL_COLORMAPS",
    "JOURNALS",
    "MM_PER_INCH",
    "PALETTES",
    "BundleResult",
    "CheckResult",
    "JournalSpec",
    "PreflightReport",
    "RunResult",
    "apply",
    "bundle_figure",
    "despine",
    "direct_labels",
    "emphasize",
    "get_palette",
    "get_spec",
    "ghost_context",
    "in_to_mm",
    "mm_to_in",
    "preflight_figure",
    "preflight_pdf",
    "range_frame",
    "rasterize_heavy",
    "rc_params",
    "register_colormaps",
    "render_proof_sheet",
    "resolved_font_name",
    "run_script",
    "save_figure",
    "scalebar",
    "sig_bracket",
    "simulate_cvd",
    "slopegraph",
    "sparkline",
    "style_colorbar",
    "style_heatmap",
    "subtle_grid",
    "tufte_boxplot",
    "use",
    "zoom_inset",
)

# Names removed from the top level in 0.3.0 (clean break, no aliases) -> new home.
_MOVED: dict[str, str] = {
    **{name: f"mintfig.pub.{name}" for name in _PUB_MOVED},
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
    **{
        name: f"mintfig.audit.{name}"
        for name in ("audit_epistemic", "audit_figure", "audit_layout", "build_narrative")
    },
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


_CALLABLE_SUBMODULE_NAMES: frozenset[str] = frozenset(
    {"brief", "card", "edit", "inspect_data", "style"}
)


class _MintfigModule(types.ModuleType):
    """Module subclass that prevents submodule loads from shadowing top-level callables."""

    def __setattr__(self, name: str, value: object) -> None:
        if name in _CALLABLE_SUBMODULE_NAMES and isinstance(value, types.ModuleType):
            return
        super().__setattr__(name, value)


sys.modules[__name__].__class__ = _MintfigModule


def __getattr__(name: str) -> object:
    target = _LAZY_ATTRS.get(name)
    if target is not None:
        mod_name, attr_name = target
        module = importlib.import_module(mod_name, __name__)
        value = getattr(module, attr_name)
        globals()[name] = value
        return value
    if name in _LAZY_SUBMODULES:
        module = importlib.import_module(f".{name}", __name__)
        globals()[name] = module
        return module
    new_home = _MOVED.get(name)
    if new_home is not None:
        raise AttributeError(
            f"mintfig.{name} moved to {new_home} in 0.3.0{_HINTS.get(name, '')}"
        )
    raise AttributeError(f"module 'mintfig' has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__) | set(_LAZY_SUBMODULES))
