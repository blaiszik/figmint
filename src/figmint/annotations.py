"""Publication-grade scientific annotations for Matplotlib axes."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

import matplotlib as mpl
import matplotlib.patches as mpatches
import matplotlib.transforms as mtransforms
import numpy as np
from matplotlib.ticker import MaxNLocator

if TYPE_CHECKING:
    from matplotlib.axes import Axes
    from matplotlib.colorbar import Colorbar
    from matplotlib.image import AxesImage
    from matplotlib.lines import Line2D
    from matplotlib.text import Text


def _numeric_rc_font(key: str, fallback: float) -> float:
    val = mpl.rcParams.get(key, fallback)
    if isinstance(val, (int, float)):
        return float(val)
    return fallback


def _format_pvalue(p: float, *, stars: bool = False) -> str:
    """Format a p-value in Nature/Science editorial style or star notation."""
    if stars:
        if p < 1e-4:
            return "****"
        if p < 1e-3:
            return "***"
        if p < 1e-2:
            return "**"
        if p < 0.05:
            return "*"
        return "ns"

    if p < 1e-4:
        return "p < 0.0001"
    if p < 0.01:
        return f"p = {p:.4f}"
    if p < 0.1:
        return f"p = {p:.3f}"
    return f"p = {p:.2f}"


def sig_bracket(
    ax: Axes,
    x1: float,
    x2: float,
    *,
    y: float | None = None,
    p: float | None = None,
    label: str | None = None,
    height_frac: float = 0.03,
    pad_frac: float = 0.04,
    text_pad_frac: float = 0.015,
    lw: float = 0.6,
    color: str = "#111111",
    fontsize: float | None = None,
    auto_stack: bool = True,
) -> tuple[Line2D, Text | None]:
    """Draw a crisp significance bracket with automatic non-overlapping stacking.

    Tracks previously placed brackets on ``ax`` so multiple pairwise comparisons
    stack cleanly without colliding, formats ``p`` values automatically, and
    expands ``ylim`` just enough to prevent clipping.
    """
    x_lo, x_hi = (float(x1), float(x2)) if x1 <= x2 else (float(x2), float(x1))

    if label == "stars" and p is not None:
        text_str: str | None = _format_pvalue(p, stars=True)
    elif label is not None:
        text_str = str(label)
    elif p is not None:
        text_str = _format_pvalue(p, stars=False)
    else:
        text_str = None

    fs = float(fontsize) if fontsize is not None else _numeric_rc_font("legend.fontsize", 6.0)
    eff_lw = max(float(lw), 0.25)

    is_log = ax.get_yscale() == "log"
    cur_ymin, cur_ymax = ax.get_ylim()
    xlim = ax.get_xlim()
    x_span = abs(xlim[1] - xlim[0]) or 1.0
    x_tol = 0.02 * x_span

    # Snapshot baseline data range once per axes so repeated brackets step evenly.
    if not hasattr(ax, "_figmint_sig_brackets"):
        ax._figmint_sig_brackets = []  # type: ignore[attr-defined]
        data_ymax = ax.dataLim.ymax if np.isfinite(ax.dataLim.ymax) else cur_ymax
        data_ymin = ax.dataLim.ymin if np.isfinite(ax.dataLim.ymin) else cur_ymin
        if is_log:
            lo_ref = np.log10(max(cur_ymin, 1e-300))
            hi_ref = np.log10(max(cur_ymax, 1e-300))
            data_hi = np.log10(max(data_ymax, 1e-300))
            base_span = max(hi_ref - lo_ref, 0.5)
            base_top = min(hi_ref, max(data_hi, lo_ref + 0.1 * base_span))
        else:
            base_span = abs(cur_ymax - cur_ymin)
            if base_span <= 0:
                base_span = max(abs(data_ymax - data_ymin), 1.0)
            base_top = max(data_ymax, cur_ymin) if np.isfinite(data_ymax) else cur_ymax
            # Ensure base_top is not above the current upper data extent
            base_top = min(base_top, cur_ymax)
        ax._figmint_sig_base_span = base_span  # type: ignore[attr-defined]
        ax._figmint_sig_base_top = base_top  # type: ignore[attr-defined]

    placed: list[tuple[float, float, float]] = ax._figmint_sig_brackets  # type: ignore[attr-defined]
    base_span: float = ax._figmint_sig_base_span  # type: ignore[attr-defined]
    base_top: float = ax._figmint_sig_base_top  # type: ignore[attr-defined]

    # Estimate label height in data/log10 units based on axes physical height.
    ax_h_pt = ax.figure.get_figheight() * 72.0 * max(ax.get_position().height, 0.18)
    text_h_frac = max(0.065, (fs * 1.55) / max(ax_h_pt, 36.0))

    h = height_frac * base_span
    pad = pad_frac * base_span
    text_pad = text_pad_frac * base_span
    text_h = text_h_frac * base_span if text_str else 0.0

    def _overlaps_x(a1: float, a2: float, b1: float, b2: float) -> bool:
        return not (a2 < b1 - x_tol or a1 > b2 + x_tol)

    if y is None:
        y_base = base_top + pad
        if auto_stack:
            for bx1, bx2, b_top in placed:
                if _overlaps_x(x_lo, x_hi, bx1, bx2):
                    y_base = max(y_base, b_top + pad)
    else:
        y_base = np.log10(max(float(y), 1e-300)) if is_log else float(y)

    y_bar = y_base + h
    y_text = y_bar + text_pad
    top_bound = y_text + text_h

    if is_log:
        ys_plot = [10.0**y_base, 10.0**y_bar, 10.0**y_bar, 10.0**y_base]
        y_text_plot = 10.0**y_text
        needed_ymax = 10.0 ** (top_bound + pad * 0.9)
    else:
        ys_plot = [y_base, y_bar, y_bar, y_base]
        y_text_plot = y_text
        needed_ymax = top_bound + pad * 0.9

    (line,) = ax.plot(
        [x_lo, x_lo, x_hi, x_hi],
        ys_plot,
        color=color,
        linewidth=eff_lw,
        solid_capstyle="butt",
        zorder=6,
    )

    txt: Text | None = None
    if text_str is not None:
        txt = ax.text(
            0.5 * (x_lo + x_hi),
            y_text_plot,
            text_str,
            ha="center",
            va="bottom",
            color=color,
            fontsize=fs,
            zorder=6,
        )

    placed.append((x_lo, x_hi, top_bound))

    if needed_ymax > cur_ymax:
        ax.set_ylim(cur_ymin, needed_ymax)

    return line, txt


def _normalize_micro_unit(unit: str) -> str:
    """Render Unicode micro sign upright in sans-serif Helvetica via mathtext."""
    if not unit or "$" in unit:
        return unit
    if "\u00b5" in unit or "\u03bc" in unit:
        return unit.replace("\u00b5", r"$\mathrm{\mu}$").replace("\u03bc", r"$\mathrm{\mu}$")
    return unit


def scalebar(
    ax: Axes,
    length: float,
    unit: str = r"$\mathrm{\mu}$m",
    *,
    pixel_size: float = 1.0,
    location: str = "lower right",
    pad_frac: float = 0.05,
    bar_height_pt: float = 2.0,
    color: str = "white",
    label_color: str | None = None,
    frameon: bool = False,
    fontsize: float | None = None,
) -> tuple[mpatches.Rectangle, Text]:
    """Place a calibrated microscopy or spatial scale bar inside an image axes."""
    if length <= 0 or pixel_size <= 0:
        raise ValueError("length and pixel_size must be positive")

    xlim = ax.get_xlim()
    x_span = abs(xlim[1] - xlim[0])
    if x_span <= 0:
        raise ValueError("Axes x-limits have zero span; plot image before adding scalebar")

    bar_data_len = float(length) / float(pixel_size)
    bar_w_ax = bar_data_len / x_span

    ax_h_pt = ax.figure.get_figheight() * 72.0 * max(ax.get_position().height, 0.18)
    bar_h_ax = float(np.clip(bar_height_pt / max(ax_h_pt, 24.0), 0.008, 0.06))

    loc = location.lower().strip()
    if "right" in loc:
        x0 = 1.0 - pad_frac - bar_w_ax
    elif "left" in loc:
        x0 = pad_frac
    else:
        raise ValueError(f"Unsupported scalebar location {location!r}")

    fs = float(fontsize) if fontsize is not None else _numeric_rc_font("legend.fontsize", 6.0)
    txt_gap_ax = max(0.022, (2.2 / max(ax_h_pt, 24.0)))
    txt_h_ax = (fs * 1.2) / max(ax_h_pt, 24.0)

    if "lower" in loc:
        y0 = pad_frac
        y_txt = y0 + bar_h_ax + txt_gap_ax
        va = "bottom"
        frame_y0 = y0 - 0.02
        frame_h = bar_h_ax + txt_gap_ax + txt_h_ax + 0.04
    elif "upper" in loc:
        y0 = 1.0 - pad_frac - bar_h_ax
        y_txt = y0 - txt_gap_ax
        va = "top"
        frame_h = bar_h_ax + txt_gap_ax + txt_h_ax + 0.04
        frame_y0 = y0 + bar_h_ax + 0.02 - frame_h
    else:
        raise ValueError(f"Unsupported scalebar location {location!r}")

    if frameon:
        frame_pad_x = min(pad_frac * 0.55, max(0.02, 0.08 * bar_w_ax))
        frame = mpatches.FancyBboxPatch(
            (x0 - frame_pad_x, frame_y0),
            bar_w_ax + 2 * frame_pad_x,
            frame_h,
            boxstyle="round,pad=0.008,rounding_size=0.015",
            transform=ax.transAxes,
            facecolor="#111111" if color in {"white", "#ffffff", "#fff", "w"} else "#ffffff",
            edgecolor="none",
            alpha=0.55,
            zorder=9,
        )
        ax.add_patch(frame)

    bar = mpatches.Rectangle(
        (x0, y0),
        bar_w_ax,
        bar_h_ax,
        transform=ax.transAxes,
        facecolor=color,
        edgecolor="none",
        zorder=10,
    )
    ax.add_patch(bar)

    length_str = f"{int(length)}" if float(length).is_integer() else f"{length:g}"
    norm_unit = _normalize_micro_unit(unit)
    text_str = f"{length_str} {norm_unit}".strip() if norm_unit else length_str
    txt_color = label_color if label_color is not None else color

    txt = ax.text(
        x0 + 0.5 * bar_w_ax,
        y_txt,
        text_str,
        transform=ax.transAxes,
        ha="center",
        va=va,
        color=txt_color,
        fontsize=fs,
        fontweight="normal",
        zorder=11,
    )
    txt._figmint_scalebar = True  # type: ignore[attr-defined]
    ax._figmint_has_scalebar = True  # type: ignore[attr-defined]
    return bar, txt


def direct_labels(
    ax: Axes,
    *,
    pad_pt: float = 4.5,
    min_sep_pt: float = 7.5,
    fontsize: float | None = None,
    expand_xlim: float = 0.22,
    trim_spine: bool = True,
) -> list[Text]:
    """Attach color-matched, non-overlapping direct labels to line endpoints.

    Inspects all labeled ``Line2D`` artists on ``ax``, reserves right-hand space
    for labels, trims the bottom spine back to the actual data span when
    ``trim_spine=True`` (so the axis never extends emptily under the labels),
    and iteratively separates vertically adjacent labels in point-space.
    """
    candidates: list[tuple[Line2D, str, float, float]] = []
    data_x_min = np.inf
    data_x_max = -np.inf
    for line in ax.get_lines():
        if not line.get_visible():
            continue
        xdata = np.asarray(line.get_xdata(orig=False), dtype=float)
        ydata = np.asarray(line.get_ydata(orig=False), dtype=float)
        mask = np.isfinite(xdata) & np.isfinite(ydata)
        if not np.any(mask):
            continue
        xf = xdata[mask]
        yf = ydata[mask]
        lbl = line.get_label()
        if not lbl or lbl.startswith("_"):
            continue
        data_x_min = min(data_x_min, float(np.min(xf)))
        data_x_max = max(data_x_max, float(np.max(xf)))
        idx = int(np.argmax(xf))
        candidates.append((line, str(lbl), float(xf[idx]), float(yf[idx])))

    if not candidates:
        return []

    fs = float(fontsize) if fontsize is not None else _numeric_rc_font("legend.fontsize", 6.0)
    eff_min_sep = max(float(min_sep_pt), fs * 1.15)
    orig_x0, orig_x1 = ax.get_xlim()

    # Expand right x-limit to give labels room inside the axes frame.
    if expand_xlim > 0:
        x0, x1 = ax.get_xlim()
        if ax.get_xscale() == "log" and x0 > 0 and x1 > 0:
            ax.set_xlim(x0, x1 * ((x1 / x0) ** expand_xlim))
        else:
            ax.set_xlim(x0, x1 + (x1 - x0) * expand_xlim)

    fig = ax.figure
    fig.canvas.draw()
    dpi = float(fig.dpi)
    pt_per_px = 72.0 / dpi

    # Compute endpoint display positions in points.
    items: list[dict[str, object]] = []
    for line, lbl, xe, ye in candidates:
        px_x, px_y = ax.transData.transform((xe, ye))
        items.append(
            {
                "line": line,
                "label": lbl,
                "x_end": xe,
                "y_end": ye,
                "pt_y": px_y * pt_per_px,
            }
        )

    items.sort(key=lambda d: float(d["pt_y"]))  # type: ignore[arg-type]

    ax_bbox = ax.get_window_extent(fig.canvas.get_renderer())
    margin_pt = max(fs * 0.6, 3.5)
    y_lo_pt = ax_bbox.y0 * pt_per_px + margin_pt
    y_hi_pt = ax_bbox.y1 * pt_per_px - margin_pt

    ys = np.array([float(d["pt_y"]) for d in items], dtype=float)
    n = len(ys)
    if n > 1:
        avail = max(y_hi_pt - y_lo_pt, 1.0)
        if (n - 1) * eff_min_sep > avail:
            ys = np.linspace(y_lo_pt, y_hi_pt, n)
        else:
            for _ in range(250):
                moved = False
                for i in range(n - 1):
                    gap = ys[i + 1] - ys[i]
                    if gap < eff_min_sep:
                        shift = 0.5 * (eff_min_sep - gap) + 0.05
                        ys[i] -= shift
                        ys[i + 1] += shift
                        moved = True
                # Push back inside vertical bounds while preserving order.
                if ys[0] < y_lo_pt:
                    ys += y_lo_pt - ys[0]
                if ys[-1] > y_hi_pt:
                    ys -= ys[-1] - y_hi_pt
                ys = np.clip(ys, y_lo_pt, y_hi_pt)
                if not moved:
                    break
    else:
        ys[0] = float(np.clip(ys[0], y_lo_pt, y_hi_pt))

    inv_trans = ax.transData.inverted()
    text_transform = mtransforms.offset_copy(
        ax.transData,
        fig=fig,
        x=pad_pt,
        y=0.0,
        units="points",
    )

    texts: list[Text] = []
    for item, adj_pt_y in zip(items, ys):
        line = item["line"]
        xe = float(item["x_end"])  # type: ignore[arg-type]
        px_x, _ = ax.transData.transform((xe, float(item["y_end"])))  # type: ignore[arg-type]
        _, y_data = inv_trans.transform((px_x, adj_pt_y / pt_per_px))
        txt = ax.text(
            xe,
            y_data,
            str(item["label"]),
            transform=text_transform,
            color=line.get_color(),  # type: ignore[union-attr]
            fontsize=fs,
            va="center",
            ha="left",
            clip_on=False,
        )
        texts.append(txt)

    # Verify labels fit inside the axes right edge; widen xlim slightly if needed.
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    ax_bbox = ax.get_window_extent(renderer)
    max_right_px = max(t.get_window_extent(renderer).x1 for t in texts)
    if max_right_px > ax_bbox.x1 - 1.0:
        overflow_frac = (max_right_px - ax_bbox.x1 + 3.0) / max(ax_bbox.width, 1.0)
        x0, x1 = ax.get_xlim()
        if ax.get_xscale() == "log" and x0 > 0 and x1 > 0:
            ax.set_xlim(x0, x1 * ((x1 / x0) ** (overflow_frac * 1.15)))
        else:
            ax.set_xlim(x0, x1 + (x1 - x0) * (overflow_frac * 1.15))

    # Keep the bottom spine honest: stop it at the data/original domain instead
    # of running past the curves under the direct labels (Tufte range discipline).
    if trim_spine and np.isfinite(data_x_min) and np.isfinite(data_x_max):
        spine_lo = min(orig_x0, data_x_min) if orig_x0 <= orig_x1 else max(orig_x0, data_x_max)
        spine_hi = data_x_max if orig_x0 <= orig_x1 else data_x_min
        if spine_hi != spine_lo:
            ax.spines["bottom"].set_bounds(float(spine_lo), float(spine_hi))
            # Hide any auto-generated ticks that landed in the label gutter past data_x_max
            cur_ticks = np.asarray(ax.get_xticks(), dtype=float)
            lo_b, hi_b = min(spine_lo, spine_hi), max(spine_lo, spine_hi)
            span = max(hi_b - lo_b, 1e-12)
            kept = [float(t) for t in cur_ticks if lo_b - 1e-6 * span <= t <= hi_b + 1e-6 * span]
            if kept and len(kept) < len(cur_ticks):
                ax.set_xticks(kept)

    return texts


def zoom_inset(
    ax: Axes,
    bounds: tuple[float, float, float, float],
    xlim: tuple[float, float],
    ylim: tuple[float, float],
    *,
    lw: float = 0.5,
    color: str = "#555555",
) -> Axes:
    """Create a cleanly styled inset zoom axes with connector lines."""
    eff_lw = max(float(lw), 0.25)
    inset_ax = ax.inset_axes(list(bounds))
    inset_ax.set_xlim(xlim)
    inset_ax.set_ylim(ylim)
    inset_ax.set_facecolor("white")

    for spine in inset_ax.spines.values():
        spine.set_visible(True)
        spine.set_linewidth(eff_lw)
        spine.set_edgecolor(color)

    tick_pt = _numeric_rc_font("xtick.labelsize", 6.0)
    inset_ax.tick_params(
        which="both",
        direction="out",
        length=2.0,
        width=eff_lw,
        pad=1.5,
        labelsize=tick_pt,
        colors=color,
    )
    inset_ax.xaxis.set_major_locator(MaxNLocator(nbins=3))
    inset_ax.yaxis.set_major_locator(MaxNLocator(nbins=3))

    ax.indicate_inset_zoom(inset_ax, edgecolor=color, linewidth=eff_lw, alpha=0.8)
    return inset_ax


def despine(
    ax: Axes,
    top: bool = True,
    right: bool = True,
    trim: bool = False,
) -> Axes:
    """Remove top/right spines and optionally trim remaining spines to tick bounds."""
    if top:
        ax.spines["top"].set_visible(False)
    if right:
        ax.spines["right"].set_visible(False)

    ax.xaxis.set_ticks_position("bottom")
    ax.yaxis.set_ticks_position("left")

    if trim:
        xticks = np.asarray(ax.get_xticks(), dtype=float)
        x0, x1 = sorted(ax.get_xlim())
        vis_x = xticks[(xticks >= x0) & (xticks <= x1)]
        if len(vis_x) >= 2:
            ax.spines["bottom"].set_bounds(float(vis_x[0]), float(vis_x[-1]))

        yticks = np.asarray(ax.get_yticks(), dtype=float)
        y0, y1 = sorted(ax.get_ylim())
        vis_y = yticks[(yticks >= y0) & (yticks <= y1)]
        if len(vis_y) >= 2:
            ax.spines["left"].set_bounds(float(vis_y[0]), float(vis_y[-1]))

    return ax


def style_colorbar(
    cbar: Colorbar,
    label: str | None = None,
    tick_pt: float | None = None,
) -> Colorbar:
    """Apply crisp editorial styling to a Matplotlib colorbar."""
    ax_lw = _numeric_rc_font("axes.linewidth", 0.5)
    eff_lw = max(ax_lw, 0.25)
    t_pt = float(tick_pt) if tick_pt is not None else _numeric_rc_font("xtick.labelsize", 6.0)
    lbl_pt = _numeric_rc_font("axes.labelsize", 6.5)

    cbar.outline.set_linewidth(max(eff_lw * 0.85, 0.35))
    cbar.outline.set_edgecolor("#CBD3DC")
    cbar.ax.tick_params(
        direction="out",
        length=1.8,
        width=eff_lw,
        pad=2.0,
        color="#4A525A",
        labelsize=t_pt,
    )
    if label is not None:
        cbar.set_label(label, fontsize=lbl_pt, labelpad=4.0)
    return cbar


def subtle_grid(
    ax: Axes,
    *,
    axis: Literal["y", "x", "both"] = "y",
    color: str = "#E6EAF0",
    lw: float = 0.45,
    linestyle: str = "-",
) -> Axes:
    """Enable subtle behind-data editorial guide lines."""
    ax.set_axisbelow(True)
    ax.grid(
        True,
        which="major",
        axis=axis,
        color=color,
        linewidth=max(float(lw), 0.25),
        linestyle=linestyle,
    )
    return ax


def style_heatmap(
    ax: Axes,
    im: AxesImage,
    *,
    cell_border_color: str = "#FFFFFF",
    cell_border_lw: float = 1.4,
    outer_border_color: str | None = "#D8DEE6",
    annotate: bool = False,
    fmt: str = "{:d}",
    zero_color: str = "#B0B8C4",
    light_text: str = "#FFFFFF",
    dark_text: str = "#1A1D21",
    fontsize: float | None = None,
) -> list[Text]:
    """Apply clean editorial styling and optional luminance-aware annotations to a heatmap."""
    if outer_border_color is not None:
        for spine in ax.spines.values():
            spine.set_visible(True)
            spine.set_edgecolor(outer_border_color)
            spine.set_linewidth(0.45)
    else:
        for spine in ax.spines.values():
            spine.set_visible(False)

    ax.tick_params(which="both", length=0)

    raw_arr = im.get_array()
    data = np.ma.asarray(raw_arr)
    if data.ndim < 2:
        return []
    nrows, ncols = int(data.shape[0]), int(data.shape[1])

    ax.set_xticks(np.arange(-0.5, ncols, 1.0), minor=True)
    ax.set_yticks(np.arange(-0.5, nrows, 1.0), minor=True)
    ax.grid(which="major", visible=False)
    ax.grid(
        which="minor",
        color=cell_border_color,
        linestyle="-",
        linewidth=max(float(cell_border_lw), 0.25),
    )
    ax.tick_params(which="minor", bottom=False, left=False, top=False, right=False, length=0)

    texts: list[Text] = []
    if not annotate:
        return texts

    fs = float(fontsize) if fontsize is not None else _numeric_rc_font("xtick.labelsize", 6.0)
    im.autoscale_None()

    for r in range(nrows):
        for c in range(ncols):
            val = data[r, c]
            if np.ma.is_masked(val):
                continue
            fval = float(val)
            if not np.isfinite(fval):
                continue

            try:
                label_str = fmt.format(val)
            except ValueError:
                label_str = fmt.format(round(fval))

            if fval == 0.0:
                txt_color = zero_color
            else:
                rgba = im.cmap(im.norm(fval))
                luminance = 0.2126 * rgba[0] + 0.7152 * rgba[1] + 0.0722 * rgba[2]
                txt_color = light_text if luminance < 0.52 else dark_text

            txt = ax.text(
                c,
                r,
                label_str,
                ha="center",
                va="center",
                color=txt_color,
                fontsize=fs,
            )
            txt._figmint_heatmap_text = True  # type: ignore[attr-defined]
            texts.append(txt)

    return texts


def range_frame(
    ax: Axes,
    xdata: np.ndarray | list[float] | None = None,
    ydata: np.ndarray | list[float] | None = None,
    *,
    rug: bool = False,
    rug_color: str = "#8C96A4",
    rug_frac: float = 0.028,
    rug_lw: float = 0.45,
) -> Axes:
    """Apply a Tufte range frame: trim bottom and left spines to exact data [min, max].

    If ``xdata`` or ``ydata`` are omitted, bounds are inferred from all visible
    ``Line2D`` and ``PathCollection`` artists on ``ax``. When ``rug=True``,
    draws crisp 1D marginal distribution ticks along the bottom and left edges.
    """
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.xaxis.set_ticks_position("bottom")
    ax.yaxis.set_ticks_position("left")

    xs_list: list[np.ndarray] = []
    ys_list: list[np.ndarray] = []
    if xdata is not None:
        xs_list.append(np.asarray(xdata, dtype=float).ravel())
    if ydata is not None:
        ys_list.append(np.asarray(ydata, dtype=float).ravel())

    if not xs_list or not ys_list:
        for line in ax.get_lines():
            if not line.get_visible():
                continue
            lx = np.asarray(line.get_xdata(orig=False), dtype=float).ravel()
            ly = np.asarray(line.get_ydata(orig=False), dtype=float).ravel()
            if not xs_list and lx.size:
                xs_list.append(lx)
            if not ys_list and ly.size:
                ys_list.append(ly)
        for col in ax.collections:
            if not col.get_visible():
                continue
            offsets = col.get_offsets()
            if offsets is not None and len(offsets):
                arr = np.asarray(offsets, dtype=float)
                if arr.ndim == 2 and arr.shape[1] >= 2:
                    if not xs_list:
                        xs_list.append(arr[:, 0])
                    if not ys_list:
                        ys_list.append(arr[:, 1])

    x_all = np.concatenate(xs_list) if xs_list else np.array([], dtype=float)
    y_all = np.concatenate(ys_list) if ys_list else np.array([], dtype=float)
    x_fin = x_all[np.isfinite(x_all)]
    y_fin = y_all[np.isfinite(y_all)]

    if x_fin.size >= 2 and float(np.max(x_fin)) > float(np.min(x_fin)):
        ax.spines["bottom"].set_bounds(float(np.min(x_fin)), float(np.max(x_fin)))
    if y_fin.size >= 2 and float(np.max(y_fin)) > float(np.min(y_fin)):
        ax.spines["left"].set_bounds(float(np.min(y_fin)), float(np.max(y_fin)))

    if rug:
        eff_lw = max(float(rug_lw), 0.25)
        if x_fin.size:
            x_trans = ax.get_xaxis_transform()
            ax.vlines(
                x_fin,
                0.0,
                rug_frac,
                transform=x_trans,
                colors=rug_color,
                linewidth=eff_lw,
                alpha=0.75,
                zorder=2,
            )
        if y_fin.size:
            y_trans = ax.get_yaxis_transform()
            ax.hlines(
                y_fin,
                0.0,
                rug_frac,
                transform=y_trans,
                colors=rug_color,
                linewidth=eff_lw,
                alpha=0.75,
                zorder=2,
            )

    return ax


def ghost_context(
    panels: list[tuple[Axes, np.ndarray | list[float], np.ndarray | list[float]]],
    *,
    ghost_color: str = "#D5DCE5",
    ghost_lw: float = 0.55,
    ghost_alpha: float = 0.80,
    zorder: int = 1,
) -> list[Line2D]:
    """Draw muted ghost copies of peer curves behind every small-multiple panel.

    Parameters
    ----------
    panels:
        Sequence of ``(ax, x, y)`` tuples (one per small-multiple panel). In
        each panel ``i``, all peer curves ``j != i`` are drawn in muted ink so
        every panel answers Tufte's "Compared to what?" directly.
    """
    eff_lw = max(float(ghost_lw), 0.25)
    drawn: list[Line2D] = []
    for idx, (ax, _, _) in enumerate(panels):
        for other_idx, (_, ox, oy) in enumerate(panels):
            if other_idx == idx:
                continue
            (line,) = ax.plot(
                ox,
                oy,
                color=ghost_color,
                linewidth=eff_lw,
                alpha=float(ghost_alpha),
                zorder=zorder,
                label="_figmint_ghost",
            )
            drawn.append(line)
    return drawn


def tufte_boxplot(
    ax: Axes,
    groups: list[np.ndarray | list[float]],
    *,
    positions: list[float] | None = None,
    labels: list[str] | None = None,
    color: str = "#1A1D21",
    colors: list[str] | None = None,
    show_points: bool = True,
    point_alpha: float = 0.24,
    point_size: float = 6.0,
    median_size: float = 16.0,
    lw: float = 0.85,
    jitter: float = 0.12,
    seed: int = 0,
) -> dict[str, list[object]]:
    """Draw a Tufte dot-dash distribution: thin whiskers, whitespace IQR gap, median dot."""
    n = len(groups)
    pos = [float(i) for i in range(n)] if positions is None else [float(p) for p in positions]
    eff_lw = max(float(lw), 0.25)
    rng = np.random.default_rng(seed)

    medians: list[object] = []
    whiskers: list[object] = []
    points: list[object] = []

    for idx, (raw, x0) in enumerate(zip(groups, pos, strict=True)):
        vals = np.asarray(raw, dtype=float)
        vals = vals[np.isfinite(vals)]
        if vals.size == 0:
            continue
        col = colors[idx % len(colors)] if colors else color
        q1, med, q3 = (float(v) for v in np.percentile(vals, [25, 50, 75]))
        iqr = q3 - q1
        lo_vals = vals[vals >= q1 - 1.5 * iqr]
        hi_vals = vals[vals <= q3 + 1.5 * iqr]
        w_lo = float(np.min(lo_vals)) if lo_vals.size else float(np.min(vals))
        w_hi = float(np.max(hi_vals)) if hi_vals.size else float(np.max(vals))

        if show_points:
            offsets = rng.uniform(-jitter, jitter, size=vals.size)
            sc = ax.scatter(
                x0 + offsets,
                vals,
                s=point_size,
                color=col,
                alpha=point_alpha,
                linewidths=0,
                zorder=2,
            )
            points.append(sc)

        # Lower and upper whisker dashes leaving a clean whitespace IQR gap
        (l1,) = ax.plot([x0, x0], [w_lo, q1], color=col, lw=eff_lw, solid_capstyle="butt", zorder=3)
        (l2,) = ax.plot([x0, x0], [q3, w_hi], color=col, lw=eff_lw, solid_capstyle="butt", zorder=3)
        whiskers.extend([l1, l2])

        # Crisp median dot
        dot = ax.scatter(
            [x0],
            [med],
            s=median_size,
            facecolor="white",
            edgecolor=col,
            linewidths=max(eff_lw, 0.9),
            zorder=4,
        )
        medians.append(dot)

    ax.set_xticks(pos)
    if labels is not None:
        ax.set_xticklabels(labels)
    return {"medians": medians, "whiskers": whiskers, "points": points}


def _relax_positions_pt(ys_pt: np.ndarray, min_sep_pt: float, y_lo: float, y_hi: float) -> np.ndarray:
    """Iteratively separate 1D label positions in point-space inside [y_lo, y_hi]."""
    ys = np.asarray(ys_pt, dtype=float).copy()
    n = ys.size
    if n <= 1:
        return np.clip(ys, y_lo, y_hi) if n == 1 else ys
    order = np.argsort(ys)
    sorted_y = ys[order]
    avail = max(y_hi - y_lo, 1.0)
    if (n - 1) * min_sep_pt > avail:
        sorted_y = np.linspace(y_lo, y_hi, n)
    else:
        for _ in range(250):
            moved = False
            for i in range(n - 1):
                gap = sorted_y[i + 1] - sorted_y[i]
                if gap < min_sep_pt:
                    shift = 0.5 * (min_sep_pt - gap) + 0.05
                    sorted_y[i] -= shift
                    sorted_y[i + 1] += shift
                    moved = True
            if sorted_y[0] < y_lo:
                sorted_y += y_lo - sorted_y[0]
            if sorted_y[-1] > y_hi:
                sorted_y -= sorted_y[-1] - y_hi
            sorted_y = np.clip(sorted_y, y_lo, y_hi)
            if not moved:
                break
    out = np.empty_like(ys)
    out[order] = sorted_y
    return out


def slopegraph(
    ax: Axes,
    left_values: list[float] | np.ndarray,
    right_values: list[float] | np.ndarray,
    labels: list[str],
    *,
    left_label: str = "Before",
    right_label: str = "After",
    highlight: str | set[str] | list[str] | None = None,
    highlight_color: str = "#C84B31",
    base_color: str = "#7C8796",
    fmt: str = "{:.0f}",
    fontsize: float | None = None,
    min_sep_pt: float = 8.0,
    show_delta: bool = False,
) -> dict[str, list[object]]:
    """Render a frameless Tufte slopegraph comparing paired measurements across categories."""
    lv = np.asarray(left_values, dtype=float)
    rv = np.asarray(right_values, dtype=float)
    if not (len(lv) == len(rv) == len(labels)):
        raise ValueError("left_values, right_values, and labels must have equal length")

    hl_set = (
        {highlight}
        if isinstance(highlight, str)
        else (set(highlight) if highlight is not None else set())
    )
    fs = float(fontsize) if fontsize is not None else _numeric_rc_font("legend.fontsize", 6.0)
    eff_min_sep = max(float(min_sep_pt), fs * 1.25)

    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.set_xticks([])
    ax.set_yticks([])

    all_v = np.concatenate([lv, rv])
    v_min, v_max = float(np.min(all_v)), float(np.max(all_v))
    v_span = max(v_max - v_min, 1.0)
    ax.set_xlim(-0.55, 1.82 if show_delta else 1.62)
    ax.set_ylim(v_min - 0.12 * v_span, v_max + 0.18 * v_span)

    # Subtle vertical reference rails at x=0 and x=1
    ax.plot([0.0, 0.0], [v_min, v_max], color="#DCE2EA", lw=0.5, zorder=1)
    ax.plot([1.0, 1.0], [v_min, v_max], color="#DCE2EA", lw=0.5, zorder=1)

    header_y = v_max + 0.08 * v_span
    ax.text(0.0, header_y, left_label, ha="center", va="bottom", fontsize=fs, fontweight="bold", color="#4B5563")
    ax.text(1.0, header_y, right_label, ha="center", va="bottom", fontsize=fs, fontweight="bold", color="#1A1D21")

    lines: list[object] = []
    for l_val, r_val, name in zip(lv, rv, labels, strict=True):
        is_hl = name in hl_set
        col = highlight_color if is_hl else base_color
        lw = 1.45 if is_hl else 0.70
        z = 4 if is_hl else 2
        (ln,) = ax.plot(
            [0.0, 1.0],
            [l_val, r_val],
            color=col,
            lw=lw,
            marker="o",
            ms=2.8 if is_hl else 2.2,
            mfc="white" if not is_hl else col,
            mec=col,
            mew=0.8,
            zorder=z,
        )
        lines.append(ln)

    # Relax left and right label coordinates in point-space so nothing overlaps
    fig = ax.figure
    fig.canvas.draw()
    dpi = float(fig.dpi)
    pt_per_px = 72.0 / dpi
    ax_bbox = ax.get_window_extent(fig.canvas.get_renderer())
    y_lo_pt = ax_bbox.y0 * pt_per_px + fs * 0.7
    y_hi_pt = ax_bbox.y1 * pt_per_px - fs * 2.0

    l_pts = np.array([ax.transData.transform((0.0, float(v)))[1] * pt_per_px for v in lv])
    r_pts = np.array([ax.transData.transform((1.0, float(v)))[1] * pt_per_px for v in rv])
    l_adj = _relax_positions_pt(l_pts, eff_min_sep, y_lo_pt, y_hi_pt)
    r_adj = _relax_positions_pt(r_pts, eff_min_sep, y_lo_pt, y_hi_pt)
    inv = ax.transData.inverted()

    texts: list[object] = []
    for l_val, r_val, name, lp, rp in zip(lv, rv, labels, l_adj, r_adj, strict=True):
        is_hl = name in hl_set
        col = highlight_color if is_hl else "#2B3036"
        weight = "bold" if is_hl else "normal"
        px_l = ax.transData.transform((0.0, float(l_val)))[0]
        px_r = ax.transData.transform((1.0, float(r_val)))[0]
        _, ly = inv.transform((px_l, lp / pt_per_px))
        _, ry = inv.transform((px_r, rp / pt_per_px))

        t_left = ax.text(
            -0.06,
            ly,
            fmt.format(l_val),
            ha="right",
            va="center",
            fontsize=fs,
            color="#5D6673" if not is_hl else col,
            fontweight=weight,
        )
        delta_str = ""
        if show_delta:
            diff = r_val - l_val
            sign = "+" if diff >= 0 else ""
            delta_str = f" ({sign}{fmt.format(diff)})"
        t_right = ax.text(
            1.06,
            ry,
            f"{fmt.format(r_val)}  {name}{delta_str}",
            ha="left",
            va="center",
            fontsize=fs,
            color=col,
            fontweight=weight,
        )
        texts.extend([t_left, t_right])

    return {"lines": lines, "texts": texts}


def sparkline(
    ax: Axes,
    x: np.ndarray | list[float],
    y: np.ndarray | list[float],
    *,
    label: str | None = None,
    color: str = "#1A1D21",
    lw: float = 0.85,
    normal_band: tuple[float, float] | None = None,
    band_color: str = "#E8EEF5",
    show_minmax: bool = True,
    end_color: str = "#C84B31",
    end_fmt: str = "{:.2f}",
    fontsize: float | None = None,
) -> dict[str, object]:
    """Render a frameless Tufte sparkline with optional normal band and endpoint readout."""
    xv = np.asarray(x, dtype=float)
    yv = np.asarray(y, dtype=float)
    fs = float(fontsize) if fontsize is not None else _numeric_rc_font("legend.fontsize", 6.0)
    eff_lw = max(float(lw), 0.25)

    ax.set_axis_off()
    x0, x1 = float(np.min(xv)), float(np.max(xv))
    x_span = max(x1 - x0, 1e-12)
    y0, y1 = float(np.min(yv)), float(np.max(yv))
    if normal_band is not None:
        y0 = min(y0, float(normal_band[0]))
        y1 = max(y1, float(normal_band[1]))
    y_span = max(y1 - y0, 1e-12)

    if normal_band is not None:
        ax.fill_between(
            [x0, x1],
            [float(normal_band[0]), float(normal_band[0])],
            [float(normal_band[1]), float(normal_band[1])],
            color=band_color,
            alpha=0.88,
            lw=0,
            zorder=0,
        )

    (line,) = ax.plot(xv, yv, color=color, lw=eff_lw, zorder=2)

    if show_minmax and yv.size >= 3:
        i_min = int(np.argmin(yv))
        i_max = int(np.argmax(yv))
        ax.scatter(
            [xv[i_min], xv[i_max]],
            [yv[i_min], yv[i_max]],
            s=8.0,
            color="#5D6673",
            zorder=3,
        )

    ax.scatter([xv[-1]], [yv[-1]], s=13.0, color=end_color, zorder=4)

    # Reserve subtle left label space and right numerical readout inside axes
    left_pad = 0.46 * x_span if label else 0.04 * x_span
    right_pad = 0.30 * x_span
    ax.set_xlim(x0 - left_pad, x1 + right_pad)
    ax.set_ylim(y0 - 0.22 * y_span, y1 + 0.22 * y_span)

    lbl_txt: Text | None = None
    if label:
        lbl_txt = ax.text(
            x0 - 0.06 * x_span,
            0.5 * (y0 + y1),
            label,
            ha="right",
            va="center",
            fontsize=fs,
            color="#2B3036",
        )
    end_txt = ax.text(
        x1 + 0.05 * x_span,
        float(yv[-1]),
        end_fmt.format(float(yv[-1])),
        ha="left",
        va="center",
        fontsize=fs,
        fontweight="bold",
        color=end_color,
    )
    return {"line": line, "label": lbl_txt, "end_text": end_txt}


def emphasize(
    ax: Axes,
    keep: str | tuple[str, ...] | list[str],
    *,
    dim_color: str = "#C2C9D2",
    dim_alpha: float = 0.45,
    dim_lw: float = 0.65,
    focus_lw: float | None = None,
) -> list[Line2D]:
    """De-emphasize background curves on ``ax`` so the focal series in ``keep`` pop.

    Returns the list of emphasized ``Line2D`` artists.
    """
    keep_set = {keep} if isinstance(keep, str) else set(keep)
    focused: list[Line2D] = []
    for line in ax.get_lines():
        lbl = str(line.get_label() or "")
        if not lbl or lbl.startswith("_"):
            continue
        if lbl in keep_set:
            if focus_lw is not None:
                line.set_linewidth(max(float(focus_lw), 0.25))
            line.set_zorder(max(line.get_zorder(), 4))
            focused.append(line)
        else:
            line.set_color(dim_color)
            line.set_alpha(float(dim_alpha))
            line.set_linewidth(max(float(dim_lw), 0.25))
            line.set_zorder(min(line.get_zorder(), 2))
    return focused
