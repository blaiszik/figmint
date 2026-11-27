"""Export utilities for journal-compliant figure output."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING

import matplotlib as mpl
from matplotlib.collections import PathCollection, PolyCollection, QuadMesh
from matplotlib.lines import Line2D

if TYPE_CHECKING:
    from matplotlib.artist import Artist
    from matplotlib.axes import Axes
    from matplotlib.figure import Figure

    from .specs import JournalSpec


def _iter_all_axes(fig: Figure) -> Iterator[Axes]:
    """Yield every Axes in *fig*, including nested inset/child axes."""
    seen: set[int] = set()
    stack: list[Axes] = list(fig.axes)
    while stack:
        ax = stack.pop(0)
        aid = id(ax)
        if aid in seen:
            continue
        seen.add(aid)
        yield ax
        for child in getattr(ax, "child_axes", ()):
            if id(child) not in seen:
                stack.append(child)


def _artist_vertex_count(artist: object) -> int:
    """Estimate the number of points or vertices carried by a Matplotlib artist."""
    if isinstance(artist, PathCollection):
        offsets = artist.get_offsets()
        n_offsets = len(offsets) if offsets is not None else 0
        paths = artist.get_paths()
        n_verts = sum(len(p.vertices) for p in paths) if paths else 0
        return max(n_offsets, n_verts)

    if isinstance(artist, QuadMesh):
        coords = artist.get_coordinates() if hasattr(artist, "get_coordinates") else None
        if coords is not None and coords.ndim >= 2:
            return int(coords.shape[0] * coords.shape[1])
        arr = artist.get_array()
        return int(arr.size) if arr is not None else 0

    if isinstance(artist, PolyCollection):
        paths = artist.get_paths()
        return sum(len(p.vertices) for p in paths) if paths else 0

    if isinstance(artist, Line2D):
        xdata = artist.get_xdata(orig=False)
        return len(xdata) if xdata is not None else 0

    return 0


def _rasterize_heavy_artists(fig: Figure, threshold: int) -> list[tuple[Artist, bool]]:
    """Rasterize dense artists and return ``(artist, previous_rasterized_state)`` pairs."""
    changed: list[tuple[Artist, bool]] = []
    for ax in _iter_all_axes(fig):
        for collection in ax.collections:
            if not collection.get_visible():
                continue
            if (
                isinstance(collection, (PathCollection, PolyCollection, QuadMesh))
                and _artist_vertex_count(collection) >= threshold
            ):
                changed.append((collection, bool(collection.get_rasterized())))
                collection.set_rasterized(True)

        for line in ax.lines:
            if not line.get_visible():
                continue
            if _artist_vertex_count(line) >= threshold:
                changed.append((line, bool(line.get_rasterized())))
                line.set_rasterized(True)
    return changed


def rasterize_heavy(
    fig: Figure,
    threshold: int = 10_000,
    dpi: int | None = None,
) -> int:
    """Selectively rasterize dense data artists while keeping text and axes vector.

    Scans ``PathCollection``, ``PolyCollection``, ``QuadMesh``, and ``Line2D``
    artists across all axes (including insets) and calls ``set_rasterized(True)``
    whenever an artist has at least ``threshold`` points or vertices. The change
    is permanent on the figure; :func:`save_figure` instead applies it only for
    the duration of the save.

    Parameters
    ----------
    fig:
        Matplotlib figure to inspect.
    threshold:
        Minimum point/vertex count to trigger selective rasterization.
    dpi:
        Optional DPI to assign on the figure for rasterized artists.

    Returns
    -------
    int
        Number of artists rasterized.
    """
    if dpi is not None:
        fig.set_dpi(dpi)
    return len(_rasterize_heavy_artists(fig, threshold))


def _panel_slug_for_axes(
    ax: Axes,
    fallback_index: int,
    slug_map: dict[int, str],
) -> str:
    """Resolve a deterministic Illustrator/Inkscape layer prefix for ``ax``."""
    key = getattr(ax, "_mintfig_panel_key", None)
    if key is not None and str(key).strip():
        return f"panel-{str(key).strip().lower()}"
    parent = getattr(ax, "_parent_axes", None)
    if parent is not None and id(parent) in slug_map:
        if getattr(ax, "_colorbar", None) is not None or ax.get_label() == "<colorbar>":
            return f"{slug_map[id(parent)]}/colorbar"
        return f"{slug_map[id(parent)]}/inset"
    if getattr(ax, "_colorbar", None) is not None or ax.get_label() == "<colorbar>":
        return f"colorbar-{fallback_index + 1}"
    letter = chr(ord("a") + fallback_index) if fallback_index < 26 else f"ax{fallback_index + 1}"
    return f"panel-{letter}"


def _apply_semantic_gids(fig: Figure) -> list[tuple[Artist, str | None]]:
    """Assign deterministic semantic SVG/PDF ``gid`` layers to untagged artists.

    Organizes exported vector files into hierarchical Illustrator/Inkscape groups
    (``panel-a/axes``, ``panel-a/data``, ``panel-a/annotations``, ``panel-a/labels``)
    without overwriting any caller-assigned or internal ``gid`` (such as
    ``mintfig-margin``). Returns ``(artist, previous_gid)`` pairs so callers can
    restore live figure state after saving.
    """
    changed: list[tuple[Artist, str | None]] = []
    used_gids: set[str] = set()

    # Reserve any pre-existing gids so new ones never collide.
    for existing in fig.findobj():
        gid = existing.get_gid()
        if gid:
            used_gids.add(str(gid))

    def _claim(base: str) -> str:
        if base not in used_gids:
            used_gids.add(base)
            return base
        idx = 2
        while f"{base}/{idx}" in used_gids:
            idx += 1
        name = f"{base}/{idx}"
        used_gids.add(name)
        return name

    def _tag(artist: Artist | None, base: str) -> None:
        if artist is None or artist.get_gid() is not None:
            return
        changed.append((artist, None))
        artist.set_gid(_claim(base))

    # Map figure-level panel labels first so `panel-a/labels` belongs cleanly to the panel tag.
    for txt in getattr(fig, "texts", ()):
        if getattr(txt, "_mintfig_panel_label", False):
            pkey = getattr(txt, "_mintfig_panel_key", None)
            if pkey is None:
                raw = txt.get_text().strip()
                if raw and len(raw) <= 3 and raw.isalnum():
                    pkey = raw.lower()
            if pkey is not None:
                _tag(txt, f"panel-{str(pkey).lower()}/labels")

    all_axes = list(_iter_all_axes(fig))
    slug_map: dict[int, str] = {}
    panel_idx = 0
    for ax in all_axes:
        is_aux = (
            getattr(ax, "_colorbar", None) is not None
            or ax.get_label() == "<colorbar>"
            or getattr(ax, "_parent_axes", None) is not None
        )
        slug = _panel_slug_for_axes(ax, panel_idx, slug_map)
        slug_map[id(ax)] = slug
        if not is_aux:
            panel_idx += 1

    for ax in all_axes:
        slug = slug_map[id(ax)]
        _tag(ax, f"{slug}/axes")

        # Data artists (lines, collections, images, non-annotation patches)
        for line in ax.lines:
            if getattr(line, "_mintfig_leader", False) or getattr(line, "_mintfig_annotation", False):
                _tag(line, f"{slug}/annotations")
            else:
                _tag(line, f"{slug}/data")
        for col in ax.collections:
            _tag(col, f"{slug}/data")
        for im in ax.images:
            _tag(im, f"{slug}/data")
        for patch in ax.patches:
            if patch is ax.patch:
                continue
            if getattr(patch, "_mintfig_annotation", False):
                _tag(patch, f"{slug}/annotations")
            else:
                _tag(patch, f"{slug}/data")

        # Annotations (in-axes text, callouts, legends)
        for txt in ax.texts:
            _tag(txt, f"{slug}/annotations")
        leg = ax.get_legend()
        if leg is not None:
            _tag(leg, f"{slug}/annotations")

        # Labels (title, xlabel, ylabel)
        if ax.title.get_text().strip():
            _tag(ax.title, f"{slug}/labels")
        if ax.xaxis.label.get_text().strip():
            _tag(ax.xaxis.label, f"{slug}/labels")
        if ax.yaxis.label.get_text().strip():
            _tag(ax.yaxis.label, f"{slug}/labels")

    return changed


def _resolve_save_spec(
    fig: Figure,
    journal: str | JournalSpec | None,
    spec: JournalSpec | None,
) -> JournalSpec | None:
    """Resolve the journal spec for :func:`save_figure` from ``journal``, ``spec``, or the figure tag."""
    from .specs import get_spec

    if journal is not None and spec is not None:
        resolved = get_spec(journal)
        if resolved != spec:
            raise ValueError(
                "save_figure() received conflicting journal= and spec= arguments; pass only one."
            )
        return resolved
    if journal is not None:
        return get_spec(journal)
    if spec is not None:
        return get_spec(spec)
    tag = getattr(fig, "_mintfig_journal", None)
    if isinstance(tag, str) and tag:
        try:
            return get_spec(tag)
        except ValueError:
            # Custom (unregistered) JournalSpec names cannot be looked up by name.
            return None
    return None


def save_figure(
    fig: Figure,
    path: str | Path,
    *,
    journal: str | JournalSpec | None = None,
    spec: JournalSpec | None = None,
    dpi: int | None = None,
    rasterize_above: int | None = 10_000,
    transparent: bool = False,
    lock_dimensions: bool = True,
    deterministic: bool = True,
) -> Path:
    """Save a figure with locked physical dimensions and editable vector fonts.

    Parameters
    ----------
    fig:
        Matplotlib figure to save.
    path:
        Destination file path (PDF, PNG, SVG, EPS, TIFF, etc.).
    journal:
        Journal name (e.g. ``"nature"``) or :class:`~mintfig.specs.JournalSpec`
        used to choose the default DPI.
    spec:
        Backward-compatible alias for ``journal`` accepting a
        :class:`~mintfig.specs.JournalSpec`.
    dpi:
        Explicit output resolution. Defaults to the journal's ``dpi_combo``.
        When neither ``journal`` nor ``spec`` is given, the journal tagged on
        the figure by :class:`~mintfig.Plate` / :func:`~mintfig.figure` is
        used; otherwise ``500``.
    rasterize_above:
        If positive, selectively rasterize data artists with at least this many
        points/vertices so dense plots produce compact vector PDFs. Each
        artist's previous rasterization state is restored after saving.
    transparent:
        Whether to save with a transparent background.
    lock_dimensions:
        When ``True`` (default), passes ``bbox_inches=None`` so the exported
        MediaBox matches ``fig.get_size_inches()`` exactly without drift.
    deterministic:
        When ``True`` (default), omit PDF/SVG creation timestamps and use a
        fixed SVG id salt so repeated saves of the same figure are
        byte-identical.

    Returns
    -------
    Path
        Path to the written file.
    """
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    resolved_spec = _resolve_save_spec(fig, journal, spec)
    effective_dpi = (
        dpi if dpi is not None else (resolved_spec.dpi_combo if resolved_spec is not None else 500)
    )

    suffix = out_path.suffix.lower()
    extra_kwargs: dict[str, object] = {}
    if suffix == ".pdf":
        metadata: dict[str, object] = {"Creator": "mintfig"}
        if deterministic:
            metadata["CreationDate"] = None
        extra_kwargs["metadata"] = metadata
    elif suffix == ".svg":
        metadata = {"Creator": "mintfig"}
        if deterministic:
            metadata["Date"] = None
        extra_kwargs["metadata"] = metadata
    elif suffix == ".png":
        extra_kwargs["metadata"] = {"Software": "mintfig"}

    bbox_inches = None if lock_dimensions else "tight"

    rc_overrides: dict[str, object] = {
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
        "svg.fonttype": "none",
    }
    if deterministic and mpl.rcParams.get("svg.hashsalt") is None:
        rc_overrides["svg.hashsalt"] = "mintfig"

    changed: list[tuple[Artist, bool]] = []
    gid_changed: list[tuple[Artist, str | None]] = []
    try:
        if rasterize_above is not None and rasterize_above > 0:
            changed = _rasterize_heavy_artists(fig, rasterize_above)
        if suffix in {".svg", ".pdf"}:
            gid_changed = _apply_semantic_gids(fig)
        with mpl.rc_context(rc_overrides):
            fig.savefig(
                out_path,
                dpi=effective_dpi,
                bbox_inches=bbox_inches,
                transparent=transparent,
                **extra_kwargs,
            )
    finally:
        for artist, prev_gid in gid_changed:
            artist.set_gid(prev_gid)
        for artist, previous in changed:
            artist.set_rasterized(previous)

    return out_path
