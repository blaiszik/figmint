"""Editorial color palettes, banned colormaps, and CVD / grayscale simulation."""

from __future__ import annotations

from typing import Literal

import matplotlib as mpl
import numpy as np
from matplotlib.colors import LinearSegmentedColormap

PALETTES: dict[str, list[str]] = {
    "nature": [
        "#E64B35",
        "#4DBBD5",
        "#00A087",
        "#3C5488",
        "#F39B7F",
        "#8491B4",
        "#91D1C2",
        "#7E6148",
    ],
    "nature_muted": [
        "#C84B31",
        "#2C5F8A",
        "#1E8A78",
        "#6E5A8A",
        "#C98A2E",
        "#5B6B7C",
        "#9E5B40",
        "#3A4654",
    ],
    "science": [
        "#3B4992",
        "#EE0000",
        "#008B45",
        "#631879",
        "#008280",
        "#BB0021",
        "#5F559B",
        "#A20056",
    ],
    "okabe_ito": [
        "#0072B2",
        "#D55E00",
        "#009E73",
        "#CC79A7",
        "#E69F00",
        "#56B4E9",
        "#F0E442",
        "#222222",
    ],
    "tol_bright": [
        "#4477AA",
        "#EE6677",
        "#228833",
        "#CCBB44",
        "#66CCEE",
        "#AA3377",
        "#BBBBBB",
    ],
    "tol_muted": [
        "#332288",
        "#88CCEE",
        "#44AA99",
        "#117733",
        "#999933",
        "#DDCC77",
        "#CC6677",
        "#882255",
        "#AA4499",
    ],
}

BANNED_COLORMAPS: frozenset[str] = frozenset(
    {
        "jet",
        "rainbow",
        "hsv",
        "gist_rainbow",
        "nipy_spectral",
        "prism",
        "flag",
    }
)

# Machado, Oliveira & Fernandes (2009), IEEE TVCG, severity = 1.0 (dichromacy)
# Matrices operate in linear sRGB space; row sums equal 1.0 (achromatic white preserved).
_CVD_MATRICES: dict[str, np.ndarray] = {
    "deuteranopia": np.array(
        [
            [0.367322, 0.860646, -0.227968],
            [0.280085, 0.672501, 0.047413],
            [-0.011820, 0.042940, 0.968881],
        ],
        dtype=np.float64,
    ),
    "protanopia": np.array(
        [
            [0.152286, 1.052583, -0.204868],
            [0.114503, 0.786281, 0.099216],
            [-0.003882, -0.048116, 1.051998],
        ],
        dtype=np.float64,
    ),
    "tritanopia": np.array(
        [
            [1.255528, -0.076749, -0.178779],
            [-0.078411, 0.930809, 0.147602],
            [0.004733, 0.691367, 0.303900],
        ],
        dtype=np.float64,
    ),
}

# Rec.709 / sRGB luminance weights in linear light
_REC709_WEIGHTS = np.array([0.2126, 0.7152, 0.0722], dtype=np.float64)


def get_palette(name: str) -> list[str]:
    """Return a copy of the named color palette."""
    if not isinstance(name, str):
        raise TypeError(f"Palette name must be a str, got {type(name).__name__}")
    key = name.strip().lower().replace("-", "_").replace(" ", "_")
    if key not in PALETTES:
        valid = ", ".join(sorted(PALETTES.keys()))
        raise ValueError(f"Unknown palette {name!r}. Available palettes: {valid}")
    return list(PALETTES[key])


def _srgb_to_linear(srgb: np.ndarray) -> np.ndarray:
    """Convert sRGB values in [0, 1] to linear RGB."""
    return np.where(srgb <= 0.04045, srgb / 12.92, np.power((srgb + 0.055) / 1.055, 2.4))


def _linear_to_srgb(linear: np.ndarray) -> np.ndarray:
    """Convert linear RGB values in [0, 1] to sRGB."""
    clipped = np.clip(linear, 0.0, 1.0)
    return np.where(
        clipped <= 0.0031308,
        12.92 * clipped,
        1.055 * np.power(clipped, 1.0 / 2.4) - 0.055,
    )


def simulate_cvd(
    rgb: np.ndarray,
    kind: Literal["deuteranopia", "protanopia", "tritanopia", "grayscale"],
) -> np.ndarray:
    """Simulate color-vision deficiency or print grayscale on an RGB(A) image array.

    Parameters
    ----------
    rgb:
        NumPy array of shape ``(..., 3)`` (or ``(..., 4)``, preserving alpha) with
        ``uint8`` values in ``[0, 255]`` or floating-point values in ``[0.0, 1.0]``.
    kind:
        One of ``"deuteranopia"``, ``"protanopia"``, ``"tritanopia"``, or ``"grayscale"``.

    Returns
    -------
    np.ndarray
        Simulated image array with the same shape and dtype as ``rgb``.
    """
    arr = np.asarray(rgb)
    if arr.ndim < 2 or arr.shape[-1] not in (3, 4):
        raise ValueError(f"Expected array with shape (..., 3) or (..., 4), got {arr.shape}")

    kind_key = kind.strip().lower()
    if kind_key not in ("deuteranopia", "protanopia", "tritanopia", "grayscale"):
        raise ValueError(
            f"Unknown CVD simulation kind {kind!r}. "
            "Expected one of: 'deuteranopia', 'protanopia', 'tritanopia', 'grayscale'."
        )

    is_uint8 = arr.dtype == np.uint8
    if is_uint8:
        rgb_float = arr[..., :3].astype(np.float64) / 255.0
    elif np.issubdtype(arr.dtype, np.floating):
        rgb_float = np.clip(arr[..., :3].astype(np.float64), 0.0, 1.0)
    else:
        raise TypeError(f"Expected uint8 or floating-point array, got dtype {arr.dtype}")

    linear = _srgb_to_linear(rgb_float)

    if kind_key == "grayscale":
        lum = np.tensordot(linear, _REC709_WEIGHTS, axes=([-1], [0]))
        sim_linear = np.repeat(lum[..., np.newaxis], 3, axis=-1)
    else:
        matrix = _CVD_MATRICES[kind_key]
        sim_linear = np.einsum("...j,ij->...i", linear, matrix)

    sim_srgb = np.clip(_linear_to_srgb(sim_linear), 0.0, 1.0)

    if is_uint8:
        sim_rgb = np.rint(sim_srgb * 255.0).astype(np.uint8)
    else:
        sim_rgb = sim_srgb.astype(arr.dtype)

    if arr.shape[-1] == 4:
        return np.concatenate([sim_rgb, arr[..., 3:4]], axis=-1)
    return sim_rgb


_EDITORIAL_COLORMAP_STOPS: dict[str, list[str]] = {
    "figmint_navy": ["#F7F9FC", "#DCE6F2", "#9CB9D6", "#507AA6", "#25456E", "#152640"],
    "figmint_teal": ["#F6FAFA", "#D2ECE8", "#7DC9BF", "#1B9A87", "#0C594E"],
    "figmint_coral": ["#FCF8F7", "#F8DDD6", "#EE9E8A", "#DC5842", "#8C2215"],
    "figmint_div": ["#254F82", "#72A2C9", "#F7F8FA", "#E98B77", "#B83227"],
}

EDITORIAL_COLORMAPS: tuple[str, ...] = (
    "figmint_navy",
    "figmint_teal",
    "figmint_coral",
    "figmint_div",
)


def register_colormaps() -> tuple[str, ...]:
    """Register figmint's editorial Matplotlib colormaps (and reversed variants)."""
    for name in EDITORIAL_COLORMAPS:
        stops = _EDITORIAL_COLORMAP_STOPS[name]
        if name not in mpl.colormaps:
            cmap = LinearSegmentedColormap.from_list(name, stops)
            mpl.colormaps.register(cmap, name=name)
        rev_name = f"{name}_r"
        if rev_name not in mpl.colormaps:
            rev_cmap = LinearSegmentedColormap.from_list(rev_name, list(reversed(stops)))
            mpl.colormaps.register(rev_cmap, name=rev_name)
    return EDITORIAL_COLORMAPS


register_colormaps()
