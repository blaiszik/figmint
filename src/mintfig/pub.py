"""Publication tools: journal-ready plates, styling, annotation, export and preflight.

``import mintfig as mint`` keeps the top level for explaining a result; everything a
journal figure needs lives here, under ``mint.pub``::

    import mintfig as mint

    with mint.pub.use("nature"):
        fig, ax = mint.figure("nature", "single")
        ax.plot(x, y, label="model")
        mint.pub.direct_labels(ax)
        mint.pub.save_figure(fig, "figure1.pdf", journal="nature")

``preflight_pdf`` reads PDFs with ``pypdf``: ``pip install "mintfig[pub]"``.
"""

from __future__ import annotations

from .annotations import (
    despine,
    direct_labels,
    emphasize,
    ghost_context,
    place_labels,
    range_frame,
    scalebar,
    sig_bracket,
    slopegraph,
    sparkline,
    style_colorbar,
    style_heatmap,
    subtle_grid,
    tufte_boxplot,
    zoom_inset,
)
from .bundle import BundleResult, bundle_figure, to_publication
from .export import rasterize_heavy, save_figure
from .palettes import (
    BANNED_COLORMAPS,
    EDITORIAL_COLORMAPS,
    PALETTES,
    get_palette,
    register_colormaps,
    simulate_cvd,
)
from .plate import Plate, figure
from .preflight import CheckResult, PreflightReport, preflight_figure, preflight_pdf
from .proof import render_proof_sheet
from .runner import RunResult, run_script
from .specs import JOURNALS, MM_PER_INCH, JournalSpec, get_spec, in_to_mm, mm_to_in
from .style import apply, rc_params, resolved_font_name, use

__all__ = [
    "BANNED_COLORMAPS",
    "EDITORIAL_COLORMAPS",
    "JOURNALS",
    "MM_PER_INCH",
    "PALETTES",
    "BundleResult",
    "CheckResult",
    "JournalSpec",
    "Plate",
    "PreflightReport",
    "RunResult",
    "apply",
    "bundle_figure",
    "despine",
    "direct_labels",
    "emphasize",
    "figure",
    "get_palette",
    "get_spec",
    "ghost_context",
    "in_to_mm",
    "mm_to_in",
    "place_labels",
    "preflight_figure",
    "preflight_pdf",
    "range_frame",
    "rasterize_heavy",
    "rc_params",
    "register_colormaps",
    "render_proof_sheet",
    "resolved_font_name",
    "run_script",
    "save_figure",
    "scalebar",
    "sig_bracket",
    "simulate_cvd",
    "slopegraph",
    "sparkline",
    "style_colorbar",
    "style_heatmap",
    "subtle_grid",
    "to_publication",
    "tufte_boxplot",
    "use",
    "zoom_inset",
]
