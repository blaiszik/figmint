"""15-second live terminal demo and "One Dataset, Six Surfaces" HTML showcase."""

from __future__ import annotations

import base64
import html
import io
import os
import re
import shutil
import sys
import tempfile
import textwrap
from collections.abc import Mapping
from pathlib import Path
from typing import Any, TextIO

from ._chip_bridge import import_mintchip

__all__ = [
    "DEMO_DATASET",
    "build_showcase_html",
    "run_demo",
]

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
_ANSI_TOKEN_RE = re.compile(r"\x1b\[([0-9;]*)m")

#: Shared 5-seed ablation dataset rendered across every surface in the demo & showcase.
DEMO_DATASET: dict[str, Any] = {
    "kicker": "ABLATION · 5 SEEDS",
    "takeaway": "Retrieval reaches 91.4% accuracy at step 600, +7.6 pts over LoRA-only",
    "subtitle": "5-seed mean with 95% CI band · validation pass@1",
    "source": "mintfig demo · 5-seed ablation (n = 5)",
    "steps": [0, 100, 200, 300, 400, 500, 600],
    "series": {
        "Retrieval": [61.2, 71.8, 79.4, 84.6, 88.5, 90.4, 91.4],
        "LoRA-only": [60.8, 68.5, 74.1, 78.2, 81.0, 82.9, 83.8],
        "Base": [60.5, 64.9, 68.7, 71.4, 73.2, 74.5, 75.1],
    },
    "band": {
        "Retrieval": [1.4, 1.3, 1.2, 1.0, 0.9, 0.8, 0.7],
        "LoRA-only": [1.5, 1.4, 1.3, 1.2, 1.1, 1.0, 0.9],
        "Base": [1.6, 1.5, 1.4, 1.3, 1.2, 1.1, 1.0],
    },
    "band_label": "95% CI (n = 5 seeds)",
    "events": {300: "LR decay"},
    "highlight": "Retrieval",
    "baseline": "Base",
    "card_takeaway": "Retrieval beats LoRA-only by +7.6 pts at step 600",
    "card_subtitle": "5-seed ablation summary · validation pass@1",
    "card_metrics": [
        {
            "label": "Retrieval",
            "value": "91.4%",
            "delta": "+16.3 pts",
            "good": True,
            "spark": [61.2, 71.8, 79.4, 84.6, 88.5, 90.4, 91.4],
            "note": "±0.7% 95% CI",
        },
        {
            "label": "LoRA-only",
            "value": "83.8%",
            "delta": "+8.7 pts",
            "good": True,
            "spark": [60.8, 68.5, 74.1, 78.2, 81.0, 82.9, 83.8],
            "note": "±0.9% 95% CI",
        },
        {
            "label": "Base",
            "value": "75.1%",
            "delta": "baseline",
            "good": None,
            "spark": [60.5, 64.9, 68.7, 71.4, 73.2, 74.5, 75.1],
            "note": "±1.0% 95% CI",
        },
        {
            "label": "Gain vs LoRA",
            "value": "+7.6 pts",
            "delta": "p < 0.01",
            "good": True,
            "spark": [0.4, 3.3, 5.3, 6.4, 7.5, 7.5, 7.6],
            "note": "n = 5 seeds",
        },
    ],
    "final_values": {
        "Retrieval": 91.4,
        "LoRA-only": 83.8,
        "Base": 75.1,
    },
}


def _resolve_width(width: int | str = 72) -> int:
    """Resolve an integer width or ``"auto"`` into a safe terminal column count."""
    if isinstance(width, str):
        cleaned = width.strip().lower()
        if cleaned == "auto":
            cols = shutil.get_terminal_size((72, 24)).columns
            return max(56, min(132, int(cols)))
        return max(40, int(float(cleaned)))
    return max(40, int(width))


def _detect_surface_dict() -> dict[str, Any]:
    """Call ``mintfig.surface.detect_surface()`` with a clean stdlib fallback."""
    try:
        from .surface import detect_surface

        info = detect_surface()
        if hasattr(info, "to_dict"):
            return dict(info.to_dict())
        return {
            "surface": str(getattr(info, "surface", "terminal_braille")),
            "harness": str(getattr(info, "harness", "terminal")),
            "protocol": str(getattr(info, "protocol", "unicode")),
            "color": bool(getattr(info, "color", True)),
            "truecolor": bool(getattr(info, "truecolor", False)),
            "in_tmux": bool(getattr(info, "in_tmux", False)),
            "width_cols": int(getattr(info, "width_cols", 72)),
            "prefers_dark": bool(getattr(info, "prefers_dark", True)),
            "supports_images": bool(getattr(info, "supports_images", False)),
            "supports_html": bool(getattr(info, "supports_html", False)),
            "reason": str(getattr(info, "reason", "fallback surface detection")),
        }
    except ImportError:
        from .terminal import detect_graphics_protocol, in_notebook

        env = os.environ
        protocol = detect_graphics_protocol()
        in_tmux = bool(env.get("TMUX"))
        tty = sys.stdout.isatty()
        no_color = bool(env.get("NO_COLOR"))
        force_color = bool(env.get("FORCE_COLOR"))
        colorterm = env.get("COLORTERM", "").lower()
        truecolor = colorterm in {"truecolor", "24bit"}
        if in_notebook():
            surface = "notebook_html"
            harness = "jupyter"
        elif protocol in {"kitty", "iterm2"} and tty:
            surface = "terminal_image"
            harness = protocol
        elif tty or force_color:
            surface = "terminal_braille"
            harness = "terminal"
        else:
            surface = "ci_plain"
            harness = "unknown"
        return {
            "surface": surface,
            "harness": harness,
            "protocol": protocol,
            "color": (not no_color) and (tty or force_color),
            "truecolor": truecolor,
            "in_tmux": in_tmux,
            "width_cols": 72,
            "prefers_dark": True,
            "supports_images": protocol in {"kitty", "iterm2"},
            "supports_html": in_notebook(),
            "reason": f"protocol={protocol}, tty={tty}",
        }


def _clip_plain(text: str, width: int, *, ascii_only: bool = False) -> str:
    """Clip plain text cleanly to ``<= width`` columns."""
    if len(text) <= width:
        return text
    if width <= 1:
        return text[:width]
    ell = "." if ascii_only else "\N{HORIZONTAL ELLIPSIS}"
    return text[: width - 1].rstrip() + ell


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


def _clamp_ansi_line(line: str, width: int) -> str:
    """Ensure a potentially ANSI-styled line does not exceed ``width`` visible chars."""
    plain = _strip_ansi(line)
    if len(plain) <= width:
        return line
    out: list[str] = []
    vis = 0
    pos = 0
    has_ansi = False
    for m in _ANSI_RE.finditer(line):
        chunk = line[pos : m.start()]
        if chunk:
            rem = width - vis
            if rem <= 0:
                break
            if len(chunk) > rem:
                out.append(chunk[:rem])
                vis += rem
                break
            out.append(chunk)
            vis += len(chunk)
        out.append(m.group(0))
        has_ansi = True
        pos = m.end()
    else:
        tail = line[pos:]
        rem = width - vis
        if tail and rem > 0:
            out.append(tail[:rem])
    result = "".join(out)
    if has_ansi and not result.endswith("\x1b[0m"):
        result += "\x1b[0m"
    return result


def _paint(text: str, *, fg_rgb: tuple[int, int, int] | None = None, bold: bool = False, dim: bool = False, use_color: bool = True) -> str:
    if not use_color or not text:
        return text
    codes: list[str] = []
    if bold:
        codes.append("1")
    if dim:
        codes.append("2")
    if fg_rgb is not None:
        r, g, b = fg_rgb
        codes.append(f"38;2;{r};{g};{b}")
    if not codes:
        return text
    return f"\x1b[{';'.join(codes)}m{text}\x1b[0m"


def _build_ablation_explanation(*, style: str = "pine", kicker: str | None = None) -> Any:
    """Build the shared 5-seed ablation training-curve ``Explanation``."""
    from .explainer import explain, trend

    ds = DEMO_DATASET
    panel = trend(
        ds["steps"],
        ds["series"],
        title="Validation accuracy over training steps",
        label="Validation accuracy",
        unit="%",
        x_label="Training step",
        highlight=ds["highlight"],
        baseline=ds["baseline"],
        band=ds["band"],
        band_label=ds["band_label"],
        events=ds["events"],
    )
    eff_kicker = ds["kicker"] if kicker is None else kicker
    return explain(
        ds["takeaway"],
        panel,
        kicker=eff_kicker or None,
        subtitle=ds["subtitle"],
        source=ds["source"],
        style=style,
        strict=False,
    )


def _build_ablation_card(*, style: str = "pine", include_panel: bool = False) -> Any:
    """Build the shared PR / release KPI ``SummaryCard`` from the 5-seed dataset."""
    from .card import card
    from .explainer import compare

    ds = DEMO_DATASET
    panel = None
    if include_panel:
        panel = compare(
            ds["final_values"],
            title="Step 600 validation accuracy (5-seed mean)",
            label="Accuracy",
            unit="%",
            highlight=ds["highlight"],
            baseline=ds["baseline"],
            show_delta=True,
        )
    return card(
        ds["card_takeaway"],
        ds["card_metrics"],
        panel=panel,
        subtitle=ds["card_subtitle"],
        source=ds["source"],
        style=style,
    )


def _render_mintchip_section(*, width: int, color: bool, ascii_only: bool) -> str | None:
    """Render a compact ``mintchip`` Braille table when ``mintchip`` is importable."""
    mc = import_mintchip()
    if mc is None:
        return None
    table_fn = getattr(mc, "table", None)
    if not callable(table_fn):
        return None
    ds = DEMO_DATASET
    rows = [
        {
            "variant": "Retrieval",
            "curve": ds["series"]["Retrieval"],
            "ci95": (90.7, 92.1),
            "vs_base": 16.3,
        },
        {
            "variant": "LoRA-only",
            "curve": ds["series"]["LoRA-only"],
            "ci95": (82.9, 84.7),
            "vs_base": 8.7,
        },
        {
            "variant": "Base",
            "curve": ds["series"]["Base"],
            "ci95": (74.1, 76.1),
            "vs_base": 0.0,
        },
    ]
    columns = {
        "variant": "text",
        "curve": {"chip": "spark", "header": "Steps 0-600"},
        "ci95": {"chip": "ci", "header": "95% CI (%)"},
        "vs_base": {"chip": "delta", "header": "vs Base", "unit": "pts"},
    }
    try:
        tbl = table_fn(
            rows,
            columns,
            highlight=("Retrieval",),
            baseline="Base",
            title="mintchip shared-scale Braille table (5 seeds)",
        )
        rendered = tbl.text(
            width=width,
            color=color,
            ascii=ascii_only,
            braille=not ascii_only,
        )
    except Exception:  # noqa: BLE001 - optional companion library fallback
        return None
    return "\n".join(_clamp_ansi_line(ln, width) for ln in str(rendered).splitlines())


def _figure_png_b64(fig: Any, *, dpi: int = 180, facecolor: str | None = None) -> str:
    """Render a Matplotlib Figure to a base64-encoded PNG string."""
    buf = io.BytesIO()
    kwargs: dict[str, Any] = {"format": "png", "dpi": dpi}
    if facecolor is not None:
        kwargs["facecolor"] = facecolor
        kwargs["edgecolor"] = facecolor
    fig.savefig(buf, **kwargs)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _ansi_to_html(text: str) -> str:
    """Convert 24-bit ANSI SGR terminal output into safe HTML ``<span>`` runs."""
    out: list[str] = []
    pos = 0
    fg: str | None = None
    bold = False
    dim = False

    def _emit_chunk(raw: str) -> None:
        if not raw:
            return
        escaped = html.escape(raw)
        styles: list[str] = []
        if fg is not None:
            styles.append(f"color:{fg}")
        if bold:
            styles.append("font-weight:700")
        if dim:
            styles.append("opacity:0.68")
        if styles:
            out.append(f'<span style="{";".join(styles)}">{escaped}</span>')
        else:
            out.append(escaped)

    for match in _ANSI_TOKEN_RE.finditer(text):
        _emit_chunk(text[pos : match.start()])
        pos = match.end()
        code_str = match.group(1)
        if not code_str or code_str == "0":
            fg = None
            bold = False
            dim = False
            continue
        parts = [int(p) if p.isdigit() else 0 for p in code_str.split(";")]
        i = 0
        while i < len(parts):
            code = parts[i]
            if code == 0:
                fg = None
                bold = False
                dim = False
                i += 1
            elif code == 1:
                bold = True
                i += 1
            elif code == 2:
                dim = True
                i += 1
            elif code == 22:
                bold = False
                dim = False
                i += 1
            elif code == 39:
                fg = None
                i += 1
            elif code == 38 and i + 4 < len(parts) and parts[i + 1] == 2:
                r, g, b = parts[i + 2], parts[i + 3], parts[i + 4]
                fg = f"rgb({r},{g},{b})"
                i += 5
            else:
                i += 1

    _emit_chunk(text[pos:])
    return "".join(out)


def build_showcase_html(
    *,
    terminal_braille: str | None = None,
    surface_info: Mapping[str, Any] | None = None,
) -> str:
    """Build the zero-CDN, self-contained 'One Dataset, Six Surfaces' showcase HTML."""
    import matplotlib.pyplot as plt

    from .bundle import to_publication
    from .interactive import render_html_fragment

    ds = DEMO_DATASET

    # 1. Surface 1: 72-col 24-bit Braille ANSI (pine)
    if terminal_braille is None:
        exp_term = _build_ablation_explanation(style="pine")
        try:
            terminal_braille = exp_term.to_text(width=72, color=True, mode="braille")
        finally:
            plt.close(exp_term.fig)
    term_html = _ansi_to_html(terminal_braille)

    # 2. Surface 2: Chat PNG (style="mint")
    exp_mint = _build_ablation_explanation(style="mint")
    try:
        mint_png_b64 = _figure_png_b64(exp_mint.fig, dpi=180, facecolor=exp_mint.theme.background)
        # 6. Surface 6: Nature 89 mm single-column publication figure + auto-drafted LaTeX caption
        with tempfile.TemporaryDirectory(prefix="mintfig-showcase-pub-") as tmp_dir:
            pub_bundle = to_publication(
                exp_mint,
                journal="nature",
                width="single",
                out_dir=Path(tmp_dir),
                include_proof=False,
                preview_dpi=240,
            )
            pub_png_b64 = base64.b64encode(pub_bundle.preview_png.read_bytes()).decode("ascii")
            pub_caption = (
                pub_bundle.caption_txt.read_text(encoding="utf-8").strip()
                if pub_bundle.caption_txt and pub_bundle.caption_txt.is_file()
                else ""
            )
            pub_tex = (
                pub_bundle.figure_tex.read_text(encoding="utf-8").strip()
                if pub_bundle.figure_tex.is_file()
                else ""
            )
            pub_passed = bool(pub_bundle.report.passed)
            pub_w_mm = pub_bundle.report.width_mm
            pub_h_mm = pub_bundle.report.height_mm
    finally:
        plt.close(exp_mint.fig)

    # 3. Surface 3: Dark Mode PNG (style="pine")
    exp_pine = _build_ablation_explanation(style="pine")
    try:
        pine_png_b64 = _figure_png_b64(exp_pine.fig, dpi=180, facecolor=exp_pine.theme.background)
    finally:
        plt.close(exp_pine.fig)

    # 4. Surface 4: PR / Release KPI Summary Card PNG
    kpi_card = _build_ablation_card(style="mint", include_panel=True)
    try:
        card_png_b64 = _figure_png_b64(kpi_card.fig, dpi=180, facecolor=kpi_card.theme.background)
    finally:
        plt.close(kpi_card.fig)

    # 5. Surface 5: Interactive Hover-to-Cite HTML fragment
    exp_html = _build_ablation_explanation(style="mintfig")
    try:
        interactive_fragment = render_html_fragment(exp_html, interactive=True)
    finally:
        plt.close(exp_html.fig)

    surf_label = ""
    if surface_info:
        surf_label = f"{surface_info.get('surface', 'terminal_braille')} · {surface_info.get('harness', 'terminal')}"

    esc = html.escape
    pub_dims = (
        f"{pub_w_mm:.1f} × {pub_h_mm:.1f} mm"
        if pub_w_mm is not None and pub_h_mm is not None
        else "89 mm single-column"
    )
    pub_badge = "Preflight PASS" if pub_passed else "Preflight Checked"

    css = """
:root {
  --bg: #F6F8F7;
  --paper: #FFFFFF;
  --ink: #12211C;
  --muted: #4E635B;
  --border: #D4E2DC;
  --accent: #0F8B6D;
  --accent-soft: #E5F4EF;
  --pine-bg: #0F1715;
  --pine-ink: #E6F2EE;
  --pine-border: #233631;
}
* { box-sizing: border-box; }
html, body {
  margin: 0;
  padding: 0;
  background: var(--bg);
  color: var(--ink);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
  line-height: 1.48;
  -webkit-font-smoothing: antialiased;
}
.page {
  max-width: 1220px;
  margin: 0 auto;
  padding: 28px 20px 52px;
}
.hero {
  background: linear-gradient(135deg, #0F1715 0%, #152822 100%);
  color: #EAF5F0;
  border-radius: 16px;
  padding: 26px 28px 24px;
  border: 1px solid #223A33;
  box-shadow: 0 10px 30px rgba(15, 23, 21, 0.12);
}
.hero-kicker {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 0.74rem;
  font-weight: 700;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: #38DDA9;
  margin-bottom: 8px;
}
.hero h1 {
  margin: 0;
  font-size: clamp(1.55rem, 2.8vw, 2.2rem);
  line-height: 1.18;
  letter-spacing: -0.02em;
}
.hero p {
  margin: 10px 0 0;
  max-width: 78ch;
  color: #B7CEC5;
  font-size: 0.96rem;
}
.hero-meta {
  margin-top: 16px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.pill {
  display: inline-flex;
  align-items: center;
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 0.76rem;
  font-weight: 600;
  background: rgba(56, 221, 169, 0.14);
  color: #7CF0C7;
  border: 1px solid rgba(56, 221, 169, 0.28);
}
.tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 22px 0 18px;
}
.tab-btn {
  appearance: none;
  border: 1px solid var(--border);
  background: var(--paper);
  color: var(--ink);
  font-size: 0.83rem;
  font-weight: 600;
  padding: 8px 13px;
  border-radius: 999px;
  cursor: pointer;
  transition: background 120ms ease, border-color 120ms ease, color 120ms ease;
}
.tab-btn:hover {
  border-color: var(--accent);
  color: var(--accent);
}
.tab-btn[aria-pressed="true"] {
  background: var(--accent);
  border-color: var(--accent);
  color: #FFFFFF;
}
.grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 18px;
}
.grid.single-view {
  grid-template-columns: minmax(0, 1fr);
}
@media (max-width: 920px) {
  .grid { grid-template-columns: minmax(0, 1fr); }
}
.card {
  background: var(--paper);
  border: 1px solid var(--border);
  border-radius: 14px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  box-shadow: 0 2px 10px rgba(18, 33, 28, 0.04);
}
.card.hidden { display: none; }
.card-head {
  padding: 14px 18px 12px;
  border-bottom: 1px solid var(--border);
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
}
.card-num {
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--accent);
}
.card-title {
  margin: 2px 0 0;
  font-size: 1.02rem;
  font-weight: 700;
  color: var(--ink);
}
.card-sub {
  margin: 3px 0 0;
  font-size: 0.82rem;
  color: var(--muted);
}
.badge {
  flex-shrink: 0;
  font-size: 0.72rem;
  font-weight: 700;
  padding: 3px 9px;
  border-radius: 999px;
  background: var(--accent-soft);
  color: var(--accent);
}
.card-body {
  padding: 16px 18px 18px;
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.img-frame {
  border-radius: 10px;
  overflow: hidden;
  border: 1px solid var(--border);
  background: #FFFFFF;
}
.img-frame.dark-frame {
  background: var(--pine-bg);
  border-color: var(--pine-border);
}
.img-frame img {
  display: block;
  width: 100%;
  height: auto;
}
.term-window {
  background: var(--pine-bg);
  color: var(--pine-ink);
  border: 1px solid var(--pine-border);
  border-radius: 10px;
  overflow: hidden;
}
.term-bar {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  background: #14211E;
  border-bottom: 1px solid var(--pine-border);
  font-size: 0.74rem;
  color: #8BA89E;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
}
.dot { width: 10px; height: 10px; border-radius: 50%; display: inline-block; }
.dot-r { background: #E06C75; }
.dot-y { background: #E5C07B; }
.dot-g { background: #38DDA9; }
.term-pre {
  margin: 0;
  padding: 14px 16px;
  overflow-x: auto;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
  font-size: 12.2px;
  line-height: 1.32;
  white-space: pre;
  color: var(--pine-ink);
}
.interactive-stage {
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 10px;
  background: #FFFFFF;
}
.caption-box {
  background: #F4F7F6;
  border: 1px solid var(--border);
  border-left: 3px solid var(--accent);
  border-radius: 8px;
  padding: 10px 12px;
  font-size: 0.82rem;
  color: #21342E;
}
.caption-box strong {
  display: block;
  font-size: 0.74rem;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--accent);
  margin-bottom: 4px;
}
.tex-details {
  font-size: 0.8rem;
  color: var(--muted);
}
.tex-details summary {
  cursor: pointer;
  font-weight: 600;
  color: var(--accent);
}
.tex-pre {
  margin: 8px 0 0;
  padding: 10px 12px;
  border-radius: 8px;
  background: #0F1715;
  color: #D7EAE2;
  overflow-x: auto;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 11.5px;
  line-height: 1.4;
}
.page-foot {
  margin-top: 24px;
  text-align: center;
  font-size: 0.82rem;
  color: var(--muted);
}
.page-foot code {
  background: #E8F0ED;
  color: #12211C;
  padding: 2px 6px;
  border-radius: 5px;
  font-size: 0.78rem;
}
"""

    js = """
(function () {
  var buttons = Array.prototype.slice.call(document.querySelectorAll('.tab-btn'));
  var cards = Array.prototype.slice.call(document.querySelectorAll('.card[data-surface]'));
  var grid = document.getElementById('showcase-grid');
  function selectSurface(target) {
    buttons.forEach(function (btn) {
      btn.setAttribute('aria-pressed', btn.getAttribute('data-target') === target ? 'true' : 'false');
    });
    if (target === 'all') {
      grid.classList.remove('single-view');
      cards.forEach(function (c) { c.classList.remove('hidden'); });
    } else {
      grid.classList.add('single-view');
      cards.forEach(function (c) {
        if (c.getAttribute('data-surface') === target) {
          c.classList.remove('hidden');
        } else {
          c.classList.add('hidden');
        }
      });
    }
  }
  buttons.forEach(function (btn) {
    btn.addEventListener('click', function () {
      selectSurface(btn.getAttribute('data-target'));
    });
  });
})();
"""

    surface_pill = f'<span class="pill">Detected: {esc(surf_label)}</span>' if surf_label else ""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>mintfig — One Dataset, Six Surfaces</title>
<style>
{css}
</style>
</head>
<body>
<main class="page">
  <header class="hero">
    <div class="hero-kicker">mintfig Showcase · Zero-CDN Self-Contained</div>
    <h1>One Dataset, Six Surfaces</h1>
    <p>{esc(ds["takeaway"])}. Every card below renders the exact same 5-seed ablation dataset (steps 0–600, 95% CI bands, LR decay event at step 300) tailored to its delivery surface.</p>
    <div class="hero-meta">
      <span class="pill">5-seed ablation · n = 5</span>
      <span class="pill">6 native surfaces</span>
      <span class="pill">Offline single-file HTML</span>
      {surface_pill}
    </div>
  </header>

  <nav class="tabs" aria-label="Filter surfaces">
    <button type="button" class="tab-btn" data-target="all" aria-pressed="true">All 6 Surfaces</button>
    <button type="button" class="tab-btn" data-target="terminal_braille" aria-pressed="false">1 · Terminal Braille</button>
    <button type="button" class="tab-btn" data-target="chat_png_mint" aria-pressed="false">2 · Chat PNG (Mint)</button>
    <button type="button" class="tab-btn" data-target="dark_png_pine" aria-pressed="false">3 · Dark Mode (Pine)</button>
    <button type="button" class="tab-btn" data-target="pr_card" aria-pressed="false">4 · PR KPI Card</button>
    <button type="button" class="tab-btn" data-target="interactive_html" aria-pressed="false">5 · Interactive HTML</button>
    <button type="button" class="tab-btn" data-target="nature_publication" aria-pressed="false">6 · Nature 89 mm</button>
  </nav>

  <section id="showcase-grid" class="grid" aria-label="Six surfaces">
    <article class="card" data-surface="terminal_braille">
      <div class="card-head">
        <div>
          <div class="card-num">Surface 1 · CLI / Coding Agent</div>
          <h2 class="card-title">Terminal 72-col Braille ANSI</h2>
          <p class="card-sub">2×4 Unicode Braille sub-pixels with 24-bit pine truecolor inside 72 columns.</p>
        </div>
        <span class="badge">72 cols</span>
      </div>
      <div class="card-body">
        <div class="term-window">
          <div class="term-bar">
            <span class="dot dot-r"></span>
            <span class="dot dot-y"></span>
            <span class="dot dot-g"></span>
            <span>mintfig demo --style pine --width 72</span>
          </div>
          <pre class="term-pre">{term_html}</pre>
        </div>
      </div>
    </article>

    <article class="card" data-surface="chat_png_mint">
      <div class="card-head">
        <div>
          <div class="card-num">Surface 2 · Light Chat / Docs</div>
          <h2 class="card-title">Chat PNG (style=&quot;mint&quot;)</h2>
          <p class="card-sub">Message-first headline, emerald accent flag, direct end labels, and 95% CI ribbons.</p>
        </div>
        <span class="badge">style=&quot;mint&quot;</span>
      </div>
      <div class="card-body">
        <div class="img-frame">
          <img src="data:image/png;base64,{mint_png_b64}" alt="{esc(ds['takeaway'])} (mint chat PNG)">
        </div>
      </div>
    </article>

    <article class="card" data-surface="dark_png_pine">
      <div class="card-head">
        <div>
          <div class="card-num">Surface 3 · Dark Mode / Slides</div>
          <h2 class="card-title">Dark Mode (style=&quot;pine&quot;)</h2>
          <p class="card-sub">Deep botanical pine canvas (#0F1715) with WCAG-checked luminous mint strokes.</p>
        </div>
        <span class="badge">style=&quot;pine&quot;</span>
      </div>
      <div class="card-body">
        <div class="img-frame dark-frame">
          <img src="data:image/png;base64,{pine_png_b64}" alt="{esc(ds['takeaway'])} (pine dark mode PNG)">
        </div>
      </div>
    </article>

    <article class="card" data-surface="pr_card">
      <div class="card-head">
        <div>
          <div class="card-num">Surface 4 · Pull Request / Release</div>
          <h2 class="card-title">PR / Release KPI Summary Card</h2>
          <p class="card-sub">4 KPI tiles with sparklines and deltas above a step-600 comparison panel.</p>
        </div>
        <span class="badge">mint.card</span>
      </div>
      <div class="card-body">
        <div class="img-frame">
          <img src="data:image/png;base64,{card_png_b64}" alt="{esc(ds['card_takeaway'])} (PR KPI summary card)">
        </div>
      </div>
    </article>

    <article class="card" data-surface="interactive_html">
      <div class="card-head">
        <div>
          <div class="card-num">Surface 5 · Browser / MCP App</div>
          <h2 class="card-title">Interactive Hover-to-Cite HTML</h2>
          <p class="card-sub">Hover any vertex for exact values &amp; 95% CIs, click to copy a citation, or switch themes live.</p>
        </div>
        <span class="badge">fig.to_html()</span>
      </div>
      <div class="card-body">
        <div class="interactive-stage">
          {interactive_fragment}
        </div>
      </div>
    </article>

    <article class="card" data-surface="nature_publication">
      <div class="card-head">
        <div>
          <div class="card-num">Surface 6 · Manuscript Submission</div>
          <h2 class="card-title"><em>Nature</em> 89 mm Publication Figure</h2>
          <p class="card-sub">Exact physical single-column geometry ({esc(pub_dims)}), journal typography, and auto-drafted LaTeX legend.</p>
        </div>
        <span class="badge">{esc(pub_badge)}</span>
      </div>
      <div class="card-body">
        <div class="img-frame">
          <img src="data:image/png;base64,{pub_png_b64}" alt="Nature 89 mm publication figure preview">
        </div>
        <div class="caption-box">
          <strong>Auto-drafted caption.txt</strong>
          <div>{esc(pub_caption)}</div>
        </div>
        <details class="tex-details">
          <summary>View LaTeX figure.tex snippet</summary>
          <pre class="tex-pre">{esc(pub_tex)}</pre>
        </details>
      </div>
    </article>
  </section>

  <footer class="page-foot">
    Generated by <code>mintfig demo --html</code> · Next: <code>mintfig mcp --install</code> · <code>mintfig plot data.csv --braille</code>
  </footer>
</main>
<script>
{js}
</script>
</body>
</html>
"""


def run_demo(
    *,
    width: int | str = 72,
    color: bool | None = None,
    style: str = "pine",
    ascii_only: bool = False,
    html_out: str | Path | None = None,
    stream: TextIO | None = None,
    quiet: bool = False,
) -> dict[str, Any]:
    """Run the 15-second live terminal demo and optionally emit the 6-surface showcase HTML.

    Parameters
    ----------
    width:
        Target terminal column width (default ``72``) or ``"auto"``.
    color:
        Enable 24-bit ANSI colors. ``None`` auto-resolves from ``NO_COLOR`` / ``FORCE_COLOR`` /
        detected surface capabilities. Forced ``False`` when ``ascii_only=True``.
    style:
        Visual theme name for the terminal demo (default ``"pine"``).
    ascii_only:
        Render pure ASCII graphics and box borders (no Unicode Braille or ANSI color).
    html_out:
        Optional output path for the zero-CDN self-contained "One Dataset, Six Surfaces" HTML.
    stream:
        Output text stream (defaults to ``sys.stdout``).
    quiet:
        When ``True``, do not print the terminal output to ``stream`` (still returned in the dict).
    """
    import matplotlib.pyplot as plt

    w = _resolve_width(width)
    surface_info = _detect_surface_dict()

    if ascii_only:
        use_color = False
    elif color is not None:
        use_color = bool(color)
    else:
        if os.environ.get("NO_COLOR"):
            use_color = False
        elif os.environ.get("FORCE_COLOR"):
            use_color = True
        else:
            use_color = bool(surface_info.get("color", True))

    # 1. Crisp 1-line detected harness/surface banner strictly fitting <= w cols
    surf_name = str(surface_info.get("surface", "terminal_braille"))
    harness_name = str(surface_info.get("harness", "terminal"))
    proto_name = str(surface_info.get("protocol", "unicode"))
    banner_plain = _clip_plain(
        f"Detected surface: {surf_name} ({harness_name}, {proto_name}, {w} cols)",
        w,
        ascii_only=ascii_only,
    )
    banner_line = _paint(banner_plain, fg_rgb=(56, 221, 169), bold=True, use_color=use_color)

    # 2. 72-col 24-bit Braille training curve with 95% CI band + event + kicker
    exp = _build_ablation_explanation(style=style)
    try:
        term_mode = "ascii" if ascii_only else "braille"
        curve_text = exp.to_text(width=w, color=use_color, mode=term_mode)
    finally:
        plt.close(exp.fig)
    curve_text = "\n".join(_clamp_ansi_line(ln, w) for ln in curve_text.splitlines())

    # 3. 72-col PR KPI Summary Card with straight box borders & inline sparklines
    kpi_card = _build_ablation_card(style=style, include_panel=False)
    try:
        card_text = kpi_card.to_terminal(
            width=w,
            color=use_color,
            ascii_only=ascii_only,
            style=style,
        )
    finally:
        plt.close(kpi_card.fig)
    card_text = "\n".join(_clamp_ansi_line(ln, w) for ln in card_text.splitlines())

    # 4. Compact mintchip Braille table (when mintchip is importable; skipped gracefully otherwise)
    chip_text = _render_mintchip_section(width=w, color=use_color, ascii_only=ascii_only)

    # 5. 2-line "Next steps" footer strictly <= w cols
    rule_ch = "-" if ascii_only else "─"
    footer_rule = _paint(rule_ch * w, dim=True, use_color=use_color)
    next_line_1 = "Next: mintfig mcp --install  |  mintfig plot data.csv --braille"
    next_line_2 = "      mintfig demo --html showcase.html"
    footer_lines: list[str] = [footer_rule]
    if len(next_line_1) <= w:
        footer_lines.append(_paint(next_line_1, fg_rgb=(56, 221, 169), use_color=use_color))
    else:
        for wrapped in textwrap.wrap(next_line_1, width=w, break_long_words=True):
            footer_lines.append(_paint(wrapped, fg_rgb=(56, 221, 169), use_color=use_color))
    if len(next_line_2) <= w:
        footer_lines.append(_paint(next_line_2, dim=True, use_color=use_color))
    else:
        for wrapped in textwrap.wrap(next_line_2.strip(), width=w, break_long_words=True):
            footer_lines.append(_paint(wrapped, dim=True, use_color=use_color))

    sections = [banner_line, "", curve_text, "", card_text]
    if chip_text:
        sections.extend(["", chip_text])
    sections.extend(["", "\n".join(footer_lines)])
    terminal_text = "\n".join(sections)

    # Optional 6-surface showcase HTML
    resolved_html_path: Path | None = None
    if html_out is not None:
        resolved_html_path = Path(html_out)
        resolved_html_path.parent.mkdir(parents=True, exist_ok=True)
        # Always render a crisp color pine Braille curve for the HTML showcase terminal card
        if not ascii_only and use_color and style == "pine" and w == 72:
            showcase_term = curve_text
        else:
            exp_show_term = _build_ablation_explanation(style="pine")
            try:
                showcase_term = exp_show_term.to_text(width=72, color=True, mode="braille")
            finally:
                plt.close(exp_show_term.fig)
        showcase_html = build_showcase_html(
            terminal_braille=showcase_term,
            surface_info=surface_info,
        )
        resolved_html_path.write_text(showcase_html, encoding="utf-8")

    if not quiet:
        target_stream = sys.stdout if stream is None else stream
        print(terminal_text, file=target_stream)

    return {
        "surface": surface_info,
        "width": w,
        "style": style,
        "color": use_color,
        "ascii_only": ascii_only,
        "terminal": terminal_text,
        "has_mintchip": bool(chip_text),
        "html_path": str(resolved_html_path.resolve()) if resolved_html_path is not None else None,
        "surfaces": [
            "terminal_braille",
            "chat_png_mint",
            "dark_png_pine",
            "pr_card",
            "interactive_html",
            "nature_publication",
        ],
    }
