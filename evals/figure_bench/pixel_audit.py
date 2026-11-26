"""Library-agnostic PNG pixel auditor (Pillow + NumPy only, zero mintfig imports).

Inspects any rendered PNG figure regardless of the library that produced it
(Matplotlib, Seaborn, Altair, Plotly, ggplot2, D3, mintfig):

- Display-width scaling & downscaled reader copy generation
  (:func:`render_at_display_width`).
- Rainbow / jet hue-sweep detection in HSV space, tuned so discrete 3-6 color
  categorical palettes and perceptually uniform colormaps (viridis, plasma,
  inferno, magma, cividis, coolwarm, RdBu) never false-positive.
- Standalone Machado et al. (2009) deuteranopia + WCAG grayscale luminance
  contrast checks, supporting both light and dark surfaces.
- Empty-canvas detection (``ink_fraction < 0.002``) and edge-clipping ink ratio.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

DISPLAY_WIDTH_PX = 700
SURFACE_WIDTHS: dict[str, int] = {
    "chat": 700,
    "narrow": 450,
    "slide": 1280,
    "dark": 700,
    "html": 700,
    "terminal": 700,
}

# Machado et al. (2009) deuteranopia severity=1.0 simulation matrix in linear RGB.
_DEUTERANOPIA_MATRIX = np.array(
    [
        [0.367322, 0.860646, -0.227968],
        [0.280085, 0.672501, 0.047413],
        [-0.011820, 0.042940, 0.968881],
    ],
    dtype=np.float32,
)


def _load_rgb(png_path: str | Path, *, surface: str = "chat") -> tuple[np.ndarray, tuple[int, int]]:
    """Open ``png_path`` as an uint8 RGB array, compositing transparency onto the surface background."""
    with Image.open(png_path) as raw:
        size = (int(raw.width), int(raw.height))
        if raw.mode in ("RGBA", "LA") or (raw.mode == "P" and "transparency" in raw.info):
            rgba = raw.convert("RGBA")
            bg_color = (17, 24, 39, 255) if surface == "dark" else (255, 255, 255, 255)
            bg = Image.new("RGBA", rgba.size, bg_color)
            rgb = Image.alpha_composite(bg, rgba).convert("RGB")
        else:
            rgb = raw.convert("RGB")
        return np.asarray(rgb, dtype=np.uint8), size


def render_at_display_width(
    png: str | Path,
    out_png: str | Path,
    width_px: int = DISPLAY_WIDTH_PX,
    *,
    strip_metadata: bool = True,
) -> tuple[int, int]:
    """Write a copy of ``png`` downscaled to ``width_px`` (never upscaled).

    When ``strip_metadata`` is True (default), PNG text chunks (such as
    ``mintfig:takeaway``) are not copied, making the output safe for blind readers.
    Returns ``(out_width, out_height)``.
    """
    src = Path(png)
    dst = Path(out_png)
    dst.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(src) as img:
        w, h = int(img.width), int(img.height)
        if width_px > 0 and w > width_px:
            new_w = int(width_px)
            new_h = max(1, round(h * new_w / w))
            resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        else:
            new_w, new_h = w, h
            resized = img.copy()
        if strip_metadata:
            resized.save(dst, format="PNG")
        else:
            resized.save(dst, format="PNG", pnginfo=img.info.get("pnginfo"))
    return new_w, new_h


def _srgb_to_linear(rgb01: np.ndarray) -> np.ndarray:
    return np.where(rgb01 <= 0.04045, rgb01 / 12.92, np.power((rgb01 + 0.055) / 1.055, 2.4))


def _linear_to_srgb(lin: np.ndarray) -> np.ndarray:
    lin_c = np.clip(lin, 0.0, 1.0)
    return np.where(lin_c <= 0.0031308, lin_c * 12.92, 1.055 * np.power(lin_c, 1.0 / 2.4) - 0.055)


def _relative_luminance(rgb01: np.ndarray) -> np.ndarray:
    lin = _srgb_to_linear(rgb01)
    return 0.2126 * lin[..., 0] + 0.7152 * lin[..., 1] + 0.0722 * lin[..., 2]


def _contrast_ratio(lum1: np.ndarray | float, lum2: np.ndarray | float) -> np.ndarray | float:
    hi = np.maximum(lum1, lum2)
    lo = np.minimum(lum1, lum2)
    return (hi + 0.05) / (lo + 0.05)


def _simulate_deuteranopia(rgb01: np.ndarray) -> np.ndarray:
    lin = _srgb_to_linear(rgb01)
    sim_lin = np.tensordot(lin, _DEUTERANOPIA_MATRIX.T, axes=([-1], [0]))
    return _linear_to_srgb(sim_lin)


def _rgb_to_hsv(rgb01: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    r, g, b = rgb01[..., 0], rgb01[..., 1], rgb01[..., 2]
    mx = np.maximum(np.maximum(r, g), b)
    mn = np.minimum(np.minimum(r, g), b)
    df = mx - mn
    s = np.where(mx > 1e-6, df / np.maximum(mx, 1e-6), 0.0)
    v = mx
    h = np.zeros_like(mx)
    mask = df > 1e-6
    rm = mask & (mx == r)
    gm = mask & (mx == g) & ~rm
    bm = mask & ~rm & ~gm
    h[rm] = (60.0 * ((g[rm] - b[rm]) / df[rm])) % 360.0
    h[gm] = (60.0 * ((b[gm] - r[gm]) / df[gm]) + 120.0) % 360.0
    h[bm] = (60.0 * ((r[bm] - g[bm]) / df[bm]) + 240.0) % 360.0
    return h, s, v


def _estimate_background(rgb_u8: np.ndarray) -> np.ndarray:
    """Estimate background RGB from the outermost border pixels."""
    top = rgb_u8[0, :, :]
    bottom = rgb_u8[-1, :, :]
    left = rgb_u8[:, 0, :]
    right = rgb_u8[:, -1, :]
    border = np.concatenate([top, bottom, left, right], axis=0)
    return np.median(border, axis=0).astype(np.float32)


def _detect_rainbow(
    h: np.ndarray, s: np.ndarray, v: np.ndarray, total_pixels: int
) -> tuple[bool, int, int, float]:
    """Detect rainbow/jet hue sweeps without false positives on discrete or viridis-family plots."""
    sat_mask = (s >= 0.45) & (v >= 0.25)
    sat_fraction = float(sat_mask.mean())
    if sat_fraction < 0.01:
        return False, 0, 0, sat_fraction

    hs = h[sat_mask]
    oct_counts = np.histogram(hs, bins=8, range=(0.0, 360.0))[0]
    fine_counts = np.histogram(hs, bins=36, range=(0.0, 360.0))[0]

    oct_thr = max(15, 0.0005 * total_pixels)
    fine_thr = max(8, 0.0002 * total_pixels)
    oct_active = oct_counts >= oct_thr
    fine_active = fine_counts >= fine_thr

    n_octants = int(oct_active.sum())
    n_fine = int(fine_active.sum())

    # True rainbow/jet/hsv/nipy_spectral sweeps cover warm red + green + cyan/blue continuously.
    # Requiring >= 14 fine 10-degree hue bins separates smooth hue sweeps from 3-6 discrete colors,
    # and requiring red + green + cyan/blue prevents viridis (no red) and plasma/inferno (no green)
    # from ever false-positiving.
    has_red = bool(oct_active[0] or oct_active[7])
    has_green = bool(oct_active[2] or oct_active[3])
    has_blue_cyan = bool(oct_active[4] or oct_active[5])

    suspected = n_octants >= 5 and n_fine >= 14 and has_red and has_green and has_blue_cyan
    return suspected, n_octants, n_fine, sat_fraction


def _check_cvd_and_grayscale(
    rgb01: np.ndarray,
    bg_rgb01: np.ndarray,
    ink_mask: np.ndarray,
    h: np.ndarray,
    s: np.ndarray,
    v: np.ndarray,
) -> dict[str, Any]:
    """Check deuteranopia & grayscale luminance contrast and red-green collision."""
    if not np.any(ink_mask):
        return {
            "cvd_ok": False,
            "cvd_collision_suspected": False,
            "grayscale_ok": False,
            "ink_contrast_median": 1.0,
            "cvd_contrast_median": 1.0,
        }

    bg_lum = float(_relative_luminance(bg_rgb01))
    ink_rgb = rgb01[ink_mask]
    ink_lum = _relative_luminance(ink_rgb)
    orig_contrast = _contrast_ratio(ink_lum, bg_lum)
    ink_contrast_median = float(np.median(orig_contrast))

    # Colored ink subset (saturated pixels) vs background in grayscale & deuteranopia
    colored_mask = ink_mask & (s >= 0.25) & (v >= 0.15)
    if np.any(colored_mask):
        col_rgb = rgb01[colored_mask]
        col_lum = _relative_luminance(col_rgb)
        gray_contrast = _contrast_ratio(col_lum, bg_lum)
        # Most colored ink should maintain at least 1.5:1 luminance contrast against the background
        grayscale_ok = float(np.percentile(gray_contrast, 75)) >= 1.5

        sim_col = _simulate_deuteranopia(col_rgb)
        sim_bg = _simulate_deuteranopia(bg_rgb01)
        sim_lum = _relative_luminance(sim_col)
        sim_bg_lum = float(_relative_luminance(sim_bg))
        cvd_contrast = _contrast_ratio(sim_lum, sim_bg_lum)
        cvd_contrast_median = float(np.median(cvd_contrast))
        cvd_bg_ok = float(np.percentile(cvd_contrast, 75)) >= 1.5
    else:
        # Monochrome / grayscale figure
        grayscale_ok = float(np.percentile(orig_contrast, 75)) >= 1.8
        cvd_contrast_median = ink_contrast_median
        cvd_bg_ok = grayscale_ok

    # Check whether two prominent saturated hue groups collapse under deuteranopia
    # (classic isoluminant red vs green collision).
    total_px = rgb01.shape[0] * rgb01.shape[1]
    cvd_collision = False
    prominent_sat = colored_mask & (s >= 0.45) & (v >= 0.25)
    if int(prominent_sat.sum()) >= max(40, int(0.005 * total_px)):
        sat_h = h[prominent_sat]
        sat_rgb = rgb01[prominent_sat]
        sat_sim = _simulate_deuteranopia(sat_rgb)
        sat_sim_lum = _relative_luminance(sat_sim)
        # Group into 6 coarse 60-degree hue sectors (red, yellow, green, cyan, blue, magenta)
        sectors = (np.floor(((sat_h + 30.0) % 360.0) / 60.0)).astype(int)
        min_cluster = max(25, int(0.004 * total_px))
        clusters: list[tuple[np.ndarray, np.ndarray, float]] = []
        for sec in range(6):
            cm = sectors == sec
            if int(cm.sum()) >= min_cluster:
                mean_orig = sat_rgb[cm].mean(axis=0)
                mean_sim = sat_sim[cm].mean(axis=0)
                mean_lum = float(sat_sim_lum[cm].mean())
                clusters.append((mean_orig, mean_sim, mean_lum))
        for i in range(len(clusters)):
            for j in range(i + 1, len(clusters)):
                orig_dist = float(np.linalg.norm(clusters[i][0] - clusters[j][0]))
                sim_dist = float(np.linalg.norm(clusters[i][1] - clusters[j][1]))
                lum_diff = abs(clusters[i][2] - clusters[j][2])
                if orig_dist >= 0.35 and sim_dist < 0.085 and lum_diff < 0.06:
                    cvd_collision = True
                    break
            if cvd_collision:
                break

    return {
        "cvd_ok": bool(cvd_bg_ok and not cvd_collision),
        "cvd_collision_suspected": cvd_collision,
        "grayscale_ok": bool(grayscale_ok),
        "ink_contrast_median": round(ink_contrast_median, 2),
        "cvd_contrast_median": round(cvd_contrast_median, 2),
    }


def audit_png(
    png_path: str | Path,
    *,
    display_width_px: int = DISPLAY_WIDTH_PX,
    surface: str = "chat",
    render_copy_to: str | Path | None = None,
) -> dict[str, Any]:
    """Perform a library-agnostic pixel audit of ``png_path``.

    Returns dimensions, display-scaled dimensions, background polarity,
    ink density / empty-canvas detection, edge-clipping ink ratio, rainbow
    colormap detection, and deuteranopia + grayscale contrast checks.
    """
    path = Path(png_path)
    rgb_u8, (w, h) = _load_rgb(path, surface=surface)

    target_w = int(display_width_px) if display_width_px > 0 else SURFACE_WIDTHS.get(surface, DISPLAY_WIDTH_PX)
    shown_w = min(target_w, w)
    shown_h = max(1, round(h * shown_w / w)) if w > 0 else h

    if render_copy_to is not None:
        render_at_display_width(path, render_copy_to, width_px=target_w)

    bg_u8 = _estimate_background(rgb_u8)
    bg_rgb01 = (bg_u8 / 255.0).astype(np.float32)
    bg_lum = float(_relative_luminance(bg_rgb01))
    is_dark = bg_lum < 0.35

    # Edge-clipping ink ratio on the outermost 2-pixel border of the full-res PNG
    border_diff = np.max(np.abs(rgb_u8.astype(np.float32) - bg_u8), axis=-1)
    b = min(2, max(1, min(h, w) // 4))
    edge_strips = [
        border_diff[:b, :] > 25.0,
        border_diff[-b:, :] > 25.0,
        border_diff[:, :b] > 25.0,
        border_diff[:, -b:] > 25.0,
    ]
    edge_ratios = [float(s.mean()) for s in edge_strips]
    edge_ink_ratio = float(np.mean(edge_ratios))
    max_edge_ink_ratio = float(np.max(edge_ratios))
    edge_clipped = edge_ink_ratio > 0.05 or max_edge_ink_ratio > 0.12

    # Downsample very large images for fast HSV + CVD statistics
    max_side = max(w, h)
    if max_side > 600:
        scale = 600.0 / max_side
        sw, sh = max(1, round(w * scale)), max(1, round(h * scale))
        work_u8 = np.asarray(
            Image.fromarray(rgb_u8).resize((sw, sh), Image.Resampling.BILINEAR),
            dtype=np.uint8,
        )
    else:
        work_u8 = rgb_u8

    diff = np.max(np.abs(work_u8.astype(np.float32) - bg_u8), axis=-1)
    ink_mask = diff > 20.0
    ink_fraction = float(ink_mask.mean())
    empty_canvas = ink_fraction < 0.002

    rgb01 = work_u8.astype(np.float32) / 255.0
    hue, sat, val = _rgb_to_hsv(rgb01)
    total_px = work_u8.shape[0] * work_u8.shape[1]

    rainbow_suspected, n_octants, n_fine, sat_fraction = _detect_rainbow(hue, sat, val, total_px)
    cvd = _check_cvd_and_grayscale(rgb01, bg_rgb01, ink_mask, hue, sat, val)

    issues: list[str] = []
    if empty_canvas:
        issues.append(f"empty_canvas: ink_fraction={ink_fraction:.4f} (< 0.002)")
    if edge_clipped:
        issues.append(f"edge_clipped: edge_ink_ratio={edge_ink_ratio:.3f} (max_edge={max_edge_ink_ratio:.3f})")
    if rainbow_suspected:
        issues.append(
            f"rainbow_colormap_suspected: {n_octants} hue octants / {n_fine} fine hue bins"
        )
    if not cvd["cvd_ok"]:
        reason = "red-green collision" if cvd["cvd_collision_suspected"] else "low deuteranopia contrast"
        issues.append(f"cvd_issue: {reason}")
    if not cvd["grayscale_ok"]:
        issues.append("grayscale_low_contrast: colored ink lacks luminance contrast against background")
    if surface == "dark" and not is_dark:
        issues.append("surface_mismatch: dark surface requested but background is light")

    return {
        "png_px": [w, h],
        "shown_px": [shown_w, shown_h],
        "display_width_px": shown_w,
        "surface": surface,
        "is_dark_background": is_dark,
        "bg_rgb": [round(float(c)) for c in bg_u8],
        "ink_fraction": round(ink_fraction, 5),
        "empty_canvas": empty_canvas,
        "edge_ink_ratio": round(edge_ink_ratio, 4),
        "max_edge_ink_ratio": round(max_edge_ink_ratio, 4),
        "edge_clipped": edge_clipped,
        "rainbow_colormap_suspected": rainbow_suspected,
        "saturated_hue_octants": n_octants,
        "saturated_fine_hue_bins": n_fine,
        "saturated_fraction": round(sat_fraction, 4),
        "cvd_ok": cvd["cvd_ok"],
        "cvd_collision_suspected": cvd["cvd_collision_suspected"],
        "grayscale_ok": cvd["grayscale_ok"],
        "ink_contrast_median": cvd["ink_contrast_median"],
        "cvd_contrast_median": cvd["cvd_contrast_median"],
        "issues": issues,
    }
