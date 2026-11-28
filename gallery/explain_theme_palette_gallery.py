"""Theme (``style=``) and color palette (``palette=``) gallery generator (all data synthetic).

Generates:
- ``gallery/output/explain_themes/style_<name>.png`` for all built-in styles
  (``mintfig``, ``mint``, ``pine``, ``botanical``, ``bold``, ``editorial``,
  ``paper``, ``dark``, ``mono``, ``sketch``).
- ``gallery/output/explain_themes/palette_<name>.png`` for all ``mint.explain`` palettes
  (``default``, ``okabe_ito``, ``tol``, ``earth``, ``ocean``, ``berry``, ``mint``,
  ``spearmint``, ``matcha``, ``glacier``, ``mineral``), using a 4-series figure so
  every colour slot is visible side by side.
- ``gallery/output/explain_themes/palettes_overview.png`` — a clean visual swatch sheet of
  all explain palettes, publication palettes, surface themes, and editorial colormaps.
"""

from __future__ import annotations

import math
from pathlib import Path

import matplotlib as mpl
import numpy as np
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.patches import FancyBboxPatch

import mintfig as mint
from mintfig.palettes import EDITORIAL_COLORMAPS, PALETTES
from mintfig.themes import EXPLAIN_PALETTES, THEMES, relative_luminance

OUT_DIR = Path(__file__).resolve().parent / "output" / "explain_themes"
SOURCE = "synthetic example data"


def _theme_demo(style_name: str) -> mint.Explanation:
    """Two-panel comparison + trend showcasing a visual surface theme."""
    return mint.explain(
        "Retriever B lifts accuracy by 9 points while keeping latency steady across loads",
        mint.compare(
            {"Retriever B": 86, "Retriever A": 77, "Hybrid": 81, "BM25": 68},
            error={
                "Retriever B": (84, 88),
                "Retriever A": (75, 79),
                "Hybrid": (79, 83),
                "BM25": (66, 70),
            },
            error_label="95% CI",
            baseline="BM25",
            highlight=["Retriever B", "Hybrid"],
            label="Top-5 recall",
            unit="%",
            title="Retriever B leads outside noise",
        ),
        mint.trend(
            [10, 25, 50, 100, 200],
            {
                "Retriever B": [42, 46, 51, 58, 66],
                "Hybrid": [48, 56, 68, 86, 112],
                "BM25": [28, 30, 33, 37, 42],
            },
            baseline="BM25",
            highlight=["Retriever B", "Hybrid"],
            label="p95 latency",
            unit="ms",
            x_label="Queries per second",
            title="Hybrid slows sharply past 100 QPS",
        ),
        style=style_name,
        source=SOURCE,
    )


def _palette_demo(palette_name: str) -> mint.Explanation:
    """Four-series figure displaying all four CVD-verified slots of an explain palette."""
    steps = [0, 500, 1000, 1500, 2000]
    curves = {
        "Alpha": [12, 58, 76, 84, 88],
        "Beta": [10, 49, 67, 74, 78],
        "Gamma": [11, 41, 56, 63, 68],
        "Delta": [9, 32, 44, 51, 55],
    }
    finals = {k: v[-1] for k, v in curves.items()}
    return mint.explain(
        f"Palette '{palette_name}': four distinct hues stay separated in colour, CVD and print",
        mint.compare(
            finals,
            highlight=["Alpha", "Beta", "Gamma"],
            label="Final score",
            unit="%",
            title="Three accents plus muted context",
        ),
        mint.trend(
            steps,
            curves,
            label="Validation score",
            unit="%",
            x_label="Step",
            title="All four series slots over training",
        ),
        palette=palette_name,
        source=SOURCE,
    )


def _render_palette_overview(out_path: Path) -> None:
    """Render a crisp visual reference card for all built-in palettes, themes, and colormaps."""
    with mpl.rc_context(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["Helvetica Neue", "Helvetica", "Arial", "DejaVu Sans"],
            "figure.facecolor": "#FFFFFF",
            "savefig.facecolor": "#FFFFFF",
        }
    ):
        fig = Figure(figsize=(9.2, 9.4), dpi=220)
        FigureCanvasAgg(fig)
        ax = fig.add_axes([0.0, 0.0, 1.0, 1.0])
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.axis("off")

        ink = "#13221D"
        muted = "#4D5F58"

        ax.plot([0.03, 0.97], [0.980, 0.980], color="#007A66", linewidth=2.0)
        ax.text(
            0.03,
            0.966,
            "mintfig Color Palettes, Surface Themes & Editorial Colormaps",
            fontsize=13.5,
            fontweight="bold",
            color=ink,
            va="top",
        )
        ax.text(
            0.03,
            0.936,
            "Every mint.explain palette and theme is verified for deuteranopia, protanopia, grayscale separation, and WCAG 4.5:1 text contrast.",
            fontsize=8.3,
            color=muted,
            va="top",
        )

        # Left column: mint.explain palettes (palette=...)
        ax.text(0.03, 0.900, "mint.explain palettes (palette=...)", fontsize=9.5, fontweight="bold", color=ink)
        pal_items = list(EXPLAIN_PALETTES.items())
        pal_step = min(0.036, 0.39 / max(1, len(pal_items)))
        y = 0.868
        for name, pal in pal_items:
            ax.text(0.03, y, name, fontsize=8.0, fontweight="bold", color=ink, va="center")
            x0 = 0.160
            for idx, hex_col in enumerate(pal.series_colors):
                rect = FancyBboxPatch(
                    (x0 + idx * 0.064, y - 0.012),
                    0.055,
                    0.024,
                    boxstyle="round,pad=0.001,rounding_size=0.004",
                    facecolor=hex_col,
                    edgecolor="#FFFFFF",
                    linewidth=0.5,
                )
                ax.add_patch(rect)
            # Sequential mini-ramp for matrix()
            rx0 = 0.425
            ramp_w = 0.095
            n_stops = max(1, len(pal.seq_stops))
            seg_w = ramp_w / n_stops
            for idx, hex_col in enumerate(pal.seq_stops):
                rect = FancyBboxPatch(
                    (rx0 + idx * seg_w, y - 0.010),
                    seg_w,
                    0.020,
                    boxstyle="square,pad=0",
                    facecolor=hex_col,
                    edgecolor="none",
                )
                ax.add_patch(rect)
            y -= pal_step

        # Right column: publication PALETTES
        ax.text(0.555, 0.900, "Publication palettes (mint.pub.get_palette)", fontsize=9.5, fontweight="bold", color=ink)
        y = 0.868
        for name, cols in PALETTES.items():
            ax.text(0.555, y, name, fontsize=8.2, fontweight="bold", color=ink, va="center")
            x0 = 0.705
            sw = 0.029
            for idx, hex_col in enumerate(cols[:8]):
                rect = FancyBboxPatch(
                    (x0 + idx * (sw + 0.004), y - 0.013),
                    sw,
                    0.026,
                    boxstyle="round,pad=0.001,rounding_size=0.004",
                    facecolor=hex_col,
                    edgecolor="#FFFFFF",
                    linewidth=0.5,
                )
                ax.add_patch(rect)
            y -= 0.052

        # Middle band: Built-in surface themes (style=...) in 3 rows x 5 columns
        ax.plot([0.03, 0.97], [0.472, 0.472], color="#DFEBE6", linewidth=0.8)
        ax.text(
            0.03,
            0.448,
            "Surface themes (style=...) — curated flagship editions first",
            fontsize=9.5,
            fontweight="bold",
            color=ink,
        )
        theme_items = list(THEMES.items())
        ncols = 5
        nrows = max(1, math.ceil(len(theme_items) / ncols))
        gap_x = 0.014
        tw = (0.94 - (ncols - 1) * gap_x) / ncols
        th = 0.082
        gap_y = 0.015
        top_y = 0.432
        for idx, (name, theme) in enumerate(theme_items):
            r = idx // ncols
            c = idx % ncols
            tx = 0.03 + c * (tw + gap_x)
            ty = top_y - (r + 1) * th - r * gap_y
            is_dark = relative_luminance(theme.background) < 0.2
            card = FancyBboxPatch(
                (tx, ty),
                tw,
                th,
                boxstyle="round,pad=0.002,rounding_size=0.007",
                facecolor=theme.background,
                edgecolor="#32433D" if is_dark else "#CBD7D2",
                linewidth=0.8,
            )
            ax.add_patch(card)
            if theme.top_rule and theme.top_rule_color:
                ax.plot(
                    [tx + 0.008, tx + tw - 0.008],
                    [ty + th - 0.007, ty + th - 0.007],
                    color=theme.top_rule_color,
                    linewidth=1.0 if theme.top_flag else 1.4,
                )
            if theme.top_flag:
                flag_col = theme.top_flag_color or theme.top_rule_color or theme.ink
                ax.plot(
                    [tx + 0.008, tx + 0.008 + min(0.044, tw * 0.26)],
                    [ty + th - 0.006, ty + th - 0.006],
                    color=flag_col,
                    linewidth=2.4,
                    solid_capstyle="butt",
                )
            ax.text(
                tx + 0.010,
                ty + th - 0.024,
                name,
                fontsize=8.1,
                fontweight="bold",
                fontfamily="serif" if theme.allow_serif_title else "sans-serif",
                color=theme.ink,
                va="center",
            )
            sw_gap = 0.007
            sw_w = (tw - 0.020 - 3 * sw_gap) / 4.0
            for s_idx, hex_col in enumerate(theme.series_colors[:4]):
                dot = FancyBboxPatch(
                    (tx + 0.010 + s_idx * (sw_w + sw_gap), ty + 0.011),
                    sw_w,
                    0.023,
                    boxstyle="round,pad=0.001,rounding_size=0.003",
                    facecolor=hex_col,
                    edgecolor="none",
                )
                ax.add_patch(dot)

        # Bottom band: Editorial colormaps
        cmap_hdr_y = top_y - nrows * th - (nrows - 1) * gap_y - 0.032
        ax.text(0.03, cmap_hdr_y, "Editorial colormaps (Matplotlib registered)", fontsize=9.5, fontweight="bold", color=ink)
        grad = np.linspace(0, 1, 256)[np.newaxis, :]
        cx = 0.03
        cw = 0.215
        for name in EDITORIAL_COLORMAPS:
            cax = fig.add_axes([cx, 0.028, cw, 0.040])
            cax.imshow(grad, aspect="auto", cmap=mpl.colormaps[name])
            cax.set_xticks([])
            cax.set_yticks([])
            for sp in cax.spines.values():
                sp.set_edgecolor("#CBD3DF")
                sp.set_linewidth(0.6)
            ax.text(cx, 0.074, name, fontsize=8.0, fontweight="bold", color=muted, va="bottom")
            cx += cw + 0.026

        fig.savefig(out_path, dpi=220, facecolor="#FFFFFF")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for style_name in THEMES:
        s = _theme_demo(style_name).save(OUT_DIR / f"style_{style_name}.png", write_spec=True)
        print(f"style_{style_name}: ok={s['ok']} issues={s['issues']}")
    for pal_name in EXPLAIN_PALETTES:
        s = _palette_demo(pal_name).save(OUT_DIR / f"palette_{pal_name}.png", write_spec=True)
        print(f"palette_{pal_name}: ok={s['ok']} issues={s['issues']}")
    _render_palette_overview(OUT_DIR / "palettes_overview.png")
    print("palettes_overview.png written")


if __name__ == "__main__":
    main()
