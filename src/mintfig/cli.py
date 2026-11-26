"""Command-line interface for mintfig runner, preflight, specs, and skills."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import textwrap
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .preflight import preflight_pdf
from .runner import run_script
from .skill import (
    VALID_TARGETS,
    get_agents_snippet,
    get_full_skill_bundle,
    get_skill_markdown,
    install_skill,
)
from .specs import JOURNALS, JournalSpec, get_spec


def _format_widths(spec: JournalSpec) -> str:
    """Format unique preset column widths cleanly for CLI display."""
    by_width: dict[float, list[str]] = {}
    for name, w in spec.widths_mm.items():
        by_width.setdefault(w, []).append(name)
    parts = [f"{'/'.join(names)}={w:.0f}" for w, names in sorted(by_width.items())]
    return ", ".join(parts) + " mm"


def _verified_label(spec: JournalSpec) -> str:
    """Return the spec's last-verified date, or ``"unverified"`` when unset."""
    return getattr(spec, "last_verified", "") or "unverified"


def _spec_to_dict(spec: JournalSpec) -> dict[str, Any]:
    """Serialize a JournalSpec including v0.2 provenance fields."""
    return {
        "name": spec.name,
        "display_name": spec.display_name,
        "spec_version": getattr(spec, "spec_version", ""),
        "last_verified": getattr(spec, "last_verified", ""),
        "source_url": getattr(spec, "source_url", ""),
        "widths_mm": dict(spec.widths_mm),
        "max_height_mm": spec.max_height_mm,
        "max_page_height_mm": spec.max_page_height_mm,
        "font_family": list(spec.font_family),
        "font_min_pt": spec.font_min_pt,
        "font_max_pt": spec.font_max_pt,
        "body_pt": spec.body_pt,
        "tick_pt": spec.tick_pt,
        "legend_pt": spec.legend_pt,
        "panel_label_pt": spec.panel_label_pt,
        "panel_label_case": spec.panel_label_case,
        "axes_linewidth_pt": spec.axes_linewidth_pt,
        "data_linewidth_pt": spec.data_linewidth_pt,
        "min_linewidth_pt": spec.min_linewidth_pt,
        "dpi_photo": spec.dpi_photo,
        "dpi_combo": spec.dpi_combo,
        "dpi_line": spec.dpi_line,
        "default_palette": spec.default_palette,
    }


def _format_single_spec(spec: JournalSpec) -> str:
    """Format a detailed single-journal specification table."""
    spec_version = getattr(spec, "spec_version", "")
    last_verified = getattr(spec, "last_verified", "")
    verified_str = f"verified {last_verified}" if last_verified else "unverified"
    source_url = getattr(spec, "source_url", "")
    lines = [
        f"{spec.display_name} ({spec.name})",
        "─" * 64,
        f"  Spec version      : {spec_version} ({verified_str})",
        f"  Source URL        : {source_url}",
        f"  Column widths     : {_format_widths(spec)}",
        f"  Max height        : {spec.max_height_mm:.0f} mm (page max {spec.max_page_height_mm:.0f} mm)",
        f"  Font family       : {', '.join(spec.font_family)}",
        f"  Font size bounds  : {spec.font_min_pt:.1f}–{spec.font_max_pt:.1f} pt",
        f"  Body / Tick / Leg : {spec.body_pt:.1f} / {spec.tick_pt:.1f} / {spec.legend_pt:.1f} pt",
        f"  Panel labels      : {spec.panel_label_pt:.1f} pt {spec.panel_label_weight} ({spec.panel_label_case})",
        f"  Line widths       : axes {spec.axes_linewidth_pt:.2f} pt, data {spec.data_linewidth_pt:.2f} pt, min {spec.min_linewidth_pt:.2f} pt",
        f"  DPI (photo/combo) : {spec.dpi_photo} / {spec.dpi_combo} / {spec.dpi_line} (line)",
        f"  Default palette   : {spec.default_palette}",
    ]
    return "\n".join(lines)


def _format_all_specs() -> str:
    """Format a compact overview table of all supported journal specs."""
    headers = ("Journal", "Widths (mm)", "Max H", "Font (pt)", "Panel", "Version", "Verified")
    rows: list[tuple[str, str, str, str, str, str, str]] = []
    for key, spec in JOURNALS.items():
        unique_w = "/".join(f"{w:.0f}" for w in sorted(set(spec.widths_mm.values())))
        max_h = f"{spec.max_height_mm:.0f} ({spec.max_page_height_mm:.0f})"
        font_rng = f"{spec.font_min_pt:.0f}–{spec.font_max_pt:.0f}"
        panel = f"{spec.panel_label_pt:.1f}pt {spec.panel_label_case}"
        version = getattr(spec, "spec_version", "")
        verified = _verified_label(spec)
        rows.append(
            (f"{key} ({spec.display_name})", unique_w, max_h, font_rng, panel, version, verified)
        )

    widths = [max(len(headers[i]), *(len(row[i]) for row in rows)) for i in range(len(headers))]
    fmt = "  ".join(f"{{:<{w}}}" for w in widths)
    sep = "─" * (sum(widths) + 2 * (len(widths) - 1))

    lines = [fmt.format(*headers), sep]
    for row in rows:
        lines.append(fmt.format(*row))
    lines.append("")
    for key, spec in JOURNALS.items():
        source_url = getattr(spec, "source_url", "")
        if source_url:
            lines.append(f"  {key}: {source_url}")
    return "\n".join(lines)


def _parse_width_arg(raw: str | None) -> str | float | None:
    """Convert numeric CLI --width values to float while preserving preset names."""
    if raw is None:
        return None
    try:
        return float(raw)
    except ValueError:
        return raw


def _parse_targets_arg(raw_targets: Sequence[str] | None) -> list[str]:
    """Parse comma-separated or repeated --target values."""
    if not raw_targets:
        return ["claude", "antigravity", "agents-md"]
    parsed: list[str] = []
    for item in raw_targets:
        for part in item.split(","):
            cleaned = part.strip()
            if cleaned:
                parsed.append(cleaned)
    return parsed or ["claude", "antigravity", "agents-md"]


def _parse_list_arg(raw_values: Sequence[str] | None) -> list[str] | None:
    """Parse comma-separated or repeated CLI string list flags."""
    if not raw_values:
        return None
    out: list[str] = []
    for item in raw_values:
        for part in item.split(","):
            cleaned = part.strip()
            if cleaned:
                out.append(cleaned)
    return out or None


def _parse_reference_arg(raw: str | None) -> float | tuple[float, str] | None:
    """Parse ``--reference 100`` or ``--reference 100:SLA budget``."""
    if raw is None:
        return None
    if ":" in raw:
        val_s, label_s = raw.split(":", 1)
        return (float(val_s.strip()), label_s.strip())
    return float(raw.strip())


def _parse_waterfall_start(raw: str | None) -> float | tuple[str, float] | None:
    """Parse ``--waterfall-start 69.0`` or ``--waterfall-start Base:69.0``."""
    if raw is None:
        return None
    if ":" in raw:
        label_s, val_s = raw.split(":", 1)
        return (label_s.strip() or "Start", float(val_s.strip()))
    return float(raw.strip())


def _parse_sort_arg(raw: str | None) -> bool | str | None:
    if raw is None:
        return None
    low = raw.strip().lower()
    if low in {"true", "1", "yes"}:
        return True
    if low in {"false", "0", "no"}:
        return False
    return raw.strip()


def _format_inspect_text(info: dict[str, Any]) -> str:
    """Format an ``inspect_data`` dict into concise plain text for terminals."""
    src = info.get("source") or "<in-memory>"
    lines = [f"{src} — {info['rows']} rows × {len(info['columns'])} columns"]
    lines.append("─" * 64)
    for prof in info.get("column_profiles", []):
        ctype = prof["type"]
        if ctype == "numeric":
            extra = f"min={prof['min']}, median={prof['median']}, max={prof['max']}"
            if prof.get("spans_decades"):
                extra += " (spans decades -> log)"
        elif ctype == "date":
            extra = f"{prof['min']} .. {prof['max']} ({prof['unique']} unique)"
        else:
            samples = ", ".join(prof.get("samples", [])[:4])
            extra = f"{prof['unique']} unique [{samples}]"
        miss = f", {prof['missing']} missing" if prof.get("missing") else ""
        lines.append(f"  {prof['name']:<18} {ctype:<12} {extra}{miss}")
    recs = info.get("recommendations", [])
    if recs:
        lines.append("\nRecommended mintfig forms:")
        for idx, rec in enumerate(recs, 1):
            lines.append(f"  {idx}. {rec['kind']}: {rec['reason']}")
            lines.append(f"     Python: {rec['python']}")
            if rec.get("cli"):
                lines.append(f"     CLI:    {rec['cli']}")
    return "\n".join(lines)


def _add_summary_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--summary",
        choices=("compact", "full"),
        default="compact",
        dest="summary_view",
        help="Summary printed to stdout: compact (default; ok, ship, path, takeaway, deliver, "
        "issues, top facts) or full (every key).",
    )


def _add_density_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--density",
        choices=("regular", "compact"),
        default=None,
        help="Layout density: regular (default) or compact (thinner bars, tighter rows and gaps).",
    )
    parser.add_argument(
        "--no-color-names",
        action="store_false",
        dest="color_names",
        default=None,
        help="Do not draw entity names in titles in their series colour.",
    )


def _density_overrides(args: argparse.Namespace) -> dict[str, Any]:
    """``density`` / ``color_names`` given on the command line, as explain() keywords."""
    out: dict[str, Any] = {}
    if args.density is not None:
        out["density"] = args.density
    if args.color_names is not None:
        out["color_names"] = args.color_names
    return out


def _print_summary(summary: Any, view: str = "compact") -> None:
    if view == "full":
        print(json.dumps(dict(summary), indent=2, ensure_ascii=False))
    else:
        print(summary)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mintfig",
        description="Publication-ready scientific figure runner, preflight linter, and skill CLI.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # `mintfig run <script.py> [--journal nature] [--width ...] [--bundle out/] [--no-proof] [--json] [--strict]`
    run_parser = subparsers.add_parser(
        "run",
        help="Execute a plotting script, run preflight compliance checks, and optionally export a bundle.",
    )
    run_parser.add_argument(
        "script_path",
        type=Path,
        help="Path to the Python plotting script exposing build(), plate, or fig.",
    )
    run_parser.add_argument(
        "--journal",
        "-j",
        default="nature",
        help="Target journal preset name (default: nature).",
    )
    run_parser.add_argument(
        "--width",
        "-w",
        default=None,
        help="Optional column preset (single/double/full) or mm width forwarded to build(width=...).",
    )
    run_parser.add_argument(
        "--bundle",
        "-b",
        type=Path,
        default=None,
        help="Output directory for the submission bundle (PDF, SVG, PNG, proof, TeX, report.json).",
    )
    run_parser.add_argument(
        "--no-proof",
        action="store_true",
        help="Skip proof.png generation when exporting a bundle.",
    )
    run_parser.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="Output the structured v0.2 JSON report.",
    )
    run_parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat warnings as failures (exit code 1 on any warning or error).",
    )

    # `mintfig check plot.py [--claim "..."] [--width chat] [--json]`  (any Matplotlib script)
    # `mintfig check <pdf_path> --journal nature [--json] [--strict]`  (journal preflight)
    check_parser = subparsers.add_parser(
        "check",
        help=(
            "Check a Matplotlib script's figures against their own data at reading size "
            "(plot.py), or run journal preflight on an exported PDF (figure.pdf)."
        ),
    )
    check_parser.add_argument(
        "pdf_path",
        type=Path,
        metavar="path",
        help="A plotting script (.py) to run and check, or a PDF figure to preflight.",
    )
    check_parser.add_argument(
        "--claim",
        default=None,
        help="Script only: the sentence to check against the data (default: each figure's headline).",
    )
    check_parser.add_argument(
        "--width",
        default="chat",
        help="Script only: narrow (450 px), chat (700 px, default), slide (1280 px) or pixels.",
    )
    check_parser.add_argument(
        "--journal",
        "-j",
        default="nature",
        help="PDF only: target journal preset name (default: nature).",
    )
    check_parser.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="Output the preflight report as formatted JSON.",
    )
    check_parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat warnings as failures (exit code 1 on any warning or failure).",
    )

    # `mintfig specs [--journal nature] [--json]`
    specs_parser = subparsers.add_parser(
        "specs",
        help="Display official journal physical dimension and typography specifications.",
    )
    specs_parser.add_argument(
        "--journal",
        "-j",
        default=None,
        help="Show detailed specification for a specific journal preset.",
    )
    specs_parser.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="Output journal specification(s) as formatted JSON.",
    )

    # `mintfig explain <spec.json | -> --out fig.png [--write-spec]` / `mintfig explain --example`
    explain_parser = subparsers.add_parser(
        "explain",
        help="Render a message-first chat figure from a JSON spec (takeaway + panels).",
    )
    explain_parser.add_argument(
        "spec_path",
        nargs="?",
        default=None,
        help="Path to the JSON spec, a PNG saved by mintfig (it carries its spec), or '-' "
        "to read JSON from stdin.",
    )
    explain_parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output image path (.png, .svg, .pdf, or .html). Required unless --example.",
    )
    explain_parser.add_argument(
        "--style",
        default=None,
        help="Visual style override: mintfig (default), bold, editorial, paper, dark, mono, or sketch.",
    )
    explain_parser.add_argument(
        "--palette",
        default=None,
        help="Color palette override: default, okabe_ito, tol, earth, ocean, or berry.",
    )
    explain_parser.add_argument(
        "--accent",
        default=None,
        help="Custom primary highlight accent color override (e.g. '#D97757').",
    )
    explain_parser.add_argument(
        "--lenient",
        "--no-strict",
        action="store_true",
        dest="lenient",
        help="Non-strict mode: auto-adjust soft limits instead of rejecting, and ship if no visual defects remain.",
    )
    explain_parser.add_argument(
        "--write-spec",
        action="store_true",
        help="Also write <out>.json, the normalised spec that reproduces the figure.",
    )
    explain_parser.add_argument(
        "--show-spec",
        action="store_true",
        help="Print the spec embedded in a mintfig PNG (or the JSON spec) and exit.",
    )
    explain_parser.add_argument(
        "--example",
        action="store_true",
        help="Print an example spec to stdout and exit.",
    )
    _add_density_args(explain_parser)
    _add_summary_arg(explain_parser)

    # `mintfig show <path_or_spec> [--mode auto|kitty|iterm2|unicode|ascii] [--width 78] [--no-color]`
    show_parser = subparsers.add_parser(
        "show",
        help="Display a mintfig spec or PNG in the terminal (Kitty/iTerm2 graphics or Unicode/ASCII).",
    )
    show_parser.add_argument(
        "path_or_spec",
        help="Path to a JSON spec, a PNG file, or '-' to read a JSON spec from stdin.",
    )
    show_parser.add_argument(
        "--mode",
        choices=("auto", "kitty", "iterm2", "unicode", "ascii"),
        default="auto",
        help="Rendering mode (default: auto).",
    )
    show_parser.add_argument(
        "--width",
        type=int,
        default=78,
        help="Target text width in columns for unicode/ascii modes (default: 78).",
    )
    show_parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable ANSI color sequences in unicode/ascii output.",
    )

    # `mintfig inspect <data.csv|tsv|json|jsonl> [--json]`
    inspect_parser = subparsers.add_parser(
        "inspect",
        help="Profile a CSV/TSV/JSON/JSONL file without pandas and recommend mintfig forms.",
    )
    inspect_parser.add_argument(
        "data_path",
        type=Path,
        help="Path to a .csv, .tsv, .json, or .jsonl data file.",
    )
    inspect_parser.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="Output column profiles and recommendations as formatted JSON.",
    )

    # `mintfig plot <data.csv|tsv|json|jsonl> --kind <form> --takeaway "..." --out fig.png`
    plot_parser = subparsers.add_parser(
        "plot",
        help="Render a message-first figure directly from a CSV/TSV/JSON/JSONL file without writing Python.",
    )
    plot_parser.add_argument("data_path", type=Path, help="Input .csv, .tsv, .json, or .jsonl file.")
    plot_parser.add_argument(
        "--kind",
        "-k",
        required=True,
        choices=(
            "auto",
            "compare",
            "trend",
            "change",
            "distribution",
            "histogram",
            "relate",
            "share",
            "matrix",
            "table",
            "waterfall",
            "timeline",
            "flow",
        ),
        help="Chart form to render (use 'auto' to pick the top recommended form).",
    )
    plot_parser.add_argument("--takeaway", "-t", required=True, help="One-sentence takeaway title.")
    plot_parser.add_argument("--out", "-o", type=Path, default=None, help="Output path (.png, .svg, .pdf, or .html).")
    plot_parser.add_argument("--show", action="store_true", help="Display the figure in the terminal.")
    plot_parser.add_argument(
        "--show-mode",
        choices=("auto", "kitty", "iterm2", "unicode", "ascii"),
        default="auto",
        help="Terminal rendering mode when --show is set (default: auto).",
    )
    plot_parser.add_argument("--show-width", type=int, default=78, help="Terminal text width when --show is set.")
    plot_parser.add_argument("--subtitle", default=None, help="Figure subtitle.")
    plot_parser.add_argument("--source", default=None, help="Data source line.")
    plot_parser.add_argument("--note", default=None, help="Figure footer note.")
    plot_parser.add_argument("--style", default="mintfig", help="Visual theme name.")
    plot_parser.add_argument("--palette", default=None, help="Color palette name.")
    plot_parser.add_argument("--accent", default=None, help="Custom accent hex color.")
    plot_parser.add_argument("--width", default="chat", help="Target width preset ('narrow', 'chat', 'slide') or mm.")
    plot_parser.add_argument("--title", default=None, help="Panel headline.")
    plot_parser.add_argument("--label", default=None, help="Measured quantity label.")
    plot_parser.add_argument("--unit", default=None, help="Short unit symbol (e.g. ms, %).")
    plot_parser.add_argument("--x-label", default=None, help="X-axis label.")
    plot_parser.add_argument("--y-label", default=None, help="Y-axis label (relate).")
    plot_parser.add_argument("--name", default=None, help="Item/stage name column.")
    plot_parser.add_argument("--value", default=None, help="Value/delta column.")
    plot_parser.add_argument("--group", default=None, help="Group/lane column.")
    plot_parser.add_argument("--x", default=None, help="X column (trend/relate).")
    plot_parser.add_argument("--y", default=None, help="Y column (trend/relate).")
    plot_parser.add_argument("--series", default=None, help="Series column (trend).")
    plot_parser.add_argument("--before", default=None, help="Before column (change).")
    plot_parser.add_argument("--after", default=None, help="After column (change).")
    plot_parser.add_argument("--rows", default=None, help="Row category column (matrix).")
    plot_parser.add_argument("--cols", default=None, help="Column category column (matrix).")
    plot_parser.add_argument("--start", default=None, help="Start column (timeline).")
    plot_parser.add_argument("--end", default=None, help="End column (timeline).")
    plot_parser.add_argument("--names", default=None, help="Point name column (relate).")
    plot_parser.add_argument("--groups", default=None, help="Point group column (relate).")
    plot_parser.add_argument("--highlight", action="append", default=None, help="Highlight name(s), comma-separated or repeated.")
    plot_parser.add_argument("--baseline", default=None, help="Baseline/control item name.")
    plot_parser.add_argument("--reference", default=None, help="Reference value or value:label.")
    plot_parser.add_argument("--sort", default=None, help="Sort order (true/false/asc/desc/column).")
    plot_parser.add_argument("--fmt", default=None, help="Value format spec.")
    plot_parser.add_argument("--log", action="store_true", help="Use log scale on y/value axis.")
    plot_parser.add_argument("--log-x", action="store_true", help="Use log scale on x axis.")
    plot_parser.add_argument("--no-zero", action="store_true", help="Do not force zero baseline (compare dots).")
    plot_parser.add_argument("--show-delta", action="store_true", help="Show inline baseline delta (compare).")
    plot_parser.add_argument("--mode", default=None, help="Distribution mode ('dots' or 'quantile').")
    plot_parser.add_argument("--bins", default=None, help="Histogram bins ('auto' or integer).")
    plot_parser.add_argument("--frontier", action="store_true", help="Draw Pareto frontier (relate).")
    plot_parser.add_argument("--label-all", action="store_true", help="Label all points (relate).")
    plot_parser.add_argument("--connect-groups", action="store_true", help="Connect group trajectories (relate).")
    plot_parser.add_argument("--fit", action="store_true", help="Draw linear fit (relate).")
    plot_parser.add_argument("--bold-best", action="store_true", help="Bold numeric column winners (table).")
    plot_parser.add_argument("--waterfall-start", default=None, help="Waterfall start value or label:value.")
    plot_parser.add_argument("--total-label", default="Total", help="Waterfall total bar label.")
    plot_parser.add_argument("--no-total", action="store_true", help="Omit waterfall final total bar.")
    plot_parser.add_argument("--reason", default=None, help="Drop reason column (flow).")
    plot_parser.add_argument("--triangle", choices=("lower", "upper"), default=None, help="Triangle mask (matrix).")
    plot_parser.add_argument("--mask-diagonal", action="store_true", help="Mask self-diagonal (matrix).")
    plot_parser.add_argument("--lenient", "--no-strict", action="store_true", dest="lenient", help="Auto-adjust soft limits.")
    plot_parser.add_argument("--write-spec", action="store_true", help="Also write <out>.json spec.")
    _add_density_args(plot_parser)
    _add_summary_arg(plot_parser)

    # `mintfig brief <fig1.png|spec1.json> [<fig2.png> ...] --title "..." --out report.html|report.md`
    brief_parser = subparsers.add_parser(
        "brief",
        help="Compose 1–12 saved mintfig PNGs or JSON specs into a single HTML or Markdown briefing.",
    )
    brief_parser.add_argument(
        "figures",
        nargs="+",
        type=Path,
        help="One or more mintfig PNG files (embedded spec) or JSON spec files.",
    )
    brief_parser.add_argument("--title", "-t", required=True, help="Briefing title.")
    brief_parser.add_argument("--out", "-o", type=Path, required=True, help="Output .html or .md path.")
    brief_parser.add_argument("--subtitle", default=None, help="Briefing subtitle.")
    brief_parser.add_argument(
        "--summary",
        action="append",
        default=None,
        help="Key finding bullet (repeatable).",
    )
    brief_parser.add_argument("--source", default=None, help="Briefing footer source.")
    brief_parser.add_argument("--style", default=None, help="Optional theme override for HTML styling.")
    brief_parser.add_argument(
        "--intro",
        default=None,
        help="Opening paragraph, placed after the findings overview and before the first figure.",
    )

    # `mintfig edit <fig.png|spec.json> [flags] --out out.png`
    edit_parser = subparsers.add_parser(
        "edit",
        help="Surgically edit an existing mintfig PNG or JSON spec without rewriting a script.",
    )
    edit_parser.add_argument("figure_path", type=Path, help="Path to a mintfig PNG (embedded spec) or JSON spec.")
    edit_parser.add_argument("--out", "-o", type=Path, default=None, help="Output path (.png, .svg, .pdf, or .html).")
    edit_parser.add_argument("--show", action="store_true", help="Display the edited figure in the terminal.")
    edit_parser.add_argument(
        "--show-mode",
        choices=("auto", "kitty", "iterm2", "unicode", "ascii"),
        default="auto",
        help="Terminal rendering mode when --show is set (default: auto).",
    )
    edit_parser.add_argument("--show-width", type=int, default=78, help="Terminal text width when --show is set.")
    edit_parser.add_argument("--takeaway", "-t", default=None, help="New takeaway title.")
    edit_parser.add_argument("--subtitle", default=None, help="New subtitle (pass '' to clear).")
    edit_parser.add_argument("--source", default=None, help="New source line (pass '' to clear).")
    edit_parser.add_argument("--note", default=None, help="New note (pass '' to clear).")
    edit_parser.add_argument("--style", default=None, help="New theme name.")
    edit_parser.add_argument("--palette", default=None, help="New palette name.")
    edit_parser.add_argument("--accent", default=None, help="New accent hex color (pass '' to clear).")
    edit_parser.add_argument("--width", default=None, help="New target width ('narrow', 'chat', 'slide', or mm).")
    edit_parser.add_argument("--panel", default="a", help="Panel key ('a', 'b', ...) to edit (default: a).")
    edit_parser.add_argument("--title", default=None, help="New panel headline.")
    edit_parser.add_argument("--label", default=None, help="New panel label.")
    edit_parser.add_argument("--unit", default=None, help="New panel unit.")
    edit_parser.add_argument("--highlight", action="append", default=None, help="New highlight name(s), comma-separated or repeated.")
    edit_parser.add_argument("--baseline", default=None, help="New baseline item (pass '' to clear).")
    edit_parser.add_argument("--sort", default=None, help="New sort order.")
    edit_parser.add_argument("--reference", default=None, help="New reference value or value:label.")
    edit_parser.add_argument("--show-delta", action="store_true", default=None, help="Enable inline baseline delta.")
    edit_parser.add_argument("--drop", action="append", default=None, help="Item/series name(s) to remove from --panel.")
    edit_parser.add_argument("--keep", action="append", default=None, help="Keep only these item/series name(s) in --panel.")
    edit_parser.add_argument("--drop-panel", default=None, help="Drop an entire panel by key (e.g. 'b').")
    edit_parser.add_argument("--lenient", "--no-strict", action="store_true", dest="lenient", help="Auto-adjust soft limits.")
    edit_parser.add_argument("--write-spec", action="store_true", help="Also write <out>.json spec.")
    _add_density_args(edit_parser)
    _add_summary_arg(edit_parser)

    # `mintfig doctor [--json] [--out DIR]`
    doctor_parser = subparsers.add_parser(
        "doctor",
        help="Report which delivery surfaces work here and render a sample figure.",
    )
    doctor_parser.add_argument(
        "--json", action="store_true", dest="as_json", help="Output the report as JSON."
    )
    doctor_parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Directory for the sample figure (default: a new temporary directory, kept).",
    )

    # `mintfig skill [--install] [--global] [--target ...] [--root .] [--print [--all]] [--snippet]`
    skill_parser = subparsers.add_parser(
        "skill",
        help="Print or install mintfig agent skill instructions (Claude, Antigravity, Cursor, Codex, AGENTS.md).",
    )
    skill_parser.add_argument(
        "--install",
        action="store_true",
        help="Install skill and/or instruction files into --root (or user home with --global).",
    )
    skill_parser.add_argument(
        "--global",
        action="store_true",
        dest="global_install",
        help=(
            "Install globally into user-home agent directories "
            "(auto-detects installed agents when --target is omitted)."
        ),
    )
    skill_parser.add_argument(
        "--target",
        action="append",
        default=None,
        help=(
            "Comma-separated install target(s): "
            f"{','.join(VALID_TARGETS)},all "
            "(default: claude,antigravity,agents-md; with --global: auto-detect)."
        ),
    )
    skill_parser.add_argument(
        "--root",
        type=Path,
        default=Path("."),
        help="Project root directory for --install (default: current directory).",
    )
    skill_parser.add_argument(
        "--home",
        type=Path,
        default=None,
        help=argparse.SUPPRESS,
    )
    skill_parser.add_argument(
        "--print",
        action="store_true",
        dest="print_skill",
        help="Print the bundled SKILL.md to stdout without modifying disk.",
    )
    skill_parser.add_argument(
        "--all",
        action="store_true",
        dest="print_all",
        help="With --print, include all bundled references/*.md with section headers.",
    )
    skill_parser.add_argument(
        "--snippet",
        action="store_true",
        help="Print the marker-wrapped AGENTS.md / CLAUDE.md snippet without modifying disk.",
    )

    # `mintfig hook [--install | --uninstall | --status | run] [--target ...] [--global] [--root .]`
    hook_parser = subparsers.add_parser(
        "hook",
        help="Install, inspect, remove, or run automatic PostToolUse figure-audit hooks.",
    )
    hook_parser.add_argument(
        "action",
        nargs="?",
        choices=("run",),
        default=None,
        help="Use 'run' inside a PostToolUse hook to audit a plotting script from stdin JSON.",
    )
    hook_parser.add_argument(
        "--install",
        action="store_true",
        help="Install mintfig PostToolUse hook(s) idempotently without clobbering existing settings.",
    )
    hook_parser.add_argument(
        "--uninstall",
        action="store_true",
        help="Remove installed mintfig PostToolUse hook(s), preserving existing user settings.",
    )
    hook_parser.add_argument(
        "--status",
        action="store_true",
        help="Show whether mintfig PostToolUse hook(s) are installed.",
    )
    hook_parser.add_argument(
        "--target",
        action="append",
        default=None,
        help="Comma-separated hook target(s): claude,cursor,codex,all (default: claude).",
    )
    hook_parser.add_argument(
        "--global",
        action="store_true",
        dest="global_install",
        help="Target user-home agent config directories (e.g. ~/.claude/settings.json).",
    )
    hook_parser.add_argument(
        "--root",
        type=Path,
        default=Path("."),
        help="Project root directory for project-local hook install/status (default: current directory).",
    )
    hook_parser.add_argument(
        "--home",
        type=Path,
        default=None,
        help=argparse.SUPPRESS,
    )
    hook_parser.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="Output --status as JSON.",
    )

    return parser


def _run_explain(args: argparse.Namespace) -> int:
    """Render a JSON explain spec; always prints one JSON object for the calling agent.

    Exit codes: 0 rendered with no errors, 1 rendered but an issue has
    severity "error", 2 the spec was rejected (nothing rendered).
    """
    from .explainer import EXAMPLE_SPEC, ExplainError, explain_from_spec, read_png_text

    if args.example:
        print(json.dumps(EXAMPLE_SPEC, indent=2, ensure_ascii=False))
        return 0

    def _reject(message: str, fix_hint: str, rule: str = "explain_spec") -> int:
        payload = {
            "schema_version": "0.2",
            "ok": False,
            "rendered": False,
            "stage": "spec",
            "rule": rule,
            "error": message,
            "fix_hint": fix_hint,
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 2

    if args.spec_path is None or (args.out is None and not args.show_spec):
        return _reject(
            "mintfig explain needs a spec and --out.",
            "Run `mintfig explain spec.json --out fig.png` (or `-` to read stdin, or a PNG saved "
            "by mintfig); `mintfig explain --example` prints a spec to start from.",
        )
    try:
        if args.spec_path != "-" and Path(args.spec_path).read_bytes()[:8] == b"\x89PNG\r\n\x1a\n":
            embedded = read_png_text(args.spec_path)
            if "mintfig:spec" not in embedded:
                return _reject(
                    f"{args.spec_path} carries no mintfig spec.",
                    "Only PNGs written by mintfig (Explanation.save, embed on by default) carry "
                    "their spec; pass the .json spec instead.",
                )
            raw = embedded["mintfig:spec"]
        else:
            raw = (
                sys.stdin.read() if args.spec_path == "-" else Path(args.spec_path).read_text("utf-8")
            )
        spec = json.loads(raw)
    except OSError as exc:
        return _reject(f"Cannot read the spec: {exc}", "Check the path, or pipe the JSON to `-`.")
    except UnicodeDecodeError as exc:
        return _reject(
            f"The spec is not text: {exc}", "Pass a JSON spec or a PNG saved by mintfig."
        )
    except json.JSONDecodeError as exc:
        return _reject(f"The spec is not valid JSON: {exc}", "Fix the JSON syntax and re-run.")
    if args.show_spec:
        print(json.dumps(spec, indent=2, ensure_ascii=False))
        return 0
    if not isinstance(spec, dict):
        return _reject(
            "The spec must be a JSON object.",
            'Use {"takeaway": "...", "panels": [...]}; see `mintfig explain --example`.',
        )
    if args.style is not None:
        spec = {**spec, "style": args.style}
    if args.palette is not None:
        spec = {**spec, "palette": args.palette}
    if getattr(args, "accent", None) is not None:
        spec = {**spec, "accent": args.accent}
    spec = {**spec, **_density_overrides(args)}
    try:
        explanation = explain_from_spec(spec, strict=not args.lenient)
    except ExplainError as exc:
        return _reject(exc.message, exc.fix_hint, exc.rule)
    except (KeyError, TypeError, ValueError) as exc:
        return _reject(str(exc), "See `mintfig explain --example` for the expected shape.")
    summary = explanation.save(args.out, write_spec=args.write_spec)
    _print_summary(summary, args.summary_view)
    return 0 if summary["ok"] else 1


def _run_show(args: argparse.Namespace) -> int:
    """Render a mintfig spec or PNG to the terminal."""
    from .explainer import ExplainError
    from .terminal import show_in_terminal

    try:
        target: Any
        if args.path_or_spec == "-":
            raw = sys.stdin.read()
            target = json.loads(raw)
            if not isinstance(target, dict):
                raise ValueError("JSON spec from stdin must be a JSON object.")
        else:
            target = Path(args.path_or_spec)
        rendered = show_in_terminal(
            target,
            mode=args.mode,
            width=args.width,
            color=not args.no_color,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ExplainError, ValueError, TypeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(rendered)
    return 0


def _emit_explanation(
    explanation: Any,
    *,
    out: Path | None,
    write_spec: bool,
    show: bool,
    show_mode: str,
    show_width: int,
    summary_view: str = "compact",
) -> int:
    """Save ``explanation`` to ``out`` (PNG/SVG/PDF/HTML) and/or render to terminal."""
    if out is not None:
        summary = explanation.save(out, write_spec=write_spec)
    else:
        summary = explanation.summary()

    if show:
        from .terminal import show_in_terminal

        print(show_in_terminal(explanation, mode=show_mode, width=show_width))
    else:
        _print_summary(summary, summary_view)
    return 0 if summary["ok"] else 1


def _run_inspect(args: argparse.Namespace) -> int:
    """Inspect a CSV/TSV/JSON/JSONL file and recommend mintfig forms."""
    from .explainer import ExplainError
    from .inspect_data import inspect_data

    try:
        info = inspect_data(args.data_path)
    except (ExplainError, OSError, ValueError) as exc:
        if args.as_json:
            payload = {
                "ok": False,
                "error": exc.message if isinstance(exc, ExplainError) else str(exc),
                "fix_hint": exc.fix_hint if isinstance(exc, ExplainError) else "Check the file path and format.",
            }
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            print(f"Error: {exc}", file=sys.stderr)
        return 2
    if args.as_json:
        print(json.dumps(info, indent=2, ensure_ascii=False))
    else:
        print(_format_inspect_text(info))
    return 0


def _run_plot(args: argparse.Namespace) -> int:
    """Build and render a figure directly from a CSV/TSV/JSON/JSONL file."""
    from . import explainer as fm_exp
    from .explainer import ExplainError
    from .inspect_data import load_table_file

    def _reject(message: str, fix_hint: str, rule: str = "plot_cli") -> int:
        payload = {
            "schema_version": "0.2",
            "ok": False,
            "rendered": False,
            "stage": "spec",
            "rule": rule,
            "error": message,
            "fix_hint": fix_hint,
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 2

    if args.out is None and not args.show:
        return _reject(
            "mintfig plot needs --out <path> or --show.",
            "Pass --out fig.png (or fig.html) to write a file, or --show for terminal display.",
        )

    try:
        rows = load_table_file(args.data_path)
        hl = _parse_list_arg(args.highlight)
        ref = _parse_reference_arg(args.reference)
        sort_v = _parse_sort_arg(args.sort)
        common: dict[str, Any] = {}
        if args.title is not None:
            common["title"] = args.title
        if args.label is not None:
            common["label"] = args.label
        if args.unit is not None:
            common["unit"] = args.unit
        if hl is not None:
            common["highlight"] = hl if len(hl) > 1 else hl[0]
        if args.fmt is not None:
            common["fmt"] = args.fmt

        kind = args.kind
        with fm_exp.lenient() if args.lenient else _null_ctx():
            if kind == "auto":
                from .inspect_data import auto_panel

                panel = auto_panel(
                    rows,
                    title=args.title,
                    label=args.label,
                    unit=args.unit,
                    highlight=common.get("highlight"),
                    baseline=args.baseline,
                )
            elif kind == "compare":
                kw = {**common}
                if args.name:
                    kw["name"] = args.name
                if args.group:
                    kw["group"] = args.group
                if args.value:
                    kw["value"] = args.value
                if args.baseline:
                    kw["baseline"] = args.baseline
                if ref is not None:
                    kw["reference"] = ref
                if sort_v is not None:
                    kw["sort"] = sort_v
                if args.log:
                    kw["log"] = True
                if args.no_zero:
                    kw["zero"] = False
                if args.show_delta:
                    kw["show_delta"] = True
                panel = fm_exp.compare(rows, **kw)
            elif kind == "share":
                kw = {**common}
                if args.name:
                    kw["name"] = args.name
                if args.value:
                    kw["value"] = args.value
                panel = fm_exp.share(rows, **kw)
            elif kind == "change":
                if not (args.before and args.after):
                    raise ExplainError(
                        "mintfig plot --kind change requires --before and --after column names.",
                        fix_hint="Pass --before col1 --after col2 --name item_col.",
                    )
                kw = {**common, "data": rows}
                if args.name:
                    kw["name"] = args.name
                panel = fm_exp.change(args.before, args.after, **kw)
            elif kind == "trend":
                if not args.x:
                    raise ExplainError(
                        "mintfig plot --kind trend requires --x column name.",
                        fix_hint="Pass --x step_col --y val_col (and optional --series group_col).",
                    )
                kw = {**common, "data": rows}
                if args.y:
                    kw["y"] = args.y
                if args.x_label:
                    kw["x_label"] = args.x_label
                if args.baseline:
                    kw["baseline"] = args.baseline
                if ref is not None:
                    kw["reference"] = ref
                if args.log:
                    kw["log"] = True
                if args.log_x:
                    kw["log_x"] = True
                if args.fit:
                    kw["fit"] = True
                panel = fm_exp.trend(args.x, args.series, **kw)
            elif kind in {"distribution", "histogram"}:
                kw = {**common}
                if args.group:
                    kw["group"] = args.group
                if args.value:
                    kw["value"] = args.value
                if args.baseline:
                    kw["baseline"] = args.baseline
                if ref is not None:
                    kw["reference"] = ref
                if args.log:
                    kw["log"] = True
                if args.mode:
                    kw["mode"] = args.mode
                if args.bins is not None:
                    kw["bins"] = int(args.bins) if args.bins.isdigit() else args.bins
                panel = (
                    fm_exp.histogram(rows, **kw)
                    if kind == "histogram"
                    else fm_exp.distribution(rows, **kw)
                )
            elif kind == "relate":
                if not (args.x and args.y):
                    raise ExplainError(
                        "mintfig plot --kind relate requires --x and --y column names.",
                        fix_hint="Pass --x cost_col --y score_col [--names model_col] [--groups family_col].",
                    )
                kw = {**common, "data": rows}
                kw["x_label"] = args.x_label or args.x
                kw["y_label"] = args.y_label or args.y
                if args.names:
                    kw["names"] = args.names
                if args.groups:
                    kw["groups"] = args.groups
                if ref is not None:
                    kw["reference"] = ref
                if args.log:
                    kw["log_y"] = True
                if args.log_x:
                    kw["log_x"] = True
                if args.frontier:
                    kw["frontier"] = True
                if args.label_all:
                    kw["label_all"] = True
                if args.connect_groups:
                    kw["connect_groups"] = True
                if args.fit:
                    kw["fit"] = True
                panel = fm_exp.relate(args.x, args.y, **kw)
            elif kind == "matrix":
                kw = {**common}
                if args.rows:
                    kw["rows"] = args.rows
                if args.cols:
                    kw["cols"] = args.cols
                if args.value:
                    kw["value"] = args.value
                if args.triangle:
                    kw["triangle"] = args.triangle
                if args.mask_diagonal:
                    kw["mask_diagonal"] = True
                panel = fm_exp.matrix(rows, **kw)
            elif kind == "table":
                kw = {**common}
                if args.baseline:
                    kw["baseline"] = args.baseline
                if args.bold_best:
                    kw["bold_best"] = True
                if sort_v is not None and isinstance(sort_v, str):
                    kw["sort"] = sort_v
                panel = fm_exp.table(rows, **kw)
            elif kind == "waterfall":
                kw = {**common}
                if args.name:
                    kw["name"] = args.name
                if args.value:
                    kw["value"] = args.value
                if args.waterfall_start is not None:
                    kw["start"] = _parse_waterfall_start(args.waterfall_start)
                if args.total_label != "Total":
                    kw["total_label"] = args.total_label
                if args.no_total:
                    kw["show_total"] = False
                if ref is not None:
                    kw["reference"] = ref
                panel = fm_exp.waterfall(rows, **kw)
            elif kind == "timeline":
                kw = {**common}
                if args.name:
                    kw["name"] = args.name
                if args.start:
                    kw["start"] = args.start
                if args.end:
                    kw["end"] = args.end
                if args.group:
                    kw["group"] = args.group
                if args.x_label:
                    kw["x_label"] = args.x_label
                if ref is not None:
                    kw["reference"] = ref
                if sort_v is not None:
                    kw["sort"] = bool(sort_v)
                panel = fm_exp.timeline(rows, **kw)
            elif kind == "flow":
                kw = {**common}
                if args.name:
                    kw["name"] = args.name
                if args.value:
                    kw["value"] = args.value
                if args.reason:
                    kw["reason"] = args.reason
                panel = fm_exp.flow(rows, **kw)
            else:
                raise ExplainError(f"Unsupported kind {kind!r}.", fix_hint="Choose a valid form.")

            explanation = fm_exp.explain(
                args.takeaway,
                panel,
                subtitle=args.subtitle,
                source=args.source,
                note=args.note,
                style=args.style,
                palette=args.palette,
                accent=args.accent,
                width=_parse_width_arg(args.width) or "chat",
                strict=not args.lenient,
                **_density_overrides(args),
            )
    except ExplainError as exc:
        return _reject(exc.message, exc.fix_hint, exc.rule)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        return _reject(str(exc), "Check column names with `mintfig inspect <file>` and re-run.")

    return _emit_explanation(
        explanation,
        out=args.out,
        write_spec=args.write_spec,
        show=args.show,
        show_mode=args.show_mode,
        show_width=args.show_width,
        summary_view=args.summary_view,
    )


def _run_edit(args: argparse.Namespace) -> int:
    """Surgically edit a saved mintfig PNG or JSON spec from the CLI."""
    from .edit import edit as _edit
    from .explainer import ExplainError

    def _reject(message: str, fix_hint: str, rule: str = "edit_cli") -> int:
        payload = {
            "schema_version": "0.2",
            "ok": False,
            "rendered": False,
            "stage": "spec",
            "rule": rule,
            "error": message,
            "fix_hint": fix_hint,
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 2

    if args.out is None and not args.show:
        return _reject(
            "mintfig edit needs --out <path> or --show.",
            "Pass --out edited.png (or edited.html) or --show.",
        )

    def _clearable(val: str | None) -> Any:
        return None if val == "" else val

    try:
        kwargs: dict[str, Any] = {
            "panel": args.panel,
            "strict": not args.lenient,
        }
        if args.takeaway is not None:
            kwargs["takeaway"] = args.takeaway
        if args.subtitle is not None:
            kwargs["subtitle"] = _clearable(args.subtitle)
        if args.source is not None:
            kwargs["source"] = _clearable(args.source)
        if args.note is not None:
            kwargs["note"] = _clearable(args.note)
        if args.style is not None:
            kwargs["style"] = args.style
        if args.palette is not None:
            kwargs["palette"] = _clearable(args.palette)
        if args.accent is not None:
            kwargs["accent"] = _clearable(args.accent)
        if args.width is not None:
            kwargs["width"] = _parse_width_arg(args.width)
        if args.title is not None:
            kwargs["title"] = _clearable(args.title)
        if args.label is not None:
            kwargs["label"] = _clearable(args.label)
        if args.unit is not None:
            kwargs["unit"] = _clearable(args.unit)
        hl = _parse_list_arg(args.highlight)
        if hl is not None:
            kwargs["highlight"] = hl if len(hl) > 1 else hl[0]
        if args.baseline is not None:
            kwargs["baseline"] = _clearable(args.baseline)
        if args.sort is not None:
            kwargs["sort"] = _parse_sort_arg(args.sort)
        if args.reference is not None:
            kwargs["reference"] = _parse_reference_arg(args.reference)
        if args.show_delta is not None:
            kwargs["show_delta"] = args.show_delta
        drops = _parse_list_arg(args.drop)
        if drops is not None:
            kwargs["drop"] = drops
        keeps = _parse_list_arg(args.keep)
        if keeps is not None:
            kwargs["keep"] = keeps
        if args.drop_panel is not None:
            kwargs["drop_panel"] = args.drop_panel
        kwargs.update(_density_overrides(args))

        explanation = _edit(args.figure_path, **kwargs)
    except ExplainError as exc:
        return _reject(exc.message, exc.fix_hint, exc.rule)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        return _reject(str(exc), "Verify the input PNG/JSON path and edit flags.")

    return _emit_explanation(
        explanation,
        out=args.out,
        write_spec=args.write_spec,
        show=args.show,
        show_mode=args.show_mode,
        show_width=args.show_width,
        summary_view=args.summary_view,
    )


class _null_ctx:
    """Minimal no-op context manager for strict mode inside ``_run_plot``."""

    def __enter__(self) -> None:
        return None

    def __exit__(self, *args: object) -> None:
        return None


def _run_brief(args: argparse.Namespace) -> int:
    """Compose saved mintfig PNGs / JSON specs into a cohesive HTML or Markdown briefing."""
    from .brief import brief as _brief
    from .explainer import ExplainError

    try:
        report = _brief(
            args.title,
            *([args.intro] if args.intro else []),
            *args.figures,
            subtitle=args.subtitle,
            summary=args.summary,
            source=args.source,
            style=args.style,
        )
        meta = report.save(args.out)
    except (ExplainError, OSError, ValueError, TypeError) as exc:
        payload = {
            "ok": False,
            "error": exc.message if isinstance(exc, ExplainError) else str(exc),
            "fix_hint": exc.fix_hint if isinstance(exc, ExplainError) else "Check input PNG/JSON paths and --out.",
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 2
    print(json.dumps(meta, indent=2, ensure_ascii=False))
    return 0 if meta["ship_all"] else 1


def _run_doctor(args: argparse.Namespace) -> int:
    """Report the delivery surfaces available here and render the example spec."""
    import tempfile

    import matplotlib.pyplot as plt

    from . import style as _style
    from .explainer import EXAMPLE_SPEC, explain_from_spec
    from .terminal import detect_graphics_protocol, in_notebook

    out_dir = Path(args.out) if args.out is not None else Path(tempfile.mkdtemp(prefix="mintfig-doctor-"))
    out_dir.mkdir(parents=True, exist_ok=True)
    fig = explain_from_spec(EXAMPLE_SPEC)
    try:
        fig.save(out_dir / "example.png")
        summary = fig.save(out_dir / "example.html")
    finally:
        plt.close(fig.fig)
    theme = fig.theme
    font = (
        _style._resolve_font_tuple(theme.body_family)
        if theme.body_family
        else _style.resolved_font_name(fig.spec)
    )
    protocol = detect_graphics_protocol()
    tty = sys.stdout.isatty()
    surfaces = {
        "inline_image_protocol": protocol if protocol in {"kitty", "iterm2"} else None,
        "body_font": font,
        "stdout_is_tty": tty,
        "notebook": in_notebook(),
    }
    if surfaces["notebook"]:
        show_uses = "notebook display"
    elif surfaces["inline_image_protocol"] and tty:
        show_uses = f"inline PNG ({protocol})"
    else:
        show_uses = "plain text (fig.to_text())"
    report = {
        "surfaces": surfaces,
        "show_uses": show_uses,
        "out_dir": str(out_dir.resolve()),
        "deliver": summary["deliver"],
    }
    if args.as_json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0
    yes_no = {True: "yes", False: "no"}
    print("mintfig doctor")
    print(f"  inline image protocol: {surfaces['inline_image_protocol'] or 'none'}")
    print(f"  body font:             {font}")
    print(f"  stdout is a terminal:  {yes_no[tty]}")
    print(f"  notebook:              {yes_no[surfaces['notebook']]}")
    print(f"  fig.show() uses:       {show_uses}")
    kept = "" if args.out is not None else " (temporary folder, kept; delete it when done)"
    print(f"  sample written to:     {out_dir.resolve()}{kept}")
    deliver = summary["deliver"]
    print()
    print("deliver:")
    print(f"  markdown: {deliver['markdown']}")
    print(f"  caption:  {deliver['caption']}")
    print(f"  html:     {deliver['html']}")
    print("  text:")
    print(textwrap.indent(deliver["text"], "    "))
    return 0


def _rerun_with_fixed_hash_seed() -> int | None:
    """Re-run ``mintfig run`` or ``mintfig explain`` with ``PYTHONHASHSEED=0``.

    Matplotlib's PDF font subsetting iterates hash-ordered sets, so the bytes of
    an embedded bold font (every panel label) vary with Python's per-process
    string hash seed. The seed can only be chosen before the interpreter starts,
    so the real CLI re-invokes itself once with a fixed seed to keep
    ``figure.pdf`` byte-reproducible. Returns the child's exit code, or ``None``
    when the seed is already set by the caller and no re-run is needed.
    """
    if os.environ.get("PYTHONHASHSEED") is not None:
        return None
    env = dict(os.environ, PYTHONHASHSEED="0")
    return subprocess.call([sys.executable, "-m", "mintfig.cli", *sys.argv[1:]], env=env)



def _run_figure_check(args: argparse.Namespace) -> int:
    """`mintfig check plot.py`: exit 0 when every figure ships, 1 when one needs a fix,
    2 when the script fails or draws no figure."""
    from .figcheck import WIDTHS, check_script, format_report

    width: str | int = args.width
    if width not in WIDTHS:
        try:
            width = int(str(width).removesuffix("px"))
        except ValueError:
            print(f"Error: --width must be one of {sorted(WIDTHS)} or pixels, not {args.width!r}", file=sys.stderr)
            return 2
    try:
        reports = check_script(args.pdf_path, claim=args.claim, width=width)
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001 - the script's own failure, reported as exit 2
        print(f"[SCRIPT ERROR] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    if not reports:
        print("Error: the script drew no figure.", file=sys.stderr)
        return 2
    if args.as_json:
        print(json.dumps({"schema_version": "0.2", "figures": reports}, indent=2, ensure_ascii=False,
                         default=str))
    else:
        print("\n\n".join(format_report(r) for r in reports))
    blocked = [r for r in reports if not r["ship"]]
    if args.strict:
        blocked += [r for r in reports if r["ship"] and (r["issues"] or r["advisories"])]
    return 1 if blocked else 0

def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point for `mintfig`."""
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    # Only the real command line (argv is None) re-runs; in-process callers keep
    # their interpreter and can set PYTHONHASHSEED themselves.
    if argv is None and args.command in {"run", "explain", "plot", "edit"}:
        child_code = _rerun_with_fixed_hash_seed()
        if child_code is not None:
            return child_code

    if args.command == "specs":
        if args.journal is not None:
            try:
                spec = get_spec(args.journal)
            except (KeyError, ValueError) as exc:
                print(f"Error: {exc}", file=sys.stderr)
                return 1
            if args.as_json:
                print(json.dumps(_spec_to_dict(spec), indent=2))
            else:
                print(_format_single_spec(spec))
        else:
            if args.as_json:
                payload = {key: _spec_to_dict(spec) for key, spec in JOURNALS.items()}
                print(json.dumps(payload, indent=2))
            else:
                print(_format_all_specs())
        return 0

    if args.command == "check" and args.pdf_path.suffix.lower() == ".py":
        return _run_figure_check(args)

    if args.command == "check":
        try:
            report = preflight_pdf(args.pdf_path, journal=args.journal)
        except (FileNotFoundError, KeyError, ValueError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1

        if args.as_json:
            print(json.dumps(report.to_dict(), indent=2))
        else:
            print(report.summary())

        passed = report.passed and (not args.strict or not report.warnings)
        return 0 if passed else 1

    if args.command == "run":
        try:
            result = run_script(
                args.script_path,
                journal=args.journal,
                width=_parse_width_arg(args.width),
                bundle_dir=args.bundle,
                include_proof=not args.no_proof,
                strict=args.strict,
            )
        except (KeyError, ValueError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 2

        if args.as_json:
            print(json.dumps(result.to_dict(), indent=2))
        elif result.report is not None:
            print(result.report.summary())
            for issue in result.report.issues:
                if issue.fix_hint:
                    print(f"  hint ({issue.rule}): {issue.fix_hint}")
            if result.bundle is not None:
                print(f"Bundle written to: {result.bundle.out_dir}")
        else:
            print(f"[{result.stage.upper()} ERROR] {result.error}", file=sys.stderr)
            if result.fix_hint:
                print(f"Fix hint: {result.fix_hint}", file=sys.stderr)
        return result.exit_code

    if args.command == "explain":
        return _run_explain(args)

    if args.command == "show":
        return _run_show(args)

    if args.command == "inspect":
        return _run_inspect(args)

    if args.command == "plot":
        return _run_plot(args)

    if args.command == "edit":
        return _run_edit(args)

    if args.command == "brief":
        return _run_brief(args)

    if args.command == "doctor":
        return _run_doctor(args)

    if args.command == "skill":
        if args.snippet:
            print(get_agents_snippet(), end="")
            return 0
        if args.install:
            if args.target:
                targets: list[str] | None = _parse_targets_arg(args.target)
            elif args.global_install:
                targets = None
            else:
                targets = _parse_targets_arg(None)
            try:
                written = install_skill(
                    root=args.root,
                    targets=targets,
                    global_install=args.global_install,
                    home=args.home,
                )
            except ValueError as exc:
                print(f"Error: {exc}", file=sys.stderr)
                return 1
            for path in written:
                print(f"Installed: {path}")
            return 0
        # Default or --print: output SKILL.md (or full bundle with --all) without touching disk
        if args.print_all:
            print(get_full_skill_bundle(), end="")
        else:
            print(get_skill_markdown(), end="")
        return 0

    if args.command == "hook":
        return _run_hook(args)

    return 1


def _run_hook(args: argparse.Namespace) -> int:
    """Dispatch `mintfig hook` subcommand."""
    from .hooks import (
        format_hook_status,
        hook_status,
        install_hook,
        run_hook,
        uninstall_hook,
    )

    if args.action == "run":
        rc, output = run_hook()
        if output:
            print(output)
        return rc

    raw_targets = _parse_list_arg(args.target)

    if args.install:
        targets = raw_targets if raw_targets is not None else (None if args.global_install else ["claude"])
        try:
            written = install_hook(
                root=args.root,
                targets=targets,
                global_install=args.global_install,
                home=args.home,
            )
        except ValueError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        for path in written:
            print(f"Installed hook: {path}")
        return 0

    if args.uninstall:
        targets = raw_targets if raw_targets is not None else (None if args.global_install else ["claude"])
        try:
            updated = uninstall_hook(
                root=args.root,
                targets=targets,
                global_install=args.global_install,
                home=args.home,
            )
        except ValueError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        if updated:
            for path in updated:
                print(f"Removed hook: {path}")
        else:
            print("No mintfig hooks found to remove.")
        return 0

    # Default or --status
    try:
        status = hook_status(
            root=args.root,
            targets=raw_targets,
            global_install=args.global_install,
            home=args.home,
        )
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    if args.as_json:
        print(json.dumps(status, indent=2, ensure_ascii=False))
    else:
        print(format_hook_status(status))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
