"""Visual surface themes and color palettes for ``mint.explain``.

Built-in themes: ``mintfig`` (default), ``mint``, ``pine`` (alias ``mint_dark``),
``botanical``, ``bold``, ``editorial``, ``paper``, ``dark``, ``mono``, ``sketch``.
Built-in explain palettes: ``default``, ``okabe_ito``, ``tol``, ``earth``,
``ocean``, ``berry``, ``mint``, ``spearmint``, ``matcha``, ``glacier``, ``mineral``.

A theme or palette changes only the visual surface — typography, colour palette,
background, gridlines, axis framing, header/footer rules, and optional hand-drawn
sketch jitter. It never changes the information-design rules enforced by
``mint.explain`` (takeaway titles, sorted zero-based bars, <= 4 coloured series,
<= 3 highlights, direct labels, chat legibility, or CVD/grayscale separation).
"""

from __future__ import annotations

import importlib
import os
from collections.abc import Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import matplotlib as mpl
from matplotlib.colors import to_rgb

from .specs import JournalSpec

try:
    import tomllib
except ImportError:  # pragma: no cover - Python 3.10 fallback
    tomllib = None  # type: ignore[assignment]

style = importlib.import_module("mintfig.style")


@dataclass(frozen=True)
class Theme:
    """Immutable surface style for ``mint.explain`` figures."""

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
    accent_colors: tuple[str, ...] = ("#1F5A9D", "#CD4324", "#0F9478")
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

    # Editorial chrome (header & footer rules + Economist/FT top accent flag)
    top_rule: bool = False
    top_rule_color: str | None = None
    top_rule_lw: float = 1.2
    top_flag: bool = False
    top_flag_color: str | None = None
    top_flag_width_mm: float = 14.0
    top_flag_lw: float = 3.2
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
        if self.name == "mintfig" and not self.extra_rc:
            return params

        require_bold = self.sketch is None
        if self.body_family is not None:
            font_name = style._resolve_font_tuple(self.body_family, require_bold=require_bold)
            params["font.sans-serif"] = style._ordered_font_stack(
                self.body_family, require_bold=require_bold
            )
            params["mathtext.rm"] = font_name
            params["mathtext.it"] = f"{font_name}:italic"
            params["mathtext.bf"] = f"{font_name}:bold"
            params["mathtext.sf"] = font_name
            params["mathtext.cal"] = font_name

        if self.title_family is not None:
            params["font.serif"] = style._ordered_font_stack(
                self.title_family, require_bold=require_bold
            )

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

MINTFIG_THEME = Theme(
    name="mintfig",
    description="Clean default mintfig chat style: white ground, restrained editorial palette, quiet gridlines.",
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
    body_family=style.EDITORIAL_SANS_FONTS,
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
    title_family=style.EDITORIAL_SERIF_FONTS,
    body_family=style.EDITORIAL_SANS_FONTS,
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
    top_rule_lw=0.65,
    top_flag=True,
    top_flag_color="#CD4324",
    top_flag_width_mm=14.0,
    top_flag_lw=3.2,
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
        "Liberation Sans",
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

# paper: warm parchment/ivory ground (#FAF7F0) with espresso ink, serif headline,
# and warm editorial hues — min_gray=0.135, min_cvd=0.390.
PAPER_THEME = Theme(
    name="paper",
    description="Warm ivory paper ground with espresso ink, serif headlines, and refined earth-editorial hues.",
    background="#FAF7F0",
    ink="#221E1A",
    muted="#635B52",
    axis="#8F867A",
    grid="#E7E0D3",
    context_line="#BEB5A7",
    context_fill="#D7CFC2",
    zero_line="#221E1A",
    halo_alpha=0.90,
    series_colors=("#1E446E", "#B83B1E", "#36997A", "#DAA424"),
    accent_colors=("#B83B1E", "#1E446E", "#36997A"),
    seq_stops=("#F7F3EA", "#D8E1E8", "#A3BACD", "#608AB0", "#1E446E", "#132D4A"),
    div_low=("#153559", "#4B7CA8", "#A8C3DA"),
    div_high=("#EBB4A2", "#D96B4D", "#A32F14"),
    div_mid="#EFEAE0",
    title_family=style.EDITORIAL_SERIF_FONTS,
    body_family=style.EDITORIAL_SANS_FONTS,
    title_scale=1.38,
    title_weight="bold",
    allow_serif_title=True,
    panel_tag_color="#635B52",
    grid_style="-",
    grid_lw=0.5,
    axis_lw=0.6,
    zero_line_lw=0.8,
    line_lw=1.75,
    context_line_lw=0.9,
    facet_line_lw=1.5,
    top_rule=True,
    top_rule_color="#221E1A",
    top_rule_lw=1.0,
    footer_rule=True,
    footer_rule_color="#DDD4C4",
    footer_rule_lw=0.6,
)

# dark: deep slate charcoal ground (#14181F) for dark-mode chat UIs and slides,
# with crisp off-white ink and luminous CVD-safe hues — min_gray=0.094, min_cvd=0.320.
DARK_THEME = Theme(
    name="dark",
    description="Dark slate ground with crisp light ink and luminous CVD-safe hues for dark UIs and slides.",
    background="#14181F",
    ink="#ECEFF4",
    muted="#9AA5B4",
    axis="#657082",
    grid="#272E3B",
    context_line="#586375",
    context_fill="#3A4354",
    zero_line="#CBD3DF",
    halo_alpha=0.88,
    series_colors=("#4A89DC", "#F47E62", "#4BD9BA", "#F6DF78"),
    accent_colors=("#F47E62", "#4A89DC", "#4BD9BA"),
    seq_stops=("#1C2330", "#223654", "#2B5182", "#3B72B3", "#589BE3", "#8CC4F8"),
    div_low=("#78B8F5", "#4381C4", "#233C59"),
    div_high=("#5B2B24", "#B84C3B", "#F4866C"),
    div_mid="#222936",
    body_family=style.EDITORIAL_SANS_FONTS,
    title_scale=1.32,
    title_weight="bold",
    panel_tag_color="#9AA5B4",
    grid_style="-",
    grid_lw=0.55,
    axis_lw=0.65,
    zero_line_lw=0.85,
    line_lw=1.85,
    context_line_lw=0.95,
    facet_line_lw=1.55,
)

# mono: crisp monochrome print/handout theme with one vermilion highlight accent
# — min_gray=0.098, min_cvd=0.343.
MONO_THEME = Theme(
    name="mono",
    description="High-contrast monochrome print theme with a single vermilion highlight accent.",
    background="#FFFFFF",
    ink="#111111",
    muted="#555555",
    axis="#787878",
    grid="#E5E5E5",
    context_line="#B0B0B0",
    context_fill="#D0D0D0",
    zero_line="#111111",
    halo_alpha=0.90,
    series_colors=("#3F4954", "#C8321E", "#7C858F", "#B0B8C0"),
    accent_colors=("#C8321E", "#3F4954", "#7C858F"),
    seq_stops=("#F5F5F5", "#DCDCDC", "#B4B4B4", "#828282", "#4E4E4E", "#222222"),
    div_low=("#222222", "#666666", "#B8B8B8"),
    div_high=("#F0B8AE", "#DE6A56", "#B82814"),
    div_mid="#F0F0F0",
    body_family=style.EDITORIAL_SANS_FONTS,
    title_scale=1.32,
    title_weight="bold",
    panel_tag_color="#C8321E",
    grid_style="-",
    grid_lw=0.5,
    axis_lw=0.65,
    zero_line_lw=0.85,
    line_lw=1.75,
    context_line_lw=0.9,
    facet_line_lw=1.5,
)

# mint: flagship clean whisper-mint ground (#F8FBFA) with pine-charcoal ink,
# crisp mint-emerald top rule, soft mint-gray gridlines, and zero-yellow mint palette
# — min_gray=0.113, min_cvd=0.258.
MINT_THEME = Theme(
    name="mint",
    description="Flagship mint surface: whisper-mint ground, pine-charcoal ink, emerald top rule, and zero-yellow mint palette.",
    background="#F8FBFA",
    ink="#13221D",
    muted="#4D5F58",
    axis="#7A9188",
    grid="#DFEBE6",
    context_line="#A8BDB4",
    context_fill="#CBDAD3",
    zero_line="#13221D",
    halo_alpha=0.90,
    series_colors=("#0F8B6D", "#2B5E9E", "#6E2356", "#8B9AA6"),
    accent_colors=("#0F8B6D", "#2B5E9E", "#6E2356"),
    seq_stops=("#F2FAF7", "#CBEBE0", "#8ED2BC", "#47B393", "#0F8B6D", "#0A5A46"),
    div_low=("#5C1B47", "#99497E", "#D6A9C7"),
    div_high=("#A7DFCD", "#42B290", "#0B6B53"),
    div_mid="#F2F6F4",
    body_family=style.EDITORIAL_SANS_FONTS,
    title_scale=1.34,
    title_weight="bold",
    panel_tag_color="#0F8B6D",
    grid_style="-",
    grid_lw=0.5,
    axis_lw=0.6,
    zero_line_lw=0.8,
    line_lw=1.8,
    context_line_lw=0.9,
    facet_line_lw=1.5,
    top_rule=True,
    top_rule_color="#BFD6CD",
    top_rule_lw=0.7,
    top_flag=True,
    top_flag_color="#0F8B6D",
    top_flag_width_mm=14.0,
    top_flag_lw=3.2,
    footer_rule=True,
    footer_rule_color="#DCE7E2",
    footer_rule_lw=0.6,
)

# pine: deep pine-slate dark ground (#0F1715) with ice-mint ink and luminous
# zero-yellow CVD-safe hues (spearmint, sky blue, soft orchid, cool silver)
# — min_gray=0.087, min_cvd=0.304.
PINE_THEME = Theme(
    name="pine",
    description="Deep pine-slate dark ground with ice-mint ink and luminous zero-yellow CVD-safe hues.",
    background="#0F1715",
    ink="#E8F1EE",
    muted="#94ACA3",
    axis="#587067",
    grid="#1F2D28",
    context_line="#4E665E",
    context_fill="#2D3F39",
    zero_line="#C5D6CF",
    halo_alpha=0.88,
    series_colors=("#38DDA9", "#69B4F8", "#CE62B0", "#E4EFEA"),
    accent_colors=("#38DDA9", "#CE62B0", "#69B4F8"),
    seq_stops=("#172420", "#1C3B32", "#1F5849", "#247D66", "#2CA888", "#5AE0B8"),
    div_low=("#E08AC8", "#A84E90", "#542449"),
    div_high=("#1C4A3C", "#259173", "#5CE3B9"),
    div_mid="#1A2622",
    body_family=style.EDITORIAL_SANS_FONTS,
    title_scale=1.32,
    title_weight="bold",
    panel_tag_color="#38DDA9",
    grid_style="-",
    grid_lw=0.55,
    axis_lw=0.65,
    zero_line_lw=0.85,
    line_lw=1.85,
    context_line_lw=0.95,
    facet_line_lw=1.55,
)

# botanical: warm sage-ivory herbarium ground (#F5F8F4) with serif headline,
# deep forest ink, and zero-yellow matcha palette — min_gray=0.118, min_cvd=0.242.
BOTANICAL_THEME = Theme(
    name="botanical",
    description="Warm sage-ivory herbarium surface with serif headlines, deep forest ink, and zero-yellow matcha hues.",
    background="#F5F8F4",
    ink="#18241C",
    muted="#4E5F53",
    axis="#7F9183",
    grid="#E1EAE0",
    context_line="#B1C0B3",
    context_fill="#CFDACC",
    zero_line="#18241C",
    halo_alpha=0.90,
    series_colors=("#4A8F5D", "#3A2014", "#7AA3CC", "#962444"),
    accent_colors=("#4A8F5D", "#962444", "#3A2014"),
    seq_stops=("#F4F8F3", "#D6E6D4", "#A7CBA5", "#72AE76", "#4A8F5D", "#2A5B39"),
    div_low=("#751A34", "#B24F6B", "#E2B2C0"),
    div_high=("#B6D8BE", "#6CA97B", "#346D44"),
    div_mid="#F1F4F0",
    title_family=style.EDITORIAL_SERIF_FONTS,
    body_family=style.EDITORIAL_SANS_FONTS,
    title_scale=1.38,
    title_weight="bold",
    allow_serif_title=True,
    panel_tag_color="#3A6B4A",
    grid_style="-",
    grid_lw=0.5,
    axis_lw=0.6,
    zero_line_lw=0.8,
    line_lw=1.75,
    context_line_lw=0.9,
    facet_line_lw=1.5,
    top_rule=True,
    top_rule_color="#2D5A3D",
    top_rule_lw=1.1,
    footer_rule=True,
    footer_rule_color="#D5E0D4",
    footer_rule_lw=0.6,
)

THEMES: dict[str, Theme] = {
    "mintfig": MINTFIG_THEME,
    "mint": MINT_THEME,
    "pine": PINE_THEME,
    "botanical": BOTANICAL_THEME,
    "bold": BOLD_THEME,
    "editorial": EDITORIAL_THEME,
    "paper": PAPER_THEME,
    "dark": DARK_THEME,
    "mono": MONO_THEME,
    "sketch": SKETCH_THEME,
}

THEME_ALIASES: dict[str, str] = {
    "default": "mintfig",
    "mint_dark": "pine",
    "newspaper": "editorial",
    "warm": "paper",
    "print": "mono",
    "hand_drawn": "sketch",
}


# --------------------------------------------------------------------------- #
# Explain color palettes (independent of surface theme)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ExplainPalette:
    """CVD- and grayscale-verified 4-color + matrix palette for ``mint.explain``."""

    name: str
    description: str
    series_colors: tuple[str, ...]
    accent_colors: tuple[str, ...]
    seq_stops: tuple[str, ...]
    div_low: tuple[str, ...]
    div_high: tuple[str, ...]
    div_mid: str = "#F1F2F4"


EXPLAIN_PALETTES: dict[str, ExplainPalette] = {
    "default": ExplainPalette(
        name="default",
        description="The active style's built-in editorial palette (blue, vermilion, teal, amber).",
        series_colors=MINTFIG_THEME.series_colors,
        accent_colors=MINTFIG_THEME.accent_colors,
        seq_stops=MINTFIG_THEME.seq_stops,
        div_low=MINTFIG_THEME.div_low,
        div_high=MINTFIG_THEME.div_high,
        div_mid=MINTFIG_THEME.div_mid,
    ),
    "okabe_ito": ExplainPalette(
        name="okabe_ito",
        description="Okabe-Ito colorblind-safe palette tuned for grayscale separation and 4.5:1 text contrast.",
        series_colors=("#005E94", "#CC5500", "#00A87E", "#E6AF00"),
        accent_colors=("#CC5500", "#005E94", "#00A87E"),
        seq_stops=("#F2F7FB", "#C2DFEE", "#7BB9DA", "#2E8EC2", "#005E94", "#003D63"),
        div_low=("#00446E", "#2E8EC2", "#9CCCE6"),
        div_high=("#F2B896", "#E07938", "#B54800"),
        div_mid="#F2F3F5",
    ),
    "tol": ExplainPalette(
        name="tol",
        description="Paul Tol scientific palette: indigo, crimson, emerald, and warm gold.",
        series_colors=("#332288", "#CC3344", "#229966", "#DDAA33"),
        accent_colors=("#CC3344", "#332288", "#229966"),
        seq_stops=("#F4F3FA", "#CFCBE8", "#9D95D1", "#685CB2", "#332288", "#21155C"),
        div_low=("#241766", "#5D4FA6", "#ACA4D9"),
        div_high=("#F0B0B8", "#DE6472", "#B52434"),
        div_mid="#F2F2F5",
    ),
    "earth": ExplainPalette(
        name="earth",
        description="Warm natural tones: deep slate blue, terracotta, moss green, and ochre.",
        series_colors=("#203F60", "#B84228", "#4D8B55", "#D49E2A"),
        accent_colors=("#B84228", "#203F60", "#4D8B55"),
        seq_stops=("#F5F6F8", "#CFD8E2", "#97AEC4", "#5B80A3", "#203F60", "#132940"),
        div_low=("#17304A", "#4F7499", "#A6BCD1"),
        div_high=("#EAB5A6", "#D46D52", "#A1341B"),
        div_mid="#F2F1EE",
    ),
    "ocean": ExplainPalette(
        name="ocean",
        description="Marine palette: deep cobalt, reef coral, seafoam teal, and sand gold.",
        series_colors=("#143E66", "#D95240", "#1A9E9E", "#DEB030"),
        accent_colors=("#D95240", "#143E66", "#1A9E9E"),
        seq_stops=("#F2F7F9", "#C5E1E6", "#7EC2CC", "#359EA8", "#1A7D8A", "#0F4D59"),
        div_low=("#103252", "#3A729E", "#99BCD6"),
        div_high=("#F2BAB2", "#E47868", "#BF3B2A"),
        div_mid="#F2F4F5",
    ),
    "berry": ExplainPalette(
        name="berry",
        description="Rich plum, steel blue, forest emerald, and warm honey.",
        series_colors=("#7B2466", "#1D619E", "#128060", "#CE9216"),
        accent_colors=("#7B2466", "#1D619E", "#128060"),
        seq_stops=("#F9F3F7", "#E4C5DC", "#C68DB8", "#A1568E", "#7B2466", "#521444"),
        div_low=("#154878", "#4682B8", "#A3C4E0"),
        div_high=("#E5B3D7", "#BA66A3", "#7B2466"),
        div_mid="#F3F2F4",
    ),
    "mint": ExplainPalette(
        name="mint",
        description="Zero-yellow mint emerald lead with steel blue, rich plum, and cool slate.",
        series_colors=MINT_THEME.series_colors,
        accent_colors=MINT_THEME.accent_colors,
        seq_stops=MINT_THEME.seq_stops,
        div_low=MINT_THEME.div_low,
        div_high=MINT_THEME.div_high,
        div_mid=MINT_THEME.div_mid,
    ),
    "spearmint": ExplainPalette(
        name="spearmint",
        description="Zero-yellow bright spearmint lead with midnight indigo, deep orchid, and pewter.",
        series_colors=("#129C7E", "#1D2F73", "#8E2B7E", "#99A6AF"),
        accent_colors=("#129C7E", "#8E2B7E", "#1D2F73"),
        seq_stops=("#F1FAF7", "#C6ECE1", "#85D5BF", "#3CB89A", "#129C7E", "#0B6350"),
        div_low=("#6B1E5E", "#A44E96", "#DBB2D4"),
        div_high=("#A6E3D2", "#3EBA9B", "#0D7861"),
        div_mid="#F2F5F4",
    ),
    "matcha": ExplainPalette(
        name="matcha",
        description="Zero-yellow warm botanical matcha/sage lead with espresso, slate blue, and claret.",
        series_colors=BOTANICAL_THEME.series_colors,
        accent_colors=BOTANICAL_THEME.accent_colors,
        seq_stops=BOTANICAL_THEME.seq_stops,
        div_low=BOTANICAL_THEME.div_low,
        div_high=BOTANICAL_THEME.div_high,
        div_mid=BOTANICAL_THEME.div_mid,
    ),
    "glacier": ExplainPalette(
        name="glacier",
        description="Zero-yellow glacier teal lead with cobalt, indigo-violet, and cool graphite.",
        series_colors=("#0F919A", "#2663BA", "#4D1E7A", "#9EA7B2"),
        accent_colors=("#0F919A", "#2663BA", "#4D1E7A"),
        seq_stops=("#F1F9FA", "#C4E6E9", "#7ECAD0", "#38AAB2", "#0F919A", "#095B61"),
        div_low=("#3B1660", "#72499E", "#BDA9D6"),
        div_high=("#A5DCE0", "#3EAAB2", "#0C6E75"),
        div_mid="#F2F5F7",
    ),
    "mineral": ExplainPalette(
        name="mineral",
        description="Zero-yellow jade lead with deep burgundy, denim steel blue, and charcoal.",
        series_colors=("#169168", "#A8244E", "#70A0CC", "#222930"),
        accent_colors=("#169168", "#A8244E", "#70A0CC"),
        seq_stops=("#F2F9F6", "#C8E8DB", "#89CEB5", "#44B08B", "#169168", "#0D5D42"),
        div_low=("#7F1939", "#BC5274", "#E6B4C4"),
        div_high=("#AED2E8", "#6598C4", "#2E6294"),
        div_mid="#F3F4F5",
    ),
}


def get_explain_palette(palette: str | ExplainPalette = "default") -> ExplainPalette:
    """Resolve an explain color palette by name or :class:`ExplainPalette` instance."""
    if isinstance(palette, ExplainPalette):
        return palette
    if not isinstance(palette, str):
        raise TypeError(
            f"palette must be a palette name or ExplainPalette instance, got {type(palette).__name__}."
        )
    key = palette.strip().lower().replace("-", "_").replace(" ", "_")
    if key not in EXPLAIN_PALETTES:
        valid = ", ".join(EXPLAIN_PALETTES)
        raise ValueError(f"Unknown palette {palette!r}. Choose one of: {valid}.")
    return EXPLAIN_PALETTES[key]


def _lift_for_dark_ground(color: str, bg: str) -> str:
    """Lighten a series color when placed on a dark theme background so contrast stays >= 4.5:1."""
    if contrast_ratio(color, bg) >= 4.5:
        return color
    rgb = to_rgb(color)
    for mix in (0.18, 0.32, 0.45, 0.58, 0.72):
        lifted = tuple(c + (1.0 - c) * mix for c in rgb)
        cand = "#{:02X}{:02X}{:02X}".format(*(round(v * 255) for v in lifted))
        if contrast_ratio(cand, bg) >= 4.5:
            return cand
    return "#DCE6F2"


def apply_palette(theme: Theme, palette: str | ExplainPalette | None) -> tuple[Theme, str | None]:
    """Overlay ``palette`` onto ``theme``; returns ``(resolved_theme, canonical_palette_name)``."""
    if palette is None:
        return theme, None
    pal = get_explain_palette(palette)
    if pal.name == "default":
        return theme, None
    is_dark = relative_luminance(theme.background) < 0.2
    if is_dark:
        series = tuple(_lift_for_dark_ground(c, theme.background) for c in pal.series_colors)
        accents = tuple(_lift_for_dark_ground(c, theme.background) for c in pal.accent_colors)
        return (
            replace(
                theme,
                series_colors=series,
                accent_colors=accents,
            ),
            pal.name,
        )
    return (
        replace(
            theme,
            series_colors=pal.series_colors,
            accent_colors=pal.accent_colors,
            seq_stops=pal.seq_stops,
            div_low=pal.div_low,
            div_high=pal.div_high,
            div_mid=pal.div_mid,
        ),
        pal.name,
    )


def apply_accent(theme: Theme, accent: str | None) -> tuple[Theme, str | None]:
    """Override the primary highlight colour on ``theme`` with a custom accent hex/color."""
    if accent is None:
        return theme, None
    if not isinstance(accent, str) or not accent.strip():
        raise ValueError(f"accent must be a color string like '#2563EB', got {accent!r}.")
    raw = accent.strip()
    try:
        rgb = to_rgb(raw)
    except ValueError as exc:
        raise ValueError(f"Unknown accent color {accent!r}. Pass a hex color like '#D97757'.") from exc
    orig_hex = "#{:02X}{:02X}{:02X}".format(*(round(c * 255) for c in rgb))
    hex_col = orig_hex
    is_dark = relative_luminance(theme.background) < 0.2
    if is_dark:
        hex_col = _lift_for_dark_ground(hex_col, theme.background)
    elif contrast_ratio(hex_col, theme.background) < 3.0:
        # Gently deepen overly pale accents on light grounds so bars/markers stay readable.
        for factor in (0.82, 0.68, 0.54, 0.40):
            cand = "#{:02X}{:02X}{:02X}".format(*(round(c * factor * 255) for c in rgb))
            if contrast_ratio(cand, theme.background) >= 3.0:
                hex_col = cand
                break
    series = list(theme.series_colors)
    if theme.accent_colors and theme.accent_colors[0] in series:
        series[series.index(theme.accent_colors[0])] = hex_col
    elif len(series) >= 2:
        series[1] = hex_col
    else:
        series[0] = hex_col
    accents = (hex_col, *theme.accent_colors[1:])
    return replace(theme, series_colors=tuple(series), accent_colors=accents), orig_hex


def get_theme(theme: str | Theme = "mintfig") -> Theme:
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


def _normalize_registry_key(name: str) -> str:
    key = name.strip().lower().replace("-", "_").replace(" ", "_")
    if not key:
        raise ValueError("Theme/palette name must be a non-empty string.")
    return key


def register_theme(
    theme: Theme,
    *,
    aliases: Sequence[str] = (),
    overwrite: bool = False,
) -> Theme:
    """Register a custom :class:`Theme` (and optional aliases) for ``style=`` lookup."""
    if not isinstance(theme, Theme):
        raise TypeError(f"theme must be a Theme instance, got {type(theme).__name__}.")
    key = _normalize_registry_key(theme.name)
    if key in THEMES and not overwrite:
        raise ValueError(f"Theme {key!r} is already registered; pass overwrite=True to replace.")
    THEMES[key] = theme
    for alias in aliases:
        alias_key = _normalize_registry_key(alias)
        if alias_key in THEME_ALIASES and not overwrite:
            raise ValueError(
                f"Theme alias {alias_key!r} is already registered; pass overwrite=True to replace."
            )
        THEME_ALIASES[alias_key] = key
    return theme


def register_palette(palette: ExplainPalette, *, overwrite: bool = False) -> ExplainPalette:
    """Register a custom :class:`ExplainPalette` for ``palette=`` lookup."""
    if not isinstance(palette, ExplainPalette):
        raise TypeError(
            f"palette must be an ExplainPalette instance, got {type(palette).__name__}."
        )
    key = _normalize_registry_key(palette.name)
    if key in EXPLAIN_PALETTES and not overwrite:
        raise ValueError(f"Palette {key!r} is already registered; pass overwrite=True to replace.")
    EXPLAIN_PALETTES[key] = palette
    return palette


def _read_pyproject_mintfig(cwd: Path | None = None) -> dict[str, Any]:
    """Read ``[tool.mintfig]`` from the nearest ``pyproject.toml`` walking up from ``cwd``."""
    start = (cwd if cwd is not None else Path.cwd()).resolve()
    if start.is_file():
        start = start.parent
    for directory in (start, *start.parents):
        candidate = directory / "pyproject.toml"
        if not candidate.is_file():
            continue
        if tomllib is None:  # pragma: no cover - Python 3.10 without tomllib
            return {}
        try:
            data = tomllib.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        tool = data.get("tool")
        if isinstance(tool, dict):
            mintfig_cfg = tool.get("mintfig")
            if isinstance(mintfig_cfg, dict):
                return mintfig_cfg
        return {}
    return {}


def resolve_default_style(cwd: Path | None = None) -> str:
    """Resolve the default style: ``MINTFIG_STYLE`` -> nearest ``pyproject.toml`` -> ``'mintfig'``."""
    env_val = os.environ.get("MINTFIG_STYLE", "").strip()
    if env_val:
        return env_val
    cfg = _read_pyproject_mintfig(cwd=cwd)
    raw = cfg.get("style")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return "mintfig"


def resolve_default_palette(cwd: Path | None = None) -> str | None:
    """Resolve the default palette: ``MINTFIG_PALETTE`` -> nearest ``pyproject.toml`` -> ``None``."""
    env_val = os.environ.get("MINTFIG_PALETTE", "").strip()
    if env_val:
        return env_val
    cfg = _read_pyproject_mintfig(cwd=cwd)
    raw = cfg.get("palette")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return None


def render_themes_swatch_card(out_path: str | Path) -> Path:
    """Render a crisp visual swatch card of all registered styles and explain palettes."""
    import math

    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure
    from matplotlib.patches import FancyBboxPatch

    target = Path(out_path)
    target.parent.mkdir(parents=True, exist_ok=True)

    aliases_by_theme: dict[str, list[str]] = {}
    for alias, canonical in THEME_ALIASES.items():
        aliases_by_theme.setdefault(canonical, []).append(alias)

    themes_list = list(THEMES.items())
    palettes_list = list(EXPLAIN_PALETTES.items())

    theme_cols = 5
    theme_rows = max(1, math.ceil(len(themes_list) / theme_cols))
    pal_cols = 2
    pal_rows = max(1, math.ceil(len(palettes_list) / pal_cols))

    fig_h = 1.65 + theme_rows * 1.18 + pal_rows * 0.54 + 0.55
    fig_w = 9.4

    with mpl.rc_context(
        {
            "font.family": "sans-serif",
            "font.sans-serif": style._ordered_font_stack(style.EDITORIAL_SANS_FONTS, require_bold=True),
            "figure.facecolor": "#FFFFFF",
            "savefig.facecolor": "#FFFFFF",
        }
    ):
        fig = Figure(figsize=(fig_w, fig_h), dpi=220)
        FigureCanvasAgg(fig)
        ax = fig.add_axes([0.0, 0.0, 1.0, 1.0])
        ax.set_xlim(0.0, fig_w)
        ax.set_ylim(0.0, fig_h)
        ax.axis("off")

        ink = "#13221D"
        muted = "#4D5F58"
        accent = "#0F8B6D"

        # Top emerald header rule
        ax.plot([0.32, fig_w - 0.32], [fig_h - 0.22, fig_h - 0.22], color=accent, linewidth=2.2)

        ax.text(
            0.32,
            fig_h - 0.38,
            "mintfig Surface Themes & Color Palettes",
            fontsize=14.0,
            fontweight="bold",
            color=ink,
            va="top",
        )
        ax.text(
            0.32,
            fig_h - 0.72,
            f"{len(themes_list)} surface themes (style=...) and {len(palettes_list)} CVD/grayscale/WCAG-verified explain palettes (palette=...).",
            fontsize=8.6,
            color=muted,
            va="top",
        )

        # Section 1: Surface themes
        y_themes_hdr = fig_h - 1.12
        ax.text(
            0.32,
            y_themes_hdr,
            "Surface themes (style=...)",
            fontsize=10.0,
            fontweight="bold",
            color=ink,
            va="top",
        )

        card_gap_x = 0.14
        card_gap_y = 0.16
        margin_x = 0.32
        usable_w = fig_w - 2 * margin_x
        card_w = (usable_w - (theme_cols - 1) * card_gap_x) / theme_cols
        card_h = 0.96
        y_cards_top = y_themes_hdr - 0.30

        for idx, (name, theme) in enumerate(themes_list):
            row = idx // theme_cols
            col = idx % theme_cols
            x0 = margin_x + col * (card_w + card_gap_x)
            y0 = y_cards_top - (row + 1) * card_h - row * card_gap_y
            is_dark = relative_luminance(theme.background) < 0.2
            edge = "#32433D" if is_dark else "#D3DDD8"

            card = FancyBboxPatch(
                (x0, y0),
                card_w,
                card_h,
                boxstyle="round,pad=0.0,rounding_size=0.08",
                facecolor=theme.background,
                edgecolor=edge,
                linewidth=0.9,
            )
            ax.add_patch(card)

            # Optional theme top accent stripe + Economist/FT top flag inside card
            if theme.top_rule and theme.top_rule_color:
                ax.plot(
                    [x0 + 0.08, x0 + card_w - 0.08],
                    [y0 + card_h - 0.08, y0 + card_h - 0.08],
                    color=theme.top_rule_color,
                    linewidth=1.0 if theme.top_flag else 1.6,
                )
            if theme.top_flag:
                flag_col = theme.top_flag_color or theme.top_rule_color or theme.ink
                ax.plot(
                    [x0 + 0.08, x0 + 0.08 + min(0.32, card_w * 0.28)],
                    [y0 + card_h - 0.065, y0 + card_h - 0.065],
                    color=flag_col,
                    linewidth=2.6,
                    solid_capstyle="butt",
                )

            alias_list = aliases_by_theme.get(name, [])
            label_title = name if not alias_list else f"{name} ({alias_list[0]})"
            title_font = "serif" if theme.allow_serif_title else "sans-serif"
            ax.text(
                x0 + 0.10,
                y0 + card_h - 0.21,
                label_title,
                fontsize=8.3,
                fontweight="bold",
                fontfamily=title_font,
                color=theme.ink,
                va="top",
            )
            ax.text(
                x0 + 0.10,
                y0 + card_h - 0.43,
                f"bg {theme.background}",
                fontsize=6.8,
                color=theme.muted,
                va="top",
            )

            # 4 series swatches across the bottom of the card
            sw_gap = 0.06
            sw_pad = 0.10
            sw_w = (card_w - 2 * sw_pad - 3 * sw_gap) / 4.0
            sw_h = 0.24
            for s_idx, hex_col in enumerate(theme.series_colors[:4]):
                sx = x0 + sw_pad + s_idx * (sw_w + sw_gap)
                swatch = FancyBboxPatch(
                    (sx, y0 + 0.10),
                    sw_w,
                    sw_h,
                    boxstyle="round,pad=0.0,rounding_size=0.04",
                    facecolor=hex_col,
                    edgecolor="none",
                )
                ax.add_patch(swatch)

        # Divider
        y_div = y_cards_top - theme_rows * card_h - (theme_rows - 1) * card_gap_y - 0.24
        ax.plot([margin_x, fig_w - margin_x], [y_div, y_div], color="#DFEBE6", linewidth=0.9)

        # Section 2: Explain palettes (2 columns)
        y_pal_hdr = y_div - 0.16
        ax.text(
            margin_x,
            y_pal_hdr,
            "Explain palettes (palette=..., 4 series slots + sequential ramp)",
            fontsize=10.0,
            fontweight="bold",
            color=ink,
            va="top",
        )

        col_gap = 0.36
        col_w = (usable_w - col_gap) / pal_cols
        row_step = 0.50
        y_pal_start = y_pal_hdr - 0.42
        split = math.ceil(len(palettes_list) / pal_cols)

        for idx, (name, pal) in enumerate(palettes_list):
            col = 0 if idx < split else 1
            row = idx if idx < split else idx - split
            x0 = margin_x + col * (col_w + col_gap)
            yc = y_pal_start - row * row_step

            ax.text(
                x0,
                yc + 0.04,
                name,
                fontsize=8.4,
                fontweight="bold",
                color=ink,
                va="center",
            )

            # 4 series color pills + hex labels
            sx0 = x0 + 0.96
            sw_w = 0.52
            sw_gap = 0.07
            for s_idx, hex_col in enumerate(pal.series_colors[:4]):
                sx = sx0 + s_idx * (sw_w + sw_gap)
                pill = FancyBboxPatch(
                    (sx, yc - 0.06),
                    sw_w,
                    0.22,
                    boxstyle="round,pad=0.0,rounding_size=0.04",
                    facecolor=hex_col,
                    edgecolor="#FFFFFF",
                    linewidth=0.5,
                )
                ax.add_patch(pill)
                ax.text(
                    sx + sw_w / 2.0,
                    yc - 0.13,
                    hex_col.upper(),
                    fontsize=5.6,
                    color=muted,
                    ha="center",
                    va="top",
                )

            # Sequential ramp on the right side of the column
            rx0 = sx0 + 4 * (sw_w + sw_gap) + 0.08
            ramp_total = max(0.72, (x0 + col_w) - rx0)
            n_stops = max(1, len(pal.seq_stops))
            seg_w = ramp_total / n_stops
            for r_idx, hex_col in enumerate(pal.seq_stops):
                seg = FancyBboxPatch(
                    (rx0 + r_idx * seg_w, yc - 0.04),
                    seg_w,
                    0.18,
                    boxstyle="square,pad=0.0",
                    facecolor=hex_col,
                    edgecolor="none",
                )
                ax.add_patch(seg)

        # Footer note
        ax.text(
            margin_x,
            0.18,
            "Configure project defaults via MINTFIG_STYLE / MINTFIG_PALETTE or [tool.mintfig] in pyproject.toml.",
            fontsize=7.3,
            color=muted,
            va="bottom",
        )

        fig.savefig(target, dpi=220, facecolor="#FFFFFF")

    return target
