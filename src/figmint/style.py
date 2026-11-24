"""Publication-grade Matplotlib styling and font resolution for Nature & Science."""

from __future__ import annotations

from contextlib import AbstractContextManager
from functools import lru_cache
from typing import Any

import matplotlib as mpl
from cycler import cycler
from matplotlib import font_manager

from .palettes import get_palette
from .specs import JournalSpec, get_spec


@lru_cache(maxsize=16)
def _resolve_font_tuple(families: tuple[str, ...]) -> str:
    """Return the first installed font family name from ``families``."""
    installed = {entry.name.lower(): entry.name for entry in font_manager.fontManager.ttflist}
    for candidate in families:
        key = candidate.lower()
        if key in installed:
            return installed[key]
    for candidate in families:
        try:
            fp = font_manager.FontProperties(family=candidate)
            found_path = font_manager.findfont(fp, fallback_to_default=False)
            if found_path:
                return candidate
        except ValueError:
            continue
    return "DejaVu Sans"


def resolved_font_name(spec: str | JournalSpec = "nature") -> str:
    """Detect the first installed sans-serif font from ``spec.font_family``."""
    resolved_spec = get_spec(spec)
    return _resolve_font_tuple(resolved_spec.font_family)


def rc_params(
    journal: str | JournalSpec = "nature",
    *,
    palette: str | None = None,
) -> dict[str, Any]:
    """Build a Matplotlib rcParams dictionary conforming to ``journal`` specs."""
    spec = get_spec(journal)
    colors = get_palette(palette if palette is not None else spec.default_palette)
    font_name = resolved_font_name(spec)
    minor_tick_w = max(spec.min_linewidth_pt, round(spec.axes_linewidth_pt * 0.75, 3))

    return {
        # Editable vector font embedding (TrueType Type 42 in PDF/PS, raw text in SVG)
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
        "svg.fonttype": "none",
        # Typography (uniform sans-serif body + math)
        "font.family": "sans-serif",
        "font.sans-serif": list(spec.font_family),
        "font.size": spec.body_pt,
        "text.color": "#1A1D21",
        "mathtext.fontset": "custom",
        "mathtext.rm": font_name,
        "mathtext.it": f"{font_name}:italic",
        "mathtext.bf": f"{font_name}:bold",
        "mathtext.sf": font_name,
        # Variables render italic ($T$, $P$, $\rho$) while explicit \mathrm{...} stays upright.
        "mathtext.default": "it",
        "mathtext.fallback": "stixsans",
        "axes.unicode_minus": True,
        # Axes & spines
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.linewidth": spec.axes_linewidth_pt,
        "axes.edgecolor": "#2B3036",
        "axes.labelcolor": "#1A1D21",
        "axes.labelsize": spec.body_pt,
        "axes.labelpad": 3.5,
        "axes.titlesize": spec.body_pt,
        "axes.titlepad": 5.5,
        "axes.titleweight": "normal",
        "axes.axisbelow": True,
        "axes.grid": False,
        "axes.prop_cycle": cycler(color=colors),
        # Crisp outward ticks
        "xtick.direction": "out",
        "ytick.direction": "out",
        "xtick.top": False,
        "ytick.right": False,
        "xtick.color": "#2B3036",
        "ytick.color": "#2B3036",
        "xtick.major.width": spec.axes_linewidth_pt,
        "ytick.major.width": spec.axes_linewidth_pt,
        "xtick.minor.width": minor_tick_w,
        "ytick.minor.width": minor_tick_w,
        "xtick.major.size": 2.2,
        "ytick.major.size": 2.2,
        "xtick.minor.size": 1.3,
        "ytick.minor.size": 1.3,
        "xtick.major.pad": 2.5,
        "ytick.major.pad": 2.5,
        "xtick.labelsize": spec.tick_pt,
        "ytick.labelsize": spec.tick_pt,
        # Clean frameless legends
        "legend.frameon": False,
        "legend.fontsize": spec.legend_pt,
        "legend.title_fontsize": spec.legend_pt,
        "legend.handlelength": 1.4,
        "legend.handletextpad": 0.5,
        "legend.borderaxespad": 0.4,
        "legend.labelspacing": 0.3,
        # Data strokes & perceptual default colormap
        "lines.linewidth": spec.data_linewidth_pt,
        "lines.solid_capstyle": "round",
        "lines.solid_joinstyle": "round",
        "lines.markersize": 3.5,
        "lines.markeredgewidth": 0.5,
        "patch.linewidth": spec.axes_linewidth_pt,
        "hatch.linewidth": spec.axes_linewidth_pt,
        "errorbar.capsize": 1.5,
        "image.cmap": "viridis",
        # Figure & export defaults
        "figure.facecolor": "white",
        "figure.edgecolor": "white",
        "figure.dpi": 150,
        "savefig.facecolor": "white",
        "savefig.edgecolor": "white",
        "savefig.dpi": spec.dpi_combo,
        "savefig.transparent": False,
    }


def use(
    journal: str | JournalSpec = "nature",
    *,
    palette: str | None = None,
) -> AbstractContextManager[None]:
    """Context manager applying journal rcParams without leaking global state."""
    return mpl.rc_context(rc=rc_params(journal, palette=palette))


def apply(
    journal: str | JournalSpec = "nature",
    *,
    palette: str | None = None,
) -> dict[str, Any]:
    """Apply journal rcParams globally to ``matplotlib.rcParams`` and return them."""
    params = rc_params(journal, palette=palette)
    mpl.rcParams.update(params)
    return params
