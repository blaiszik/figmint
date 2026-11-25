"""Empirical validation harness for mintfig v0.2 (10 clean + 25 messy scripts).

Runs every control and messy script through the real CLI:
    .venv/bin/mintfig run <script> --journal <j> --json

Repairs messy scripts using a strictly capped <= 2-loop generic rule-based
repair engine driven purely by the structured JSON response (`stage`,
`issues[].rule`, `issues[].panel`, `issues[].elements`, `issues[].fix_hint`).
No per-filename hardcoding is used.

Outputs:
    evals/output/eval_results.json
    evals/output/repaired_scripts/*.py
    evals/output/bundles/<stem>/*
    evals/output/eval_contact_sheet.png
"""

from __future__ import annotations

import ast
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from mintfig.specs import get_spec

ROOT = Path(__file__).resolve().parent.parent
CORPUS_DIR = ROOT / "evals" / "corpus"
OUT_DIR = ROOT / "evals" / "output"
REPAIRED_DIR = OUT_DIR / "repaired_scripts"
BUNDLES_DIR = OUT_DIR / "bundles"
MINTFIG_BIN = ROOT / ".venv" / "bin" / "mintfig"

BANNED_CMAP_REPLACEMENTS: dict[str, str] = {
    "jet": "viridis",
    "rainbow": "viridis",
    "hsv": "twilight",
    "gist_rainbow": "viridis",
    "nipy_spectral": "viridis",
    "prism": "viridis",
    "flag": "viridis",
}


def _target_journal(script_path: Path) -> str:
    first_line = script_path.read_text(encoding="utf-8").splitlines()[0]
    m = re.match(r"^#\s*target_journal:\s*(\w+)", first_line)
    return m.group(1) if m else "nature"


def _run_mintfig_cli(
    script_path: Path,
    journal: str,
    *,
    bundle_dir: Path | None = None,
    no_proof: bool = True,
) -> tuple[int, dict[str, Any]]:
    cmd = [str(MINTFIG_BIN), "run", str(script_path), "--journal", journal, "--json"]
    if bundle_dir is not None:
        cmd.extend(["--bundle", str(bundle_dir)])
        if no_proof:
            cmd.append("--no-proof")
    env = {**os.environ, "MPLCONFIGDIR": "/tmp/mpl-mintfig"}
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env, check=False)
    stdout = proc.stdout.strip()
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        payload = {
            "ok": False,
            "stage": "cli_parse_error",
            "error": f"Non-JSON stdout ({exc}): {stdout[:300]} | stderr: {proc.stderr[:300]}",
            "issues": [],
        }
    return proc.returncode, payload


# ---------------------------------------------------------------------------
# Generic, JSON-driven repair transforms (NO per-filename cheats)
# ---------------------------------------------------------------------------


def _ensure_mintfig_import_and_apply(source: str, journal: str) -> str:
    """Ensure mintfig is imported and journal styling is applied."""
    if "import mintfig" not in source:
        lines = source.splitlines()
        insert_idx = 0
        for i, line in enumerate(lines):
            if line.startswith(("import ", "from ")):
                insert_idx = i + 1
        lines.insert(insert_idx, "")
        lines.insert(insert_idx + 1, "import mintfig as mint")
        source = "\n".join(lines) + "\n"

    # Determine imported alias for mintfig
    alias = "fm"
    m_alias = re.search(r"import\s+mintfig\s+as\s+(\w+)", source)
    if m_alias:
        alias = m_alias.group(1)
    elif re.search(r"\bimport\s+mintfig\b", source):
        alias = "mintfig"

    # Inject apply(journal) at top of build() if script creates raw plt.subplots/figure without mint.use/Plate
    apply_call = f'{alias}.apply("{journal}")'
    if apply_call not in source and f"{alias}.use(" not in source and f"{alias}.Plate(" not in source:
        source = re.sub(
            r"(def\s+build\([^)]*\)\s*(?:->\s*[^:]+)?:\s*\n)",
            rf"\1    {apply_call}\n",
            source,
            count=1,
        )
    return source


def _repair_contract(source: str) -> str:
    """Fix exit-code-2 contract failure by exposing build()/plate/fig via AST inspection."""
    tree = ast.parse(source)
    func_names: list[str] = []
    var_names: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name != "build":
            func_names.append(node.name)
        elif isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name):
                    # Prefer variables assigned a Plate or plt.subplots/figure call
                    val_src = ast.get_source_segment(source, node.value) or ""
                    if any(k in val_src for k in ("Plate(", "subplots(", "figure(")):
                        var_names.append(tgt.id)

    if func_names:
        return source.rstrip() + f"\n\nbuild = {func_names[-1]}\n"
    if var_names:
        v = var_names[-1]
        if "plate" in v.lower():
            return source.rstrip() + f"\n\nplate = {v}\n"
        return source.rstrip() + f"\n\nfig = {v}\n"
    return source


def _nearest_width_mm(current_w: float, journal: str) -> float:
    spec = get_spec(journal)
    allowed = sorted(set(spec.widths_mm.values()))
    return min(allowed, key=lambda w: abs(w - current_w))


def _inject_kwarg_in_call(source: str, call_prefix: str, kwarg_str: str) -> str:
    """Safely inject a keyword argument before the matching closing ')' of a code call."""
    # Find call_prefix on an actual code line (skipping docstrings/comments)
    m = re.search(rf"^[ \t]*[^#\"'\n]*?({re.escape(call_prefix)}\()", source, flags=re.MULTILINE)
    if not m:
        return source
    start = m.start(1)
    open_paren = start + len(call_prefix)
    depth = 0
    end_paren = -1
    for i in range(open_paren, len(source)):
        ch = source[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                end_paren = i
                break
    if end_paren == -1:
        return source
    inner = source[open_paren + 1 : end_paren].strip()
    if kwarg_str.split("=")[0].strip() in inner:
        return source
    sep = ", " if inner else ""
    return source[:end_paren] + f"{sep}{kwarg_str}" + source[end_paren:]


def _repair_dimensions(source: str, payload: dict[str, Any], journal: str) -> str:
    """Fix width/height dimension failures using target journal spec and current aspect."""
    spec = get_spec(journal)
    dims = payload.get("dimensions_mm", {})
    cur_w = float(dims.get("width", 162.6))
    cur_h = float(dims.get("height", 121.9))

    # Choose appropriate target width from journal presets
    has_multipanel = bool(re.search(r"subplots\(\s*[2-9]", source)) or "layout=[[" in source
    if has_multipanel:
        target_w = max(spec.widths_mm.values())
    else:
        allowed = sorted(set(spec.widths_mm.values()))
        if cur_w > max(allowed):
            target_w = max(allowed) if cur_w > 220 else (allowed[1] if len(allowed) > 1 else allowed[0])
        else:
            target_w = _nearest_width_mm(cur_w, journal)

    aspect = cur_h / cur_w if cur_w > 0 else 0.72
    target_h = round(min(max(target_w * min(max(aspect, 0.55), 0.85), 48.0), spec.max_height_mm - 10.0), 1)

    # Case 1: Plate(..., height_mm=...) exceeds max height
    if "Plate(" in source and cur_h > spec.max_height_mm:
        clamped_h = round(min(spec.max_height_mm - 12.0, 155.0), 1)
        source = re.sub(r"height_mm\s*=\s*[0-9.]+", f"height_mm={clamped_h}", source)
        return source

    # Case 2: Raw plt.subplots(...) or plt.figure(...)
    source = _ensure_mintfig_import_and_apply(source, journal)
    w_in = round(target_w / 25.4, 6)
    h_in = round(target_h / 25.4, 6)

    if re.search(r"figsize\s*=\s*\([^)]+\)", source):
        source = re.sub(
            r"figsize\s*=\s*\([^)]+\)",
            f"figsize=({w_in}, {h_in})",
            source,
        )
    else:
        source = _inject_kwarg_in_call(source, "plt.subplots", f"figsize=({w_in}, {h_in})")

    # Ensure constrained layout on subplots/figure calls that lack it
    if 'layout="constrained"' not in source and "layout='constrained'" not in source:
        source = _inject_kwarg_in_call(source, "plt.subplots", 'layout="constrained"')
    return source


def _repair_colormaps(source: str, issues: list[dict[str, Any]]) -> str:
    """Replace any flagged banned colormap with a perceptual alternative."""
    found_cmaps: set[str] = set()
    for iss in issues:
        if iss.get("rule") == "colormaps":
            for el in iss.get("elements", []):
                found_cmaps.add(str(el).lower())
            msg = str(iss.get("message", "")).lower()
            for banned in BANNED_CMAP_REPLACEMENTS:
                if banned in msg:
                    found_cmaps.add(banned)
    for banned in found_cmaps:
        repl = BANNED_CMAP_REPLACEMENTS.get(banned, "viridis")
        source = re.sub(
            rf"""cmap\s*=\s*(['"]){re.escape(banned)}\1""",
            f'cmap="{repl}"',
            source,
        )
    return source


def _repair_font_sizes(source: str, journal: str) -> str:
    """Clamp explicit fontsize/labelsize literals into journal-compliant [font_min_pt, font_max_pt]."""
    spec = get_spec(journal)
    lo = spec.font_min_pt
    hi = spec.font_max_pt

    def _clamp_match(m: re.Match[str]) -> str:
        kw = m.group(1)
        val = float(m.group(2))
        if val < lo:
            return f"{kw}={max(lo, spec.tick_pt):.1f}"
        if val > hi:
            return f"{kw}={spec.body_pt:.1f}"
        return m.group(0)

    return re.sub(r"\b(fontsize|labelsize|size)\s*=\s*([0-9]+(?:\.[0-9]+)?)", _clamp_match, source)


def _repair_font_family(source: str, journal: str) -> str:
    """Remove serif fontfamily/rcParams overrides and apply journal sans-serif style."""
    source = re.sub(r",\s*fontfamily\s*=\s*['\"][^'\"]+['\"]", "", source)
    source = re.sub(r",\s*family\s*=\s*['\"][^'\"]+['\"]", "", source)
    source = re.sub(r"plt\.rcParams\[['\"]font\.family['\"]\]\s*=\s*['\"][^'\"]+['\"]\s*\n?", "", source)
    source = re.sub(r"plt\.rcParams\[['\"]pdf\.fonttype['\"]\]\s*=\s*\d+\s*\n?", "", source)
    source = _ensure_mintfig_import_and_apply(source, journal)
    return source


def _repair_hairline_strokes(source: str) -> str:
    """Raise any explicit non-zero linewidth/lw < 0.25 pt up to 0.5 pt."""

    def _fix_lw(m: re.Match[str]) -> str:
        kw = m.group(1)
        val = float(m.group(2))
        if 0.0 < val < 0.25:
            return f"{kw}=0.5"
        return m.group(0)

    return re.sub(r"\b(linewidth|lw)\s*=\s*([0-9]+(?:\.[0-9]+)?)", _fix_lw, source)


def _repair_canvas_clipping(source: str, issues: list[dict[str, Any]]) -> str:
    """Fix clipped text by enabling constrained layout, removing cramped margins, and clamping fig.text."""
    # Remove manual cramped subplots_adjust(...)
    source = re.sub(r"^[ \t]*fig\.subplots_adjust\([^)]*\)[ \t]*\n?", "", source, flags=re.MULTILINE)

    # Ensure constrained layout if using plt.subplots
    if "plt.subplots(" in source and 'layout="constrained"' not in source and "layout='constrained'" not in source:
        source = _inject_kwarg_in_call(source, "plt.subplots", 'layout="constrained"')

    # Fix out-of-bounds fig.text(x, y >= 0.98, ...) -> move inside canvas via ax.set_title or safe y=0.96
    def _fix_fig_text(m: re.Match[str]) -> str:
        prefix = m.group(1)
        x_val = float(m.group(2))
        y_val = float(m.group(3))
        rest = m.group(4)
        new_x = min(max(x_val, 0.05), 0.95)
        new_y = min(max(y_val, 0.05), 0.96)
        rest = re.sub(r"""va\s*=\s*['"]bottom['"]""", 'va="top"', rest)
        return f"{prefix}({new_x:.2f}, {new_y:.2f}, {rest}"

    source = re.sub(
        r"((?:plate\.)?fig\.text)\(\s*([0-9.]+)\s*,\s*([0-9.]+)\s*,\s*(.*)",
        _fix_fig_text,
        source,
    )

    # If a clipped xlabel is overly long, wrap it nicely across two lines
    for iss in issues:
        if iss.get("rule") == "canvas_clipping":
            for el in iss.get("elements", []):
                s = str(el)
                if len(s) > 42 and f'"{s}"' in source:
                    words = s.split()
                    mid = len(words) // 2
                    wrapped = " ".join(words[:mid]) + "\\n" + " ".join(words[mid:])
                    source = source.replace(f'"{s}"', f'"{wrapped}"', 1)
    return source


def _repair_text_overlaps(source: str, issues: list[dict[str, Any]], loop_idx: int) -> str:
    """Resolve severe text collisions using elements & fix_hint from JSON."""
    for iss in issues:
        if iss.get("rule") != "text_overlaps":
            continue
        elements = [str(e) for e in iss.get("elements", [])]
        hint = str(iss.get("fix_hint", "")).lower()

        # Case A: Tick-vs-tick overlap (rotate xticklabels, escalating to 90 deg on Loop 2 if still cramped)
        if ("tick" in hint or "rotation" in hint or "maxnlocator" in hint) and "set_xticklabels(" in source:
            if "rotation=" not in source:
                source = re.sub(
                    r"set_xticklabels\(([^)]+)\)",
                    r'set_xticklabels(\1, rotation=40, ha="right")',
                    source,
                    count=1,
                )
                continue
            if "rotation=90" not in source:
                source = re.sub(
                    r"rotation\s*=\s*\d+(?:\s*,\s*ha\s*=\s*['\"][^'\"]+['\"])?",
                    'rotation=90, ha="center"',
                    source,
                    count=1,
                )
                continue

        # Case B: Legend collides with annotation text -> move legend to opposite corner
        if "legend" in hint or "legend(" in source:
            m_leg = re.search(r"""legend\([^)]*loc\s*=\s*['"]([^'"]+)['"]""", source)
            if m_leg:
                old_loc = m_leg.group(1)
                new_loc = "lower right" if "upper" in old_loc else "upper right"
                source = source.replace(f'loc="{old_loc}"', f'loc="{new_loc}"', 1)
                source = source.replace(f"loc='{old_loc}'", f'loc="{new_loc}"', 1)
                continue

        # Case C: Two colliding text annotations -> shift the second colliding ax.text y-coord cleanly
        if len(elements) >= 2:
            target_label = elements[1]
            # Find ax.text(x, y, "target_label", ...) or axes[...].text(...)
            pattern = re.compile(
                rf"""(\.text\(\s*[-+]?[0-9.]+\s*,\s*)([-+]?[0-9.]+)(\s*,\s*['"]{re.escape(target_label)}['"])"""
            )
            m = pattern.search(source)
            if m:
                y_val = float(m.group(2))
                # Estimate vertical step based on scale of y_val (or fallback 0.75 * (loop_idx + 1))
                delta = max(0.75, abs(y_val) * 0.38) * (loop_idx + 1)
                new_y = round(y_val - delta, 3)
                source = source[: m.start(2)] + f"{new_y}" + source[m.end(2) :]
    return source


def apply_repairs(source: str, payload: dict[str, Any], journal: str, loop_idx: int) -> str:
    """Apply all generic repairs triggered by the current mintfig run --json payload."""
    stage = payload.get("stage", "preflight")
    if stage == "contract":
        return _repair_contract(source)

    issues = payload.get("issues", [])
    active_rules = {str(i.get("rule")) for i in issues if i.get("severity") in {"error", "warning"}}

    if "dimensions" in active_rules:
        source = _repair_dimensions(source, payload, journal)
    if "colormaps" in active_rules:
        source = _repair_colormaps(source, issues)
    if "font_sizes" in active_rules:
        source = _repair_font_sizes(source, journal)
    if "font_family" in active_rules or "vector_fonts" in active_rules:
        source = _repair_font_family(source, journal)
    if "hairline_strokes" in active_rules:
        source = _repair_hairline_strokes(source)
    if "canvas_clipping" in active_rules:
        source = _repair_canvas_clipping(source, issues)
    if "text_overlaps" in active_rules:
        source = _repair_text_overlaps(source, issues, loop_idx)

    return source


# ---------------------------------------------------------------------------
# Contact Sheet Builder (3x3 grid of 9 diverse repaired figures)
# ---------------------------------------------------------------------------


def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "/System/Library/Fonts/HelveticaNeue.ttc",
        "/System/Library/Fonts/Helvetica.ttc",
    ]
    for path in candidates:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size=size, index=1 if bold else 0)
            except OSError:
                continue
    return ImageFont.load_default()


def build_contact_sheet(records: list[dict[str, Any]], out_path: Path) -> list[str]:
    """Build a crisp 3x3 contact sheet from 9 diverse repaired messy figures."""
    # Pick 9 diverse repaired scripts that passed and have preview.png
    preferred_prefixes = [
        "messy_01_",  # default scatter -> Nature 89 mm
        "messy_05_",  # volcano jet -> viridis
        "messy_06_",  # heatmap rainbow -> viridis
        "messy_08_",  # survival tiny text -> 6 pt
        "messy_11_",  # clipped xlabel -> constrained + wrapped
        "messy_13_",  # colliding labels -> separated
        "messy_15_",  # Science 55 mm cramped ticks -> rotated
        "messy_16_",  # legend collision -> relocated
        "messy_24_",  # compound 2x2 multi-panel mess -> full repair
    ]
    selected: list[dict[str, Any]] = []
    by_name = {r["script"]: r for r in records if r.get("final_ok") and r.get("preview_png")}
    for pref in preferred_prefixes:
        for name, rec in by_name.items():
            if name.startswith(pref):
                selected.append(rec)
                break
    # Fill up to 9 if any preferred didn't pass
    for rec in by_name.values():
        if len(selected) >= 9:
            break
        if rec not in selected:
            selected.append(rec)

    cell_w, cell_h = 820, 620
    pad = 36
    gap = 28
    header_h = 132
    card_hdr = 62
    cols, rows = 3, 3

    canvas_w = pad * 2 + cols * cell_w + (cols - 1) * gap
    canvas_h = header_h + pad + rows * cell_h + (rows - 1) * gap + pad
    canvas = Image.new("RGB", (canvas_w, canvas_h), (246, 248, 251))
    draw = ImageDraw.Draw(canvas)

    f_title = _load_font(40, bold=True)
    f_sub = _load_font(22, bold=False)
    f_card = _load_font(20, bold=True)
    f_meta = _load_font(17, bold=False)
    f_pill = _load_font(16, bold=True)

    draw.rectangle([0, 0, canvas_w, header_h], fill=(18, 24, 38))
    draw.text(
        (pad, 24),
        "MINTFIG v0.2 EMPIRICAL VALIDATION  ·  Repaired Messy Figures (3×3 Contact Sheet)",
        fill=(255, 255, 255),
        font=f_title,
    )
    draw.text(
        (pad, 78),
        "9 diverse messy shot-#0 scripts auto-repaired in <= 2 loops purely from `mintfig run --json` structured fix_hints",
        fill=(186, 196, 214),
        font=f_sub,
    )

    chosen_names: list[str] = []
    for idx, rec in enumerate(selected[:9]):
        chosen_names.append(rec["script"])
        r_idx, c_idx = divmod(idx, cols)
        x0 = pad + c_idx * (cell_w + gap)
        y0 = header_h + pad + r_idx * (cell_h + gap)
        draw.rounded_rectangle(
            [x0, y0, x0 + cell_w, y0 + cell_h],
            radius=14,
            fill=(255, 255, 255),
            outline=(214, 220, 230),
            width=2,
        )

        short_name = rec["script"].replace(".py", "")
        dims = rec.get("final_dimensions_mm", {})
        meta_str = (
            f"{rec['journal']} · {dims.get('width', 0):.0f}×{dims.get('height', 0):.0f} mm · "
            f"Loop {rec['loops_used']}"
        )
        draw.text((x0 + 16, y0 + 10), short_name, fill=(18, 24, 38), font=f_card)
        draw.text((x0 + 16, y0 + 36), meta_str, fill=(92, 102, 118), font=f_meta)

        # Green PASS pill
        pill_txt = "PASS"
        pb = draw.textbbox((0, 0), pill_txt, font=f_pill)
        pw = pb[2] - pb[0] + 24
        ph = pb[3] - pb[1] + 12
        px0 = x0 + cell_w - pw - 14
        py0 = y0 + 14
        draw.rounded_rectangle([px0, py0, px0 + pw, py0 + ph], radius=ph // 2, fill=(220, 252, 231))
        draw.text((px0 + 12 - pb[0], py0 + 6 - pb[1]), pill_txt, fill=(21, 128, 61), font=f_pill)
        draw.line([(x0 + 12, y0 + card_hdr), (x0 + cell_w - 12, y0 + card_hdr)], fill=(235, 238, 243), width=2)

        img = Image.open(rec["preview_png"]).convert("RGB")
        avail_w = cell_w - 28
        avail_h = cell_h - card_hdr - 24
        scale = min(avail_w / img.width, avail_h / img.height)
        nw = round(img.width * scale)
        nh = round(img.height * scale)
        resized = img.resize((nw, nh), Image.Resampling.LANCZOS)
        ix = x0 + (cell_w - nw) // 2
        iy = y0 + card_hdr + (cell_h - card_hdr - nh) // 2
        canvas.paste(resized, (ix, iy))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out_path, dpi=(200, 200))
    return chosen_names


# ---------------------------------------------------------------------------
# Main Eval Runner
# ---------------------------------------------------------------------------


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPAIRED_DIR.mkdir(parents=True, exist_ok=True)
    BUNDLES_DIR.mkdir(parents=True, exist_ok=True)

    clean_scripts = sorted(CORPUS_DIR.glob("clean_*.py"))
    messy_scripts = sorted(CORPUS_DIR.glob("messy_*.py"))

    # --- 1. Evaluate 10 Clean Control Scripts ---
    clean_records: list[dict[str, Any]] = []
    for sp in clean_scripts:
        journal = _target_journal(sp)
        code, payload = _run_mintfig_cli(sp, journal)
        summary = payload.get("summary", {})
        clean_records.append(
            {
                "script": sp.name,
                "journal": journal,
                "exit_code": code,
                "ok": bool(payload.get("ok", False)),
                "errors": int(summary.get("errors", 0)),
                "warnings": int(summary.get("warnings", 0)),
                "dimensions_mm": payload.get("dimensions_mm", {}),
                "issues": payload.get("issues", []),
            }
        )

    # --- 2. Evaluate 25 Messy Scripts with <= 2-Loop Generic Repair Harness ---
    messy_records: list[dict[str, Any]] = []
    for sp in messy_scripts:
        journal = _target_journal(sp)
        work_script = REPAIRED_DIR / sp.name
        source = sp.read_text(encoding="utf-8")
        work_script.write_text(source, encoding="utf-8")

        history: list[dict[str, Any]] = []
        loops_used = 0
        final_code = 1
        final_payload: dict[str, Any] = {}

        for loop_idx in range(3):  # Loop 0, Loop 1, Loop 2 (strictly <= 2 repair loops)
            code, payload = _run_mintfig_cli(work_script, journal)
            summary = payload.get("summary", {})
            issues = payload.get("issues", [])
            err_rules = [i["rule"] for i in issues if i.get("severity") == "error"]
            warn_rules = [i["rule"] for i in issues if i.get("severity") == "warning"]
            # Consider "clean pass" as ok==True AND 0 errors AND 0 warnings
            clean_pass = (code == 0) and bool(payload.get("ok", False)) and (int(summary.get("warnings", 0)) == 0)
            error_free = (code == 0) and bool(payload.get("ok", False))
            history.append(
                {
                    "loop": loop_idx,
                    "exit_code": code,
                    "stage": payload.get("stage", "preflight"),
                    "ok": bool(payload.get("ok", False)),
                    "errors": int(summary.get("errors", 0)),
                    "warnings": int(summary.get("warnings", 0)),
                    "error_rules": err_rules,
                    "warn_rules": warn_rules,
                    "clean_pass": clean_pass,
                    "error_free": error_free,
                }
            )
            final_code = code
            final_payload = payload
            loops_used = loop_idx
            if clean_pass or loop_idx == 2:
                break

            # Apply generic JSON-driven repairs for next loop
            new_source = apply_repairs(source, payload, journal, loop_idx)
            source = new_source
            work_script.write_text(source, encoding="utf-8")

        # Export bundle for every passing repaired script
        bundle_dir = BUNDLES_DIR / sp.stem
        preview_png = None
        if final_code == 0:
            b_code, b_payload = _run_mintfig_cli(work_script, journal, bundle_dir=bundle_dir, no_proof=True)
            if b_code == 0:
                final_payload = b_payload
                preview_png = b_payload.get("artifacts", {}).get("preview_png")

        messy_records.append(
            {
                "script": sp.name,
                "journal": journal,
                "loops_used": loops_used,
                "loop0_ok": history[0]["error_free"],
                "loop0_clean": history[0]["clean_pass"],
                "loop1_ok": any(h["error_free"] for h in history if h["loop"] <= 1),
                "loop1_clean": any(h["clean_pass"] for h in history if h["loop"] <= 1),
                "loop2_ok": any(h["error_free"] for h in history if h["loop"] <= 2),
                "loop2_clean": any(h["clean_pass"] for h in history if h["loop"] <= 2),
                "final_ok": final_code == 0,
                "final_warnings": int(final_payload.get("summary", {}).get("warnings", 0)),
                "final_errors": int(final_payload.get("summary", {}).get("errors", 0)),
                "final_dimensions_mm": final_payload.get("dimensions_mm", {}),
                "preview_png": preview_png,
                "history": history,
            }
        )

    contact_sheet_path = OUT_DIR / "eval_contact_sheet.png"
    contact_sheet_scripts = build_contact_sheet(messy_records, contact_sheet_path)

    n_clean = len(clean_records)
    n_messy = len(messy_records)
    clean_fp_errors = sum(1 for r in clean_records if not r["ok"] or r["errors"] > 0)
    clean_fp_warnings = sum(1 for r in clean_records if r["warnings"] > 0)

    metrics = {
        "control_set": {
            "total": n_clean,
            "false_positive_errors": clean_fp_errors,
            "false_positive_warnings": clean_fp_warnings,
            "clean_pass_rate": round((n_clean - clean_fp_errors) / n_clean, 4) if n_clean else 0.0,
        },
        "messy_set": {
            "total": n_messy,
            "loop0_error_free": sum(1 for r in messy_records if r["loop0_ok"]),
            "loop0_clean_zero_warn": sum(1 for r in messy_records if r["loop0_clean"]),
            "loop1_error_free": sum(1 for r in messy_records if r["loop1_ok"]),
            "loop1_clean_zero_warn": sum(1 for r in messy_records if r["loop1_clean"]),
            "loop2_error_free": sum(1 for r in messy_records if r["loop2_ok"]),
            "loop2_clean_zero_warn": sum(1 for r in messy_records if r["loop2_clean"]),
            "loop2_error_free_rate": round(sum(1 for r in messy_records if r["loop2_ok"]) / n_messy, 4)
            if n_messy
            else 0.0,
            "loop2_clean_rate": round(sum(1 for r in messy_records if r["loop2_clean"]) / n_messy, 4)
            if n_messy
            else 0.0,
        },
        "contact_sheet_scripts": contact_sheet_scripts,
        "clean_records": clean_records,
        "messy_records": messy_records,
    }

    results_path = OUT_DIR / "eval_results.json"
    results_path.write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"control_set": metrics["control_set"], "messy_set": metrics["messy_set"]}, indent=2))


if __name__ == "__main__":
    main()
