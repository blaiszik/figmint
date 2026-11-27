"""The 0.3.0 top-level surface: what stays, where the rest moved, and no pypdf on import."""

from __future__ import annotations

import subprocess
import sys

import pytest

import mintfig as mint

TOP_LEVEL = {
    "explain", "compare", "trend", "change", "distribution", "histogram", "relate", "share",
    "matrix", "table", "waterfall", "timeline", "flow", "forest", "custom", "Explanation", "Panel",
    "ExplainError", "lenient", "load", "edit", "Session", "brief", "Brief", "card", "SummaryCard",
    "inspect_data", "auto_panel", "load_table_file", "Plate", "figure", "__version__",
    "inline", "InlineGraphic", "check", "style", "notebook",
}  # fmt: skip

PUB = [
    "despine", "direct_labels", "emphasize", "ghost_context", "range_frame", "scalebar",
    "sig_bracket", "slopegraph", "sparkline", "style_colorbar", "style_heatmap", "subtle_grid",
    "tufte_boxplot", "zoom_inset", "save_figure", "rasterize_heavy", "bundle_figure",
    "BundleResult", "CheckResult", "PreflightReport", "preflight_figure", "preflight_pdf",
    "render_proof_sheet", "run_script", "RunResult", "JOURNALS", "MM_PER_INCH", "JournalSpec",
    "get_spec", "in_to_mm", "mm_to_in", "apply", "use", "rc_params", "resolved_font_name",
    "BANNED_COLORMAPS", "EDITORIAL_COLORMAPS", "PALETTES", "get_palette", "register_colormaps",
    "simulate_cvd",
]  # fmt: skip

MOVED = {
    **{name: f"mintfig.pub.{name}" for name in PUB},
    **{
        name: f"mintfig.themes.{name}"
        for name in (
            "THEMES", "Theme", "get_theme", "EXPLAIN_PALETTES", "ExplainPalette",
            "get_explain_palette",
        )
    },
    **{
        name: f"mintfig.audit.{name}"
        for name in ("audit_figure", "audit_layout", "audit_epistemic", "build_narrative")
    },
    **{
        name: f"mintfig.skill.{name}"
        for name in ("install_skill", "get_skill_markdown", "get_agents_snippet", "VALID_TARGETS")
    },
    "render_html": "mintfig.interactive.render_html",
    "render_terminal": "mintfig.terminal.render_terminal",
    "show_in_terminal": "mintfig.terminal.show_in_terminal",
    "explain_from_spec": "mintfig.load",
    "panel_from_spec": "mintfig.explainer.panel_from_spec",
}  # fmt: skip


def test_top_level_all_is_the_frozen_list() -> None:
    assert len(PUB) == 41
    assert set(mint.__all__) == TOP_LEVEL
    for name in mint.__all__:
        assert hasattr(mint, name), name
    assert mint.__version__ == "0.3.2"


@pytest.mark.parametrize("name", sorted(MOVED))
def test_moved_name_points_to_its_new_home(name: str) -> None:
    with pytest.raises(AttributeError) as info:
        getattr(mint, name)
    assert MOVED[name] in str(info.value)
    assert name not in mint.__all__


@pytest.mark.parametrize("name", sorted(MOVED))
def test_new_home_resolves(name: str) -> None:
    obj = mint
    for part in MOVED[name].split(".")[1:]:
        obj = getattr(obj, part)
    assert obj is not None


def test_pub_exports_resolve() -> None:
    assert set(mint.pub.__all__) == set(PUB) | {
        "Plate",
        "figure",
        "place_labels",
        "to_publication",
    }
    for name in mint.pub.__all__:
        assert getattr(mint.pub, name) is not None
    assert mint.pub.Plate is mint.Plate
    assert mint.pub.figure is mint.figure


def test_unknown_attribute_still_raises_plainly() -> None:
    with pytest.raises(AttributeError, match="no attribute 'not_a_name'"):
        _ = mint.not_a_name


def test_import_does_not_load_pypdf() -> None:
    code = "import sys, mintfig; print('pypdf' in sys.modules)"
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )
    assert out.stdout.strip() == "False"


def test_import_is_lazy_for_heavy_deps_and_preserves_callables() -> None:
    code = (
        "import sys, mintfig; "
        "heavy = [m for m in ('matplotlib', 'numpy', 'PIL', 'pypdf') if m in sys.modules]; "
        "print(','.join(heavy))"
    )
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )
    assert out.stdout.strip() == ""

    # Submodule imports with matching names must never shadow top-level callables.
    code2 = (
        "import mintfig as mint; "
        "import mintfig.brief, mintfig.edit, mintfig.inspect_data, mintfig.style; "
        "assert callable(mint.brief); "
        "assert callable(mint.edit); "
        "assert callable(mint.inspect_data); "
        "assert callable(mint.style); "
        "print('ok')"
    )
    out2 = subprocess.run(
        [sys.executable, "-c", code2], capture_output=True, text=True, check=True
    )
    assert out2.stdout.strip() == "ok"
