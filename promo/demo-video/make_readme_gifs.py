"""Build crisp, high-DPI, zero-grain README GIFs from lossless Remotion PNG sequences.

Pipeline:
1. Render ``ReadmeOpener`` and ``ReadmeCheck`` from ``src/readme-index.ts`` at native
   ``1280x720`` (15 fps) using lossless PNG frames (``--sequence --image-format=png``)
   so text and inline SVG chips never suffer JPEG mosquito noise or fractional CSS scaling.
2. Deduplicate static hold frames (combining consecutive near-identical frames' durations)
   and quantize with 256-color ``FASTOCTREE`` + ``dither=NONE`` so solid ``#0B1020`` dark
   backgrounds and pure ``#FFFFFF`` chat/figure cards stay 100% flat with zero grain.

Usage:
    # Encode from already-rendered PNG sequence directories:
    python make_readme_gifs.py --opener-dir /tmp/remotion_opener --check-dir /tmp/remotion_check

    # Or render + encode end-to-end:
    python make_readme_gifs.py --render
"""

from __future__ import annotations

import argparse
import re
import subprocess
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
OUT_DIR = REPO_ROOT / "gallery" / "output" / "readme_comparison"


def render_png_sequences(opener_dir: Path, check_dir: Path, *, concurrency: int = 4) -> None:
    """Bundle src/readme-index.ts and render both README compositions to lossless PNGs."""
    with tempfile.TemporaryDirectory(prefix="mintfig_remotion_bundle_") as bundle_dir:
        subprocess.run(
            [
                str(HERE / "node_modules" / ".bin" / "remotion"),
                "bundle",
                "src/readme-index.ts",
                "--out-dir",
                bundle_dir,
            ],
            cwd=HERE,
            check=True,
        )
        subprocess.run(
            [
                "node",
                str(HERE / "render_readme_frames.mjs"),
                bundle_dir,
                str(opener_dir),
                str(check_dir),
                str(concurrency),
            ],
            cwd=HERE,
            check=True,
        )


def _frame_sort_key(path: Path) -> tuple[int, str]:
    m = re.search(r"(\d+)", path.stem)
    return (int(m.group(1)) if m else 0, path.name)


def png_sequence_to_gif(
    seq_dir: Path,
    gif_path: Path,
    *,
    fps: int = 15,
    width: int | None = None,
    height: int | None = None,
    static_mad_threshold: float = 0.005,
    hold_end_ms: int = 1600,
) -> tuple[int, int, float]:
    """Encode a lossless PNG frame sequence into a crisp, deduplicated looping GIF."""
    paths = sorted(seq_dir.glob("*.png"), key=_frame_sort_key)
    if not paths:
        raise FileNotFoundError(f"No PNG frames found in {seq_dir}")

    frame_ms = round(1000.0 / fps)
    kept_rgb: list[Image.Image] = []
    durations: list[int] = []
    prev_arr: np.ndarray | None = None

    for idx, p in enumerate(paths):
        im = Image.open(p).convert("RGB")
        if width is not None and height is not None and im.size != (width, height):
            im = im.resize((width, height), Image.Resampling.LANCZOS)
        arr = np.asarray(im, dtype=np.int16)
        is_last = idx == len(paths) - 1
        if prev_arr is not None:
            mad = float(np.abs(arr - prev_arr).mean())
            if mad <= static_mad_threshold and not (is_last and mad > 0.0):
                durations[-1] += frame_ms
                continue
        kept_rgb.append(im)
        durations.append(frame_ms)
        prev_arr = arr

    if durations:
        durations[-1] = max(durations[-1], hold_end_ms)

    # Per-frame 256-color FASTOCTREE with zero dithering preserves razor-sharp text
    # anti-aliasing, pure #FFFFFF cards, and completely flat #0B1020 backgrounds.
    quantized = [
        im.quantize(colors=256, method=Image.Quantize.FASTOCTREE, dither=Image.Dither.NONE)
        for im in kept_rgb
    ]

    gif_path.parent.mkdir(parents=True, exist_ok=True)
    quantized[0].save(
        gif_path,
        save_all=True,
        append_images=quantized[1:],
        duration=durations,
        loop=0,
        optimize=True,
    )
    size_kb = gif_path.stat().st_size / 1024.0
    return len(paths), len(quantized), size_kb


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--render", action="store_true", help="Render PNG sequences with Remotion first.")
    parser.add_argument("--opener-dir", type=Path, default=None, help="Directory of ReadmeOpener PNG frames.")
    parser.add_argument("--check-dir", type=Path, default=None, help="Directory of ReadmeCheck PNG frames.")
    parser.add_argument("--width", type=int, default=1280, help="Output GIF width (default: native 1280).")
    parser.add_argument("--height", type=int, default=720, help="Output GIF height (default: native 720).")
    parser.add_argument("--fps", type=int, default=15, help="Source sequence FPS (default: 15).")
    args = parser.parse_args()

    tmp_ctx = tempfile.TemporaryDirectory(prefix="mintfig_readme_seq_") if args.render else None
    try:
        if args.render:
            assert tmp_ctx is not None
            base = Path(tmp_ctx.name)
            opener_dir = args.opener_dir or (base / "opener")
            check_dir = args.check_dir or (base / "check")
            render_png_sequences(opener_dir, check_dir)
        else:
            opener_dir = args.opener_dir
            check_dir = args.check_dir

        if opener_dir is not None:
            raw, kept, kb = png_sequence_to_gif(
                opener_dir,
                OUT_DIR / "opener.gif",
                fps=args.fps,
                width=args.width,
                height=args.height,
                hold_end_ms=1600,
            )
            print(f"opener.gif ({args.width}x{args.height}): {raw} -> {kept} deduped frames, {kb:.1f} KB")

        if check_dir is not None:
            raw, kept, kb = png_sequence_to_gif(
                check_dir,
                OUT_DIR / "mintcheck.gif",
                fps=args.fps,
                width=args.width,
                height=args.height,
                hold_end_ms=1800,
            )
            print(f"mintcheck.gif ({args.width}x{args.height}): {raw} -> {kept} deduped frames, {kb:.1f} KB")

        if opener_dir is None and check_dir is None:
            parser.error("Pass --render or at least one of --opener-dir / --check-dir.")
    finally:
        if tmp_ctx is not None:
            tmp_ctx.cleanup()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
