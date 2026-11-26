"""Convert Remotion MP4 renders into compact, crisp, looping README GIFs.

Uses Remotion's bundled ``ffmpeg`` to decode scaled frames and Pillow to
deduplicate static hold frames (combining consecutive near-identical frames'
durations) with per-frame adaptive 256-color quantization and delta
optimization so white cards stay pure ``#FFFFFF`` while file sizes stay small.

Outputs:
- ``gallery/output/readme_comparison/opener.gif`` (from ``out/agent-reply-16x9.mp4``)
- ``gallery/output/readme_comparison/mintcheck.gif`` (from ``out/mintfig-check-16x9.mp4``)
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
OUT_DIR = REPO_ROOT / "gallery" / "output" / "readme_comparison"


def _find_ffmpeg() -> tuple[Path, Path]:
    compositor_root = HERE / "node_modules" / "@remotion"
    for cand in sorted(compositor_root.glob("compositor-*/ffmpeg")):
        if cand.is_file():
            return cand, cand.parent
    raise FileNotFoundError(
        "Could not find Remotion's bundled ffmpeg under promo/demo-video/node_modules/@remotion/."
    )


def mp4_to_compact_gif(
    mp4_path: Path,
    gif_path: Path,
    *,
    start_s: float,
    end_s: float,
    width: int = 840,
    height: int = 472,
    extract_fps: int = 10,
    speed: float = 1.35,
    static_mad_threshold: float = 0.35,
    hold_end_ms: int = 1400,
) -> tuple[int, int, float]:
    """Extract frames with Remotion ffmpeg and write a deduplicated looping GIF."""
    ffmpeg_bin, lib_dir = _find_ffmpeg()
    env = os.environ.copy()
    existing_dyld = env.get("DYLD_LIBRARY_PATH", "")
    env["DYLD_LIBRARY_PATH"] = f"{lib_dir}:{existing_dyld}" if existing_dyld else str(lib_dir)

    frame_ms = max(20, round(1000.0 / (extract_fps * speed)))

    with tempfile.TemporaryDirectory(prefix="mintfig_gif_") as tmp:
        tmp_dir = Path(tmp)
        pattern = str(tmp_dir / "f_%05d.png")
        cmd = [
            str(ffmpeg_bin),
            "-y",
            "-ss",
            f"{start_s:.2f}",
            "-to",
            f"{end_s:.2f}",
            "-i",
            str(mp4_path),
            "-r",
            str(extract_fps),
            "-s",
            f"{width}x{height}",
            pattern,
            "-loglevel",
            "error",
        ]
        subprocess.run(cmd, env=env, check=True)
        paths = sorted(tmp_dir.glob("f_*.png"))
        if not paths:
            raise RuntimeError(f"No frames extracted from {mp4_path}")

        kept_rgb: list[Image.Image] = []
        durations: list[int] = []
        prev_arr: np.ndarray | None = None

        for p in paths:
            im = Image.open(p).convert("RGB")
            arr = np.asarray(im, dtype=np.int16)
            if prev_arr is not None:
                mad = float(np.abs(arr - prev_arr).mean())
                if mad < static_mad_threshold:
                    durations[-1] += frame_ms
                    continue
            kept_rgb.append(im)
            durations.append(frame_ms)
            prev_arr = arr

        if durations:
            durations[-1] = max(durations[-1], hold_end_ms)

        # Quantize each frame independently with FASTOCTREE (256 colors) so pure white
        # cards and vibrant mint/red accents stay 100% faithful across dark & light scenes.
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
    # 1. Opening GIF: AgentReply starting right at the wall-of-text problem (skip 0-3s title card)
    #    Wall of text -> mintchip inline chips & popover -> mintchip forest table -> mintfig figure + hover + cite
    raw1, kept1, kb1 = mp4_to_compact_gif(
        HERE / "out" / "agent-reply-16x9.mp4",
        OUT_DIR / "opener.gif",
        start_s=3.4,
        end_s=30.8,
        width=840,
        height=472,
        extract_fps=10,
        speed=1.35,
        static_mad_threshold=0.35,
        hold_end_ms=1600,
    )
    print(f"opener.gif: {raw1} -> {kept1} deduped frames, {kb1:.1f} KB")

    # 2. Validation GIF: MintCheck starting right at the broken Matplotlib figure (skip 0-4s title card)
    #    Broken Matplotlib -> mintfig check FIX FIRST -> fixed chart SHIP -> mint.explain -> figure-bench stats
    raw2, kept2, kb2 = mp4_to_compact_gif(
        HERE / "out" / "mintfig-check-16x9.mp4",
        OUT_DIR / "mintcheck.gif",
        start_s=4.3,
        end_s=36.3,
        width=840,
        height=472,
        extract_fps=10,
        speed=1.35,
        static_mad_threshold=0.35,
        hold_end_ms=1800,
    )
    print(f"mintcheck.gif: {raw2} -> {kept2} deduped frames, {kb2:.1f} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
