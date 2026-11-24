"""Journal physical specifications for publication-ready scientific figures."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

MM_PER_INCH: float = 25.4


def mm_to_in(mm: float) -> float:
    """Convert millimeters to inches."""
    return float(mm) / MM_PER_INCH


def in_to_mm(inches: float) -> float:
    """Convert inches to millimeters."""
    return float(inches) * MM_PER_INCH


@dataclass(frozen=True)
class JournalSpec:
    """Immutable physical, typographic, and export specification for a journal."""

    name: str
    display_name: str
    widths_mm: dict[str, float]
    max_height_mm: float
    max_page_height_mm: float
    font_family: tuple[str, ...]
    font_min_pt: float
    font_max_pt: float
    body_pt: float
    tick_pt: float
    legend_pt: float
    panel_label_pt: float
    panel_label_case: Literal["lower", "upper"]
    panel_label_weight: str = "bold"
    axes_linewidth_pt: float = 0.5
    data_linewidth_pt: float = 0.9
    min_linewidth_pt: float = 0.25
    tick_length_pt: float = 2.5
    dpi_photo: int = 300
    dpi_combo: int = 500
    dpi_line: int = 1000
    default_palette: str = "nature"
    # Empty by default so custom JournalSpec instances do not inherit a
    # verification or version claim from built-in publisher presets.
    spec_version: str = ""
    # ISO date the spec was last checked against the publisher's guidelines;
    # empty means unverified (custom specs must not inherit a verification claim).
    last_verified: str = ""
    source_url: str = ""

    def resolve_width_mm(self, width: str | float) -> float:
        """Resolve a column preset name or explicit positive millimeter width."""
        if isinstance(width, str):
            key = width.strip().lower()
            lookup = {k.lower(): v for k, v in self.widths_mm.items()}
            if key not in lookup:
                valid = ", ".join(sorted(self.widths_mm.keys()))
                raise ValueError(
                    f"Unknown width preset {width!r} for {self.display_name}. "
                    f"Valid presets: {valid}"
                )
            return float(lookup[key])
        if isinstance(width, bool) or not isinstance(width, (int, float)):
            raise TypeError(
                f"width must be a preset name (str) or positive float in mm, got {type(width).__name__}"
            )
        val = float(width)
        if not math.isfinite(val) or val <= 0.0:
            raise ValueError(f"width must be a finite positive number in mm, got {width!r}")
        return val


JOURNALS: dict[str, JournalSpec] = {
    "nature": JournalSpec(
        name="nature",
        display_name="Nature Portfolio",
        widths_mm={
            "single": 89.0,
            "mid": 120.0,
            "1.5col": 120.0,
            "double": 183.0,
            "full": 183.0,
        },
        max_height_mm=170.0,
        max_page_height_mm=247.0,
        font_family=("Helvetica", "Arial", "Liberation Sans", "DejaVu Sans"),
        font_min_pt=5.0,
        font_max_pt=7.0,
        body_pt=6.5,
        tick_pt=6.0,
        legend_pt=6.0,
        panel_label_pt=8.0,
        panel_label_case="lower",
        dpi_photo=300,
        dpi_combo=500,
        dpi_line=1000,
        default_palette="nature",
        spec_version="2025.1",
        last_verified="2026-11-23",
        source_url="https://www.nature.com/nature/for-authors/final-submission",
    ),
    "science": JournalSpec(
        name="science",
        display_name="Science (AAAS)",
        widths_mm={
            "single": 55.0,
            "double": 120.0,
            "2col": 120.0,
            "full": 184.0,
            "3col": 184.0,
        },
        max_height_mm=180.0,
        max_page_height_mm=230.0,
        font_family=("Helvetica", "Arial", "Liberation Sans", "DejaVu Sans"),
        font_min_pt=6.0,
        font_max_pt=8.0,
        body_pt=7.0,
        tick_pt=6.0,
        legend_pt=6.5,
        panel_label_pt=8.5,
        panel_label_case="upper",
        dpi_photo=300,
        dpi_combo=600,
        dpi_line=1200,
        default_palette="science",
        spec_version="2025.1",
        last_verified="2026-11-23",
        source_url="https://www.science.org/content/page/instructions-preparing-revised-manuscript",
    ),
    "science_advances": JournalSpec(
        name="science_advances",
        display_name="Science Advances",
        widths_mm={
            "single": 84.0,
            "mid": 120.0,
            "double": 175.0,
            "full": 175.0,
        },
        max_height_mm=180.0,
        max_page_height_mm=230.0,
        font_family=("Helvetica", "Arial", "Liberation Sans", "DejaVu Sans"),
        font_min_pt=6.0,
        font_max_pt=8.0,
        body_pt=7.0,
        tick_pt=6.0,
        legend_pt=6.5,
        panel_label_pt=8.5,
        panel_label_case="upper",
        dpi_photo=300,
        dpi_combo=600,
        dpi_line=1200,
        default_palette="science",
        spec_version="2025.1",
        last_verified="2026-11-23",
        source_url="https://www.science.org/content/page/science-advances-information-authors",
    ),
    "cell": JournalSpec(
        name="cell",
        display_name="Cell Press",
        widths_mm={
            "single": 85.0,
            "mid": 114.0,
            "1.5col": 114.0,
            "double": 174.0,
            "full": 174.0,
        },
        max_height_mm=200.0,
        max_page_height_mm=230.0,
        font_family=("Helvetica", "Arial", "Liberation Sans", "DejaVu Sans"),
        font_min_pt=6.0,
        font_max_pt=8.0,
        body_pt=7.0,
        tick_pt=6.0,
        legend_pt=6.5,
        panel_label_pt=8.5,
        panel_label_case="upper",
        dpi_photo=300,
        dpi_combo=500,
        dpi_line=1000,
        default_palette="nature_muted",
        spec_version="2025.1",
        last_verified="2026-11-23",
        source_url="https://www.cell.com/figureguidelines",
    ),
    "pnas": JournalSpec(
        name="pnas",
        display_name="PNAS",
        widths_mm={
            "single": 87.0,
            "mid": 114.0,
            "1.5col": 114.0,
            "double": 178.0,
            "full": 178.0,
        },
        max_height_mm=200.0,
        max_page_height_mm=225.0,
        font_family=("Helvetica", "Arial", "Liberation Sans", "DejaVu Sans"),
        font_min_pt=6.0,
        font_max_pt=10.0,
        body_pt=7.0,
        tick_pt=6.5,
        legend_pt=6.5,
        panel_label_pt=9.0,
        panel_label_case="upper",
        dpi_photo=300,
        dpi_combo=600,
        dpi_line=1200,
        default_palette="nature_muted",
        spec_version="2025.1",
        last_verified="2026-11-23",
        source_url="https://www.pnas.org/author-center/submitting-your-manuscript",
    ),
    "neurips": JournalSpec(
        name="neurips",
        display_name="NeurIPS",
        widths_mm={
            "half": 67.0,
            "single": 67.0,
            "mid": 111.8,
            "double": 139.7,
            "full": 139.7,
        },
        max_height_mm=180.0,
        max_page_height_mm=228.6,
        font_family=("Helvetica", "Arial", "Liberation Sans", "DejaVu Sans"),
        font_min_pt=6.0,
        font_max_pt=10.0,
        body_pt=7.5,
        tick_pt=6.5,
        legend_pt=6.5,
        panel_label_pt=8.5,
        panel_label_case="lower",
        dpi_photo=300,
        dpi_combo=500,
        dpi_line=1000,
        default_palette="nature_muted",
        spec_version="2025.1",
        last_verified="2026-11-23",
        source_url="https://neurips.cc/Conferences/2025/PaperInformation/StyleFiles",
    ),
    "screen": JournalSpec(
        name="screen",
        display_name="Screen / Chat Review",
        widths_mm={
            "chat": 140.0,
            "single": 140.0,
            "wide": 180.0,
            "double": 180.0,
            "full": 180.0,
            "slide": 240.0,
        },
        max_height_mm=135.0,
        max_page_height_mm=160.0,
        font_family=("Helvetica", "Arial", "Liberation Sans", "DejaVu Sans"),
        font_min_pt=7.0,
        font_max_pt=12.0,
        body_pt=8.5,
        tick_pt=7.5,
        legend_pt=7.5,
        panel_label_pt=10.0,
        panel_label_case="lower",
        axes_linewidth_pt=0.6,
        data_linewidth_pt=1.2,
        dpi_photo=200,
        dpi_combo=220,
        dpi_line=300,
        default_palette="nature_muted",
        spec_version="0.3",
        last_verified="2026-11-23",
        source_url="",
    ),
}


def get_spec(journal: str | JournalSpec) -> JournalSpec:
    """Return a JournalSpec from a journal identifier or pass through an existing spec."""
    if isinstance(journal, JournalSpec):
        return journal
    if not isinstance(journal, str):
        raise TypeError(f"journal must be a str or JournalSpec, got {type(journal).__name__}")
    key = journal.strip().lower().replace("-", "_").replace(" ", "_")
    if key not in JOURNALS:
        valid = ", ".join(sorted(JOURNALS.keys()))
        raise ValueError(f"Unknown journal {journal!r}. Available journals: {valid}")
    return JOURNALS[key]
