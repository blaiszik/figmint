"""Visual surface themes for ``fm.explain`` (``figmint``, ``bold``, ``editorial``, ``sketch``).

A theme changes only the visual surface — typography, colour palette, background,
gridlines, axis framing, header/footer rules, and optional hand-drawn sketch jitter.
It never changes the information-design rules enforced by ``fm.explain`` (takeaway
titles, sorted zero-based bars, <= 4 coloured series, <= 3 highlights, direct labels,
chat legibility, or CVD/grayscale separation).
"""

from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from typing import Any

import matplotlib as mpl
from matplotlib.colors import to_rgb

from . import style
from .specs import JournalSpec


@dataclass(frozen=True)
class Theme:
    """Immutable surface style for ``fm.explain`` figures."""

    name: str
    description: str

    # Surface & structural colours
    background: str = "#FFFFFF"
    ink: str = "#1A1D21"
    muted: str = "#5B6570"
    axis: str = "#8A939E"
    grid: str = "#E3E7EC"
    context_line: str = "#B4BCC6"
    context_fill: str = "#CDD3DA"
    zero_line: str = "#1A1D21"
    halo_alpha: float = 0.85

    # Categorical & matrix palettes (strictly 4 series + 3 accents, CVD/grayscale verified)
    series_colors: tuple[str, ...] = ("#1F5A9D", "#CD4324", "#0F9478", "#CC8800")
    accent_colors: tuple[str, ...] = ("#CD4324", "#1F5A9D", "#0F9478")
    seq_stops: tuple[str, ...] = (
        "#F4F7FB",
        "#C9DBEF",
        "#8FB5DF",
        "#4F8ACB",
        "#1F5A9D",
        "#173F70",
    )
    div_low: tuple[str, ...] = ("#1B4E8A", "#4F8ACB", "#A9C7E6")
    div_high: tuple[str, ...] = ("#F0B7A4", "#DD6F50", "#B5391E")
    div_mid: str = "#F1F2F4"

    # Typography
    title_family: tuple[str, ...] | None = None
    body_family: tuple[str, ...] | None = None
    title_scale: float = 1.3
    title_weight: str = "bold"
    allow_serif_title: bool = False
    panel_tag_color: str | None = None

    # Gridlines, spines & ticks
    grid_style: str = "-"
    grid_lw: float = 0.5
    grid_both_axes: bool = False
    hide_spines: bool = False
    axis_lw: float = 0.6
    zero_line_lw: float = 0.7
    tick_length: float = 2.5
    tick_width: float = 0.6
    inline_y_ticks: bool = False

    # Data strokes & marks
    line_lw: float = 1.7
    context_line_lw: float = 0.9
    facet_line_lw: float = 1.5
    line_capstyle: str = "round"
    bar_height: float = 0.66
    bar_edgecolor: str | None = None
    bar_edge_lw: float = 0.0

    # Editorial chrome (header & footer rules)
    top_rule: bool = False
    top_rule_color: str | None = None
    top_rule_lw: float = 1.2
    footer_rule: bool = False
    footer_rule_color: str | None = None
    footer_rule_lw: float = 0.7

    # Glyphs & sketch effects
    minus_sign: str = "\N{MINUS SIGN}"
    ellipsis: str = "\N{HORIZONTAL ELLIPSIS}"
    en_dash: str = "\N{EN DASH}"
    sketch: tuple[float, float, float] | None = None
    stroke_outline_pt: float = 0.0
    warn_unless_illustrative: bool = False
    extra_rc: dict[str, Any] = field(default_factory=dict)

    @property
    def default_color(self) -> str:
        return self.series_colors[0]

    @property
    def resolved_panel_tag_color(self) -> str:
        return self.panel_tag_color if self.panel_tag_color is not None else self.muted

    def rc_params(self, spec: JournalSpec) -> dict[str, Any]:
        """Build Matplotlib rcParams layering theme surface tokens onto ``spec``."""
        params = style.rc_params(spec)
        # Per-glyph fallback: Matplotlib draws a character the body font lacks (an arrow,
        # "∝", "ℏ") from the next family in this list instead of a missing-glyph box.
        # DejaVu Sans ships with Matplotlib, so the fallback exists on every host.
        params["font.family"] = ["sans-serif", "DejaVu Sans"]
        # The "custom" mathtext fontset looks up every slot when it first lays out a
        # super/subscript, including \mathcal's default "cursive" stack, whose first
        # installed entry on some systems has no usable weight: Matplotlib then logs a
        # "findfont: Failed to find font weight normal" warning on every run. Chat
        # figures never draw \mathcal ($...$ is not math there), so point the slot at
        # the body font and the cursive stack is never probed.
        params["mathtext.cal"] = params["mathtext.rm"]
        if self.name == "figmint" and not self.extra_rc:
            return params

        if self.body_family is not None:
            font_name = style._resolve_font_tuple(self.body_family)
            params["font.sans-serif"] = list(self.body_family)
            params["mathtext.rm"] = font_name
            params["mathtext.it"] = f"{font_name}:italic"
            params["mathtext.bf"] = f"{font_name}:bold"
            params["mathtext.sf"] = font_name
            params["mathtext.cal"] = font_name

        if self.title_family is not None:
            params["font.serif"] = list(self.title_family)

        params["text.color"] = self.ink
        params["axes.labelcolor"] = self.ink
        params["figure.facecolor"] = self.background
        params["figure.edgecolor"] = self.background
        params["savefig.facecolor"] = self.background
        params["savefig.edgecolor"] = self.background
        params["axes.facecolor"] = self.background
        params["axes.edgecolor"] = self.background if self.hide_spines else self.axis
        params["lines.solid_capstyle"] = self.line_capstyle

        if self.sketch is not None:
            params["path.sketch"] = self.sketch
        if self.minus_sign == "-":
            params["axes.unicode_minus"] = False

        if self.extra_rc:
            params.update(self.extra_rc)
        return params

    def rc_context(self, spec: JournalSpec) -> AbstractContextManager[None]:
        """Context manager applying this theme's rcParams without leaking global state."""
        return mpl.rc_context(rc=self.rc_params(spec))


def relative_luminance(color: str) -> float:
    """Compute WCAG 2.1 relative luminance for a Matplotlib color string."""

    def _lin(c: float) -> float:
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (_lin(c) for c in to_rgb(color))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(fg: str, bg: str = "#FFFFFF") -> float:
    """Return WCAG contrast ratio between ``fg`` and ``bg`` (>= 1.0)."""
    l1 = relative_luminance(fg)
    l2 = relative_luminance(bg)
    hi, lo = (l1, l2) if l1 >= l2 else (l2, l1)
    return (hi + 0.05) / (lo + 0.05)


# --------------------------------------------------------------------------- #
# Built-in themes
# --------------------------------------------------------------------------- #

FIGMINT_THEME = Theme(
    name="figmint",
    description="Clean default figmint chat style: white ground, restrained editorial palette, quiet gridlines.",
)

# bold: high-contrast surface on a #F0F0F0 matte-gray ground with heavy lines.
# Series palette: bright blue (#008FD5), vermilion (#D6381C),
# deep plum (#6B1C6D), and warm gold (#DDA324) — min_gray=0.080, min_cvd=0.316.
BOLD_THEME = Theme(
    name="bold",
    description="Bold, high-contrast data journalism look on a matte-gray ground; best for a single strong comparison or trend.",
    background="#F0F0F0",
    ink="#222222",
    muted="#525252",
    axis="#7A7A7A",
    grid="#CBCBCB",
    context_line="#A6A6A6",
    context_fill="#C6C6C6",
    zero_line="#3A3A3A",
    halo_alpha=0.92,
    series_colors=("#008FD5", "#D6381C", "#6B1C6D", "#DDA324"),
    accent_colors=("#D6381C", "#008FD5", "#6B1C6D"),
    seq_stops=("#E6EEF4", "#B8D8EE", "#74B9E3", "#2A9FD9", "#0079B8", "#005380"),
    div_low=("#005B8C", "#008FD5", "#94CDEB"),
    div_high=("#F0B0A1", "#E36249", "#B82910"),
    div_mid="#E4E4E4",
    body_family=("Helvetica Neue", "Helvetica", "Arial", "Liberation Sans", "DejaVu Sans"),
    title_scale=1.42,
    title_weight="bold",
    panel_tag_color="#D6381C",
    grid_style="-",
    grid_lw=0.6,
    grid_both_axes=True,
    hide_spines=True,
    axis_lw=0.0,
    zero_line_lw=1.2,
    tick_length=0.0,
    tick_width=0.0,
    line_lw=2.3,
    context_line_lw=1.2,
    facet_line_lw=1.9,
    line_capstyle="butt",
    bar_height=0.70,
    footer_rule=True,
    footer_rule_color="#BEBEBE",
    footer_rule_lw=0.8,
)

# editorial: newspaper-graphics surface with a stark white ground, crisp black top rule,
# bold Georgia serif headline paired with Helvetica Neue body, thin dotted horizontal
# gridlines, dark baseline, and y-tick labels sitting above gridlines with top-only unit.
# Series palette: editorial steel blue, brick terracotta, sage teal, warm ochre
# — min_gray=0.075, min_cvd=0.260.
EDITORIAL_THEME = Theme(
    name="editorial",
    description="Quiet, annotation-led newspaper editorial style with serif headlines and above-gridline labels; best for multi-panel arguments.",
    background="#FFFFFF",
    ink="#121212",
    muted="#666666",
    axis="#333333",
    grid="#D6D6D6",
    context_line="#C0C0C0",
    context_fill="#D8D8D8",
    zero_line="#222222",
    halo_alpha=0.92,
    series_colors=("#285F8A", "#D44D27", "#4B9B88", "#D9A226"),
    accent_colors=("#D44D27", "#285F8A", "#4B9B88"),
    seq_stops=("#F5F7F9", "#D3E0EA", "#9EBBD1", "#6191B5", "#285F8A", "#193F5E"),
    div_low=("#1A476A", "#4A7FA8", "#A7C4DA"),
    div_high=("#F0B8A5", "#DF7452", "#B83B19"),
    div_mid="#F2F2F2",
    title_family=("Georgia", "Charter", "DejaVu Serif", "serif"),
    body_family=("Helvetica Neue", "Helvetica", "Arial", "Liberation Sans", "DejaVu Sans"),
    title_scale=1.42,
    title_weight="bold",
    allow_serif_title=True,
    panel_tag_color="#121212",
    grid_style=":",
    grid_lw=0.6,
    grid_both_axes=False,
    hide_spines=False,
    axis_lw=0.65,
    zero_line_lw=0.95,
    tick_length=2.5,
    tick_width=0.6,
    inline_y_ticks=True,
    line_lw=1.65,
    context_line_lw=0.85,
    facet_line_lw=1.45,
    line_capstyle="round",
    bar_height=0.64,
    top_rule=True,
    top_rule_color="#121212",
    top_rule_lw=1.3,
    footer_rule=True,
    footer_rule_color="#DCDCDC",
    footer_rule_lw=0.6,
)

# sketch: hand-drawn style with deterministic Matplotlib path.sketch jitter,
# hand-lettered font stack, bold black ink strokes, no gridlines, ASCII minus/ellipsis,
# and an honesty warning unless source/note marks the data as illustrative or synthetic.
# Series palette: marker blue, comic red, whiteboard green, highlighter gold
# — min_gray=0.058, min_cvd=0.284.
SKETCH_THEME = Theme(
    name="sketch",
    description="Hand-drawn sketch style signaling a conceptual or illustrative point rather than exact measurements.",
    background="#FFFFFF",
    ink="#111111",
    muted="#484848",
    axis="#111111",
    grid="#E2E2E2",
    context_line="#9A9A9A",
    context_fill="#D2D2D2",
    zero_line="#111111",
    halo_alpha=0.92,
    series_colors=("#16508F", "#DC4426", "#3D9970", "#E2A61E"),
    accent_colors=("#DC4426", "#16508F", "#3D9970"),
    seq_stops=("#F4F7FC", "#C9DBF2", "#8FB4E2", "#4E88CA", "#16508F", "#0E3563"),
    div_low=("#123F73", "#4A82C2", "#A6C5E8"),
    div_high=("#F5B6A8", "#E56D52", "#BD2F14"),
    div_mid="#F3F3F3",
    body_family=(
        "Humor Sans",
        "Comic Neue",
        "Chalkboard SE",
        "Chalkboard",
        "Comic Sans MS",
        "DejaVu Sans",
    ),
    title_scale=1.35,
    title_weight="bold",
    panel_tag_color="#111111",
    grid_style="none",
    grid_lw=0.0,
    grid_both_axes=False,
    hide_spines=False,
    axis_lw=1.2,
    zero_line_lw=1.25,
    tick_length=3.5,
    tick_width=1.1,
    line_lw=1.9,
    context_line_lw=1.15,
    facet_line_lw=1.65,
    line_capstyle="round",
    bar_height=0.64,
    bar_edgecolor="#111111",
    bar_edge_lw=0.9,
    minus_sign="-",
    ellipsis="...",
    en_dash="-",
    sketch=(0.9, 95.0, 2.0),
    stroke_outline_pt=2.5,
    warn_unless_illustrative=True,
)

THEMES: dict[str, Theme] = {
    "figmint": FIGMINT_THEME,
    "bold": BOLD_THEME,
    "editorial": EDITORIAL_THEME,
    "sketch": SKETCH_THEME,
}

THEME_ALIASES: dict[str, str] = {
    "default": "figmint",
    "newspaper": "editorial",
    "hand_drawn": "sketch",
}


def get_theme(theme: str | Theme = "figmint") -> Theme:
    """Resolve a theme name, alias, or :class:`Theme` instance."""
    if isinstance(theme, Theme):
        return theme
    if not isinstance(theme, str):
        raise TypeError(
            f"style must be a theme name or Theme instance, got {type(theme).__name__}."
        )
    key = theme.strip().lower().replace("-", "_").replace(" ", "_")
    canonical = THEME_ALIASES.get(key, key)
    if canonical not in THEMES:
        valid = ", ".join(THEMES)
        raise ValueError(f"Unknown style {theme!r}. Choose one of: {valid}.")
    return THEMES[canonical]
