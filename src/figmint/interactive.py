"""Self-contained interactive HTML delivery ("Martini-glass" view) for figmint figures.

Emits a zero-dependency, zero-CDN HTML5 document (or embeddable fragment for
Jupyter ``_repr_html_()``) with:

* Crisp inline SVG rendered directly from ``Explanation.fig`` under its theme.
* Automatic light/dark surface theming matching ``Explanation.theme``.
* Interactive toolbar, toggleable Facts & Data drawer (computed panel facts +
  raw spec data tables), Download SVG, Copy Spec JSON, and a "Critique / Ask
  Agent" panel that generates structured feedback JSON and ``fm.edit(...)``
  snippets.
"""

from __future__ import annotations

import hashlib
import html
import io
import json
import math
import re
from collections.abc import Mapping, Sequence
from typing import Any

from ._explain.core import Panel, _GlyphCapture
from ._explain.layout import Explanation, explain_from_spec
from .themes import Theme, relative_luminance

__all__ = ["render_html", "render_html_fragment"]

_XML_DECL_RE = re.compile(r"^\s*<\?xml[^>]*\?>\s*", re.IGNORECASE)
_DOCTYPE_RE = re.compile(r"^\s*<!DOCTYPE[^>]*>\s*", re.IGNORECASE)


def _ensure_explanation(exp_or_spec: Explanation | Mapping[str, Any]) -> Explanation:
    """Resolve an ``Explanation`` instance or build one from a JSON spec dict."""
    if isinstance(exp_or_spec, Explanation):
        return exp_or_spec
    if isinstance(exp_or_spec, Mapping):
        return explain_from_spec(exp_or_spec)
    raise TypeError(
        "Expected an Explanation or a spec mapping, "
        f"got {type(exp_or_spec).__name__}."
    )


def _safe_json_for_script(obj: Any) -> str:
    """Serialize ``obj`` to JSON safe for embedding inside an HTML ``<script>`` tag.

    Replaces ``<``, ``>``, ``&``, and Unicode line separators so untrusted data
    can never terminate a ``<script>`` block or inject HTML comments.
    """
    raw = json.dumps(obj, ensure_ascii=False, indent=2)
    return (
        raw.replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def _render_inline_svg(exp: Explanation) -> str:
    """Export ``exp.fig`` to a clean, embeddable inline ``<svg>`` string."""
    buf = io.BytesIO()
    with exp.theme.rc_context(exp.spec), _GlyphCapture():
        exp.fig.savefig(
            buf,
            format="svg",
            facecolor=exp.theme.background,
            edgecolor=exp.theme.background,
        )
    svg = buf.getvalue().decode("utf-8")
    svg = _XML_DECL_RE.sub("", svg)
    svg = _DOCTYPE_RE.sub("", svg)
    return svg.strip()


def _fmt_cell(val: Any) -> str:
    """Format a scalar cell cleanly for data-drawer tables."""
    if val is None:
        return "—"
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, float):
        if not math.isfinite(val):
            return "—"
        if abs(val - round(val)) < 1e-9 and abs(val) < 1e12:
            return f"{round(val):,}"
        return f"{val:.4g}"
    if isinstance(val, int):
        return f"{val:,}"
    return str(val)


def _is_numeric_cell(val: Any) -> bool:
    if isinstance(val, bool) or val is None:
        return False
    if isinstance(val, (int, float)):
        return math.isfinite(float(val))
    return False


def _panel_data_table(panel: Panel) -> tuple[list[str], list[list[str]], list[bool], str | None]:
    """Extract ``(headers, rows, numeric_flags, note)`` from a panel's spec."""
    spec = panel.spec
    kind = panel.kind
    unit_suffix = f" ({panel.unit})" if panel.unit else ""

    if kind == "compare":
        values = spec.get("values")
        if isinstance(values, Mapping) and values:
            first_val = next(iter(values.values()))
            if isinstance(first_val, Mapping):
                series_names: list[str] = []
                for sub in values.values():
                    if isinstance(sub, Mapping):
                        for sk in sub:
                            if str(sk) not in series_names:
                                series_names.append(str(sk))
                headers = ["Item", *[f"{s}{unit_suffix}" for s in series_names]]
                rows = [
                    [
                        str(item),
                        *[_fmt_cell(sub.get(s) if isinstance(sub, Mapping) else None) for s in series_names],
                    ]
                    for item, sub in values.items()
                ]
                return headers, rows, [False, *([True] * len(series_names))], None
            items = list(values.items())
            if spec.get("sort", True):
                items.sort(
                    key=lambda kv: float(kv[1]) if _is_numeric_cell(kv[1]) else float("-inf"),
                    reverse=True,
                )
            val_col = (panel.label or "Value") + unit_suffix
            headers = ["Item", val_col]
            rows = [[str(k), _fmt_cell(v)] for k, v in items]
            return headers, rows, [False, True], None

    if kind == "share":
        parts = spec.get("parts")
        if isinstance(parts, Mapping) and parts:
            items = sorted(
                parts.items(),
                key=lambda kv: float(kv[1]) if _is_numeric_cell(kv[1]) else float("-inf"),
                reverse=True,
            )
            total = sum(float(v) for _, v in items if _is_numeric_cell(v))
            val_col = (panel.label or "Value") + unit_suffix
            headers = ["Part", val_col, "Share"]
            rows = []
            for k, v in items:
                pct = f"{(float(v) / total * 100.0):.1f}%" if total > 0 and _is_numeric_cell(v) else "—"
                rows.append([str(k), _fmt_cell(v), pct])
            return headers, rows, [False, True, True], None

    if kind == "table":
        cols = [str(c) for c in (spec.get("columns") or [])]
        raw_rows = spec.get("rows") or []
        if cols and isinstance(raw_rows, Sequence):
            num_flags = []
            for c_idx in range(len(cols)):
                col_vals = [r[c_idx] for r in raw_rows if isinstance(r, Sequence) and c_idx < len(r)]
                num_flags.append(bool(col_vals) and all(_is_numeric_cell(v) or v is None for v in col_vals))
            rows = [
                [_fmt_cell(r[c]) if c < len(r) else "—" for c in range(len(cols))]
                for r in raw_rows
                if isinstance(r, Sequence)
            ]
            return cols, rows, num_flags, None

    if kind == "trend":
        x_vals = spec.get("x") or []
        series = spec.get("series")
        x_hdr = str(spec.get("x_label") or "x")
        if isinstance(series, Mapping) and series:
            names = [str(k) for k in series]
            headers = [x_hdr, *[f"{n}{unit_suffix}" for n in names]]
            n_rows = max((len(v) for v in series.values() if isinstance(v, Sequence)), default=0)
            max_show = 40
            rows = []
            for idx in range(min(n_rows, max_show)):
                xv = _fmt_cell(x_vals[idx]) if idx < len(x_vals) else str(idx)
                row = [xv]
                for n in names:
                    seq = series.get(n)
                    val = seq[idx] if isinstance(seq, Sequence) and idx < len(seq) else None
                    row.append(_fmt_cell(val))
                rows.append(row)
            note = f"Showing first {max_show} of {n_rows} points." if n_rows > max_show else None
            return headers, rows, [False, *([True] * len(names))], note
        if isinstance(series, Sequence) and not isinstance(series, (str, bytes)):
            val_col = (panel.label or "Value") + unit_suffix
            headers = [x_hdr, val_col]
            max_show = 40
            rows = [
                [_fmt_cell(x_vals[i]) if i < len(x_vals) else str(i), _fmt_cell(series[i])]
                for i in range(min(len(series), max_show))
            ]
            note = f"Showing first {max_show} of {len(series)} points." if len(series) > max_show else None
            return headers, rows, [False, True], note
        points = spec.get("points")
        if isinstance(points, Mapping) and points:
            raw_names = [str(k) for k in points]
            disp_names = [n if n else (panel.label or "Value") for n in raw_names]
            headers = [x_hdr, *[f"{dn}{unit_suffix}" for dn in disp_names]]
            n_rows = max(
                (len(v) for v in points.values() if isinstance(v, Sequence)),
                default=0,
            )
            max_show = 40
            rows = []
            for idx in range(min(n_rows, max_show)):
                xv = _fmt_cell(x_vals[idx]) if idx < len(x_vals) else str(idx)
                row = [xv]
                for rname in raw_names:
                    buckets = points.get(rname)
                    mean_val: float | None = None
                    if isinstance(buckets, Sequence) and idx < len(buckets):
                        bucket = buckets[idx]
                        if isinstance(bucket, Sequence) and not isinstance(bucket, (str, bytes)):
                            nums = [float(v) for v in bucket if _is_numeric_cell(v)]
                            if nums:
                                mean_val = sum(nums) / len(nums)
                        elif _is_numeric_cell(bucket):
                            mean_val = float(bucket)
                    row.append(_fmt_cell(mean_val))
                rows.append(row)
            note = (
                f"Showing per-x replicate means (first {max_show} of {n_rows} points)."
                if n_rows > max_show
                else "Values show per-x replicate means."
            )
            return headers, rows, [False, *([True] * len(raw_names))], note

    if kind == "matrix":
        r_labels = [str(r) for r in (spec.get("rows") or [])]
        c_labels = [str(c) for c in (spec.get("cols") or [])]
        vals = spec.get("values") or []
        if c_labels and isinstance(vals, Sequence):
            headers = ["", *c_labels]
            rows = []
            for r_idx, row_vals in enumerate(vals):
                rl = r_labels[r_idx] if r_idx < len(r_labels) else f"r{r_idx + 1}"
                if isinstance(row_vals, Sequence):
                    rows.append([rl, *[_fmt_cell(v) for v in row_vals]])
            return headers, rows, [False, *([True] * len(c_labels))], None

    if kind == "change":
        before = spec.get("before") or {}
        after = spec.get("after") or {}
        labels = spec.get("labels") or ["Before", "After"]
        lbl_b = str(labels[0]) if len(labels) >= 1 else "Before"
        lbl_a = str(labels[1]) if len(labels) >= 2 else "After"
        if isinstance(before, Mapping) and isinstance(after, Mapping):
            headers = ["Item", f"{lbl_b}{unit_suffix}", f"{lbl_a}{unit_suffix}", f"Delta{unit_suffix}"]
            rows = []
            for item, bv in before.items():
                av = after.get(item)
                if _is_numeric_cell(bv) and _is_numeric_cell(av):
                    delta = float(av) - float(bv)
                    delta_str = f"{delta:+.4g}" if abs(delta) < 1e12 else _fmt_cell(delta)
                else:
                    delta_str = "—"
                rows.append([str(item), _fmt_cell(bv), _fmt_cell(av), delta_str])
            return headers, rows, [False, True, True, True], None

    if kind == "distribution":
        groups = spec.get("groups")
        if isinstance(groups, Mapping):
            headers = ["Group", "n", f"Min{unit_suffix}", f"Median{unit_suffix}", f"Max{unit_suffix}"]
            rows = []
            for gname, vals in groups.items():
                nums = sorted(float(v) for v in vals if _is_numeric_cell(v))
                if nums:
                    mid = len(nums) // 2
                    med = nums[mid] if len(nums) % 2 else 0.5 * (nums[mid - 1] + nums[mid])
                    rows.append([str(gname), str(len(nums)), _fmt_cell(nums[0]), _fmt_cell(med), _fmt_cell(nums[-1])])
            return headers, rows, [False, True, True, True, True], None
        if isinstance(groups, Sequence) and not isinstance(groups, (str, bytes)):
            nums = sorted(float(v) for v in groups if _is_numeric_cell(v))
            if nums:
                mid = len(nums) // 2
                med = nums[mid] if len(nums) % 2 else 0.5 * (nums[mid - 1] + nums[mid])
                headers = ["Series", "n", f"Min{unit_suffix}", f"Median{unit_suffix}", f"Max{unit_suffix}"]
                rows = [[panel.label or "Values", str(len(nums)), _fmt_cell(nums[0]), _fmt_cell(med), _fmt_cell(nums[-1])]]
                return headers, rows, [False, True, True, True, True], None

    if kind == "relate":
        xs = spec.get("x") or []
        ys = spec.get("y") or []
        names = spec.get("names")
        groups = spec.get("groups")
        xh = str(spec.get("x_label") or "x")
        yh = str(spec.get("y_label") or panel.label or "y") + unit_suffix
        headers = []
        num_flags = []
        if names:
            headers.append("Name")
            num_flags.append(False)
        headers.extend([xh, yh])
        num_flags.extend([True, True])
        if groups:
            headers.append("Group")
            num_flags.append(False)
        n = min(len(xs), len(ys))
        max_show = 40
        rows = []
        for i in range(min(n, max_show)):
            row = []
            if names:
                row.append(str(names[i]) if i < len(names) else "")
            row.extend([_fmt_cell(xs[i]), _fmt_cell(ys[i])])
            if groups:
                row.append(str(groups[i]) if i < len(groups) else "")
            rows.append(row)
        note = f"Showing first {max_show} of {n} observations." if n > max_show else None
        return headers, rows, num_flags, note

    return [], [], [], None


def _render_table_html(
    headers: list[str],
    rows: list[list[str]],
    num_flags: list[bool],
    note: str | None = None,
) -> str:
    if not headers or not rows:
        return ""
    th_cells = "".join(
        ('<th class="fm-num">' if num_flags[i] else "<th>") + f"{html.escape(h, quote=True)}</th>"
        for i, h in enumerate(headers)
    )
    body_rows = []
    for row in rows:
        td_cells = "".join(
            ('<td class="fm-num">' if i < len(num_flags) and num_flags[i] else "<td>")
            + f"{html.escape(cell, quote=True)}</td>"
            for i, cell in enumerate(row)
        )
        body_rows.append(f"<tr>{td_cells}</tr>")
    note_html = (
        f'<p class="fm-table-note">{html.escape(note, quote=True)}</p>' if note else ""
    )
    return (
        '<div class="fm-table-wrap">'
        '<table class="fm-data-table">'
        f"<thead><tr>{th_cells}</tr></thead>"
        f"<tbody>{''.join(body_rows)}</tbody>"
        "</table>"
        f"{note_html}"
        "</div>"
    )


def _theme_tokens(theme: Theme) -> dict[str, str]:
    """Derive light- or dark-aware UI surface tokens from ``theme``."""
    is_dark = relative_luminance(theme.background) < 0.2
    accent = theme.accent_colors[0] if theme.accent_colors else "#CD4324"
    primary = theme.series_colors[0] if theme.series_colors else "#1F5A9D"
    if is_dark:
        surface = "#1C222C"
        surface_alt = "#232A36"
        border = theme.grid if theme.grid != theme.background else "#2E3746"
        button_bg = "#252D3A"
        button_hover = "#303A4B"
        input_bg = "#11151B"
        shadow = "0 10px 30px rgba(0, 0, 0, 0.45)"
        mode = "dark"
    else:
        surface = "#F7F8FA" if theme.background.upper() == "#FFFFFF" else theme.background
        surface_alt = "#EFF2F6" if theme.background.upper() == "#FFFFFF" else "#E9E5DC"
        border = theme.grid if theme.grid != theme.background else "#D9DFE6"
        button_bg = "#FFFFFF"
        button_hover = "#EEF2F6"
        input_bg = "#FFFFFF"
        shadow = "0 6px 24px rgba(15, 23, 42, 0.08)"
        mode = "light"
    return {
        "mode": mode,
        "bg": theme.background,
        "ink": theme.ink,
        "muted": theme.muted,
        "axis": theme.axis,
        "grid": theme.grid,
        "accent": accent,
        "primary": primary,
        "surface": surface,
        "surface_alt": surface_alt,
        "border": border,
        "button_bg": button_bg,
        "button_hover": button_hover,
        "input_bg": input_bg,
        "shadow": shadow,
    }


def _css_block(root_id: str, tokens: dict[str, str], max_width_px: int) -> str:
    sel = f"#{root_id}"
    return f"""<style>
{sel} {{
  --fm-bg: {tokens['bg']};
  --fm-ink: {tokens['ink']};
  --fm-muted: {tokens['muted']};
  --fm-border: {tokens['border']};
  --fm-surface: {tokens['surface']};
  --fm-surface-alt: {tokens['surface_alt']};
  --fm-accent: {tokens['accent']};
  --fm-primary: {tokens['primary']};
  --fm-btn-bg: {tokens['button_bg']};
  --fm-btn-hover: {tokens['button_hover']};
  --fm-input-bg: {tokens['input_bg']};
  --fm-shadow: {tokens['shadow']};
  color: var(--fm-ink);
  background: var(--fm-bg);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
  max-width: {max_width_px}px;
  margin: 0 auto;
  border: 1px solid var(--fm-border);
  border-radius: 10px;
  box-shadow: var(--fm-shadow);
  overflow: hidden;
  box-sizing: border-box;
}}
{sel} *, {sel} *::before, {sel} *::after {{ box-sizing: border-box; }}
{sel} .fm-figure-stage {{
  background: var(--fm-bg);
  padding: 12px 12px 8px;
}}
{sel} .fm-svg-wrap {{
  width: 100%;
  overflow-x: auto;
}}
{sel} .fm-svg-wrap svg {{
  width: 100%;
  height: auto;
  display: block;
}}
{sel} .fm-toolbar {{
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 10px 14px;
  background: var(--fm-surface);
  border-top: 1px solid var(--fm-border);
  font-size: 12.5px;
}}
{sel} .fm-toolbar-group {{
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
}}
{sel} .fm-btn {{
  appearance: none;
  border: 1px solid var(--fm-border);
  background: var(--fm-btn-bg);
  color: var(--fm-ink);
  padding: 5px 10px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.12s ease, border-color 0.12s ease;
}}
{sel} .fm-btn:hover {{
  background: var(--fm-btn-hover);
  border-color: var(--fm-muted);
}}
{sel} .fm-btn[aria-expanded="true"], {sel} .fm-btn-accent {{
  border-color: var(--fm-accent);
  color: var(--fm-accent);
}}
{sel} .fm-status {{
  font-size: 11.5px;
  color: var(--fm-muted);
  margin-left: 4px;
}}
{sel} .fm-drawer {{
  border-top: 1px solid var(--fm-border);
  background: var(--fm-surface);
  padding: 14px 16px;
  font-size: 13px;
  line-height: 1.45;
}}
{sel} .fm-drawer[hidden] {{ display: none; }}
{sel} .fm-drawer h3 {{
  margin: 0 0 10px;
  font-size: 13.5px;
  font-weight: 600;
  color: var(--fm-ink);
}}
{sel} .fm-panel-card {{
  background: var(--fm-bg);
  border: 1px solid var(--fm-border);
  border-radius: 8px;
  padding: 10px 12px;
  margin-bottom: 10px;
}}
{sel} .fm-panel-card:last-child {{ margin-bottom: 0; }}
{sel} .fm-panel-head {{
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 8px;
  margin-bottom: 6px;
}}
{sel} .fm-badge {{
  display: inline-block;
  font-size: 11px;
  font-weight: 600;
  padding: 1px 6px;
  border-radius: 4px;
  background: var(--fm-surface-alt);
  color: var(--fm-accent);
  border: 1px solid var(--fm-border);
}}
{sel} .fm-panel-title {{
  font-weight: 600;
  color: var(--fm-ink);
}}
{sel} .fm-panel-kind {{
  font-size: 11.5px;
  color: var(--fm-muted);
}}
{sel} .fm-facts {{
  margin: 6px 0 8px 18px;
  padding: 0;
  color: var(--fm-ink);
}}
{sel} .fm-facts li {{ margin-bottom: 3px; }}
{sel} .fm-table-wrap {{
  overflow-x: auto;
  margin-top: 6px;
}}
{sel} .fm-data-table {{
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}}
{sel} .fm-data-table th, {sel} .fm-data-table td {{
  text-align: left;
  padding: 4px 8px;
  border-bottom: 1px solid var(--fm-border);
  color: var(--fm-ink);
}}
{sel} .fm-data-table th {{
  font-weight: 600;
  color: var(--fm-muted);
  background: var(--fm-surface);
}}
{sel} .fm-data-table th.fm-num, {sel} .fm-data-table td.fm-num {{
  text-align: right;
}}
{sel} .fm-table-note {{
  margin: 4px 0 0;
  font-size: 11px;
  color: var(--fm-muted);
}}
{sel} .fm-meta-row {{
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 10px;
  font-size: 11.5px;
  color: var(--fm-muted);
}}
{sel} .fm-critique-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 10px;
  margin-bottom: 10px;
}}
{sel} .fm-field label {{
  display: block;
  font-size: 11.5px;
  font-weight: 600;
  color: var(--fm-muted);
  margin-bottom: 4px;
}}
{sel} .fm-field select, {sel} .fm-field textarea {{
  width: 100%;
  background: var(--fm-input-bg);
  color: var(--fm-ink);
  border: 1px solid var(--fm-border);
  border-radius: 6px;
  padding: 6px 8px;
  font-family: inherit;
  font-size: 12.5px;
}}
{sel} .fm-field textarea {{
  min-height: 62px;
  resize: vertical;
}}
{sel} .fm-preview {{
  background: var(--fm-input-bg);
  border: 1px solid var(--fm-border);
  border-radius: 6px;
  padding: 8px 10px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 11.5px;
  white-space: pre-wrap;
  word-break: break-word;
  margin: 8px 0;
  color: var(--fm-ink);
}}
{sel} .fm-sr-only {{
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}}
</style>"""


def _js_block(root_id: str, spec_json_safe: str, takeaway_json_safe: str) -> str:
    return f"""<script>
(function() {{
  var root = document.getElementById({json.dumps(root_id)});
  if (!root) return;
  var SPEC = {spec_json_safe};
  var TAKEAWAY = {takeaway_json_safe};
  var statusEl = root.querySelector('[data-fm-status]');

  function setStatus(msg) {{
    if (!statusEl) return;
    statusEl.textContent = msg;
    window.setTimeout(function() {{
      if (statusEl.textContent === msg) statusEl.textContent = '';
    }}, 2600);
  }}

  function copyText(text, label) {{
    if (navigator.clipboard && navigator.clipboard.writeText) {{
      navigator.clipboard.writeText(text).then(function() {{
        setStatus('Copied ' + label);
      }}, function() {{
        fallbackCopy(text, label);
      }});
    }} else {{
      fallbackCopy(text, label);
    }}
  }}

  function fallbackCopy(text, label) {{
    var ta = document.createElement('textarea');
    ta.value = text;
    ta.setAttribute('readonly', '');
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    try {{
      document.execCommand('copy');
      setStatus('Copied ' + label);
    }} catch (e) {{
      setStatus('Copy failed');
    }}
    document.body.removeChild(ta);
  }}

  function toggleDrawer(btnAttr, drawerAttr) {{
    var btn = root.querySelector('[' + btnAttr + ']');
    var drawer = root.querySelector('[' + drawerAttr + ']');
    if (!btn || !drawer) return;
    btn.addEventListener('click', function() {{
      var open = drawer.hasAttribute('hidden');
      if (open) {{
        drawer.removeAttribute('hidden');
        btn.setAttribute('aria-expanded', 'true');
      }} else {{
        drawer.setAttribute('hidden', '');
        btn.setAttribute('aria-expanded', 'false');
      }}
    }});
  }}

  toggleDrawer('data-fm-toggle-facts', 'data-fm-drawer-facts');
  toggleDrawer('data-fm-toggle-critique', 'data-fm-drawer-critique');

  var dlBtn = root.querySelector('[data-fm-download-svg]');
  if (dlBtn) {{
    dlBtn.addEventListener('click', function() {{
      var svg = root.querySelector('.fm-svg-wrap svg');
      if (!svg) return;
      var xml = new XMLSerializer().serializeToString(svg);
      var blob = new Blob([xml], {{ type: 'image/svg+xml;charset=utf-8' }});
      var url = URL.createObjectURL(blob);
      var a = document.createElement('a');
      a.href = url;
      a.download = 'figmint-figure.svg';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      setStatus('Downloaded SVG');
    }});
  }}

  var copySpecBtn = root.querySelector('[data-fm-copy-spec]');
  if (copySpecBtn) {{
    copySpecBtn.addEventListener('click', function() {{
      copyText(JSON.stringify(SPEC, null, 2), 'spec JSON');
    }});
  }}

  var panelSel = root.querySelector('[data-fm-critique-panel]');
  var actionSel = root.querySelector('[data-fm-critique-action]');
  var noteInput = root.querySelector('[data-fm-critique-note]');
  var previewEl = root.querySelector('[data-fm-critique-preview]');
  var copyJsonBtn = root.querySelector('[data-fm-copy-feedback]');
  var copyEditBtn = root.querySelector('[data-fm-copy-edit]');

  function buildCritique() {{
    var panel = panelSel ? panelSel.value : 'figure';
    var action = actionSel ? actionSel.value : 'highlight';
    var note = noteInput ? noteInput.value.trim() : '';
    var payload = {{
      target: panel,
      action: action,
      note: note,
      takeaway: TAKEAWAY
    }};
    var snippet = 'fm.edit(fig, panel=' + JSON.stringify(panel) +
      ', action=' + JSON.stringify(action) +
      ', note=' + JSON.stringify(note) + ')';
    return {{ payload: payload, snippet: snippet }};
  }}

  function refreshPreview() {{
    if (!previewEl) return;
    var c = buildCritique();
    previewEl.textContent = c.snippet + '\\n\\n' + JSON.stringify(c.payload, null, 2);
  }}

  [panelSel, actionSel, noteInput].forEach(function(el) {{
    if (el) el.addEventListener('input', refreshPreview);
    if (el) el.addEventListener('change', refreshPreview);
  }});
  refreshPreview();

  if (copyJsonBtn) {{
    copyJsonBtn.addEventListener('click', function() {{
      copyText(JSON.stringify(buildCritique().payload, null, 2), 'feedback JSON');
    }});
  }}
  if (copyEditBtn) {{
    copyEditBtn.addEventListener('click', function() {{
      copyText(buildCritique().snippet, 'fm.edit(...) snippet');
    }});
  }}
}})();
</script>"""


def render_html_fragment(
    exp_or_spec: Explanation | Mapping[str, Any],
    *,
    interactive: bool = True,
) -> str:
    """Render a self-contained embeddable HTML fragment (for Jupyter ``_repr_html_()``).

    Contains zero external CDN references; all CSS, SVG, and vanilla JS are
    inlined and scoped to a unique root container ID.
    """
    exp = _ensure_explanation(exp_or_spec)
    svg_markup = _render_inline_svg(exp)
    spec_dict = exp.to_spec()
    tokens = _theme_tokens(exp.theme)

    digest = hashlib.sha256(
        json.dumps(spec_dict, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()[:10]
    root_id = f"fm-{digest}"
    max_width_px = max(480, int(exp.display_width_px) + 48)

    css = _css_block(root_id, tokens, max_width_px)
    escaped_alt = html.escape(exp.alt_text, quote=True)
    escaped_takeaway = html.escape(exp.takeaway, quote=True)

    figure_section = (
        '<div class="fm-figure-stage">'
        f'<div class="fm-svg-wrap" role="img" aria-label="{escaped_alt}">{svg_markup}</div>'
        f'<figcaption class="fm-sr-only">{escaped_takeaway}</figcaption>'
        "</div>"
    )

    if not interactive:
        return (
            f"{css}\n"
            f'<figure id="{root_id}" class="fm-root" data-fm-theme="{html.escape(exp.theme.name, quote=True)}" '
            f'data-fm-mode="{tokens["mode"]}">'
            f"{figure_section}"
            "</figure>"
        )

    # Facts & Data drawer
    panel_cards: list[str] = []
    panel_options: list[str] = ['<option value="figure">Whole figure</option>']
    for key, panel in exp.panels.items():
        esc_key = html.escape(key, quote=True)
        esc_kind = html.escape(panel.kind, quote=True)
        esc_title = html.escape(panel.title or panel.describe, quote=True)
        opt_label = f"Panel {key}: {panel.title}" if panel.title else f"Panel {key} ({panel.kind})"
        panel_options.append(
            f'<option value="{esc_key}">{html.escape(opt_label, quote=True)}</option>'
        )
        facts_items = "".join(
            f"<li>{html.escape(fact, quote=True)}</li>" for fact in panel.facts
        )
        facts_html = f'<ul class="fm-facts">{facts_items}</ul>' if facts_items else ""
        headers, rows, num_flags, t_note = _panel_data_table(panel)
        table_html = _render_table_html(headers, rows, num_flags, t_note)
        panel_cards.append(
            '<div class="fm-panel-card">'
            '<div class="fm-panel-head">'
            f'<span class="fm-badge">Panel {esc_key}</span>'
            f'<span class="fm-panel-title">{esc_title}</span>'
            f'<span class="fm-panel-kind">({esc_kind})</span>'
            "</div>"
            f"{facts_html}"
            f"{table_html}"
            "</div>"
        )

    meta_parts = [
        f"Style: {exp.theme.name}",
        f"Palette: {exp.palette or 'default'}",
        f"Size: {exp.width_mm:.0f} × {exp.height_mm:.0f} mm",
    ]
    if exp.source:
        meta_parts.append(f"Source: {exp.source}")
    if exp.note:
        meta_parts.append(f"Note: {exp.note}")
    meta_html = (
        '<div class="fm-meta-row">'
        + "".join(f"<span>{html.escape(part, quote=True)}</span>" for part in meta_parts)
        + "</div>"
    )

    facts_drawer = (
        '<section class="fm-drawer" data-fm-drawer-facts hidden aria-label="Facts and Data">'
        "<h3>Facts &amp; Underlying Data</h3>"
        f"{''.join(panel_cards)}"
        f"{meta_html}"
        "</section>"
    )

    critique_actions = [
        ("highlight", "Highlight item / series"),
        ("drop", "Drop panel or item"),
        ("zoom", "Zoom / focus range"),
        ("style", "Adjust style / palette"),
        ("re-title", "Re-title takeaway / panel"),
        ("question", "Ask question about data"),
    ]
    action_options = "".join(
        f'<option value="{val}">{html.escape(lbl, quote=True)}</option>'
        for val, lbl in critique_actions
    )
    critique_drawer = (
        '<section class="fm-drawer" data-fm-drawer-critique hidden aria-label="Critique or ask agent">'
        "<h3>Click to Critique / Ask Agent</h3>"
        '<div class="fm-critique-grid">'
        '<div class="fm-field">'
        f'<label for="{root_id}-panel">Panel</label>'
        f'<select id="{root_id}-panel" data-fm-critique-panel>{"".join(panel_options)}</select>'
        "</div>"
        '<div class="fm-field">'
        f'<label for="{root_id}-action">Action</label>'
        f'<select id="{root_id}-action" data-fm-critique-action>{action_options}</select>'
        "</div>"
        "</div>"
        '<div class="fm-field">'
        f'<label for="{root_id}-note">Note / instruction for agent</label>'
        f'<textarea id="{root_id}-note" data-fm-critique-note '
        'placeholder="e.g., Highlight checkout vs search and annotate the v2.3 deploy"></textarea>'
        "</div>"
        '<pre class="fm-preview" data-fm-critique-preview></pre>'
        '<div class="fm-toolbar-group">'
        '<button type="button" class="fm-btn fm-btn-accent" data-fm-copy-edit>Copy fm.edit(...)</button>'
        '<button type="button" class="fm-btn" data-fm-copy-feedback>Copy Feedback JSON</button>'
        "</div>"
        "</section>"
    )

    toolbar = (
        '<div class="fm-toolbar">'
        '<div class="fm-toolbar-group">'
        '<button type="button" class="fm-btn" data-fm-toggle-facts aria-expanded="false">Facts &amp; Data</button>'
        '<button type="button" class="fm-btn" data-fm-toggle-critique aria-expanded="false">Critique / Ask Agent</button>'
        "</div>"
        '<div class="fm-toolbar-group">'
        '<button type="button" class="fm-btn" data-fm-download-svg>Download SVG</button>'
        '<button type="button" class="fm-btn" data-fm-copy-spec>Copy Spec JSON</button>'
        '<span class="fm-status" data-fm-status role="status" aria-live="polite"></span>'
        "</div>"
        "</div>"
    )

    js = _js_block(
        root_id,
        _safe_json_for_script(spec_dict),
        _safe_json_for_script(exp.takeaway),
    )

    return (
        f"{css}\n"
        f'<figure id="{root_id}" class="fm-root" data-fm-theme="{html.escape(exp.theme.name, quote=True)}" '
        f'data-fm-mode="{tokens["mode"]}">'
        f"{figure_section}"
        f"{toolbar}"
        f"{facts_drawer}"
        f"{critique_drawer}"
        "</figure>\n"
        f"{js}"
    )


def render_html(
    exp_or_spec: Explanation | Mapping[str, Any],
    *,
    interactive: bool = True,
) -> str:
    """Render a standalone, self-contained HTML5 document for an ``Explanation`` or spec dict."""
    exp = _ensure_explanation(exp_or_spec)
    fragment = render_html_fragment(exp, interactive=interactive)
    tokens = _theme_tokens(exp.theme)
    page_title = html.escape(exp.takeaway, quote=True)
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{page_title}</title>\n"
        "<style>\n"
        f"html, body {{ margin: 0; padding: 16px; background: {tokens['bg']}; color: {tokens['ink']}; }}\n"
        "</style>\n"
        "</head>\n"
        "<body>\n"
        f"{fragment}\n"
        "</body>\n"
        "</html>\n"
    )
