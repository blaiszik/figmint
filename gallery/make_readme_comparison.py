"""Render the side-by-side README comparison figures on the same ablation data.

Writes two PNGs into ``gallery/output/readme_comparison/`` without touching any
other gallery outputs:

- ``matplotlib_default.png``: a realistic default agent Matplotlib render
  (wide 12×4.8 in canvas that shrinks text below 11 px at 700 px chat width,
  truncated bar baseline, unlabelled error bars/bands, legend box, topic-only
  title) that fails ``mint.check``.
- ``mintfig_reply.png``: the clean ``mint.explain`` render of the exact same
  data, passing ``summary["ship"] is True`` with zero issues.
"""

from __future__ import annotations

import argparse
import shutil
import textwrap
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from PIL import Image, ImageDraw, ImageFont

import mintfig as mint

OUT_DIR = Path(__file__).resolve().parent / "output" / "readme_comparison"
SOURCE = "runs/ablation_2026-11 (5 seeds per variant)"

TEXT_ONLY_REPLY = (
    "I ran the ablation with five variants and five seeds each. The full model reaches "
    "0.82 test accuracy (95% CI 0.80–0.84). Removing augmentation gives 0.80 (0.78–0.82) "
    "and a smaller encoder 0.78 (0.75–0.81), both within seed noise of the full model. "
    "Removing retrieval drops accuracy to 0.74 (0.71–0.77), a loss of 8 points, and "
    "removing fine-tuning drops it to 0.69 (0.66–0.72), a loss of 13 points; neither "
    "interval overlaps the full model's. On the validation curves the three main variants "
    "start together, but by step 500 the full model is at 0.66, no retrieval at 0.60 and "
    "no fine-tuning at 0.48, and the order holds through step 2,000, where they end at "
    "0.82, 0.74 and 0.68."
)


def build_ablation_data() -> dict[str, object]:
    """Deterministic 5-variant, 5-seed ablation dataset shared by both renders."""
    rng = np.random.default_rng(7)
    steps = np.arange(0, 2001, 250)
    finals_main = {"full model": 0.82, "no retrieval": 0.74, "no fine-tuning": 0.69}
    scores = {
        "full model": 0.82,
        "no augmentation": 0.80,
        "smaller encoder": 0.78,
        "no retrieval": 0.74,
        "no fine-tuning": 0.69,
    }
    errors = {
        "full model": (0.80, 0.84),
        "no augmentation": (0.78, 0.82),
        "smaller encoder": (0.75, 0.81),
        "no retrieval": (0.71, 0.77),
        "no fine-tuning": (0.66, 0.72),
    }
    curves: dict[str, list[float]] = {}
    bands: dict[str, float] = {}
    for name, final in finals_main.items():
        tau = 420.0 if name == "no fine-tuning" else 300.0
        mean = final * (1.0 - np.exp(-steps / tau))
        curves[name] = (mean + rng.normal(0.0, 0.003, steps.size)).round(3).tolist()
        bands[name] = 0.02
    return {
        "steps": steps.tolist(),
        "scores": scores,
        "errors": errors,
        "curves": curves,
        "bands": bands,
    }


def render_matplotlib_default(data: dict[str, object], out_path: Path) -> dict[str, object]:
    """Render a realistic default agent Matplotlib plot and audit it with mint.check."""
    scores: dict[str, float] = data["scores"]  # type: ignore[assignment]
    errors: dict[str, tuple[float, float]] = data["errors"]  # type: ignore[assignment]
    steps: list[int] = data["steps"]  # type: ignore[assignment]
    curves: dict[str, list[float]] = data["curves"]  # type: ignore[assignment]
    bands: dict[str, float] = data["bands"]  # type: ignore[assignment]

    names = list(scores.keys())
    vals = [scores[k] for k in names]
    yerr = [scores[k] - errors[k][0] for k in names]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4.8))
    ax1.bar(names, vals, yerr=yerr, capsize=4, color="#1f77b4", alpha=0.85)
    ax1.set_ylim(0.55, 0.88)
    ax1.set_title("Test Accuracy")
    ax1.set_ylabel("Accuracy")
    ax1.tick_params(axis="x", rotation=22)

    for label, ys in curves.items():
        arr = np.asarray(ys, dtype=float)
        sd = bands[label]
        (line,) = ax2.plot(steps, arr, label=label, linewidth=1.8)
        ax2.fill_between(steps, arr - sd, arr + sd, alpha=0.2, color=line.get_color())
    ax2.set_title("Validation Accuracy")
    ax2.set_xlabel("Training Step")
    ax2.set_ylabel("Accuracy")
    ax2.legend(loc="lower right")

    fig.suptitle("Ablation Results")
    fig.tight_layout()

    report = mint.check(fig, dpi=150)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    return report


def render_mintfig_reply(data: dict[str, object], out_path: Path) -> dict[str, object]:
    """Render the clean mint.explain figure on the exact same dataset."""
    scores: dict[str, float] = data["scores"]  # type: ignore[assignment]
    errors: dict[str, tuple[float, float]] = data["errors"]  # type: ignore[assignment]
    steps: list[int] = data["steps"]  # type: ignore[assignment]
    curves: dict[str, list[float]] = data["curves"]  # type: ignore[assignment]
    bands: dict[str, float] = data["bands"]  # type: ignore[assignment]

    fig = mint.explain(
        "Removing retrieval costs 8 points of accuracy; removing fine-tuning costs 13",
        mint.compare(
            scores,
            error=errors,
            error_label="95% CI, 5 seeds",
            title="Both losses are outside seed noise",
            label="Test accuracy",
            highlight=["no retrieval", "no fine-tuning"],
        ),
        mint.trend(
            steps,
            curves,
            band=bands,
            band_label="± 1 s.d.",
            title="The gap opens in the first 500 steps",
            label="Validation accuracy",
            x_label="Training step",
        ),
        source=SOURCE,
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    summary = fig.save(out_path)
    return summary


def _load_font(size: int, *, bold: bool = False, italic: bool = False) -> ImageFont.FreeTypeFont:
    """Resolve a crisp sans-serif TrueType font on macOS/Linux."""
    if bold:
        candidates = [
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ]
    elif italic:
        candidates = [
            "/System/Library/Fonts/Supplemental/Arial Italic.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf",
        ]
    else:
        candidates = [
            "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ]
    for path in candidates:
        if Path(path).is_file():
            return ImageFont.truetype(path, size=size)
    return ImageFont.load_default()  # type: ignore[return-value]


def _draw_pill(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    text: str,
    font: ImageFont.FreeTypeFont,
    *,
    fill: str,
    outline: str,
    fg: str,
    pad_x: int = 20,
    pad_y: int = 10,
) -> int:
    """Draw a rounded pill and return its right-edge x coordinate."""
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    w = tw + 2 * pad_x
    h = th + 2 * pad_y
    draw.rounded_rectangle([x, y, x + w, y + h], radius=h // 2, fill=fill, outline=outline, width=2)
    draw.text((x + pad_x, y + pad_y - bbox[1]), text, font=font, fill=fg)
    return x + w


def _fit_image(img: Image.Image, max_w: int, max_h: int) -> Image.Image:
    scale = min(max_w / img.width, max_h / img.height)
    new_size = (max(1, round(img.width * scale)), max(1, round(img.height * scale)))
    return img.resize(new_size, Image.Resampling.LANCZOS)


def _render_card_frame(
    step: int,
    *,
    mpl_img: Image.Image,
    mint_img: Image.Image,
    min_text_px: float,
    show_issues: bool = True,
) -> Image.Image:
    """Render one 2x-supersampled frame and downsample to 900x540 for crisp anti-aliasing."""
    W, H = 1800, 1080
    img = Image.new("RGB", (W, H), "#F4F6F8")
    draw = ImageDraw.Draw(img)

    # Fonts (at 2x scale)
    f_tab = _load_font(24, bold=True)
    f_badge = _load_font(23, bold=True)
    f_prompt = _load_font(25, bold=True)
    f_body = _load_font(30)
    f_lead = _load_font(27, bold=True)
    f_caption = _load_font(24, italic=True)
    f_pill = _load_font(22, bold=True)
    f_note = _load_font(23)

    # Outer card with subtle border
    cx0, cy0, cx1, cy1 = 36, 32, W - 36, H - 32
    draw.rounded_rectangle(
        [cx0, cy0, cx1, cy1], radius=28, fill="#FFFFFF", outline="#DCE2EA", width=3
    )

    # Header bar
    hdr_y = cy0 + 28
    tabs = [
        (1, "1 · Text only", "#1A1D21", "#1A1D21", "#FFFFFF"),
        (2, "2 · Default Matplotlib", "#FEF3F2", "#FECDCA", "#B42318"),
        (3, "3 · mintfig reply", "#ECFDF3", "#ABEFC6", "#067647"),
    ]
    tx = cx0 + 40
    for idx, label, act_fill, act_out, act_fg in tabs:
        if idx == step:
            tx = _draw_pill(
                draw, tx, hdr_y, label, f_tab, fill=act_fill, outline=act_out, fg=act_fg
            )
        else:
            tx = _draw_pill(
                draw, tx, hdr_y, label, f_tab, fill="#F8FAFC", outline="#E2E8F0", fg="#64748B"
            )
        tx += 16

    # Right status badge
    if step == 1:
        b_txt, b_fill, b_out, b_fg = "140 words · 16 buried numbers", "#F1F5F9", "#CBD5E1", "#475569"
    elif step == 2:
        b_txt, b_fill, b_out, b_fg = "mint.check  →  ship: false", "#FEF3F2", "#FDA29B", "#B42318"
    else:
        b_txt, b_fill, b_out, b_fg = "ship: true · 15/15 clean & right #", "#ECFDF3", "#6CE9A6", "#067647"
    bb = draw.textbbox((0, 0), b_txt, font=f_badge)
    bw = (bb[2] - bb[0]) + 44
    _draw_pill(draw, cx1 - 40 - bw, hdr_y, b_txt, f_badge, fill=b_fill, outline=b_out, fg=b_fg, pad_x=22)

    # Divider under header
    div_y = cy0 + 106
    draw.line([(cx0 + 2, div_y), (cx1 - 2, div_y)], fill="#E9EEF4", width=2)

    # Prompt line
    body_x = cx0 + 48
    body_w = (cx1 - cx0) - 96
    prompt_y = div_y + 26
    draw.text((body_x, prompt_y), 'Prompt: "How did the 5-seed ablation go?"', font=f_prompt, fill="#64748B")

    if step == 1:
        # Text-only wall inside a soft chat bubble
        bub_y0 = prompt_y + 52
        bub_y1 = cy1 - 110
        draw.rounded_rectangle(
            [body_x, bub_y0, cx1 - 48, bub_y1],
            radius=20,
            fill="#F8FAFC",
            outline="#E2E8F0",
            width=2,
        )
        lines = textwrap.wrap(TEXT_ONLY_REPLY, width=102)
        ly = bub_y0 + 44
        for line in lines:
            draw.text((body_x + 40, ly), line, font=f_body, fill="#1E293B")
            ly += 52
        draw.text(
            (body_x, cy1 - 76),
            "No chart, no uncertainty comparison at a glance — readers have to parse 16 numbers by hand.",
            font=f_note,
            fill="#64748B",
        )

    elif step == 2:
        draw.text(
            (body_x, prompt_y + 44),
            "Default Matplotlib (figure-bench v0.1 initial-15: 13/15 defective, 4/15 right headline):",
            font=f_lead,
            fill="#334155",
        )
        fitted = _fit_image(mpl_img, max_w=body_w - 40, max_h=600)
        ix = cx0 + (cx1 - cx0 - fitted.width) // 2
        iy = prompt_y + 98
        draw.rounded_rectangle(
            [ix - 10, iy - 10, ix + fitted.width + 10, iy + fitted.height + 10],
            radius=14,
            fill="#FFFFFF",
            outline="#FECDCA" if show_issues else "#E2E8F0",
            width=3,
        )
        img.paste(fitted, (ix, iy))

        if show_issues:
            pills = [
                f"text_too_small ({min_text_px:.1f} px at 700 px)",
                "bar_baseline_nonzero (starts at 0.55)",
                "interval_unlabelled",
                "topic-only title",
            ]
            # Center pill row horizontally
            pill_ws = [
                (draw.textbbox((0, 0), p, font=f_pill)[2] - draw.textbbox((0, 0), p, font=f_pill)[0]) + 36
                for p in pills
            ]
            total_pw = sum(pill_ws) + 16 * (len(pills) - 1)
            px = cx0 + (cx1 - cx0 - total_pw) // 2
            py = cy1 - 92
            for p in pills:
                px = _draw_pill(
                    draw, px, py, p, f_pill, fill="#FEF3F2", outline="#FDA29B", fg="#B42318", pad_x=18, pad_y=9
                )
                px += 16

    else:
        draw.text(
            (body_x, prompt_y + 44),
            "Retrieval and fine-tuning are the two components worth keeping; the other two are within seed noise.",
            font=f_lead,
            fill="#0F172A",
        )
        fitted = _fit_image(mint_img, max_w=body_w - 140, max_h=660)
        ix = cx0 + (cx1 - cx0 - fitted.width) // 2
        iy = prompt_y + 94
        draw.rounded_rectangle(
            [ix - 8, iy - 8, ix + fitted.width + 8, iy + fitted.height + 8],
            radius=14,
            fill="#FFFFFF",
            outline="#ABEFC6",
            width=3,
        )
        img.paste(fitted, (ix, iy))
        caption = (
            "No retrieval 0.74 and no fine-tuning 0.69 against 0.82 for the full model; "
            "neither 95% CI (5 seeds) overlaps it."
        )
        cb = draw.textbbox((0, 0), caption, font=f_caption)
        cw = cb[2] - cb[0]
        draw.text(
            (cx0 + (cx1 - cx0 - cw) // 2, cy1 - 74),
            caption,
            font=f_caption,
            fill="#475569",
        )

    # Progress bar along bottom edge of card
    bar_x0, bar_x1 = cx0 + 40, cx1 - 40
    bar_y = cy1 - 18
    draw.rounded_rectangle([bar_x0, bar_y, bar_x1, bar_y + 6], radius=3, fill="#E2E8F0")
    frac = {1: 1 / 3, 2: 2 / 3, 3: 1.0}[step]
    bar_color = {1: "#334155", 2: "#D92D20", 3: "#079455"}[step]
    draw.rounded_rectangle(
        [bar_x0, bar_y, bar_x0 + int((bar_x1 - bar_x0) * frac), bar_y + 6],
        radius=3,
        fill=bar_color,
    )

    return img.resize((900, 540), Image.Resampling.LANCZOS)


def render_opener_gif(
    mpl_path: Path,
    mint_path: Path,
    mpl_report: dict[str, object],
    out_path: Path,
) -> Path:
    """Assemble a compact, auto-playing 3-beat README comparison GIF."""
    mpl_img = Image.open(mpl_path).convert("RGB")
    mint_img = Image.open(mint_path).convert("RGB")
    min_text_px = float(mpl_report["display"]["min_text_px"])  # type: ignore[index]

    f1 = _render_card_frame(1, mpl_img=mpl_img, mint_img=mint_img, min_text_px=min_text_px)
    f2a = _render_card_frame(
        2, mpl_img=mpl_img, mint_img=mint_img, min_text_px=min_text_px, show_issues=False
    )
    f2b = _render_card_frame(
        2, mpl_img=mpl_img, mint_img=mint_img, min_text_px=min_text_px, show_issues=True
    )
    f3 = _render_card_frame(3, mpl_img=mpl_img, mint_img=mint_img, min_text_px=min_text_px)

    def _blend(a: Image.Image, b: Image.Image, steps: int = 1) -> list[tuple[Image.Image, int]]:
        return [
            (Image.blend(a, b, i / (steps + 1)), 90)
            for i in range(1, steps + 1)
        ]

    timeline: list[tuple[Image.Image, int]] = [
        (f1, 2800),
        *_blend(f1, f2a, steps=1),
        (f2a, 850),
        (f2b, 3400),
        *_blend(f2b, f3, steps=1),
        (f3, 5200),
        *_blend(f3, f1, steps=1),
    ]

    # Quantize with a shared adaptive palette for clean flat backgrounds and tiny file size.
    frames = [
        im.quantize(colors=256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
        for im, _ in timeline
    ]
    durations = [dur for _, dur in timeline]

    out_path.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(
        out_path,
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=0,
        optimize=True,
    )
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate README comparison PNGs.")
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR, help="Output directory")
    parser.add_argument(
        "--copy-to",
        type=Path,
        default=None,
        help="Optional extra directory to copy both PNGs into",
    )
    args = parser.parse_args(argv)

    data = build_ablation_data()
    mpl_path = args.out_dir / "matplotlib_default.png"
    mint_path = args.out_dir / "mintfig_reply.png"
    gif_path = args.out_dir / "opener.gif"

    mpl_report = render_matplotlib_default(data, mpl_path)
    mint_summary = render_mintfig_reply(data, mint_path)
    render_opener_gif(mpl_path, mint_path, mpl_report, gif_path)

    print(
        f"matplotlib_default.png: ship={mpl_report['ship']} "
        f"issues={[i['rule'] for i in mpl_report['issues']]} "
        f"min_text_px={mpl_report['display']['min_text_px']}"
    )
    print(
        f"mintfig_reply.png: ship={mint_summary['ship']} "
        f"issues={mint_summary['issues']} "
        f"size_px={mint_summary['size_px']}"
    )
    print(f"opener.gif: {gif_path.stat().st_size / 1024:.1f} KB")

    if mpl_report["ship"] is not False:
        raise RuntimeError("Expected matplotlib_default.png to fail mint.check!")
    if mint_summary["ship"] is not True or mint_summary["issues"]:
        raise RuntimeError(f"Expected mintfig_reply.png to ship cleanly, got {mint_summary['issues']}")

    if args.copy_to is not None:
        args.copy_to.mkdir(parents=True, exist_ok=True)
        shutil.copy2(mpl_path, args.copy_to / mpl_path.name)
        shutil.copy2(mint_path, args.copy_to / mint_path.name)
        print(f"Copied both PNGs to {args.copy_to}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
