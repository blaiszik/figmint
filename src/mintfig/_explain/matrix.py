"""matrix() annotated heat-table form for mint.explain."""

from __future__ import annotations

import math
import numbers
from collections.abc import Callable, Mapping, Sequence
from typing import Any

import numpy as np
from matplotlib.axes import Axes
from matplotlib.colors import to_rgb
from matplotlib.transforms import Bbox

from ..themes import (
    MINTFIG_THEME,
)
from .core import (
    MAX_HIGHLIGHTS,
    MAX_MATRIX_COLS,
    MAX_MATRIX_ROWS,
    ExplainError,
    Panel,
    _bare_axes,
    _base_spec,
    _Ctx,
    _diff_with_unit,
    _fit_axes,
    _formatter,
    _guarded,
    _jsonable,
    _labels_collide,
    _plain,
    _relative_luminance,
    _to_float,
    _with_unit,
)

# --------------------------------------------------------------------------- #
# matrix
# --------------------------------------------------------------------------- #

_SEQ_STOPS = MINTFIG_THEME.seq_stops
_DIV_LOW = MINTFIG_THEME.div_low
_DIV_HIGH = MINTFIG_THEME.div_high
_DIV_MID = MINTFIG_THEME.div_mid


def _ramp(stops: Sequence[str], t: np.ndarray) -> np.ndarray:
    colors = np.array([to_rgb(c) for c in stops])
    pos = np.clip(t, 0.0, 1.0) * (len(stops) - 1)
    lower = np.floor(pos).astype(int).clip(0, len(stops) - 2)
    frac = (pos - lower)[..., None]
    return colors[lower] * (1 - frac) + colors[lower + 1] * frac


def _matrix_highlight(
    highlight: object, row_names: list[str], col_names: list[str]
) -> tuple[list[tuple[int, int]], list[int], list[int]]:
    """Cells ``(row, col)``, whole rows and whole columns named by ``matrix(highlight=...)``."""
    hint = (
        'Use highlight=("row name", "col name") for one cell, a list of such pairs, or a row '
        'or column name alone, e.g. highlight="Rust" or highlight=[("Rust", "perf"), "Go"].'
    )
    cells: list[tuple[int, int]] = []
    hl_rows: list[int] = []
    hl_cols: list[int] = []
    if highlight is None:
        return cells, hl_rows, hl_cols

    def _name(entry: object) -> None:
        key = str(entry)
        if key not in row_names and key not in col_names:
            raise ExplainError(
                f"matrix(highlight) names {key!r}, which is neither a row nor a column.",
                fix_hint=hint,
            )
        if key in row_names:
            hl_rows.append(row_names.index(key))
        if key in col_names:
            hl_cols.append(col_names.index(key))

    def _cell(pair: Sequence[Any]) -> None:
        r_name, c_name = str(pair[0]), str(pair[1])
        if r_name not in row_names or c_name not in col_names:
            raise ExplainError(
                f"matrix(highlight) cell ({r_name!r}, {c_name!r}) is not in rows/cols.",
                fix_hint="Use (row name, column name) pairs exactly as given. " + hint,
            )
        cells.append((row_names.index(r_name), col_names.index(c_name)))

    def _is_pair(entry: object) -> bool:
        return (
            isinstance(entry, (tuple, list))
            and len(entry) == 2
            and not any(isinstance(e, (list, tuple)) for e in entry)
        )

    if isinstance(highlight, (str, numbers.Number)):
        _name(highlight)
    elif (
        _is_pair(highlight)
        and str(highlight[0]) in row_names  # type: ignore[index]
        and str(highlight[1]) in col_names  # type: ignore[index]
    ):
        _cell(highlight)  # type: ignore[arg-type]
    elif isinstance(highlight, (list, tuple)):
        for entry in highlight:
            if _is_pair(entry):
                _cell(entry)  # type: ignore[arg-type]
            elif isinstance(entry, (str, numbers.Number)):
                _name(entry)
            else:
                raise ExplainError(
                    f"matrix(highlight) entry {entry!r} is not a (row, col) pair or a name.",
                    fix_hint=hint,
                )
    else:
        raise ExplainError(
            f"matrix(highlight) must be a pair, a list of pairs or a name, got "
            f"{type(highlight).__name__}.",
            fix_hint=hint,
        )
    total = len(cells) + len(set(hl_rows)) + len(set(hl_cols))
    if total > MAX_HIGHLIGHTS:
        raise ExplainError(
            f"matrix(highlight) marks {total} cells/rows/columns; more than {MAX_HIGHLIGHTS} "
            "highlights nothing.",
            fix_hint=f"At most {MAX_HIGHLIGHTS} highlights: outline only the cells, rows or "
            "columns the takeaway names; the numbers in every cell carry the rest.",
            rule="too_many_highlights",
        )
    return cells, sorted(set(hl_rows)), sorted(set(hl_cols))


def _matrix_outlier(
    body: np.ndarray, lo: float, hi: float
) -> tuple[tuple[int, int], tuple[float, float], str] | None:
    """The single cell furthest below (or above) the rest of both its row and its column.

    A cell stands out when it departs from the additive pattern of the grid (its row
    mean + column mean - grand mean) by at least a tenth of the value range and three
    times the typical departure, and is the lowest (highest) of its row and of its
    column; the gaps are to the next-lowest (next-highest) there. Needs 3+ rows and
    columns. A smooth gradient has no outlier, only a corner.
    """
    n_rows, n_cols = body.shape
    ok = np.isfinite(body)
    if n_rows < 3 or n_cols < 3 or ok.sum() < 6:
        return None
    with np.errstate(all="ignore"):
        grand = float(np.nanmean(body))
        fitted = (
            np.nanmean(body, axis=1)[:, None] + np.nanmean(body, axis=0)[None, :] - grand
        )
    resid = np.where(ok, body - fitted, np.nan)
    flat = np.abs(resid[ok])
    order = np.argsort(-np.nan_to_num(np.abs(resid), nan=-1.0), axis=None)
    i, j = np.unravel_index(int(order[0]), body.shape)
    size = abs(float(resid[i, j]))
    typical = float(np.median(np.sort(flat)[:-1])) if flat.size > 1 else 0.0
    if size < 0.1 * ((hi - lo) or 1.0) or size < 3.0 * typical:
        return None
    v = float(body[i, j])
    row = np.delete(body[i], j)
    col = np.delete(body[:, j], i)
    row, col = row[np.isfinite(row)], col[np.isfinite(col)]
    if row.size < 2 or col.size < 2:
        return None
    if resid[i, j] < 0:
        word, gaps = "below", (float(row.min()) - v, float(col.min()) - v)
    else:
        word, gaps = "above", (v - float(row.max()), v - float(col.max()))
    if min(gaps) <= 0:  # not the extreme of both its row and its column
        return None
    return (int(i), int(j)), gaps, word


@_guarded("matrix")
def matrix(
    values: Sequence[Sequence[float | None]] | Sequence[Mapping[str, Any]],
    *,
    rows: Sequence[str] | str | None = None,
    cols: Sequence[str] | str | None = None,
    value: str | None = None,
    title: str | None = None,
    label: str | None = None,
    unit: str | None = None,
    diverging: bool = False,
    center: float = 0.0,
    triangle: str | None = None,
    mask_diagonal: bool = False,
    highlight: Any = None,
    fmt: str | None = None,
) -> Panel:
    """How do two categorical dimensions interact? A heat table: colour for the pattern, a number in every cell.

    ``values[i][j]`` belongs to ``rows[i]`` and ``cols[j]``; a wide pandas
    DataFrame supplies ``rows`` and ``cols`` from its index and columns. For
    long/row-shaped data (``list[dict]`` or tidy DataFrame), pass column names
    ``rows="row_col", cols="col_col", value="val_col"`` to pivot automatically.
    One hue runs light to dark; ``diverging=True`` uses two hues around ``center``
    for signed data. ``highlight`` outlines cells: one ``(row, col)`` pair, a list
    of pairs, or a row or column name for the whole strip.
    """
    from .._tabular import resolve_matrix_table

    pivoted = resolve_matrix_table(values, rows_arg=rows, cols_arg=cols, value_col=value)
    if pivoted is not None:
        values, rows, cols = pivoted
    else:
        is_frame = hasattr(values, "columns") and hasattr(values, "index")
        if is_frame:
            rows = [str(r) for r in values.index] if rows is None else rows  # type: ignore[attr-defined]
            cols = [str(c) for c in values.columns] if cols is None else cols  # type: ignore[attr-defined]
            values = values.to_numpy().tolist() if hasattr(values, "to_numpy") else values  # type: ignore[attr-defined]
    if rows is None or cols is None:
        raise ExplainError(
            "matrix() needs rows= and cols= to name its rows and columns.",
            fix_hint='Pass rows=["r1", ...] and cols=["c1", ...] aligned with values, or pass a '
            "pandas DataFrame (its index and columns are used).",
        )
    if isinstance(rows, (str, bytes)) or isinstance(cols, (str, bytes)):
        raise ExplainError(
            "matrix(rows) and matrix(cols) must be lists of names.",
            fix_hint='e.g. rows=["Python", "Go"], cols=["bugfix", "docs"].',
        )
    try:
        grid = np.array(
            [
                [np.nan if v is None else _to_float(v, "matrix(values)") for v in row]
                for row in values
            ],
            dtype=float,
        )
    except (TypeError, ValueError) as exc:
        raise ExplainError(
            "matrix(values) must be a rectangular list of rows of numbers.",
            fix_hint="Pass values[i][j] for rows[i] and cols[j]; use None for empty cells.",
        ) from exc
    row_names, col_names = [str(r) for r in rows], [str(c) for c in cols]
    if grid.ndim != 2 or grid.shape != (len(row_names), len(col_names)):
        raise ExplainError(
            f"matrix(values) has shape {grid.shape} but there are {len(row_names)} rows and "
            f"{len(col_names)} cols.",
            fix_hint="values must have one inner list per row, each with one number per column.",
        )
    if len(row_names) > MAX_MATRIX_ROWS or len(col_names) > MAX_MATRIX_COLS:
        raise ExplainError(
            f"matrix() got {len(row_names)}x{len(col_names)} cells; beyond "
            f"{MAX_MATRIX_ROWS}x{MAX_MATRIX_COLS} the numbers stop being readable at chat size.",
            fix_hint=f"matrix() takes at most {MAX_MATRIX_ROWS} rows and {MAX_MATRIX_COLS} "
            "columns (swap rows and cols if only the columns are over): aggregate, keep the "
            "rows/columns the takeaway is about, or split into two matrix() panels.",
            rule="too_many_items",
        )
    if triangle is not None:
        tri_norm = str(triangle).strip().lower()
        if tri_norm not in {"lower", "upper"}:
            raise ExplainError(
                f"matrix(triangle={triangle!r}) must be 'lower', 'upper', or None.",
                fix_hint="Use triangle='lower' or triangle='upper' for symmetric matrices.",
            )
        if len(row_names) != len(col_names):
            raise ExplainError(
                f"matrix(triangle={tri_norm!r}) requires a square matrix, got {len(row_names)}x{len(col_names)}.",
                fix_hint="Drop triangle= for rectangular matrices.",
            )
        triangle = tri_norm
    if mask_diagonal and len(row_names) != len(col_names):
        raise ExplainError(
            f"matrix(mask_diagonal=True) requires a square matrix, got {len(row_names)}x{len(col_names)}.",
            fix_hint="Drop mask_diagonal=True for rectangular matrices.",
        )

    n_r, n_c = grid.shape
    hidden_mask = np.zeros((n_r, n_c), dtype=bool)
    if triangle == "lower":
        hidden_mask[np.triu_indices(n_r, k=1)] = True
    elif triangle == "upper":
        hidden_mask[np.tril_indices(n_r, k=-1)] = True
    diag_mask = np.eye(n_r, n_c, dtype=bool) if mask_diagonal else np.zeros((n_r, n_c), dtype=bool)
    active_mask = ~(hidden_mask | diag_mask)

    visible_grid = np.where(active_mask, grid, np.nan)
    finite = visible_grid[np.isfinite(visible_grid)]
    if finite.size == 0:
        raise ExplainError("matrix(values) has no finite visible cells.", fix_hint="Pass numbers.")
    cells, hl_rows, hl_cols = _matrix_highlight(highlight, row_names, col_names)

    fmt_fn = _formatter(list(finite), fmt, unit=unit)
    lo, hi = float(finite.min()), float(finite.max())

    square = row_names == col_names and len(row_names) > 1
    diag = np.diag(grid) if square else np.empty(0)
    # A constant diagonal (a correlation matrix's 1s) says nothing: leave it out of
    # highest/lowest and the means, and say so once.
    drop_diag = bool(
        square
        and (
            mask_diagonal
            or (np.isfinite(diag).all() and np.all(diag == diag[0]) and grid.size > diag.size)
        )
    )
    body = grid.copy()
    if drop_diag:
        np.fill_diagonal(body, np.nan)

    def _cell_text(at: tuple[int, int], source: np.ndarray = grid) -> str:
        return (
            f"{row_names[at[0]]} \N{MULTIPLICATION SIGN} {col_names[at[1]]} = "
            f"{_with_unit(fmt_fn(float(source[at])), unit)}"
        )

    hi_at = np.unravel_index(int(np.nanargmax(body)), grid.shape)
    lo_at = np.unravel_index(int(np.nanargmin(body)), grid.shape)
    facts = [f"highest: {_cell_text(hi_at)}", f"lowest: {_cell_text(lo_at)}"]
    if drop_diag:
        if mask_diagonal:
            facts.append("diagonal masked from colour scale and extrema")
        else:
            one = _formatter([float(diag[0])], fmt, unit=unit)(float(diag[0]))
            facts.append(f"diagonal is {_with_unit(one, unit)} throughout (excluded)")
    with np.errstate(all="ignore"):
        row_means = np.array(
            [float(np.mean(r[np.isfinite(r)])) if np.isfinite(r).any() else np.nan for r in body]
        )
        col_means = np.array(
            [
                float(np.mean(c[np.isfinite(c)])) if np.isfinite(c).any() else np.nan
                for c in body.T
            ]
        )
    symmetric = square and bool(np.allclose(grid, grid.T, equal_nan=True))
    shown_means = [*row_means, *([] if symmetric else col_means)]
    mean_fmt = _formatter([v for v in shown_means if math.isfinite(v)], fmt, unit=unit)

    def _mean_fact(which: str, means: np.ndarray, labels_: Sequence[str]) -> None:
        if np.isfinite(means).sum() < 2:
            return
        for word, pick in (("highest", np.nanargmax), ("lowest", np.nanargmin)):
            at = int(pick(means))
            facts.append(
                f"{word} {which} mean: {labels_[at]} "
                f"({_with_unit(mean_fmt(float(means[at])), unit)})"
            )

    if np.isfinite(row_means).sum() >= 2:
        _mean_fact("row", row_means, row_names)
    else:
        facts.append(
            f"highest row mean: {row_names[int(np.nanargmax(row_means))]} "
            f"({_with_unit(mean_fmt(float(np.nanmax(row_means))), unit)})"
        )
    if not symmetric:  # a symmetric matrix's column means are its row means
        _mean_fact("column", col_means, col_names)
    outlier = _matrix_outlier(body, lo, hi)
    if outlier is not None:
        at, gaps, word = outlier
        gap_fmt = _formatter(list(gaps), fmt, unit=unit)
        row_gap, col_gap = (_diff_with_unit(gap_fmt(g), unit) for g in gaps)
        nxt = "next-lowest" if word == "below" else "next-highest"
        facts.append(
            f"outlier: {_cell_text(at)}, {row_gap} {word} the {nxt} in its row and "
            f"{col_gap} {word} the {nxt} in its column"
        )

    def _same(a: tuple[int, int], b: tuple[int, int]) -> bool:
        cells_match = a == b or (symmetric and a == (b[1], b[0]))
        return cells_match and grid[a] == grid[b]

    if square:
        off = grid.copy()
        np.fill_diagonal(off, np.nan)
        if np.isfinite(off).any():
            at = np.unravel_index(int(np.nanargmax(off)), off.shape)
            if not (drop_diag and _same(at, hi_at)):  # already stated as "highest"
                facts.append(f"largest off-diagonal: {_cell_text(at, off)}")
            if diverging:
                # Signed data: the strongest relationship may be negative. A symmetric
                # matrix names each pair once (upper triangle).
                mag = np.abs(off - center)
                if symmetric:
                    mag[np.tril_indices_from(mag)] = np.nan
                if np.isfinite(mag).any():
                    st = np.unravel_index(int(np.nanargmax(mag)), mag.shape)
                    if not _same(st, at):
                        facts.append(f"strongest off-diagonal: {_cell_text(st, off)}")
    # Every highlighted cell's value; for a highlighted row or column, its strongest cell.
    for cell in cells:
        facts.append(_cell_text(cell))

    def _strongest(sel: np.ndarray, where: str, to_cell: Callable[[int], tuple[int, int]]) -> None:
        if not np.isfinite(sel).any():
            return
        score = np.abs(sel - center) if diverging else sel
        facts.append(f"{where}: strongest {_cell_text(to_cell(int(np.nanargmax(score))))}")

    for r in hl_rows:
        row = grid[r].copy()
        if square:
            row[r] = np.nan
        _strongest(row, f"{row_names[r]} row", lambda k, r=r: (r, k))
    for c in hl_cols:
        if square and symmetric and c in hl_rows:
            continue  # a symmetric matrix's row already said it
        col = grid[:, c].copy()
        if square:
            col[c] = np.nan
        _strongest(col, f"{col_names[c]} column", lambda k, c=c: (k, c))
    empty = int((active_mask & ~np.isfinite(grid)).sum())
    if empty:
        active_total = int(active_mask.sum())
        facts.append(f"{empty} of {active_total} cells empty (no value)")
    longest = max(len(fmt_fn(float(v))) for v in finite)

    def _draw(ctx: _Ctx, ax: Axes) -> None:
        sz = ctx.sizes
        theme = ctx.theme
        n_rows, n_cols = grid.shape
        if diverging:
            reach = max(hi - center, center - lo) or 1.0
            t = (visible_grid - center) / reach  # -1 .. 1
            rgb = np.where(
                (t < 0)[..., None],
                _ramp((*theme.div_low, theme.div_mid), 1.0 + np.nan_to_num(t)),
                _ramp((theme.div_mid, *theme.div_high), np.nan_to_num(t)),
            )
        else:
            t = (visible_grid - lo) / ((hi - lo) or 1.0)
            rgb = _ramp(theme.seq_stops, np.nan_to_num(t))
        bg_rgb = np.array(to_rgb(theme.background))
        empty_rgb = 0.85 * bg_rgb + 0.15 * np.array(to_rgb(theme.context_fill))
        rgb = np.where(np.isfinite(visible_grid)[..., None], rgb, empty_rgb)
        rgb = np.where(hidden_mask[..., None], bg_rgb, rgb)

        _bare_axes(ax)
        ax.imshow(
            rgb,
            aspect="auto",
            interpolation="nearest",
            zorder=1,
            extent=(-0.5, n_cols - 0.5, n_rows - 0.5, -0.5),
        )
        divider_col = theme.ink if theme.sketch is not None else theme.background
        divider_lw = 0.8 if theme.sketch is not None else 1.6
        if triangle is None or theme.sketch is None:
            ax.hlines(
                np.arange(n_rows + 1) - 0.5,
                -0.5,
                n_cols - 0.5,
                color=divider_col,
                linewidth=divider_lw,
                zorder=2,
            )
            ax.vlines(
                np.arange(n_cols + 1) - 0.5,
                -0.5,
                n_rows - 0.5,
                color=divider_col,
                linewidth=divider_lw,
                zorder=2,
            )
        ax.set_xlim(-0.5, n_cols - 0.5)
        ax.set_ylim(n_rows - 0.5, -0.5)
        if triangle == "lower":
            ax.xaxis.tick_bottom()
        else:
            ax.xaxis.tick_top()
        ax.set_xticks(range(n_cols), [_plain(c, theme) for c in col_names])
        ax.set_yticks(range(n_rows), [_plain(r, theme) for r in row_names])
        ax.tick_params(length=0, labelsize=sz.small, labelcolor=theme.ink, pad=3)
        light_ground = _relative_luminance(theme.background) > 0.5
        light_fg = "#FFFFFF" if light_ground else theme.ink
        dark_fg = theme.ink if light_ground else theme.background
        for (i, j), cell_val in np.ndenumerate(grid):
            if hidden_mask[i, j]:
                continue
            if diag_mask[i, j] or not math.isfinite(cell_val):
                note = ax.text(
                    j,
                    i,
                    "\N{EM DASH}",
                    ha="center",
                    va="center",
                    fontsize=sz.small,
                    color=theme.muted,
                    zorder=3,
                )
                note._mintfig_heatmap_text = True  # type: ignore[attr-defined]
                continue
            dark = (
                _relative_luminance(
                    "#{:02X}{:02X}{:02X}".format(*(round(c * 255) for c in rgb[i, j]))
                )
                < 0.36
            )
            note = ax.text(
                j,
                i,
                _plain(fmt_fn(float(cell_val)), theme),
                ha="center",
                va="center",
                fontsize=sz.small,
                color=light_fg if dark else dark_fg,
                zorder=3,
            )
            note._mintfig_heatmap_text = True  # type: ignore[attr-defined]
        strips = [
            *((i, j, i, j) for i, j in cells),
            *((i, 0, i, n_cols - 1) for i in hl_rows),
            *((0, j, n_rows - 1, j) for j in hl_cols),
        ]
        for i in hl_rows:
            ax.get_yticklabels()[i].set_fontweight("bold")
        for j in hl_cols:
            ax.get_xticklabels()[j].set_fontweight("bold")
        for i0, j0, i1, j1 in strips:
            ax.plot(
                [j0 - 0.5, j1 + 0.5, j1 + 0.5, j0 - 0.5, j0 - 0.5],
                [i0 - 0.5, i0 - 0.5, i1 + 0.5, i1 + 0.5, i0 - 0.5],
                color=theme.ink,
                linewidth=1.6 * sz.scale,
                zorder=4,
                solid_joinstyle="miter",
                clip_on=False,
                label="_cell",
            )

    def _check_fit(ctx: _Ctx, ax: Axes) -> None:
        cell_pt = (
            ax.get_window_extent(ctx.fig.canvas.get_renderer()).width
            * ctx.pt_per_px
            / grid.shape[1]
        )
        need_pt = longest * ctx.sizes.small * 0.6 + 3.0
        if cell_pt < need_pt:
            raise ExplainError(
                f"matrix() cells are {cell_pt:.0f} pt wide but the numbers need about {need_pt:.0f} pt.",
                fix_hint="Give the matrix a full-width row, swap rows and cols so fewer run "
                "across, shorten the numbers with fmt, or cut columns.",
                rule="matrix_cells_too_small",
            )

    def _draw_and_check(ctx: _Ctx, ax: Axes) -> Callable[[], None]:
        _draw(ctx, ax)
        return lambda: _check_fit(ctx, ax)

    def _headers(ctx: _Ctx, ax: Axes, rect: Bbox) -> list[tuple[Axes, Bbox]]:
        """Column headers must not touch: wrap long ones to two lines, else refuse.

        Runs between drawing and the final fit, on the axes at its final width.
        """
        _fit_axes(ctx.fig, ax, rect)
        renderer = ctx.fig.canvas.get_renderer()
        gap = 0.35 * ctx.sizes.small / ctx.pt_per_px

        def _collide() -> bool:
            boxes = [t.get_window_extent(renderer) for t in ax.get_xticklabels() if t.get_text()]
            return _labels_collide([(0.0, b) for b in boxes], True, gap)

        if not _collide():
            return [(ax, rect)]
        cell_pt = ax.get_window_extent(renderer).width * ctx.pt_per_px / grid.shape[1]
        wrapped: list[str] = []
        for name in col_names:
            words = name.split()
            if len(words) < 2 or ctx.measure.width_pt(name, ctx.sizes.small) <= cell_pt:
                wrapped.append(name)
                continue
            splits = [(" ".join(words[:i]), " ".join(words[i:])) for i in range(1, len(words))]
            best = min(
                splits,
                key=lambda pair: max(ctx.measure.width_pt(p, ctx.sizes.small) for p in pair),
            )
            wrapped.append("\n".join(best))
        ax.set_xticks(range(len(col_names)), [_plain(c, ctx.theme) for c in wrapped])
        for j in hl_cols:
            ax.get_xticklabels()[j].set_fontweight("bold")
        for header in ax.get_xticklabels():
            header.set_linespacing(1.05)
        if _collide():
            raise ExplainError(
                f"matrix() column headers overlap: {grid.shape[1]} columns of about "
                f"{cell_pt:.0f} pt cannot hold names such as "
                f"{max(col_names, key=len)!r}.",
                fix_hint='Give the matrix a wider cell with layout= (e.g. layout=[["a"], '
                '["b", "c"]] for a full-width row), shorten the column names, or swap rows '
                "and cols so the long names run down the side.",
                rule="matrix_cells_too_small",
            )
        return [(ax, rect)]

    return Panel(
        kind="matrix",
        title=title,
        label=label,
        unit=unit,
        spec=_base_spec(
            title,
            label,
            unit,
            values=[[None if not math.isfinite(v) else float(v) for v in row] for row in grid],
            rows=row_names,
            cols=col_names,
            diverging=diverging or None,
            center=center if diverging else None,
            triangle=triangle,
            mask_diagonal=mask_diagonal or None,
            highlight=_jsonable(highlight) if highlight is not None else None,
            fmt=fmt,
        ),
        facts=facts,
        describe=(
            f"Heat table of {label or 'values'}"
            + (f" ({unit})" if unit else "")
            + f", {len(row_names)} rows by {len(col_names)} columns, a number in every cell"
        ),
        _height_mm=lambda _w, _m, _s, _t: 6.2 * len(row_names) + 6.0,
        _min_height_mm=lambda _w, _m, _s, _t: 5.0 * len(row_names) + 6.0,
        _draw=_draw_and_check,
        _frames=_headers,
    )
