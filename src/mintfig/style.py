"""Publication-grade Matplotlib styling and font resolution for Nature & Science."""

from __future__ import annotations

from contextlib import AbstractContextManager
from functools import lru_cache
from pathlib import Path
from typing import Any

import matplotlib as mpl
from cycler import cycler
from matplotlib import font_manager

from .palettes import get_palette
from .specs import JournalSpec, get_spec

#: Modern editorial / scientific sans-serif stack (prioritized ahead of generic fallbacks).
EDITORIAL_SANS_FONTS: tuple[str, ...] = (
    "Inter",
    "IBM Plex Sans",
    "Source Sans 3",
    "Helvetica Neue",
    "Helvetica",
    "Arial",
    "Liberation Sans",
    "DejaVu Sans",
)

#: Modern editorial serif headline stack (prioritized ahead of generic fallbacks).
EDITORIAL_SERIF_FONTS: tuple[str, ...] = (
    "Newsreader",
    "Source Serif 4",
    "Georgia",
    "Charter",
    "DejaVu Serif",
    "serif",
)

_DEFAULT_SPEC_SANS: tuple[str, ...] = (
    "Helvetica",
    "Arial",
    "Liberation Sans",
    "DejaVu Sans",
)

_BUNDLED_FONTS_DIR = Path(__file__).resolve().parent / "assets" / "fonts"
_LOCAL_FONTS_REGISTERED: bool = False


def register_local_fonts(fonts_dir: str | Path | None = None) -> list[Path]:
    """Auto-register any ``.ttf`` or ``.otf`` fonts in ``src/mintfig/assets/fonts/``."""
    global _LOCAL_FONTS_REGISTERED
    directory = Path(fonts_dir) if fonts_dir is not None else _BUNDLED_FONTS_DIR
    registered: list[Path] = []
    if directory.is_dir():
        existing = {
            str(Path(entry.fname).resolve())
            for entry in font_manager.fontManager.ttflist
            if getattr(entry, "fname", None)
        }
        for path in sorted(directory.iterdir()):
            if not path.is_file() or path.suffix.lower() not in {".ttf", ".otf"}:
                continue
            resolved = str(path.resolve())
            if resolved in existing:
                continue
            try:
                font_manager.fontManager.addfont(resolved)
                existing.add(resolved)
                registered.append(path)
            except (OSError, RuntimeError, ValueError):
                continue
    if fonts_dir is None:
        _LOCAL_FONTS_REGISTERED = True
    if registered:
        _resolve_font_tuple.cache_clear()
    return registered


def _is_bold_weight(weight: object) -> bool:
    if isinstance(weight, (int, float)):
        return float(weight) >= 600.0
    text = str(weight).strip().lower()
    if text in {"bold", "semibold", "demibold", "demi", "heavy", "black", "extra bold", "ultrabold"}:
        return True
    try:
        return float(text) >= 600.0
    except ValueError:
        return False


_GENERIC_FONT_FAMILIES: frozenset[str] = frozenset(
    {"sans-serif", "serif", "monospace", "cursive", "fantasy"}
)


def _installed_font_stack(
    families: tuple[str, ...], *, require_bold: bool = False
) -> list[str]:
    """Return installed families from ``families`` in priority order (avoids findfont spam)."""
    ordered = _ordered_font_stack(families, require_bold=require_bold)
    installed = {entry.name.lower() for entry in font_manager.fontManager.ttflist}
    filtered = [
        fam
        for fam in ordered
        if fam.lower() in installed or fam.lower() in _GENERIC_FONT_FAMILIES
    ]
    return filtered or [ordered[0]]


def _ordered_font_stack(
    families: tuple[str, ...], *, require_bold: bool = False
) -> list[str]:
    """Return ``families`` with the best installed match placed first (preserving all entries)."""
    resolved = _resolve_font_tuple(families, require_bold=require_bold)
    seen: set[str] = {resolved.lower()}
    ordered = [resolved]
    for fam in families:
        key = fam.lower()
        if key not in seen:
            seen.add(key)
            ordered.append(fam)
    return ordered


def _effective_sans_stack(spec: JournalSpec) -> tuple[str, ...]:
    """Use the upgraded editorial sans stack for default screen figures.

    Preserves explicit caller overrides (e.g. ``font_family=("DejaVu Sans",)``)
    and journal-mandated print font stacks (Helvetica/Arial for Nature/Science).
    """
    if spec.name == "screen" and spec.font_family == _DEFAULT_SPEC_SANS:
        return EDITORIAL_SANS_FONTS
    return spec.font_family


@lru_cache(maxsize=32)
def _resolve_font_tuple(families: tuple[str, ...], *, require_bold: bool = False) -> str:
    """Return the first installed font family name from ``families``.

    When ``require_bold=True``, prefers a family that provides both normal and bold
    weights so headlines never silently fall back to regular 400 weight on hosts
    that only installed a single ``*-Regular.ttf`` file.
    """
    if not _LOCAL_FONTS_REGISTERED:
        register_local_fonts()
    installed: dict[str, str] = {}
    has_normal: set[str] = set()
    has_bold: set[str] = set()
    for entry in font_manager.fontManager.ttflist:
        key = entry.name.lower()
        installed.setdefault(key, entry.name)
        if _is_bold_weight(entry.weight):
            has_bold.add(key)
        else:
            has_normal.add(key)
    if require_bold:
        for candidate in families:
            key = candidate.lower()
            if key in installed and key in has_bold and key in has_normal:
                return installed[key]
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
    return _resolve_font_tuple(_effective_sans_stack(resolved_spec), require_bold=True)


def rc_params(
    journal: str | JournalSpec = "nature",
    *,
    palette: str | None = None,
) -> dict[str, Any]:
    """Build a Matplotlib rcParams dictionary conforming to ``journal`` specs."""
    spec = get_spec(journal)
    colors = get_palette(palette if palette is not None else spec.default_palette)
    sans_stack = _effective_sans_stack(spec)
    font_name = _resolve_font_tuple(sans_stack, require_bold=True)
    ordered_sans = _ordered_font_stack(sans_stack, require_bold=True)
    ordered_serif = _ordered_font_stack(EDITORIAL_SERIF_FONTS, require_bold=True)
    minor_tick_w = max(spec.min_linewidth_pt, round(spec.axes_linewidth_pt * 0.75, 3))

    return {
        # Editable vector font embedding (TrueType Type 42 in PDF/PS, raw text in SVG)
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
        "svg.fonttype": "none",
        # Typography (uniform sans-serif body + math)
        "font.family": "sans-serif",
        "font.sans-serif": ordered_sans,
        "font.serif": ordered_serif,
        "font.size": spec.body_pt,
        "text.color": "#1A1D21",
        "mathtext.fontset": "custom",
        "mathtext.rm": font_name,
        "mathtext.it": f"{font_name}:italic",
        "mathtext.bf": f"{font_name}:bold",
        "mathtext.sf": font_name,
        "mathtext.cal": font_name,
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
