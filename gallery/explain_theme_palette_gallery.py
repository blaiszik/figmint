"""Theme (``style=``) and color palette (``palette=``) gallery generator (all data synthetic).

Generates:
- ``gallery/output/explain_themes/style_<name>.png`` for all 7 built-in styles
  (``mintfig``, ``editorial``, ``paper``, ``bold``, ``dark``, ``mono``, ``sketch``).
- ``gallery/output/explain_themes/palette_<name>.png`` for all 6 ``mint.explain`` palettes
  (``default``, ``okabe_ito``, ``tol``, ``earth``, ``ocean``, ``berry``), using a 4-series
  figure so every colour slot is visible side by side.
- ``gallery/output/explain_themes/palettes_overview.png`` — a clean visual swatch sheet of
  all explain palettes, publication palettes, and editorial colormaps.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib as mpl
import numpy as np
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.patches import FancyBboxPatch

import mintfig as mint
from mintfig.palettes import EDITORIAL_COLORMAPS, PALETTES
from mintfig.themes import EXPLAIN_PALETTES, THEMES

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
    """Render a crisp visual reference card for all built-in palettes and colormaps."""
    with mpl.rc_context(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["Helvetica Neue", "Helvetica", "Arial", "DejaVu Sans"],
            "figure.facecolor": "#FFFFFF",
            "savefig.facecolor": "#FFFFFF",
        }
    ):
        fig = Figure(figsize=(8.6, 5.8), dpi=220)
        FigureCanvasAgg(fig)
        ax = fig.add_axes([0.0, 0.0, 1.0, 1.0])
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.axis("off")

        ink = "#1A1D21"
        muted = "#5B6570"

        ax.text(
            0.03,
            0.955,
            "mintfig Color Palettes & Editorial Colormaps",
            fontsize=13.5,
            fontweight="bold",
            color=ink,
            va="top",
        )
        ax.text(
            0.03,
            0.912,
            "Every mint.explain palette is verified for deuteranopia, protanopia, grayscale separation, and WCAG 4.5:1 text contrast.",
            fontsize=8.5,
            color=muted,
            va="top",
        )

        # Left column: mint.explain palettes (palette=...)
        ax.text(0.03, 0.855, "mint.explain palettes (palette=...)", fontsize=9.5, fontweight="bold", color=ink)
        y = 0.805
        for name, pal in EXPLAIN_PALETTES.items():
            ax.text(0.03, y, name, fontsize=8.5, fontweight="bold", color=ink, va="center")
            x0 = 0.165
            for idx, hex_col in enumerate(pal.series_colors):
                rect = FancyBboxPatch(
                    (x0 + idx * 0.068, y - 0.022),
                    0.058,
                    0.044,
                    boxstyle="round,pad=0.002,rounding_size=0.006",
                    facecolor=hex_col,
                    edgecolor="#FFFFFF",
                    linewidth=0.6,
                )
                ax.add_patch(rect)
            # Sequential mini-ramp for matrix()
            rx0 = 0.445
            rw = 0.034
            for idx, hex_col in enumerate(pal.seq_stops):
                rect = FancyBboxPatch(
                    (rx0 + idx * (rw / 6.0) * 6.0 * 0.25, y - 0.018),
                    rw * 0.24,
                    0.036,
                    boxstyle="square,pad=0",
                    facecolor=hex_col,
                    edgecolor="none",
                )
                ax.add_patch(rect)
            y -= 0.072

        # Right column: publication PALETTES
        ax.text(0.55, 0.855, "Publication palettes (mint.pub.get_palette)", fontsize=9.5, fontweight="bold", color=ink)
        y = 0.805
        for name, cols in PALETTES.items():
            ax.text(0.55, y, name, fontsize=8.5, fontweight="bold", color=ink, va="center")
            x0 = 0.705
            sw = 0.030
            for idx, hex_col in enumerate(cols[:8]):
                rect = FancyBboxPatch(
                    (x0 + idx * (sw + 0.004), y - 0.020),
                    sw,
                    0.040,
                    boxstyle="round,pad=0.001,rounding_size=0.005",
                    facecolor=hex_col,
                    edgecolor="#FFFFFF",
                    linewidth=0.5,
                )
                ax.add_patch(rect)
            y -= 0.072

        # Bottom band: Built-in surface themes (style=...) + editorial colormaps
        ax.plot([0.03, 0.97], [0.355, 0.355], color="#E3E7EC", linewidth=0.8)
        ax.text(0.03, 0.325, "Surface themes (style=...)", fontsize=9.5, fontweight="bold", color=ink)
        tx = 0.03
        tw = 0.125
        for name, theme in THEMES.items():
            card = FancyBboxPatch(
                (tx, 0.195),
                tw,
                0.105,
                boxstyle="round,pad=0.003,rounding_size=0.008",
                facecolor=theme.background,
                edgecolor="#CBD3DF" if theme.name != "dark" else "#3A4354",
                linewidth=0.8,
            )
            ax.add_patch(card)
            ax.text(
                tx + 0.01,
                0.278,
                name,
                fontsize=8.2,
                fontweight="bold",
                color=theme.ink,
                va="center",
            )
            for idx, hex_col in enumerate(theme.series_colors):
                dot = FancyBboxPatch(
                    (tx + 0.01 + idx * 0.026, 0.215),
                    0.021,
                    0.034,
                    boxstyle="round,pad=0.001,rounding_size=0.004",
                    facecolor=hex_col,
                    edgecolor="none",
                )
                ax.add_patch(dot)
            tx += tw + 0.011

        ax.text(0.03, 0.155, "Editorial colormaps (Matplotlib registered)", fontsize=9.5, fontweight="bold", color=ink)
        grad = np.linspace(0, 1, 256)[np.newaxis, :]
        cx = 0.03
        cw = 0.215
        for name in EDITORIAL_COLORMAPS:
            cax = fig.add_axes([cx, 0.045, cw, 0.055])
            cax.imshow(grad, aspect="auto", cmap=mpl.colormaps[name])
            cax.set_xticks([])
            cax.set_yticks([])
            for sp in cax.spines.values():
                sp.set_edgecolor("#CBD3DF")
                sp.set_linewidth(0.6)
            ax.text(cx, 0.112, name, fontsize=8.0, fontweight="bold", color=muted, va="bottom")
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
