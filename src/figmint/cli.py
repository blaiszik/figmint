"""Command-line interface for figmint runner, preflight, specs, and skills."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .preflight import preflight_pdf
from .runner import run_script
from .skill import VALID_TARGETS, get_agents_snippet, get_skill_markdown, install_skill
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


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="figmint",
        description="Publication-ready scientific figure runner, preflight linter, and skill CLI.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # `figmint run <script.py> [--journal nature] [--width ...] [--bundle out/] [--no-proof] [--json] [--strict]`
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

    # `figmint check <pdf_path> --journal nature [--json] [--strict]`
    check_parser = subparsers.add_parser(
        "check",
        help="Run automated journal preflight checks on an exported PDF figure.",
    )
    check_parser.add_argument(
        "pdf_path",
        type=Path,
        help="Path to the PDF figure to verify.",
    )
    check_parser.add_argument(
        "--journal",
        "-j",
        default="nature",
        help="Target journal preset name (default: nature).",
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

    # `figmint specs [--journal nature] [--json]`
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

    # `figmint explain <spec.json | -> --out fig.png [--write-spec]` / `figmint explain --example`
    explain_parser = subparsers.add_parser(
        "explain",
        help="Render a message-first chat figure from a JSON spec (takeaway + panels).",
    )
    explain_parser.add_argument(
        "spec_path",
        nargs="?",
        default=None,
        help="Path to the JSON spec, a PNG saved by figmint (it carries its spec), or '-' "
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
        help="Visual style override: figmint (default), bold, editorial, paper, dark, mono, or sketch.",
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
        help="Print the spec embedded in a figmint PNG (or the JSON spec) and exit.",
    )
    explain_parser.add_argument(
        "--example",
        action="store_true",
        help="Print an example spec to stdout and exit.",
    )

    # `figmint show <path_or_spec> [--mode auto|kitty|iterm2|unicode|ascii] [--width 78] [--no-color]`
    show_parser = subparsers.add_parser(
        "show",
        help="Display a figmint spec or PNG in the terminal (Kitty/iTerm2 graphics or Unicode/ASCII).",
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

    # `figmint skill [--install] [--target ...] [--root .] [--print] [--snippet]`
    skill_parser = subparsers.add_parser(
        "skill",
        help="Print or install figmint agent skill instructions (Claude, Antigravity, Cursor, Codex, AGENTS.md).",
    )
    skill_parser.add_argument(
        "--install",
        action="store_true",
        help="Install skill and/or instruction files into --root.",
    )
    skill_parser.add_argument(
        "--target",
        action="append",
        default=None,
        help=(
            "Comma-separated install target(s): "
            f"{','.join(VALID_TARGETS)} (default: claude,antigravity,agents-md)."
        ),
    )
    skill_parser.add_argument(
        "--root",
        type=Path,
        default=Path("."),
        help="Project root directory for --install (default: current directory).",
    )
    skill_parser.add_argument(
        "--print",
        action="store_true",
        dest="print_skill",
        help="Print the bundled SKILL.md to stdout without modifying disk.",
    )
    skill_parser.add_argument(
        "--snippet",
        action="store_true",
        help="Print the marker-wrapped AGENTS.md / CLAUDE.md snippet without modifying disk.",
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
            "figmint explain needs a spec and --out.",
            "Run `figmint explain spec.json --out fig.png` (or `-` to read stdin, or a PNG saved "
            "by figmint); `figmint explain --example` prints a spec to start from.",
        )
    try:
        if args.spec_path != "-" and Path(args.spec_path).read_bytes()[:8] == b"\x89PNG\r\n\x1a\n":
            embedded = read_png_text(args.spec_path)
            if "figmint:spec" not in embedded:
                return _reject(
                    f"{args.spec_path} carries no figmint spec.",
                    "Only PNGs written by figmint (Explanation.save, embed on by default) carry "
                    "their spec; pass the .json spec instead.",
                )
            raw = embedded["figmint:spec"]
        else:
            raw = (
                sys.stdin.read() if args.spec_path == "-" else Path(args.spec_path).read_text("utf-8")
            )
        spec = json.loads(raw)
    except OSError as exc:
        return _reject(f"Cannot read the spec: {exc}", "Check the path, or pipe the JSON to `-`.")
    except UnicodeDecodeError as exc:
        return _reject(
            f"The spec is not text: {exc}", "Pass a JSON spec or a PNG saved by figmint."
        )
    except json.JSONDecodeError as exc:
        return _reject(f"The spec is not valid JSON: {exc}", "Fix the JSON syntax and re-run.")
    if args.show_spec:
        print(json.dumps(spec, indent=2, ensure_ascii=False))
        return 0
    if not isinstance(spec, dict):
        return _reject(
            "The spec must be a JSON object.",
            'Use {"takeaway": "...", "panels": [...]}; see `figmint explain --example`.',
        )
    if args.style is not None:
        spec = {**spec, "style": args.style}
    if args.palette is not None:
        spec = {**spec, "palette": args.palette}
    if getattr(args, "accent", None) is not None:
        spec = {**spec, "accent": args.accent}
    try:
        explanation = explain_from_spec(spec, strict=not args.lenient)
    except ExplainError as exc:
        return _reject(exc.message, exc.fix_hint, exc.rule)
    except (KeyError, TypeError, ValueError) as exc:
        return _reject(str(exc), "See `figmint explain --example` for the expected shape.")
    if args.out.suffix.lower() in {".html", ".htm"}:
        from .interactive import render_html

        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(render_html(explanation, interactive=True), encoding="utf-8")
        explanation.saved_path = out_path.resolve()
        explanation.saved_px = None
        if args.write_spec:
            out_path.with_suffix(".json").write_text(
                json.dumps(explanation.to_spec(), indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        summary = explanation.summary()
    else:
        summary = explanation.save(args.out, write_spec=args.write_spec)
    print(summary)
    return 0 if summary["ok"] else 1


def _run_show(args: argparse.Namespace) -> int:
    """Render a figmint spec or PNG to the terminal."""
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


def _rerun_with_fixed_hash_seed() -> int | None:
    """Re-run ``figmint run`` or ``figmint explain`` with ``PYTHONHASHSEED=0``.

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
    return subprocess.call([sys.executable, "-m", "figmint.cli", *sys.argv[1:]], env=env)


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point for `figmint`."""
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    # Only the real command line (argv is None) re-runs; in-process callers keep
    # their interpreter and can set PYTHONHASHSEED themselves.
    if argv is None and args.command in {"run", "explain"}:
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

    if args.command == "skill":
        if args.snippet:
            print(get_agents_snippet(), end="")
            return 0
        if args.install:
            targets = _parse_targets_arg(args.target)
            try:
                written = install_skill(root=args.root, targets=targets)
            except ValueError as exc:
                print(f"Error: {exc}", file=sys.stderr)
                return 1
            for path in written:
                print(f"Installed: {path}")
            return 0
        # Default or --print: output SKILL.md without touching disk
        print(get_skill_markdown(), end="")
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
