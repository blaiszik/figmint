"""Visual surface themes and color palettes for ``mint.explain``.

Built-in themes: ``mintfig`` (default), ``bold``, ``editorial``, ``paper``,
``dark``, ``mono``, ``sketch``. Built-in explain palettes: ``default``,
``okabe_ito``, ``tol``, ``earth``, ``ocean``, ``berry``.

A theme or palette changes only the visual surface — typography, colour palette,
background, gridlines, axis framing, header/footer rules, and optional hand-drawn
sketch jitter. It never changes the information-design rules enforced by
``mint.explain`` (takeaway titles, sorted zero-based bars, <= 4 coloured series,
<= 3 highlights, direct labels, chat legibility, or CVD/grayscale separation).
"""

from __future__ import annotations

import importlib
from contextlib import AbstractContextManager
from dataclasses import dataclass, field, replace
from typing import Any

import matplotlib as mpl
from matplotlib.colors import to_rgb

from .specs import JournalSpec

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
        if self.name == "mintfig" and not self.extra_rc:
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
    title_family=("Georgia", "Charter", "DejaVu Serif", "serif"),
    body_family=("Helvetica Neue", "Helvetica", "Arial", "Liberation Sans", "DejaVu Sans"),
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
    body_family=("Helvetica Neue", "Helvetica", "Arial", "Liberation Sans", "DejaVu Sans"),
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
    body_family=("Helvetica Neue", "Helvetica", "Arial", "Liberation Sans", "DejaVu Sans"),
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

THEMES: dict[str, Theme] = {
    "mintfig": MINTFIG_THEME,
    "bold": BOLD_THEME,
    "editorial": EDITORIAL_THEME,
    "paper": PAPER_THEME,
    "dark": DARK_THEME,
    "mono": MONO_THEME,
    "sketch": SKETCH_THEME,
}

THEME_ALIASES: dict[str, str] = {
    "default": "mintfig",
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
