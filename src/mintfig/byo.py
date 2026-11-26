"""Zero-rewrite upgrade path for existing Matplotlib figures.

Brings plain Matplotlib/Seaborn figures into mintfig's visual, epistemic, and
delivery pipeline with 1–2 lines of code:

- :func:`style`: chat-ready Matplotlib ``rcParams`` context manager (with
  ``.apply()`` and ``.rc_params()``) sized so text stays legible (>= 11 px) at
  reading width, using mintfig's colorblind-safe palettes and clean defaults.
- :func:`figure_to_panel`: wraps any Matplotlib ``Figure`` or ``Axes`` into a
  :class:`~mintfig.Panel` backed by :func:`mintfig.check` facts & issue
  propagation so ``mint.explain(takeaway, fig)`` works seamlessly.
- :func:`load_ipython_extension` / :func:`unload_ipython_extension` /
  :func:`auto_check`: zero-dependency IPython/Jupyter integration that
  automatically checks newly created open figures after each cell.
"""

from __future__ import annotations

import importlib
import io
import math
import shlex
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from types import TracebackType
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from typing_extensions import Self

import matplotlib as mpl
from cycler import cycler
from matplotlib.axes import Axes
from matplotlib.figure import Figure, SubFigure

from ._explain.core import Panel, _Ctx, _issue
from .figcheck import WIDTHS, FigureCheck, _AggCanvas, _resolve_figure, check
from .specs import get_spec
from .themes import (
    ExplainPalette,
    Theme,
    apply_accent,
    apply_palette,
    get_theme,
)

__all__ = [
    "StyleContext",
    "auto_check",
    "figure_to_panel",
    "format_badge",
    "load_ipython_extension",
    "style",
    "unload_ipython_extension",
]

# --------------------------------------------------------------------------- #
# B1: mint.style() — chat-ready Matplotlib rcParams context manager
# --------------------------------------------------------------------------- #

#: (figsize_in, dpi, font_sizes) tuned so ticks/labels/titles stay >= 11 px at target width.
_WIDTH_PROFILES: dict[str, dict[str, Any]] = {
    "narrow": {
        "figsize": (4.5, 3.0),
        "dpi": 150,
        "font": 9.5,
        "tick": 9.0,
        "legend": 9.0,
        "label": 10.0,
        "title": 11.0,
        "suptitle": 12.0,
    },
    "chat": {
        "figsize": (6.0, 3.6),
        "dpi": 150,
        "font": 9.0,
        "tick": 8.5,
        "legend": 8.5,
        "label": 9.5,
        "title": 10.5,
        "suptitle": 11.5,
    },
    "slide": {
        "figsize": (8.5, 4.8),
        "dpi": 150,
        "font": 10.5,
        "tick": 10.0,
        "legend": 10.0,
        "label": 11.0,
        "title": 12.5,
        "suptitle": 14.0,
    },
}


def _resolve_width_profile(width: str | float) -> tuple[str | int, dict[str, Any]]:
    """Resolve ``width`` preset or positive pixel width into a sizing profile."""
    if isinstance(width, str):
        key = width.strip().lower()
        if key not in _WIDTH_PROFILES:
            valid = ", ".join(sorted(_WIDTH_PROFILES))
            raise ValueError(
                f"Unknown width {width!r}. Choose one of: {valid} (or a positive pixel width)."
            )
        return key, dict(_WIDTH_PROFILES[key])
    if isinstance(width, bool) or not isinstance(width, (int, float)):
        raise TypeError(
            f"width must be 'narrow', 'chat', 'slide', or a positive pixel width, got {type(width).__name__}."
        )
    px = float(width)
    if not math.isfinite(px) or px <= 0:
        raise ValueError(f"width in pixels must be positive, got {width!r}.")
    # Scale figsize proportionally around the chat preset (700 px -> 6.0 x 3.6 in at 150 dpi).
    fig_w = round(max(3.6, min(12.0, px / 116.67)), 2)
    fig_h = round(fig_w * 0.6, 2)
    dpi = 150
    # Guarantee tick/legend text stays >= 12.5 px at target px width even with tight bbox.
    shown = min(px, fig_w * dpi)
    px_per_pt = shown / (fig_w * 72.0)
    tick_pt = round(max(8.5, 12.5 / px_per_pt), 1)
    return round(px), {
        "figsize": (fig_w, fig_h),
        "dpi": dpi,
        "font": round(tick_pt + 0.5, 1),
        "tick": tick_pt,
        "legend": tick_pt,
        "label": round(tick_pt + 1.0, 1),
        "title": round(tick_pt + 2.0, 1),
        "suptitle": round(tick_pt + 3.0, 1),
    }


def _build_byo_rc_params(
    theme: Theme,
    profile: Mapping[str, Any],
    *,
    lead_accent: bool = False,
) -> dict[str, Any]:
    """Assemble chat-ready Matplotlib rcParams from a resolved ``Theme`` and width profile."""
    pub_style = importlib.import_module("mintfig.style")
    spec = get_spec("screen")
    body_families = tuple(theme.body_family) if theme.body_family is not None else spec.font_family
    font_name = pub_style._resolve_font_tuple(body_families)

    if lead_accent and theme.accent_colors:
        lead = theme.accent_colors[0]
        cycle_colors = [lead, *[c for c in theme.series_colors if c != lead]]
    else:
        cycle_colors = list(theme.series_colors)

    use_grid = theme.grid_style != "none" and theme.grid_lw > 0
    grid_axis = "both" if theme.grid_both_axes else "y"
    spine_color = theme.background if theme.hide_spines else theme.axis
    spine_lw = 0.0 if theme.hide_spines else max(0.5, float(theme.axis_lw))
    tick_len = 0.0 if theme.hide_spines else max(2.5, float(theme.tick_length))
    tick_w = 0.0 if theme.hide_spines else max(0.5, float(theme.tick_width))

    params: dict[str, Any] = {
        # Editable vector font embedding
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
        "svg.fonttype": "none",
        # Typography & true minus
        "font.family": ["sans-serif", "DejaVu Sans"],
        "font.sans-serif": list(body_families),
        "font.size": profile["font"],
        "text.color": theme.ink,
        "mathtext.fontset": "custom",
        "mathtext.rm": font_name,
        "mathtext.it": f"{font_name}:italic",
        "mathtext.bf": f"{font_name}:bold",
        "mathtext.sf": font_name,
        "mathtext.cal": font_name,
        "mathtext.default": "it",
        "mathtext.fallback": "stixsans",
        "axes.unicode_minus": theme.minus_sign != "-",
        # Canvas & layout
        "figure.figsize": profile["figsize"],
        "figure.dpi": profile["dpi"],
        "figure.facecolor": theme.background,
        "figure.edgecolor": theme.background,
        "figure.titlesize": profile["suptitle"],
        "figure.titleweight": theme.title_weight,
        "figure.constrained_layout.use": True,
        "savefig.dpi": profile["dpi"],
        "savefig.facecolor": theme.background,
        "savefig.edgecolor": theme.background,
        "savefig.transparent": False,
        # Axes, despining, gridlines & CVD-safe palette cycle
        "axes.facecolor": theme.background,
        "axes.edgecolor": spine_color,
        "axes.linewidth": spine_lw,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.spines.left": not theme.hide_spines,
        "axes.spines.bottom": not theme.hide_spines,
        "axes.labelcolor": theme.ink,
        "axes.labelsize": profile["label"],
        "axes.labelpad": 5.0,
        "axes.titlesize": profile["title"],
        "axes.titleweight": theme.title_weight,
        "axes.titlelocation": "left",
        "axes.titlepad": 8.0,
        "axes.axisbelow": True,
        "axes.grid": use_grid,
        "axes.grid.axis": grid_axis,
        "axes.prop_cycle": cycler(color=cycle_colors),
        "grid.color": theme.grid,
        "grid.linewidth": float(theme.grid_lw) if use_grid else 0.5,
        "grid.linestyle": theme.grid_style if use_grid else "-",
        # Crisp ticks
        "xtick.direction": "out",
        "ytick.direction": "out",
        "xtick.top": False,
        "ytick.right": False,
        "xtick.color": theme.axis,
        "ytick.color": theme.axis,
        "xtick.labelcolor": theme.ink,
        "ytick.labelcolor": theme.ink,
        "xtick.major.size": tick_len,
        "ytick.major.size": tick_len,
        "xtick.major.width": tick_w,
        "ytick.major.width": tick_w,
        "xtick.labelsize": profile["tick"],
        "ytick.labelsize": profile["tick"],
        # Frameless legends
        "legend.frameon": False,
        "legend.fontsize": profile["legend"],
        "legend.title_fontsize": profile["legend"],
        "legend.handlelength": 1.6,
        "legend.handletextpad": 0.5,
        "legend.borderaxespad": 0.5,
        "legend.labelspacing": 0.35,
        # Data strokes & perceptual colormap
        "lines.linewidth": float(theme.line_lw),
        "lines.solid_capstyle": theme.line_capstyle,
        "lines.solid_joinstyle": "round",
        "lines.markersize": 5.0,
        "lines.markeredgewidth": 0.6,
        "patch.linewidth": float(theme.bar_edge_lw),
        "patch.edgecolor": theme.bar_edgecolor or theme.background,
        "errorbar.capsize": 2.5,
        "image.cmap": "viridis",
    }

    if theme.title_family is not None:
        params["font.serif"] = list(theme.title_family)
    if theme.sketch is not None:
        params["path.sketch"] = theme.sketch
    if theme.extra_rc:
        params.update(theme.extra_rc)
    return params


class StyleContext:
    """Reusable context manager for chat-ready Matplotlib styling.

    Use as ``with mint.style(): ...`` without leaking global state, inspect via
    ``.rc_params()``, or apply globally via ``.apply()``.
    """

    def __init__(
        self,
        rc: Mapping[str, Any],
        *,
        theme: Theme,
        palette: str | None,
        accent: str | None,
        width: str | int,
    ) -> None:
        self._rc: dict[str, Any] = dict(rc)
        self.theme = theme
        self.palette = palette
        self.accent = accent
        self.width = width
        self._stack: list[Any] = []

    @property
    def figsize(self) -> tuple[float, float]:
        w, h = self._rc["figure.figsize"]
        return (float(w), float(h))

    @property
    def dpi(self) -> int:
        return int(self._rc["figure.dpi"])

    def rc_params(self) -> dict[str, Any]:
        """Return a copy of the Matplotlib rcParams dictionary."""
        return dict(self._rc)

    def apply(self) -> dict[str, Any]:
        """Apply these rcParams globally to ``matplotlib.rcParams`` and return them."""
        mpl.rcParams.update(self._rc)
        return dict(self._rc)

    def __enter__(self) -> Self:
        ctx = mpl.rc_context(rc=self._rc)
        ctx.__enter__()
        self._stack.append(ctx)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._stack:
            ctx = self._stack.pop()
            ctx.__exit__(exc_type, exc, tb)

    def __repr__(self) -> str:
        return (
            f"StyleContext(style={self.theme.name!r}, width={self.width!r}, "
            f"figsize={self.figsize!r}, dpi={self.dpi})"
        )


def style(
    style: str | Theme = "mintfig",
    *,
    palette: str | ExplainPalette | None = None,
    width: str | float = "chat",
    accent: str | None = None,
) -> StyleContext:
    """Return a chat-ready Matplotlib ``rcParams`` context manager.

    Sizes figures cleanly for the target reading width (``"chat"`` -> 6.0×3.6 in
    at 150 DPI for 700 px display; ``"narrow"`` -> 4.5×3.0 in; ``"slide"`` ->
    8.5×4.8 in), sets readable font sizes (>= 11 px at display width), applies
    mintfig's colorblind-safe theme palette, removes top/right spines, sets
    ``axes.unicode_minus=True``, ``image.cmap="viridis"``, frameless legends,
    and constrained layout.

    Examples
    --------
    >>> with mint.style():
    ...     fig, ax = plt.subplots()
    ...     ax.bar(["A", "B"], [10, 15])
    >>> mint.style("dark", palette="tol", width="narrow").apply()
    """
    resolved_theme = get_theme(style)
    resolved_theme, palette_name = apply_palette(resolved_theme, palette)
    resolved_theme, accent_hex = apply_accent(resolved_theme, accent)
    width_key, profile = _resolve_width_profile(width)
    rc = _build_byo_rc_params(resolved_theme, profile, lead_accent=accent is not None)
    return StyleContext(
        rc,
        theme=resolved_theme,
        palette=palette_name,
        accent=accent_hex,
        width=width_key,
    )


def _attach_legacy_style_helpers() -> None:
    """Expose ``mintfig.style`` module helpers on the ``style`` callable so internal
    ``from . import style as _style`` imports remain compatible after ``mint.style``
    rebinds the package attribute."""
    pub_style = importlib.import_module("mintfig.style")
    for attr in ("_resolve_font_tuple", "resolved_font_name", "rc_params", "use", "apply"):
        setattr(style, attr, getattr(pub_style, attr))


_attach_legacy_style_helpers()


# --------------------------------------------------------------------------- #
# B2: figure_to_panel() — wrap any Matplotlib Figure / Axes for mint.explain()
# --------------------------------------------------------------------------- #


def _normalize_check_width(width: str | float) -> str | int:
    """Map an ``explain()`` width argument (preset or mm/px number) to a ``mint.check`` width."""
    if isinstance(width, str):
        key = width.strip().lower()
        if key in WIDTHS:
            return key
        if key in {"single"}:
            return "chat"
        if key in {"wide", "double", "full"}:
            return "slide"
        return "chat"
    if isinstance(width, (int, float)) and not isinstance(width, bool):
        val = float(width)
        if math.isfinite(val) and val > 0:
            # explain() numeric widths are in mm (chat = 140 mm -> 700 px); > 300 is px.
            return round(val if val > 300 else val * 700.0 / 140.0)
    return "chat"


def _render_source_figure(source_fig: Figure, *, dpi: int = 300) -> tuple[Any, float]:
    """Rasterize ``source_fig`` at crisp DPI, returning ``(rgba_array, aspect_h_over_w)``."""
    import numpy as np
    from PIL import Image

    with _AggCanvas(source_fig):
        buf = io.BytesIO()
        source_fig.savefig(
            buf,
            format="png",
            dpi=dpi,
            facecolor=source_fig.get_facecolor(),
            edgecolor="none",
            bbox_inches="tight",
            pad_inches=0.04,
        )
    buf.seek(0)
    with Image.open(buf) as im:
        rgba = np.asarray(im.convert("RGBA"))
    img_h, img_w = rgba.shape[:2]
    aspect = float(img_h) / float(max(1, img_w))
    return rgba, aspect


def figure_to_panel(
    fig_or_ax: Figure | Axes | SubFigure,
    *,
    title: str | None = None,
    describe: str | None = None,
    width: str | float = "chat",
    claim: str | None = None,
) -> Panel:
    """Wrap an existing Matplotlib ``Figure`` or ``Axes`` as a :class:`~mintfig.Panel`.

    Runs :func:`mintfig.check` on the source figure to extract computed ``facts``
    and audit issues, rasterizes the figure at 300 DPI with ``aspect="equal"``
    and ``ax.set_axis_off()`` so arbitrary Matplotlib / Seaborn / 3D / colorbar
    layouts render with zero artist-copy bugs, and propagates blocking issues
    into ``Explanation.issues`` and ``Explanation.ship``.
    """
    source_fig = _resolve_figure(fig_or_ax)
    check_width = _normalize_check_width(width)
    report: FigureCheck = check(source_fig, claim=claim, width=check_width)
    rgba, aspect = _render_source_figure(source_fig, dpi=300)

    facts: list[str] = []
    panel_kinds: list[str] = []
    inferred_title: str | None = None
    for p in report.get("panels") or []:
        kind_str = str(p.get("kind") or "").strip()
        if kind_str:
            panel_kinds.append(kind_str)
        if inferred_title is None and p.get("title"):
            inferred_title = str(p["title"]).strip()
        for f in p.get("facts") or []:
            text = str(f).strip()
            if text and text not in facts:
                facts.append(text)

    if describe is not None:
        panel_describe = str(describe).strip() or "Matplotlib figure"
    else:
        unique_kinds = list(dict.fromkeys(panel_kinds))
        if unique_kinds:
            panel_describe = f"Matplotlib figure ({', '.join(unique_kinds)})"
        else:
            panel_describe = "Matplotlib figure"
        if inferred_title and title is None and inferred_title not in panel_describe:
            panel_describe = f"{panel_describe}: {inferred_title}"

    issues: list[dict[str, Any]] = []
    for raw in report.get("issues") or []:
        rule = str(raw.get("rule", "check_issue"))
        severity = str(raw.get("severity", "warning"))
        # Propagate mint.check claim mismatches as blocking errors on wrapped figures
        # without altering advisory claim semantics on built-in mint.explain forms.
        if rule == "claim_number_mismatch":
            severity = "error"
        issues.append(
            _issue(
                rule,
                severity,
                str(raw.get("message", "")),
                str(raw.get("fix_hint", "")),
            )
        )

    def _height_mm(cell_w_mm: float, _m: Any, _s: Any, _t: Any) -> float:
        return max(24.0, min(105.0, float(cell_w_mm) * aspect))

    def _min_height_mm(cell_w_mm: float, _m: Any, _s: Any, _t: Any) -> float:
        return max(22.0, min(85.0, float(cell_w_mm) * aspect * 0.78))

    def _draw(ctx: _Ctx, ax: Axes) -> None:
        ax.set_facecolor(ctx.theme.background)
        ax.imshow(rgba, aspect="equal", interpolation="lanczos")
        ax.set_axis_off()

    display_info = report.get("display") or {}
    spec_data: dict[str, Any] = {
        "source": "matplotlib",
        "title": title,
        "describe": panel_describe,
        "check_ship": bool(report.ship),
        "check_min_text_px": display_info.get("min_text_px"),
        "check_panels": [
            {"kind": p.get("kind"), "title": p.get("title")}
            for p in (report.get("panels") or [])
        ],
    }

    return Panel(
        kind="custom",
        title=title,
        label=None,
        unit=None,
        spec=spec_data,
        facts=facts,
        describe=panel_describe,
        _height_mm=_height_mm,
        _min_height_mm=_min_height_mm,
        _draw=_draw,
        issues=issues,
        stretch=True,
    )


# --------------------------------------------------------------------------- #
# Jupyter / IPython Magic (%load_ext mintfig) & auto_check()
# --------------------------------------------------------------------------- #


@dataclass
class _AutoCheckState:
    enabled: bool = True
    width: str | int = "chat"
    checked_ids: dict[int, int] = None  # type: ignore[assignment]
    callback: Any = None

    def __post_init__(self) -> None:
        if self.checked_ids is None:
            self.checked_ids = {}


_AUTO_STATE = _AutoCheckState()


def format_badge(report: Mapping[str, Any], *, label: str | None = None) -> str:
    """Format a compact 1-line ``mintfig check`` badge for notebook/terminal output."""
    disp = report.get("display") or {}
    min_px = disp.get("min_text_px")
    width_px = disp.get("width_px")
    prefix = f"mintfig check ({label})" if label else "mintfig check"
    issues = list(report.get("issues") or [])

    if report.get("ship"):
        meta: list[str] = []
        if width_px:
            meta.append(f"{width_px} px")
        if min_px is not None:
            meta.append(f"min text {min_px:.1f} px")
        if issues:
            rules = ", ".join(str(i.get("rule")) for i in issues[:2])
            meta.append(f"note: {rules}")
        detail = f" ({' · '.join(meta)})" if meta else ""
        return f"{prefix}: SHIP{detail}"

    first = issues[0] if issues else {}
    rule = str(first.get("rule", "issue"))
    hint = str(first.get("fix_hint", "")).strip()
    extra = f" (+{len(issues) - 1} more)" if len(issues) > 1 else ""
    if hint:
        return f"{prefix}: FIX FIRST — {rule}{extra}. Fix: {hint}"
    return f"{prefix}: FIX FIRST — {rule}{extra}"


def _open_pyplot_figures() -> list[tuple[int, Figure]]:
    """Return ``[(fignum, Figure), ...]`` for currently open pyplot figures."""
    if "matplotlib.pyplot" not in sys.modules:
        return []
    import matplotlib.pyplot as plt

    return [(int(num), plt.figure(num)) for num in plt.get_fignums()]


def _check_new_figures(
    *,
    width: str | int,
    seen: dict[int, int],
    emit: bool = True,
) -> list[FigureCheck]:
    """Run ``mint.check`` on open pyplot figures not yet recorded in ``seen``."""
    open_figs = _open_pyplot_figures()
    open_nums = {num for num, _ in open_figs}
    for stale in [num for num in list(seen) if num not in open_nums]:
        seen.pop(stale, None)

    reports: list[FigureCheck] = []
    for num, fig in open_figs:
        if seen.get(num) == id(fig):
            continue
        seen[num] = id(fig)
        if not fig.axes:
            continue
        report = check(fig, width=width)
        reports.append(report)
        if emit:
            label = f"fig {num}" if len(open_figs) > 1 or num > 1 else None
            print(format_badge(report, label=label))
    return reports


def _parse_magic_width(raw: str) -> str | int:
    val = raw.strip().lower()
    if val in WIDTHS:
        return val
    try:
        px = int(val)
    except ValueError as exc:
        valid = ", ".join(sorted(WIDTHS))
        raise ValueError(f"Unknown width {raw!r}. Use {valid} or a positive integer px.") from exc
    if px <= 0:
        raise ValueError(f"width must be positive, got {px}.")
    return px


class _AutoCheckController:
    """Helper / context manager returned by :func:`auto_check`."""

    def __init__(self, enabled: bool = True, *, width: str | int = "chat") -> None:
        resolved_w = _parse_magic_width(str(width))
        self._prev_enabled = _AUTO_STATE.enabled
        self._prev_width = _AUTO_STATE.width
        self.enabled = bool(enabled)
        self.width = resolved_w
        self.reports: list[FigureCheck] = []
        self._block_seen: dict[int, int] = {}

        _AUTO_STATE.enabled = self.enabled
        _AUTO_STATE.width = self.width

    def check_open(self, *, emit: bool = True) -> list[FigureCheck]:
        """Check newly created open Matplotlib figures right now."""
        if not self.enabled:
            return []
        found = _check_new_figures(width=self.width, seen=self._block_seen, emit=emit)
        self.reports.extend(found)
        return found

    def __enter__(self) -> Self:
        self._block_seen = {num: id(fig) for num, fig in _open_pyplot_figures()}
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        try:
            if exc_type is None and self.enabled:
                self.check_open(emit=True)
        finally:
            _AUTO_STATE.enabled = self._prev_enabled
            _AUTO_STATE.width = self._prev_width


def auto_check(enabled: bool = True, *, width: str | int = "chat") -> _AutoCheckController:
    """Configure or scope automatic ``mint.check`` badges on open Matplotlib figures.

    Can be called directly to toggle the IPython auto-checker::

        mint.byo.auto_check(True, width="narrow")
        mint.byo.auto_check(False)

    Or used as a context manager in any script or notebook cell::

        with mint.byo.auto_check(width="chat") as ac:
            fig, ax = plt.subplots()
            ax.plot([1, 2, 3], [2, 4, 6])
        # prints 1-line SHIP / FIX FIRST badge on exit; reports in ac.reports
    """
    return _AutoCheckController(enabled=enabled, width=width)


def _mintfig_check_magic(line: str = "") -> None:
    """IPython line magic: ``%mintfig_check [on|off|status|width=chat|narrow|slide|<px>]``."""
    tokens = shlex.split(line or "")
    if not tokens or tokens == ["status"]:
        state = "on" if _AUTO_STATE.enabled else "off"
        print(f"mintfig check: {state} (width={_AUTO_STATE.width})")
        return

    for tok in tokens:
        low = tok.strip().lower()
        if low in {"on", "enable", "true"}:
            _AUTO_STATE.enabled = True
        elif low in {"off", "disable", "false"}:
            _AUTO_STATE.enabled = False
        elif low == "status":
            pass
        elif low.startswith("width="):
            raw_w = tok.split("=", 1)[1]
            try:
                _AUTO_STATE.width = _parse_magic_width(raw_w)
            except ValueError as exc:
                print(f"mintfig check: {exc}")
                return
        else:
            print(
                f"mintfig check: unknown option {tok!r}. "
                "Usage: %mintfig_check [on|off|status|width=narrow|chat|slide|<px>]"
            )
            return

    state = "on" if _AUTO_STATE.enabled else "off"
    print(f"mintfig check: {state} (width={_AUTO_STATE.width})")


def _post_run_cell_hook(_result: Any = None) -> None:
    if not _AUTO_STATE.enabled:
        return
    _check_new_figures(width=_AUTO_STATE.width, seen=_AUTO_STATE.checked_ids, emit=True)


def load_ipython_extension(ipython: Any) -> None:
    """Register ``%mintfig_check`` line magic and ``post_run_cell`` auto-check hook.

    Duck-typed with zero IPython import dependency: works in Jupyter, IPython
    shells, and lightweight test doubles exposing ``register_magic_function``
    and ``events.register``.
    """
    if _AUTO_STATE.callback is not None:
        unload_ipython_extension(ipython)

    _AUTO_STATE.enabled = True
    _AUTO_STATE.checked_ids = {num: id(fig) for num, fig in _open_pyplot_figures()}

    if hasattr(ipython, "register_magic_function"):
        ipython.register_magic_function(_mintfig_check_magic, "line", "mintfig_check")

    events = getattr(ipython, "events", None)
    if events is not None and hasattr(events, "register"):
        events.register("post_run_cell", _post_run_cell_hook)
        _AUTO_STATE.callback = _post_run_cell_hook


def unload_ipython_extension(ipython: Any) -> None:
    """Unregister the ``post_run_cell`` auto-check hook installed by :func:`load_ipython_extension`."""
    events = getattr(ipython, "events", None)
    cb = _AUTO_STATE.callback
    if cb is not None and events is not None and hasattr(events, "unregister"):
        try:
            events.unregister("post_run_cell", cb)
        except ValueError:
            pass
    _AUTO_STATE.callback = None
    _AUTO_STATE.enabled = False
    _AUTO_STATE.checked_ids.clear()
