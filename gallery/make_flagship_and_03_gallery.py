"""Generate the dual-surface Editorial + 2×4 Braille comparison and 0.3 gallery figures.

Outputs:
- ``gallery/output/readme_comparison/flagship_editorial.png``
- ``gallery/output/readme_comparison/flagship_braille.png``
- ``gallery/output/readme_comparison/flagship_editorial_braille.png``
- ``gallery/output/explain_forms/table_graphics_scorecard.png``
- ``gallery/output/explain_forms/words_on_marks_compact.png``
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from PIL import Image, ImageDraw, ImageFont

GALLERY_DIR = Path(__file__).resolve().parent
if str(GALLERY_DIR) not in sys.path:
    sys.path.insert(0, str(GALLERY_DIR))

from braille_terminal_gallery import render_ansi_to_png

import mintfig as mint

README_OUT = GALLERY_DIR / "output" / "readme_comparison"
FORMS_OUT = GALLERY_DIR / "output" / "explain_forms"


def _load_sans_font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = (
        [
            "/System/Library/Fonts/HelveticaNeue.ttc",
            "/System/Library/Fonts/SFNS.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ]
        if bold
        else [
            "/System/Library/Fonts/HelveticaNeue.ttc",
            "/System/Library/Fonts/SFNS.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ]
    )
    for path in candidates:
        p = Path(path)
        if not p.exists():
            continue
        try:
            idx = 1 if (bold and p.suffix == ".ttc") else 0
            return ImageFont.truetype(str(p), size=size, index=idx)
        except OSError:
            continue
    return ImageFont.load_default()


def _build_flagship_data() -> dict[str, object]:
    """Shared synthetic serving telemetry used on both editorial and Braille surfaces."""
    qps = [10, 25, 50, 75, 100, 125, 150, 175, 200]
    return {
        "qps": qps,
        "series": {
            "Hybrid": [43, 52, 65, 76, 86, 95, 104, 111, 118],
            "Retriever B": [37, 41, 46, 51, 55, 58, 61, 64, 66],
            "BM25": [23, 25, 28, 31, 33, 36, 38, 40, 42],
        },
    }


def _make_flagship_explanation(*, style: str) -> mint.Explanation:
    d = _build_flagship_data()
    return mint.explain(
        "Retriever B holds p99 latency under 70\u00a0ms as Hybrid climbs past the 80\u00a0ms SLO",
        mint.trend(
            d["qps"],
            d["series"],
            baseline="BM25",
            highlight=["Retriever B", "Hybrid"],
            reference=(80, "80 ms SLO"),
            events={100: "100 QPS burst"},
            label="p99 latency",
            unit="ms",
            x_label="Queries per second",
            title="p99 query latency under rising load",
        ),
        kicker="SERVING TELEMETRY",
        subtitle="Production search cluster · median of 5 load runs",
        source="runs/search_load_2026-11",
        style=style,
    )


def build_flagship_editorial_and_braille() -> None:
    README_OUT.mkdir(parents=True, exist_ok=True)

    # 1. Editorial figure (masthead accent bar, kicker, serif headline, inline y-ticks)
    editorial_exp = _make_flagship_explanation(style="editorial")
    ed_path = README_OUT / "flagship_editorial.png"
    ed_summary = editorial_exp.save(ed_path)
    assert ed_summary["ship"] is True, f"flagship editorial did not ship: {ed_summary['issues']}"

    # 2. Matching 2×4 Braille + 24-bit ANSI terminal figure from the exact same call (style="dark")
    #    style="dark" shares editorial's terracotta + steel-blue + neutral-ink color mapping.
    dark_exp = _make_flagship_explanation(style="dark")
    ansi = dark_exp.to_text(mode="braille", color=True, width=72)
    br_path = README_OUT / "flagship_braille.png"
    render_ansi_to_png(
        ansi,
        br_path,
        title="mintfig plot load_test.csv --braille --style dark",
        badge="24-bit ANSI · 2×4 Braille",
        font_size=21,
        supersample=2,
    )

    plt.close(editorial_exp.fig)
    plt.close(dark_exp.fig)

    # 3. Compose stacked top/bottom comparison so both editorial typography and
    #    72-column 2×4 Braille stay full reading width on GitHub and PyPI (~890 px).
    ed_img = Image.open(ed_path).convert("RGBA")
    br_img = Image.open(br_path).convert("RGBA")

    target_w = 1320
    pad_x = 40
    pad_top = 34
    pad_bot = 36
    card_w = target_w - 2 * pad_x

    def _fit_width(im: Image.Image, w: int) -> Image.Image:
        h = round(im.height * (w / im.width))
        return im.resize((w, h), Image.Resampling.LANCZOS)

    ed_fit = _fit_width(ed_img, card_w)
    br_fit = _fit_width(br_img, card_w)

    # Subtle framing dimensions
    ed_pad = 14
    ed_card_h = ed_fit.height + 2 * ed_pad
    label_h = 34
    bridge_h = 54

    total_h = (
        pad_top
        + (label_h + 6)
        + ed_card_h
        + bridge_h
        + (label_h + 6)
        + br_fit.height
        + pad_bot
    )

    canvas = Image.new("RGBA", (target_w, total_h), (244, 247, 246, 255))
    draw = ImageDraw.Draw(canvas)

    # Subtle outer border
    draw.rounded_rectangle(
        (2, 2, target_w - 3, total_h - 3),
        radius=20,
        fill=(244, 247, 246, 255),
        outline=(212, 222, 218, 255),
        width=2,
    )

    tag_font = _load_sans_font(19, bold=True)
    sub_font = _load_sans_font(18, bold=False)

    def _draw_pill_row(y_pos: int, pill_txt: str, sub_txt: str, fill_rgb: tuple[int, int, int], text_rgb: tuple[int, int, int]) -> None:
        pill_h = 30
        pill_pad_x = 16
        pw = round(tag_font.getlength(pill_txt)) + 2 * pill_pad_x
        draw.rounded_rectangle(
            (pad_x, y_pos, pad_x + pw, y_pos + pill_h),
            radius=pill_h // 2,
            fill=(*fill_rgb, 255),
        )
        tb = tag_font.getbbox(pill_txt)
        ty = y_pos + (pill_h - (tb[3] - tb[1])) // 2 - tb[1]
        draw.text((pad_x + pill_pad_x, ty), pill_txt, font=tag_font, fill=(*text_rgb, 255))
        sb = sub_font.getbbox(sub_txt)
        sy = y_pos + (pill_h - (sb[3] - sb[1])) // 2 - sb[1]
        draw.text((pad_x + pw + 16, sy), sub_txt, font=sub_font, fill=(78, 92, 87, 255))

    # Top badge: Editorial / Print & Chat Surface
    y = pad_top
    _draw_pill_row(
        y,
        'EDITORIAL  ·  style="editorial"',
        "Masthead accent bar, kicker, balanced serif headline, inline y-ticks & SLO reference",
        (212, 77, 39),
        (255, 255, 255),
    )
    y += label_h + 6

    # White editorial card with subtle border
    draw.rounded_rectangle(
        (pad_x, y, pad_x + card_w, y + ed_card_h),
        radius=14,
        fill=(255, 255, 255, 255),
        outline=(214, 221, 218, 255),
        width=2,
    )
    canvas.alpha_composite(ed_fit, (pad_x, y + ed_pad))
    y += ed_card_h

    # Bridge divider showing same mint.explain() call -> two surfaces
    mid_y = y + bridge_h // 2
    draw.line((pad_x, mid_y, pad_x + card_w, mid_y), fill=(204, 216, 211, 255), width=2)
    pill_text = "Same mint.explain() call  ·  Editorial PNG / SVG / HTML  +  2×4 Braille Terminal"
    pill_h = 34
    pill_w = round(tag_font.getlength(pill_text)) + 40
    pill_x0 = (target_w - pill_w) // 2
    draw.rounded_rectangle(
        (pill_x0, mid_y - pill_h // 2, pill_x0 + pill_w, mid_y + pill_h // 2),
        radius=pill_h // 2,
        fill=(15, 23, 21, 255),
        outline=(42, 66, 58, 255),
        width=2,
    )
    pb = tag_font.getbbox(pill_text)
    py = mid_y - (pb[3] - pb[1]) // 2 - pb[1]
    draw.text((pill_x0 + 20, py), pill_text, font=tag_font, fill=(88, 214, 170, 255))
    y += bridge_h

    # Bottom badge: Terminal Braille Surface
    _draw_pill_row(
        y,
        "TERMINAL  ·  --braille --style dark",
        "Zero image viewer needed · 2×4 Unicode Braille dots + 24-bit ANSI over SSH",
        (15, 23, 21),
        (88, 214, 170),
    )
    y += label_h + 6

    canvas.alpha_composite(br_fit, (pad_x, y))

    combo_path = README_OUT / "flagship_editorial_braille.png"
    canvas.convert("RGB").save(combo_path, format="PNG", optimize=True)
    print(f"Wrote {ed_path.name}, {br_path.name}, {combo_path.name} ({canvas.size[0]}×{canvas.size[1]})")


def build_03_gallery_additions() -> None:
    FORMS_OUT.mkdir(parents=True, exist_ok=True)

    # 1. Table-graphics scorecard (bars= + interval= + spark=)
    rows = [
        {"Model": "full model", "Accuracy": 82.0, "lo": 80.5, "hi": 83.4, "Latency": 182},
        {"Model": "no retrieval", "Accuracy": 74.0, "lo": 72.1, "hi": 75.8, "Latency": 95},
        {"Model": "no fine-tuning", "Accuracy": 69.0, "lo": 67.0, "hi": 71.1, "Latency": 180},
        {"Model": "small encoder", "Accuracy": 78.2, "lo": 75.8, "hi": 80.6, "Latency": 114},
    ]
    scorecard = mint.table(
        rows,
        units={"Accuracy": "%", "Latency": "ms"},
        baseline="full model",
        highlight="no retrieval",
        interval={"Accuracy": ("lo", "hi")},
        interval_label="95% CI, 5 seeds",
        bars="Latency",
        spark={
            "Training": {
                "full model": [2, 61, 78, 82],
                "no retrieval": [2, 48, 68, 74],
                "no fine-tuning": [1, 40, 60, 69],
                "small encoder": [2, 54, 73, 78],
            }
        },
        title="Accuracy (with 95% CI whisker), latency bar, and training sparkline per variant",
    )
    t_fig = mint.explain(
        "Dropping retrieval halves latency (95\u00a0ms) while costing 8 points of accuracy",
        scorecard,
        kicker="TABLE GRAPHICS",
        source="runs/ablation_2026-11 · 5 seeds per variant",
        style="mint",
    )
    t_path = FORMS_OUT / "table_graphics_scorecard.png"
    t_summary = t_fig.save(t_path)
    assert t_summary["ship"] is True, f"table_graphics did not ship: {t_summary['issues']}"
    plt.close(t_fig.fig)
    print(f"Wrote {t_path.name} (ship={t_summary['ship']})")

    # 2. Words on marks + auto delta bracket + compact density + editorial kicker
    w_fig = mint.explain(
        "Beta scores 8 points below Alpha; Gamma finishes 13 points below",
        mint.compare(
            {"Alpha": 82.0, "Beta": 74.0, "Gamma": 69.0, "Delta": 79.0},
            label="Test accuracy",
            unit="%",
            baseline="Alpha",
            highlight=["Beta", "Gamma"],
            title="Test accuracy across ablation variants",
        ),
        kicker="WORDS ON MARKS · COMPACT DENSITY",
        source="synthetic ablation benchmark",
        density="compact",
        style="editorial",
    )
    w_path = FORMS_OUT / "words_on_marks_compact.png"
    w_summary = w_fig.save(w_path)
    assert w_summary["ship"] is True, f"words_on_marks did not ship: {w_summary['issues']}"
    plt.close(w_fig.fig)
    print(f"Wrote {w_path.name} (ship={w_summary['ship']})")


def main() -> None:
    np.random.seed(42)
    build_flagship_editorial_and_braille()
    build_03_gallery_additions()


if __name__ == "__main__":
    main()
