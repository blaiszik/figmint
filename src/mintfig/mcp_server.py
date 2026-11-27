"""Zero-dependency JSON-RPC 2.0 stdio MCP server & interactive MCP App for mintfig.

Exposes five message-first visualization tools over standard Model Context Protocol
(JSON-RPC 2.0 over newline-delimited stdin/stdout) plus a self-contained interactive
MCP App resource (``ui://mintfig/figure`` with MIME ``text/html;profile=mcp-app``)
compatible with Antigravity, Claude Desktop, Claude Code, Cursor, and Gemini CLI.

Tools
-----
- ``mint_explain``: Render a multi-panel ``mint.explain`` JSON spec (Braille + PNG + interactive UI).
- ``mint_check``: Audit an existing Matplotlib ``.py`` script or ``.ipynb`` notebook.
- ``mint_plot_file``: Plot CSV/TSV/JSON/JSONL/hyperfine/pytest/JUnit files automatically.
- ``mint_card``: Render a PR/release KPI summary card (terminal card + PNG + interactive UI).
- ``mint_chip``: Render an inline ``mintchip`` chip or shared-scale table when installed.

CLI Entry Point
---------------
- ``mintfig mcp``: Start the stdio JSON-RPC 2.0 MCP server.
- ``mintfig mcp --install [--target ...] [--dry-run]``: Register mintfig in agent hosts.
- ``mintfig mcp --status [--json]``: Report which MCP hosts have mintfig configured.
- ``mintfig mcp --print-config``: Print the standard ``mcpServers`` JSON config snippet.
"""

from __future__ import annotations

import argparse
import base64
import contextlib
import html as _html
import io
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, TextIO

from . import __version__

__all__ = [
    "APP_MIME_TYPE",
    "APP_RESOURCE_URI",
    "DEFAULT_PROTOCOL_VERSION",
    "MCP_SERVER_ENTRY",
    "MCP_TARGETS",
    "SUPPORTED_PROTOCOL_VERSIONS",
    "MCPServer",
    "cli_mcp",
    "default_mcp_config_paths",
    "install_mcp_config",
    "mcp_status",
    "print_mcp_config",
    "run_stdio_server",
]

#: MCP App resource URI for interactive figure rendering (SEP-1865).
APP_RESOURCE_URI: str = "ui://mintfig/figure"
#: MCP App HTML resource MIME type.
APP_MIME_TYPE: str = "text/html;profile=mcp-app"
#: Primary MCP protocol version advertised by this server.
DEFAULT_PROTOCOL_VERSION: str = "2025-03-26"
#: Recognized MCP protocol versions (client version echoed when supported).
SUPPORTED_PROTOCOL_VERSIONS: tuple[str, ...] = ("2025-03-26", "2024-11-05")
#: Standard zero-install ``uvx`` MCP server registration entry.
MCP_SERVER_ENTRY: dict[str, Any] = {
    "command": "uvx",
    "args": ["mintfig", "mcp"],
}
#: Canonical MCP host target identifiers for ``mintfig mcp --install``.
MCP_TARGETS: tuple[str, ...] = (
    "claude-code",
    "claude-desktop",
    "cursor",
    "gemini",
    "antigravity",
)
_TARGET_ALIASES: dict[str, str] = {
    "claude": "claude-code",
    "claude-code": "claude-code",
    "claude_code": "claude-code",
    "claude-desktop": "claude-desktop",
    "claude_desktop": "claude-desktop",
    "desktop": "claude-desktop",
    "cursor": "cursor",
    "gemini": "gemini",
    "gemini-cli": "gemini",
    "gemini_cli": "gemini",
    "antigravity": "antigravity",
    "agy": "antigravity",
}

_PROTOCOL_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_STYLE_TAG_RE = re.compile(r"<style\b[^>]*>.*?</style>", re.DOTALL | re.IGNORECASE)
_BODY_RE = re.compile(r"<body\b[^>]*>(.*)</body>", re.DOTALL | re.IGNORECASE)
_SCRIPT_RE = re.compile(r"<script\b[^>]*>.*?</script>", re.DOTALL | re.IGNORECASE)

_UI_META: dict[str, Any] = {
    "ui": {"resourceUri": APP_RESOURCE_URI},
    "ui/resourceUri": APP_RESOURCE_URI,
}

_SERVER_INSTRUCTIONS = (
    "mintfig renders message-first scientific and engineering figures with verified facts, "
    "72-column Unicode/Braille terminal summaries, high-DPI PNGs, and an interactive "
    "ui://mintfig/figure MCP App viewer. Use mint_explain for multi-panel specs, "
    "mint_plot_file for CSV/TSV/JSON/hyperfine/pytest/JUnit files, mint_card for PR/release "
    "KPI cards, mint_check to audit Matplotlib scripts or notebooks, and mint_chip for inline "
    "word-sized graphics when mintchip is installed."
)


# --------------------------------------------------------------------------- #
# Rendering & matplotlib safety helpers
# --------------------------------------------------------------------------- #


def _ensure_agg_backend() -> None:
    """Select Matplotlib's non-interactive Agg backend before pyplot is imported."""
    if not os.environ.get("MPLBACKEND"):
        os.environ["MPLBACKEND"] = "Agg"
    import matplotlib

    backend = str(matplotlib.get_backend()).lower()
    if "agg" not in backend:
        with contextlib.suppress(Exception):
            matplotlib.use("Agg", force=True)


def _figure_to_png_b64(fig: Any, *, facecolor: str = "#FFFFFF", dpi: int = 150) -> str:
    """Render a Matplotlib figure to a base64-encoded PNG string."""
    buf = io.BytesIO()
    fig.savefig(
        buf,
        format="png",
        dpi=dpi,
        facecolor=facecolor,
        edgecolor=facecolor,
    )
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _safe_json_for_script(obj: Any) -> str:
    """Serialize JSON safely for embedding inside an HTML ``<script>`` block."""
    raw = json.dumps(obj, ensure_ascii=False, separators=(",", ":"), default=str)
    return (
        raw.replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def _extract_card_fragment(full_html: str) -> str:
    """Extract a self-contained embeddable HTML fragment from ``SummaryCard.to_html()``."""
    styles = _STYLE_TAG_RE.findall(full_html)
    body_match = _BODY_RE.search(full_html)
    body_inner = body_match.group(1).strip() if body_match else full_html
    # Scope card body styles lightly so they blend cleanly inside the MCP App shell.
    cleaned_styles: list[str] = []
    for st in styles:
        s = st.replace("html,body{", ".mf-card-shell{").replace("body{", ".mf-card-shell{")
        cleaned_styles.append(s)
    return "\n".join(cleaned_styles) + f'\n<div class="mf-card-shell">{body_inner}</div>'


def _load_junit_xml_rows(path: Path) -> list[dict[str, Any]]:
    """Parse a JUnit XML report into tabular rows for ``mint_plot_file``."""
    try:
        tree = ET.parse(path)
    except ET.ParseError as exc:
        raise ValueError(f"{path.name} is not valid JUnit XML: {exc}") from exc

    root = tree.getroot()
    cases = list(root.iter("testcase"))
    if not cases:
        raise ValueError(f"{path.name} contains no <testcase> elements.")

    rows: list[dict[str, Any]] = []
    for case in cases:
        name = str(case.attrib.get("name") or "unnamed").strip()
        classname = str(case.attrib.get("classname") or "").strip()
        raw_time = case.attrib.get("time", "0")
        try:
            time_ms = round(float(raw_time) * 1000.0, 3)
        except ValueError:
            time_ms = 0.0
        if case.find("failure") is not None:
            status = "failed"
        elif case.find("error") is not None:
            status = "error"
        elif case.find("skipped") is not None:
            status = "skipped"
        else:
            status = "passed"
        short_name = name if not classname else f"{classname.rsplit('.', 1)[-1]}.{name}"
        rows.append(
            {
                "test": short_name,
                "duration_ms": time_ms,
                "status": status,
            }
        )
    return rows


def _derive_takeaway(panel: Any, path: Path) -> str:
    """Derive a clean, factual takeaway sentence when the caller omits one."""
    facts = list(getattr(panel, "facts", ()) or ())
    if facts:
        top = str(facts[0]).strip().rstrip(".")
        if top:
            return f"{path.stem}: {top}"
    desc = str(getattr(panel, "describe", "") or "").strip()
    if desc:
        return f"{path.stem}: {desc}"
    return f"Summary of {path.name}"


def _build_panel_from_rows(rows: list[dict[str, Any]], kind: str, title: str | None = None) -> Any:
    """Build an explicit mintfig panel from loaded rows for ``mint_plot_file``."""
    import mintfig as mint

    if not rows:
        raise ValueError("Data file contains zero rows.")

    cols = list(dict.fromkeys(str(k) for row in rows for k in row))
    num_cols = [
        c
        for c in cols
        if any(isinstance(r.get(c), (int, float)) and not isinstance(r.get(c), bool) for r in rows)
    ]
    cat_cols = [c for c in cols if c not in num_cols]
    kw: dict[str, Any] = {}
    if title:
        kw["title"] = title

    if kind == "compare":
        if cat_cols:
            kw["name"] = cat_cols[0]
        if num_cols:
            kw["value"] = num_cols[0]
        return mint.compare(rows, **kw)
    if kind == "share":
        if cat_cols:
            kw["name"] = cat_cols[0]
        if num_cols:
            kw["value"] = num_cols[0]
        return mint.share(rows, **kw)
    if kind == "table":
        return mint.table(rows, **kw)
    if kind in {"distribution", "histogram"}:
        if cat_cols:
            kw["group"] = cat_cols[0]
        if num_cols:
            kw["value"] = num_cols[0]
        return mint.histogram(rows, **kw) if kind == "histogram" else mint.distribution(rows, **kw)
    if kind == "trend":
        x_col = cols[0]
        y_col = num_cols[1] if len(num_cols) >= 2 and x_col == num_cols[0] else (num_cols[0] if num_cols else cols[-1])
        series_col = cat_cols[0] if cat_cols and cat_cols[0] != x_col else None
        return mint.trend(x_col, series_col, y=y_col, data=rows, **kw)
    if kind == "change":
        if len(num_cols) < 2:
            raise ValueError("kind='change' requires at least two numeric columns (before, after).")
        if cat_cols:
            kw["name"] = cat_cols[0]
        return mint.change(num_cols[0], num_cols[1], data=rows, **kw)
    if kind == "relate":
        if len(num_cols) < 2:
            raise ValueError("kind='relate' requires at least two numeric columns (x, y).")
        if cat_cols:
            kw["names"] = cat_cols[0]
        return mint.relate(num_cols[0], num_cols[1], data=rows, **kw)
    if kind == "matrix":
        return mint.matrix(rows, **kw)
    if kind == "waterfall":
        if cat_cols:
            kw["name"] = cat_cols[0]
        if num_cols:
            kw["value"] = num_cols[0]
        return mint.waterfall(rows, **kw)
    if kind == "timeline":
        spans = []
        for r in rows:
            vals = list(r.values())
            if len(vals) >= 3:
                spans.append((str(vals[0]), float(vals[1]), float(vals[2])))
        return mint.timeline(spans, **kw)
    if kind == "flow":
        stages = []
        name_c = cat_cols[0] if cat_cols else cols[0]
        val_c = num_cols[0] if num_cols else cols[1]
        for r in rows:
            stages.append((str(r.get(name_c, "")), float(r.get(val_c, 0.0))))
        return mint.flow(stages, **kw)
    if kind == "forest":
        name_c = cat_cols[0] if cat_cols else cols[0]
        val_c = num_cols[0] if num_cols else cols[1]
        data_map = {str(r[name_c]): float(r[val_c]) for r in rows if r.get(val_c) is not None}
        return mint.forest(data_map, **kw)
    raise ValueError(
        f"Unsupported panel kind {kind!r}. Use 'auto', compare, trend, change, "
        "distribution, histogram, relate, matrix, table, waterfall, timeline, flow, forest, or share."
    )


# --------------------------------------------------------------------------- #
# Interactive MCP App HTML Viewer (ui://mintfig/figure)
# --------------------------------------------------------------------------- #


def _build_mcp_app_html(initial_payload: Mapping[str, Any] | None = None) -> str:
    """Build the zero-CDN, CSP-compliant interactive MCP App HTML document.

    Implements the SEP-1865 MCP Apps JSON-RPC 2.0 ``postMessage`` handshake
    (``ui/initialize`` -> ``ui/notifications/initialized``), live host theme &
    CSS variable syncing (``ui/notifications/host-context-changed``), live tool
    result updates (``ui/notifications/tool-result`` & ``ui/notifications/tool-input``),
    auto-resize (``ui/notifications/size-changed``), theme switching
    (Auto / Light / Dark / Mint / Pine), Copy SVG, hover-to-cite, and brush-to-prompt.
    """
    init_json = _safe_json_for_script(dict(initial_payload) if initial_payload else None)
    initial_title = _html.escape(
        str(initial_payload.get("takeaway") or "mintfig Interactive Figure")
        if initial_payload
        else "mintfig Interactive Figure",
        quote=True,
    )
    app_version = _html.escape(__version__, quote=True)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>{initial_title}</title>
<style>
:root {{
  --app-bg: var(--color-background-primary, #FFFFFF);
  --app-surface: var(--color-background-secondary, #F7F9FB);
  --app-ink: var(--color-text-primary, #1A1D21);
  --app-muted: var(--color-text-secondary, #5B6570);
  --app-border: var(--color-border-primary, #DDE3EA);
  --app-accent: #0F8B6D;
  --app-good: #0F8B6D;
  --app-bad: #C93B2B;
  --app-font: var(--font-sans, system-ui, -apple-system, "Segoe UI", Helvetica, Arial, sans-serif);
}}
@media (prefers-color-scheme: dark) {{
  :root:not([data-mf-scheme="light"]):not([data-mf-scheme="mint"]) {{
    --app-bg: var(--color-background-primary, #14181F);
    --app-surface: var(--color-background-secondary, #1C222B);
    --app-ink: var(--color-text-primary, #E6E9EE);
    --app-muted: var(--color-text-secondary, #98A3B3);
    --app-border: var(--color-border-primary, #2B3340);
    --app-accent: #34D399;
    --app-good: #34D399;
    --app-bad: #F47E62;
  }}
}}
:root[data-mf-scheme="light"] {{
  --app-bg: #FFFFFF; --app-surface: #F7F9FB; --app-ink: #1A1D21;
  --app-muted: #5B6570; --app-border: #DDE3EA; --app-accent: #0F8B6D;
}}
:root[data-mf-scheme="dark"] {{
  --app-bg: #14181F; --app-surface: #1C222B; --app-ink: #E6E9EE;
  --app-muted: #98A3B3; --app-border: #2B3340; --app-accent: #34D399;
}}
:root[data-mf-scheme="mint"] {{
  --app-bg: #F6FBF9; --app-surface: #EAF5F0; --app-ink: #13251F;
  --app-muted: #46635A; --app-border: #CBE0D7; --app-accent: #0F8B6D;
}}
:root[data-mf-scheme="pine"] {{
  --app-bg: #0D1916; --app-surface: #132420; --app-ink: #E4F2EC;
  --app-muted: #8FAEA3; --app-border: #233E37; --app-accent: #34D399;
}}
* {{ box-sizing: border-box; }}
html, body {{
  margin: 0; padding: 0;
  background: var(--app-bg); color: var(--app-ink);
  font: 13px/1.45 var(--app-font);
}}
.mf-app {{
  max-width: 960px; margin: 0 auto; padding: 10px 12px 14px;
}}
.mf-app-bar {{
  display: flex; align-items: center; justify-content: space-between;
  flex-wrap: wrap; gap: 8px;
  padding-bottom: 8px; margin-bottom: 8px;
  border-bottom: 1px solid var(--app-border);
}}
.mf-app-brand {{
  display: inline-flex; align-items: center; gap: 6px;
  font-size: 12px; font-weight: 600; color: var(--app-muted);
}}
.mf-app-dot {{
  width: 8px; height: 8px; border-radius: 50%; background: var(--app-accent);
  display: inline-block;
}}
.mf-app-badge {{
  font-size: 11px; font-weight: 600; padding: 1px 7px; border-radius: 999px;
  border: 1px solid var(--app-border); color: var(--app-muted);
}}
.mf-app-badge.ship {{ color: var(--app-good); border-color: var(--app-good); }}
.mf-app-badge.fix {{ color: var(--app-bad); border-color: var(--app-bad); }}
.mf-app-controls {{
  display: inline-flex; align-items: center; flex-wrap: wrap; gap: 6px;
}}
.mf-app-themes {{
  display: inline-flex; align-items: center; gap: 2px;
  padding: 2px 3px; border: 1px solid var(--app-border); border-radius: 999px;
  background: var(--app-surface);
}}
.mf-app-controls button {{
  all: unset; cursor: pointer; font-size: 11px; line-height: 1.4;
  padding: 2px 8px; border-radius: 999px; color: var(--app-muted);
  transition: background .12s, color .12s;
}}
.mf-app-controls button:hover, .mf-app-controls button:focus-visible {{
  color: var(--app-ink);
}}
.mf-app-themes button[aria-pressed="true"] {{
  background: var(--app-ink); color: var(--app-bg); font-weight: 600;
}}
.mf-app-btn {{
  border: 1px solid var(--app-border) !important;
  background: var(--app-surface) !important;
}}
.mf-app-stage {{
  min-height: 80px;
}}
.mf-app-stage .mf-ctrl {{
  display: none;
}}
.mf-app-empty {{
  padding: 28px 16px; text-align: center; color: var(--app-muted);
  border: 1px dashed var(--app-border); border-radius: 8px;
  background: var(--app-surface);
}}
.mf-app-status {{
  margin-top: 6px; min-height: 18px; font-size: 11.5px; color: var(--app-muted);
  display: flex; align-items: center; justify-content: space-between; gap: 8px;
}}
.mf-app-facts {{
  margin-top: 8px; padding-top: 6px; border-top: 1px solid var(--app-border);
  font-size: 12px; color: var(--app-muted);
}}
.mf-app-facts summary {{
  cursor: pointer; font-weight: 600; color: var(--app-ink);
}}
.mf-app-facts ul {{
  margin: 4px 0 0; padding-left: 18px;
}}
.mf-app-img {{
  display: block; max-width: 100%; height: auto; border-radius: 6px;
}}
</style>
</head>
<body>
<div class="mf-app" id="mf-app-root" data-app-version="{app_version}">
  <div class="mf-app-bar">
    <div class="mf-app-brand">
      <span class="mf-app-dot" aria-hidden="true"></span>
      <span>mintfig</span>
      <span class="mf-app-badge" id="mf-app-badge" hidden></span>
    </div>
    <div class="mf-app-controls" role="group" aria-label="Viewer controls">
      <span class="mf-app-themes" role="group" aria-label="Theme">
        <button type="button" data-app-theme="auto" aria-pressed="true">Auto</button>
        <button type="button" data-app-theme="light" aria-pressed="false">Light</button>
        <button type="button" data-app-theme="dark" aria-pressed="false">Dark</button>
        <button type="button" data-app-theme="mint" aria-pressed="false">Mint</button>
        <button type="button" data-app-theme="pine" aria-pressed="false">Pine</button>
      </span>
      <button type="button" class="mf-app-btn" id="mf-app-copy-svg">Copy SVG</button>
    </div>
  </div>
  <div class="mf-app-stage" id="mf-app-stage">
    <div class="mf-app-empty">Waiting for a mintfig tool result (<code>mint_explain</code>, <code>mint_plot_file</code>, or <code>mint_card</code>)…</div>
  </div>
  <details class="mf-app-facts" id="mf-app-facts" hidden>
    <summary>Verified facts</summary>
    <ul id="mf-app-facts-list"></ul>
  </details>
  <div class="mf-app-status">
    <span id="mf-app-hint">Hover marks to inspect · Click to cite · Drag trend/relate panels to brush-to-prompt</span>
    <span id="mf-app-toast" role="status" aria-live="polite"></span>
  </div>
</div>
<script>
(function() {{
  var INITIAL = {init_json};
  var stage = document.getElementById("mf-app-stage");
  var badge = document.getElementById("mf-app-badge");
  var factsWrap = document.getElementById("mf-app-facts");
  var factsList = document.getElementById("mf-app-facts-list");
  var toast = document.getElementById("mf-app-toast");
  var copyBtn = document.getElementById("mf-app-copy-svg");
  var themeBtns = document.querySelectorAll("[data-app-theme]");
  var currentTheme = "auto";
  var hostCaps = {{}};
  var nextRpcId = 1;
  var pendingInitId = null;

  function showToast(msg) {{
    if (!toast) return;
    toast.textContent = msg;
    clearTimeout(showToast._t);
    showToast._t = setTimeout(function() {{ toast.textContent = ""; }}, 3200);
  }}

  function postToHost(msg) {{
    if (window.parent && window.parent !== window) {{
      window.parent.postMessage(msg, "*");
    }}
  }}

  function sendNotification(method, params) {{
    postToHost({{ jsonrpc: "2.0", method: method, params: params || {{}} }});
  }}

  function sendRequest(method, params) {{
    var id = nextRpcId++;
    postToHost({{ jsonrpc: "2.0", id: id, method: method, params: params || {{}} }});
    return id;
  }}

  function applyHostContext(ctx) {{
    if (!ctx || typeof ctx !== "object") return;
    if (ctx.styles && ctx.styles.variables && typeof ctx.styles.variables === "object") {{
      var rootStyle = document.documentElement.style;
      var vars = ctx.styles.variables;
      for (var key in vars) {{
        if (Object.prototype.hasOwnProperty.call(vars, key) && typeof vars[key] === "string") {{
          rootStyle.setProperty(key, vars[key]);
        }}
      }}
    }}
    if (currentTheme === "auto" && (ctx.theme === "dark" || ctx.theme === "light")) {{
      applySchemeAttr(ctx.theme, false);
    }}
  }}

  function applySchemeAttr(name, updateButtons) {{
    var H = document.documentElement;
    var roots = stage.querySelectorAll(".mf-root");
    if (name === "auto") {{
      H.removeAttribute("data-mf-scheme");
      for (var i = 0; i < roots.length; i++) roots[i].removeAttribute("data-mf-scheme");
    }} else {{
      H.setAttribute("data-mf-scheme", name);
      for (var j = 0; j < roots.length; j++) roots[j].setAttribute("data-mf-scheme", name);
    }}
    if (updateButtons) {{
      currentTheme = name;
      for (var k = 0; k < themeBtns.length; k++) {{
        var match = themeBtns[k].getAttribute("data-app-theme") === name;
        themeBtns[k].setAttribute("aria-pressed", match ? "true" : "false");
      }}
      showToast("Theme: " + name);
    }}
  }}

  function visibleSvg() {{
    var svgs = stage.querySelectorAll("svg");
    for (var i = 0; i < svgs.length; i++) {{
      if (svgs[i].getClientRects().length) return svgs[i];
    }}
    return svgs[0] || null;
  }}

  function copyText(text, label) {{
    if (navigator.clipboard && navigator.clipboard.writeText) {{
      navigator.clipboard.writeText(text).then(
        function() {{ showToast(label); }},
        function() {{ showToast(label); }}
      );
    }} else {{
      showToast(label);
    }}
  }}

  function mountHtmlFragment(markup) {{
    stage.innerHTML = markup;
    // Execute embedded <script> tags so hover-to-cite & brush-to-prompt bind live.
    var scripts = stage.querySelectorAll("script");
    for (var i = 0; i < scripts.length; i++) {{
      var old = scripts[i];
      var fresh = document.createElement("script");
      fresh.textContent = old.textContent || "";
      old.parentNode.replaceChild(fresh, old);
    }}
    if (currentTheme !== "auto") {{
      applySchemeAttr(currentTheme, false);
    }}
  }}

  function renderPayload(payload) {{
    if (!payload || typeof payload !== "object") return;
    if (payload.takeaway) {{
      document.title = String(payload.takeaway);
    }}
    if (typeof payload.ship === "boolean") {{
      badge.hidden = false;
      badge.textContent = payload.ship ? "SHIP" : "FIX";
      badge.className = "mf-app-badge " + (payload.ship ? "ship" : "fix");
    }} else {{
      badge.hidden = true;
    }}
    if (typeof payload.html === "string" && payload.html.trim()) {{
      mountHtmlFragment(payload.html);
    }} else if (typeof payload.image_data === "string" && payload.image_data) {{
      stage.innerHTML = '<img class="mf-app-img" alt="mintfig figure" src="data:image/png;base64,' + payload.image_data + '">';
    }} else if (typeof payload.text === "string" && payload.text) {{
      var pre = document.createElement("pre");
      pre.textContent = payload.text;
      stage.innerHTML = "";
      stage.appendChild(pre);
    }}
    if (Array.isArray(payload.facts) && payload.facts.length) {{
      factsList.innerHTML = "";
      for (var i = 0; i < payload.facts.length; i++) {{
        var li = document.createElement("li");
        li.textContent = String(payload.facts[i]);
        factsList.appendChild(li);
      }}
      factsWrap.hidden = false;
    }} else {{
      factsWrap.hidden = true;
    }}
    reportSize();
  }}

  function reportSize() {{
    var h = Math.ceil(document.documentElement.scrollHeight || document.body.scrollHeight || 320);
    sendNotification("ui/notifications/size-changed", {{ height: Math.max(150, Math.min(800, h)) }});
  }}

  for (var t = 0; t < themeBtns.length; t++) {{
    themeBtns[t].addEventListener("click", function(ev) {{
      var name = ev.currentTarget.getAttribute("data-app-theme");
      if (name) applySchemeAttr(name, true);
    }});
  }}

  if (copyBtn) {{
    copyBtn.addEventListener("click", function() {{
      var svg = visibleSvg();
      if (!svg) {{
        showToast("No SVG available yet");
        return;
      }}
      var xml = new XMLSerializer().serializeToString(svg);
      copyText(xml, "Copied SVG");
    }});
  }}

  // Mirror inner figure citation/brush notes to the shell toast & host model context if available.
  stage.addEventListener("pointerup", function() {{
    setTimeout(function() {{
      var noteEl = stage.querySelector(".mf-note");
      if (noteEl && noteEl.textContent) {{
        var txt = noteEl.textContent.trim();
        showToast(txt);
        if (hostCaps.updateModelContext && txt.indexOf("copied prompt:") === 0) {{
          sendRequest("ui/update-model-context", {{
            content: [{{ type: "text", text: txt.replace(/^copied prompt:\\s*/, "") }}]
          }});
        }}
      }}
    }}, 30);
  }});

  // MCP Apps SEP-1865 JSON-RPC 2.0 PostMessage listener
  window.addEventListener("message", function(event) {{
    var msg = event.data;
    if (!msg || typeof msg !== "object" || msg.jsonrpc !== "2.0") return;

    // Response to our ui/initialize request
    if (msg.id !== undefined && msg.id === pendingInitId && msg.result) {{
      hostCaps = msg.result.hostCapabilities || {{}};
      applyHostContext(msg.result.hostContext);
      sendNotification("ui/notifications/initialized", {{}});
      reportSize();
      return;
    }}

    // Incoming host requests
    if (msg.method === "ping" && msg.id !== undefined) {{
      postToHost({{ jsonrpc: "2.0", id: msg.id, result: {{}} }});
      return;
    }}

    // Incoming host notifications
    if (msg.method === "ui/notifications/host-context-changed") {{
      applyHostContext(msg.params);
      return;
    }}
    if (msg.method === "ui/notifications/tool-input") {{
      var args = (msg.params && msg.params.arguments) || {{}};
      var label = args.takeaway || args.path || "figure";
      showToast("Rendering " + String(label) + "…");
      return;
    }}
    if (msg.method === "ui/notifications/tool-result") {{
      var res = msg.params || {{}};
      var sc = res.structuredContent || null;
      if (sc && typeof sc === "object") {{
        renderPayload(sc);
      }} else if (Array.isArray(res.content)) {{
        var fallback = {{}};
        for (var i = 0; i < res.content.length; i++) {{
          var item = res.content[i];
          if (item && item.type === "image" && item.data) fallback.image_data = item.data;
          if (item && item.type === "text" && item.text && !fallback.text) fallback.text = item.text;
        }}
        renderPayload(fallback);
      }}
    }}
  }});

  if (INITIAL) {{
    renderPayload(INITIAL);
  }}

  if (typeof ResizeObserver !== "undefined") {{
    new ResizeObserver(function() {{ reportSize(); }}).observe(document.body);
  }}

  // Initiate MCP Apps handshake with parent host frame
  pendingInitId = sendRequest("ui/initialize", {{
    protocolVersion: "2026-01-26",
    appInfo: {{ name: "mintfig", version: "{app_version}" }},
    appCapabilities: {{}}
  }});
}})();
</script>
</body>
</html>
"""


# --------------------------------------------------------------------------- #
# Tool Schemas
# --------------------------------------------------------------------------- #


def _tool_definitions() -> list[dict[str, Any]]:
    """Return the 5 MCP tool definitions with crisp JSON Schemas."""
    return [
        {
            "name": "mint_explain",
            "title": "Explain Data with mintfig",
            "description": (
                "Render a message-first multi-panel mintfig figure from a JSON spec. "
                "Returns a 72-column Unicode/Braille summary, verified facts + ship gate, "
                "a PNG image, and updates the interactive ui://mintfig/figure MCP App."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "takeaway": {
                        "type": "string",
                        "description": "One-sentence conclusion stating the main finding and number.",
                    },
                    "panels": {
                        "type": "array",
                        "minItems": 1,
                        "description": (
                            "List of panel specs, each with 'kind' (compare, trend, change, "
                            "distribution, histogram, relate, matrix, table, waterfall, "
                            "timeline, flow, forest, share) and its data fields."
                        ),
                        "items": {"type": "object"},
                    },
                    "kicker": {"type": "string", "description": "Optional short uppercase kicker."},
                    "subtitle": {"type": "string", "description": "Optional subtitle with context/units."},
                    "source": {"type": "string", "description": "Optional data source footnote."},
                    "note": {"type": "string", "description": "Optional explanatory note."},
                    "style": {
                        "type": "string",
                        "description": "Visual theme (mintfig, mint, pine, dark, editorial, paper, bold, mono).",
                    },
                    "palette": {
                        "type": "string",
                        "description": "Color palette override (default, mint, okabe, editorial, vibrant).",
                    },
                    "accent": {"type": "string", "description": "Optional hex accent color override."},
                    "width": {
                        "oneOf": [{"type": "string"}, {"type": "number"}],
                        "description": "Width preset ('narrow', 'chat', 'slide') or width in mm.",
                    },
                    "out": {
                        "type": "string",
                        "description": "Optional output file path (.png, .svg, .pdf, .html) to save on disk.",
                    },
                },
                "required": ["takeaway", "panels"],
            },
            "_meta": dict(_UI_META),
        },
        {
            "name": "mint_check",
            "title": "Audit Matplotlib Script or Notebook",
            "description": (
                "Audit an existing Matplotlib .py script or .ipynb notebook against its own data "
                "and visual legibility gates (text size, overlap, clipping, claim-number mismatch). "
                "Returns ship status, issues, fix_hint, and extracted data facts."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to a .py Matplotlib script or .ipynb Jupyter notebook.",
                    },
                    "claim": {
                        "type": "string",
                        "description": "Optional explicit claim/takeaway text to verify numbers against.",
                    },
                    "width": {
                        "oneOf": [{"type": "string"}, {"type": "integer"}],
                        "description": "Target display width ('narrow', 'chat', 'slide', or CSS px).",
                        "default": "chat",
                    },
                },
                "required": ["path"],
            },
        },
        {
            "name": "mint_plot_file",
            "title": "Plot Data File Automatically",
            "description": (
                "Load a CSV, TSV, JSON, JSONL, hyperfine, pytest-benchmark, go/cargo bench, "
                "or JUnit XML file, auto-infer the best mintfig panel, and return a 72-column "
                "Braille summary, verified facts, PNG image, and interactive MCP App UI."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to CSV, TSV, JSON, JSONL, hyperfine, pytest, or JUnit XML file.",
                    },
                    "takeaway": {
                        "type": "string",
                        "description": "Optional one-sentence takeaway (auto-derived from top fact if omitted).",
                    },
                    "kind": {
                        "type": "string",
                        "description": "Panel kind ('auto', compare, trend, change, distribution, histogram, relate, matrix, table, waterfall, timeline, flow, forest, share).",
                        "default": "auto",
                    },
                    "style": {"type": "string", "description": "Optional visual theme name."},
                    "palette": {"type": "string", "description": "Optional palette override."},
                    "out": {
                        "type": "string",
                        "description": "Optional output file path (.png, .svg, .pdf, .html) to save on disk.",
                    },
                },
                "required": ["path"],
            },
            "_meta": dict(_UI_META),
        },
        {
            "name": "mint_card",
            "title": "Render KPI Summary Card",
            "description": (
                "Render a compact PR or release KPI summary card (metrics tiles with deltas and "
                "sparklines + optional evidence panel). Returns a 72-col terminal KPI card, PNG "
                "image, verified facts, and interactive MCP App UI."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "takeaway": {
                        "type": "string",
                        "description": "Headline takeaway summarizing the PR/release impact.",
                    },
                    "metrics": {
                        "type": "array",
                        "minItems": 1,
                        "description": "List of KPI metric objects: {label, value, delta?, good?, spark?, note?}.",
                        "items": {"type": "object"},
                    },
                    "panel": {
                        "type": "object",
                        "description": "Optional mintfig panel spec below the KPI strip.",
                    },
                    "subtitle": {"type": "string", "description": "Optional context subtitle."},
                    "source": {"type": "string", "description": "Optional source footnote."},
                    "style": {"type": "string", "description": "Optional theme name."},
                    "palette": {"type": "string", "description": "Optional palette name."},
                    "accent": {"type": "string", "description": "Optional hex accent color."},
                    "width": {
                        "oneOf": [{"type": "string"}, {"type": "number"}],
                        "description": "Optional width preset ('narrow', 'chat', 'slide') or mm float.",
                    },
                    "out": {
                        "type": "string",
                        "description": "Optional output path (.png, .svg, .pdf, .html) to save on disk.",
                    },
                },
                "required": ["takeaway", "metrics"],
            },
            "_meta": dict(_UI_META),
        },
        {
            "name": "mint_chip",
            "title": "Render Inline mintchip Graphic or Table",
            "description": (
                "Render an inline word-sized mintchip graphic (spark, bar, ci, dist, delta, "
                "gauge, strip, share, ratio, timeline, rank, waterfall, funnel, num, bullet, "
                "heat, hist, status) or a shared-scale table (kind='table') when mintchip is installed."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "kind": {
                        "type": "string",
                        "description": "mintchip kind name (e.g. 'spark', 'bar', 'ci', 'delta', 'table').",
                    },
                    "args": {
                        "type": "array",
                        "description": "Optional positional arguments passed to mintchip.<kind>(*args, **kwargs).",
                        "default": [],
                    },
                    "kwargs": {
                        "type": "object",
                        "description": "Optional keyword arguments passed to mintchip.<kind>(*args, **kwargs).",
                        "default": {},
                    },
                    "braille": {
                        "type": "boolean",
                        "description": "Render high-res Braille glyphs for text/markdown output.",
                        "default": False,
                    },
                    "theme": {
                        "type": "string",
                        "description": "Theme for SVG/HTML rendering ('auto', 'light', 'dark', 'mono').",
                        "default": "auto",
                    },
                    "format": {
                        "type": "string",
                        "enum": ["text", "markdown", "svg", "html", "all"],
                        "description": "Output format (text, markdown, svg, html, or all).",
                        "default": "text",
                    },
                },
                "required": ["kind"],
            },
        },
    ]


# --------------------------------------------------------------------------- #
# JSON-RPC 2.0 MCP Server
# --------------------------------------------------------------------------- #


class MCPServer:
    """Stateful, zero-dependency JSON-RPC 2.0 MCP server for mintfig."""

    def __init__(self) -> None:
        self._initialized: bool = False
        self._last_figure: dict[str, Any] | None = None
        self._tools: list[dict[str, Any]] = _tool_definitions()
        self._tool_names: frozenset[str] = frozenset(t["name"] for t in self._tools)

    @property
    def last_figure(self) -> dict[str, Any] | None:
        """Return the latest rendered figure payload cached for ``ui://mintfig/figure``."""
        return self._last_figure

    def render_app_html(self) -> str:
        """Return the current ``ui://mintfig/figure`` MCP App HTML document."""
        return _build_mcp_app_html(self._last_figure)

    # -- JSON-RPC 2.0 dispatch ------------------------------------------------

    def handle_message(self, raw: Mapping[str, Any]) -> dict[str, Any] | None:
        """Dispatch a single decoded JSON-RPC 2.0 request/notification.

        Returns a JSON-RPC 2.0 response dict, or ``None`` for notifications.
        """
        if not isinstance(raw, Mapping) or raw.get("jsonrpc") != "2.0":
            return self._error(raw.get("id") if isinstance(raw, Mapping) else None, -32600, "Invalid Request: expected jsonrpc '2.0'.")

        method = raw.get("method")
        msg_id = raw.get("id")
        is_notification = "id" not in raw
        params = raw.get("params")
        if params is None:
            params = {}
        if not isinstance(params, Mapping):
            if is_notification:
                return None
            return self._error(msg_id, -32602, "Invalid params: expected JSON object.")

        if not isinstance(method, str) or not method:
            if is_notification:
                return None
            return self._error(msg_id, -32600, "Invalid Request: missing method string.")

        # Notifications produce no JSON-RPC response.
        if method == "notifications/initialized":
            self._initialized = True
            return None
        if method.startswith("notifications/"):
            return None

        if method == "initialize":
            result = self._handle_initialize(params)
            return self._result(msg_id, result)
        if method == "ping":
            return self._result(msg_id, {})
        if method == "tools/list":
            return self._result(msg_id, {"tools": self._tools})
        if method == "tools/call":
            return self._handle_tools_call(msg_id, params)
        if method == "resources/list":
            return self._result(msg_id, self._handle_resources_list())
        if method == "resources/read":
            return self._handle_resources_read(msg_id, params)

        if is_notification:
            return None
        return self._error(msg_id, -32601, f"Method not found: {method}")

    def handle_line(self, line: str) -> str | None:
        """Parse one JSON-RPC line and return a serialized JSON response line or ``None``."""
        stripped = line.strip()
        if not stripped:
            return None
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError as exc:
            return json.dumps(self._error(None, -32700, f"Parse error: {exc}"), ensure_ascii=False)
        if not isinstance(payload, Mapping):
            return json.dumps(
                self._error(None, -32600, "Invalid Request: top-level JSON must be an object."),
                ensure_ascii=False,
            )
        response = self.handle_message(payload)
        if response is None:
            return None
        return json.dumps(response, ensure_ascii=False, default=str)

    def serve(self, stdin: TextIO | None = None, stdout: TextIO | None = None) -> int:
        """Run the newline-delimited JSON-RPC 2.0 stdio loop until EOF."""
        in_stream = stdin if stdin is not None else sys.stdin
        out_stream = stdout if stdout is not None else sys.stdout
        for line in in_stream:
            reply = self.handle_line(line)
            if reply is not None:
                out_stream.write(reply + "\n")
                out_stream.flush()
        return 0

    @staticmethod
    def _result(msg_id: Any, result: dict[str, Any]) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": msg_id, "result": result}

    @staticmethod
    def _error(msg_id: Any, code: int, message: str, data: Any = None) -> dict[str, Any]:
        err: dict[str, Any] = {"code": code, "message": message}
        if data is not None:
            err["data"] = data
        return {"jsonrpc": "2.0", "id": msg_id, "error": err}

    # -- Protocol handlers ----------------------------------------------------

    def _handle_initialize(self, params: Mapping[str, Any]) -> dict[str, Any]:
        req_ver = params.get("protocolVersion")
        if isinstance(req_ver, str) and (
            req_ver in SUPPORTED_PROTOCOL_VERSIONS or _PROTOCOL_DATE_RE.match(req_ver)
        ):
            protocol_version = req_ver
        else:
            protocol_version = DEFAULT_PROTOCOL_VERSION
        return {
            "protocolVersion": protocol_version,
            "capabilities": {
                "tools": {"listChanged": False},
                "resources": {"subscribe": False, "listChanged": False},
                "extensions": {
                    "io.modelcontextprotocol/ui": {
                        "mimeTypes": [APP_MIME_TYPE],
                    }
                },
            },
            "serverInfo": {
                "name": "mintfig",
                "version": __version__,
            },
            "instructions": _SERVER_INSTRUCTIONS,
        }

    def _handle_resources_list(self) -> dict[str, Any]:
        return {
            "resources": [
                {
                    "uri": APP_RESOURCE_URI,
                    "name": "mintfig Interactive Figure",
                    "title": "mintfig Interactive Figure Viewer",
                    "description": (
                        "Self-contained interactive MCP App viewer for mintfig figures "
                        "(Auto/Light/Dark/Mint/Pine theme switcher, Copy SVG, hover-to-cite, "
                        "and brush-to-prompt)."
                    ),
                    "mimeType": APP_MIME_TYPE,
                    "_meta": {"ui": {"prefersBorder": False}},
                }
            ]
        }

    def _handle_resources_read(self, msg_id: Any, params: Mapping[str, Any]) -> dict[str, Any]:
        uri = params.get("uri")
        if uri != APP_RESOURCE_URI:
            return self._error(
                msg_id,
                -32002,
                f"Resource not found: {uri!r}. Available: {APP_RESOURCE_URI!r}.",
            )
        return self._result(
            msg_id,
            {
                "contents": [
                    {
                        "uri": APP_RESOURCE_URI,
                        "mimeType": APP_MIME_TYPE,
                        "text": self.render_app_html(),
                        "_meta": {"ui": {"prefersBorder": False}},
                    }
                ]
            },
        )

    def _handle_tools_call(self, msg_id: Any, params: Mapping[str, Any]) -> dict[str, Any]:
        name = params.get("name")
        arguments = params.get("arguments")
        if not isinstance(name, str) or name not in self._tool_names:
            return self._error(
                msg_id,
                -32602,
                f"Unknown tool {name!r}. Available tools: {', '.join(sorted(self._tool_names))}.",
            )
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, Mapping):
            return self._error(msg_id, -32602, "Tool 'arguments' must be a JSON object.")

        dispatch = {
            "mint_explain": self._tool_mint_explain,
            "mint_check": self._tool_mint_check,
            "mint_plot_file": self._tool_mint_plot_file,
            "mint_card": self._tool_mint_card,
            "mint_chip": self._tool_mint_chip,
        }
        handler = dispatch[name]
        # Isolate stdout so no Matplotlib or user-script print corrupts JSON-RPC framing.
        capture_buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(capture_buf):
                tool_result = handler(arguments)
        except Exception as exc:  # noqa: BLE001 - surface clean tool error payload
            hint = getattr(exc, "fix_hint", None)
            err_payload: dict[str, Any] = {
                "ok": False,
                "tool": name,
                "error": str(exc),
                "error_type": type(exc).__name__,
            }
            if hint:
                err_payload["fix_hint"] = str(hint)
            return self._result(
                msg_id,
                {
                    "isError": True,
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(err_payload, indent=2, ensure_ascii=False),
                        }
                    ],
                    "structuredContent": err_payload,
                },
            )
        return self._result(msg_id, tool_result)

    # -- Tool implementations -------------------------------------------------

    def _render_explanation_result(
        self,
        exp: Any,
        *,
        tool_name: str,
        extra_structured: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Build a unified Text + Image + structuredContent + MCP App result for an Explanation."""
        from .interactive import render_html_fragment

        braille_text = exp.to_terminal(width=72, color=False)
        facts = [fact for panel in exp.panels.values() for fact in panel.facts]
        png_b64 = _figure_to_png_b64(
            exp.fig,
            facecolor=exp.theme.background,
            dpi=int(getattr(exp.spec, "dpi_combo", 150) or 150),
        )
        html_fragment = render_html_fragment(exp, interactive=True, responsive=False)

        meta_block: dict[str, Any] = {
            "takeaway": exp.takeaway,
            "ship": bool(exp.ship),
            "facts": facts,
            "issues": list(exp.issues),
        }
        if extra_structured:
            for k, v in extra_structured.items():
                if k not in meta_block:
                    meta_block[k] = v

        text_content = (
            f"{braille_text}\n\n"
            f"```json\n{json.dumps(meta_block, indent=2, ensure_ascii=False, default=str)}\n```"
        )
        structured: dict[str, Any] = {
            "tool": tool_name,
            "takeaway": exp.takeaway,
            "ship": bool(exp.ship),
            "facts": facts,
            "issues": list(exp.issues),
            "html": html_fragment,
            "text": braille_text,
        }
        if extra_structured:
            structured.update(extra_structured)

        self._last_figure = {
            "tool": tool_name,
            "takeaway": exp.takeaway,
            "ship": bool(exp.ship),
            "facts": facts,
            "issues": list(exp.issues),
            "html": html_fragment,
            "text": braille_text,
        }

        return {
            "isError": False,
            "content": [
                {"type": "text", "text": text_content},
                {"type": "image", "data": png_b64, "mimeType": "image/png"},
            ],
            "structuredContent": structured,
            "_meta": dict(_UI_META),
        }

    def _tool_mint_explain(self, args: Mapping[str, Any]) -> dict[str, Any]:
        _ensure_agg_backend()
        import matplotlib.pyplot as plt

        from ._explain.layout import explain_from_spec

        takeaway = args.get("takeaway")
        panels = args.get("panels")
        if not isinstance(takeaway, str) or not takeaway.strip():
            raise ValueError("mint_explain requires a non-empty 'takeaway' string.")
        if isinstance(panels, Mapping):
            panels = [panels]
        if not isinstance(panels, Sequence) or isinstance(panels, (str, bytes)) or not panels:
            raise ValueError("mint_explain requires a non-empty 'panels' list of panel specs.")

        spec: dict[str, Any] = {"takeaway": takeaway, "panels": list(panels)}
        for key in ("kicker", "subtitle", "source", "note", "style", "palette", "accent", "width"):
            if args.get(key) is not None:
                spec[key] = args[key]

        out_path = args.get("out")
        exp = explain_from_spec(spec, out=str(out_path) if out_path else None)
        try:
            extra = {"out": str(Path(out_path).resolve())} if out_path else None
            return self._render_explanation_result(exp, tool_name="mint_explain", extra_structured=extra)
        finally:
            plt.close(exp.fig)

    def _tool_mint_check(self, args: Mapping[str, Any]) -> dict[str, Any]:
        _ensure_agg_backend()
        from .figcheck import check_notebook, check_script

        raw_path = args.get("path")
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise ValueError("mint_check requires a 'path' to a .py script or .ipynb notebook.")
        target = Path(raw_path).expanduser()
        if not target.exists():
            raise FileNotFoundError(f"Target file does not exist: {target}")

        claim = args.get("claim")
        width = args.get("width", "chat")
        if target.suffix.lower() == ".ipynb":
            reports = check_notebook(target, claim=claim, width=width)
        else:
            reports = check_script(target, claim=claim, width=width)

        all_issues: list[dict[str, Any]] = []
        all_facts: list[str] = []
        fix_hints: list[str] = []
        for idx, report in enumerate(reports):
            for issue in report.get("issues", []):
                entry = dict(issue)
                if len(reports) > 1:
                    entry.setdefault("figure_index", idx)
                all_issues.append(entry)
                hint = entry.get("fix_hint")
                if isinstance(hint, str) and hint.strip() and hint not in fix_hints:
                    fix_hints.append(hint.strip())
            for panel in report.get("panels", []):
                for fact in panel.get("facts", []):
                    all_facts.append(str(fact))

        if not reports:
            ship = False
            no_fig_hint = "Ensure the script or notebook creates at least one Matplotlib figure."
            all_issues.append(
                {
                    "rule": "no_figures_found",
                    "severity": "error",
                    "message": f"No Matplotlib figures were produced when running {target.name}.",
                    "fix_hint": no_fig_hint,
                }
            )
            fix_hints.append(no_fig_hint)
        else:
            ship = all(bool(r.ship) for r in reports)

        fix_hint = "; ".join(fix_hints) if fix_hints else None
        payload: dict[str, Any] = {
            "tool": "mint_check",
            "path": str(target),
            "figure_count": len(reports),
            "ship": ship,
            "issues": all_issues,
            "fix_hint": fix_hint,
            "facts": all_facts,
            "reports": [dict(r) for r in reports],
        }
        status_label = "SHIP" if ship else "FIX"
        summary_lines = [
            f"mint_check [{status_label}] {target.name} ({len(reports)} figure(s), {len(all_issues)} issue(s))"
        ]
        if fix_hint:
            summary_lines.append(f"Fix hint: {fix_hint}")
        if all_facts:
            summary_lines.append("Facts: " + " | ".join(all_facts[:6]))
        text_body = (
            "\n".join(summary_lines)
            + "\n\n```json\n"
            + json.dumps(
                {
                    "ship": ship,
                    "figure_count": len(reports),
                    "issues": all_issues,
                    "fix_hint": fix_hint,
                    "facts": all_facts,
                },
                indent=2,
                ensure_ascii=False,
                default=str,
            )
            + "\n```"
        )
        return {
            "isError": False,
            "content": [{"type": "text", "text": text_body}],
            "structuredContent": payload,
        }

    def _tool_mint_plot_file(self, args: Mapping[str, Any]) -> dict[str, Any]:
        _ensure_agg_backend()
        import matplotlib.pyplot as plt

        import mintfig as mint

        from .inspect_data import auto_panel, load_table_file

        raw_path = args.get("path")
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise ValueError("mint_plot_file requires a 'path' to a data file.")
        target = Path(raw_path).expanduser()
        if not target.exists():
            raise FileNotFoundError(f"Data file does not exist: {target}")

        kind = str(args.get("kind") or "auto").strip().lower()
        if target.suffix.lower() == ".xml":
            rows = _load_junit_xml_rows(target)
            if kind == "auto":
                panel = mint.compare(
                    rows[:12],
                    name="test",
                    value="duration_ms",
                    title=f"{target.stem} test durations",
                    label="duration",
                    unit="ms",
                )
            else:
                panel = _build_panel_from_rows(rows, kind, title=target.stem)
        elif kind == "auto":
            panel = auto_panel(target)
        else:
            rows = load_table_file(target)
            panel = _build_panel_from_rows(rows, kind)

        takeaway = args.get("takeaway")
        if not isinstance(takeaway, str) or not takeaway.strip():
            takeaway = _derive_takeaway(panel, target)

        explain_kw: dict[str, Any] = {}
        if args.get("style"):
            explain_kw["style"] = args["style"]
        if args.get("palette"):
            explain_kw["palette"] = args["palette"]
        out_path = args.get("out")
        if out_path:
            explain_kw["out"] = str(out_path)

        exp = mint.explain(takeaway, panel, **explain_kw)
        try:
            extra: dict[str, Any] = {
                "path": str(target),
                "kind": getattr(panel, "kind", kind),
            }
            if out_path:
                extra["out"] = str(Path(out_path).resolve())
            return self._render_explanation_result(exp, tool_name="mint_plot_file", extra_structured=extra)
        finally:
            plt.close(exp.fig)

    def _tool_mint_card(self, args: Mapping[str, Any]) -> dict[str, Any]:
        _ensure_agg_backend()
        import matplotlib.pyplot as plt

        from .card import card_from_json

        takeaway = args.get("takeaway")
        metrics = args.get("metrics")
        if not isinstance(takeaway, str) or not takeaway.strip():
            raise ValueError("mint_card requires a non-empty 'takeaway' string.")
        if not isinstance(metrics, Sequence) or isinstance(metrics, (str, bytes)) or not metrics:
            raise ValueError("mint_card requires a non-empty 'metrics' list.")

        spec: dict[str, Any] = {"takeaway": takeaway, "metrics": list(metrics)}
        for key in ("panel", "subtitle", "source", "style", "palette", "accent", "width"):
            if args.get(key) is not None:
                spec[key] = args[key]

        summary_card = card_from_json(spec)
        try:
            out_path = args.get("out")
            if out_path:
                summary_card.save(str(out_path))

            card_summary = summary_card.summary()
            term_text = summary_card.to_terminal(width=72, color=False)
            png_b64 = _figure_to_png_b64(
                summary_card.fig,
                facecolor=summary_card.theme.background,
                dpi=int(getattr(summary_card.spec, "dpi_combo", 150) or 150),
            )
            html_fragment = _extract_card_fragment(summary_card.to_html())

            facts: list[str] = []
            for m in metrics:
                if isinstance(m, Mapping):
                    lbl = str(m.get("label") or "").strip()
                    val = str(m.get("value") or "").strip()
                    delta = m.get("delta")
                    item = f"{lbl}: {val}" + (f" ({delta})" if delta is not None and str(delta).strip() else "")
                    if lbl or val:
                        facts.append(item)
            for pf in card_summary.get("panel_facts") or []:
                facts.append(str(pf))

            issues = list(card_summary.get("issues") or [])
            ship = bool(summary_card.ship)
            meta_block: dict[str, Any] = {
                "takeaway": summary_card.takeaway,
                "ship": ship,
                "metrics_count": len(metrics),
                "facts": facts,
                "issues": issues,
            }
            if out_path:
                meta_block["out"] = str(Path(out_path).resolve())

            text_content = (
                f"{term_text}\n\n"
                f"```json\n{json.dumps(meta_block, indent=2, ensure_ascii=False, default=str)}\n```"
            )
            structured: dict[str, Any] = {
                "tool": "mint_card",
                "takeaway": summary_card.takeaway,
                "ship": ship,
                "metrics_count": len(metrics),
                "facts": facts,
                "issues": issues,
                "html": html_fragment,
                "text": term_text,
            }
            if out_path:
                structured["out"] = str(Path(out_path).resolve())

            self._last_figure = {
                "tool": "mint_card",
                "takeaway": summary_card.takeaway,
                "ship": ship,
                "facts": facts,
                "issues": issues,
                "html": html_fragment,
                "text": term_text,
            }

            return {
                "isError": False,
                "content": [
                    {"type": "text", "text": text_content},
                    {"type": "image", "data": png_b64, "mimeType": "image/png"},
                ],
                "structuredContent": structured,
                "_meta": dict(_UI_META),
            }
        finally:
            plt.close(summary_card.fig)

    def _tool_mint_chip(self, args: Mapping[str, Any]) -> dict[str, Any]:
        from ._chip_bridge import chip_css, import_mintchip

        kind = str(args.get("kind") or "").strip()
        if not kind:
            raise ValueError("mint_chip requires a 'kind' (e.g. 'spark', 'bar', 'ci', 'table').")

        mc = import_mintchip()
        if mc is None:
            msg = (
                "Optional companion package 'mintchip' is not installed in this environment. "
                "Install it with `pip install mintchip` (or `pip install 'mintfig[chip]'`) "
                "to render inline word-sized chips and shared-scale tables."
            )
            return {
                "isError": False,
                "content": [{"type": "text", "text": msg}],
                "structuredContent": {
                    "tool": "mint_chip",
                    "installed": False,
                    "kind": kind,
                    "message": msg,
                    "install_command": "pip install mintchip",
                },
            }

        pos_args = args.get("args") or []
        kw_args = args.get("kwargs") or {}
        if not isinstance(pos_args, list):
            raise TypeError("mint_chip 'args' must be a JSON array.")
        if not isinstance(kw_args, Mapping):
            raise TypeError("mint_chip 'kwargs' must be a JSON object.")

        braille = bool(args.get("braille", False))
        theme = str(args.get("theme") or "auto")
        fmt = str(args.get("format") or "text").strip().lower()
        if fmt not in {"text", "markdown", "svg", "html", "all"}:
            raise ValueError(f"Unsupported format {fmt!r}. Use text, markdown, svg, html, or all.")

        valid_kinds = set(getattr(mc, "REGISTRY", {}).keys()) | {"table"}
        constructor = getattr(mc, kind, None) if kind in valid_kinds or hasattr(mc, kind) else None
        if constructor is None or not callable(constructor):
            available = sorted(valid_kinds)
            raise ValueError(
                f"Unknown mintchip kind {kind!r}. Available kinds: {', '.join(available)}."
            )

        obj = constructor(*pos_args, **dict(kw_args))
        is_table_obj = kind == "table"

        rendered: dict[str, Any] = {
            "tool": "mint_chip",
            "installed": True,
            "kind": kind,
            "format": fmt,
        }

        if is_table_obj:
            text_out = obj.text(braille=braille)
            md_out = obj.markdown(braille=braille)
            html_out = f"<style>{chip_css()}</style>\n{obj.html(theme=theme)}"
            svg_out = ""
            facts = list(getattr(obj, "facts", ()) or ())
        else:
            text_out = obj.text(braille=braille)
            md_out = obj.markdown(braille=braille)
            svg_out = obj.svg(theme=theme)
            html_out = f"<style>{chip_css()}</style>\n{obj.html(theme=theme)}"
            facts = list(getattr(obj, "facts", ()) or ())

        rendered.update(
            {
                "text": text_out,
                "markdown": md_out,
                "svg": svg_out,
                "html": html_out,
                "facts": facts,
            }
        )

        if fmt == "text":
            primary = text_out
        elif fmt == "markdown":
            primary = md_out
        elif fmt == "svg":
            primary = svg_out or text_out
        elif fmt == "html":
            primary = html_out
        else:
            primary = json.dumps(rendered, indent=2, ensure_ascii=False)

        return {
            "isError": False,
            "content": [{"type": "text", "text": primary}],
            "structuredContent": rendered,
        }


# --------------------------------------------------------------------------- #
# One-command MCP Host Config Installer & Status
# --------------------------------------------------------------------------- #


def _claude_desktop_config_path(home: Path, platform: str | None = None) -> Path:
    plat = platform or sys.platform
    if plat == "darwin":
        return home / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    if plat.startswith("win"):
        appdata = os.environ.get("APPDATA")
        base = Path(appdata) if appdata else (home / "AppData" / "Roaming")
        return base / "Claude" / "claude_desktop_config.json"
    return home / ".config" / "Claude" / "claude_desktop_config.json"


def default_mcp_config_paths(
    home: str | Path | None = None,
    *,
    platform: str | None = None,
) -> dict[str, Path]:
    """Return the standard MCP JSON config file paths for every supported agent host."""
    home_path = Path(home).expanduser() if home is not None else Path.home()
    return {
        "claude-code": home_path / ".claude.json",
        "claude-desktop": _claude_desktop_config_path(home_path, platform=platform),
        "cursor": home_path / ".cursor" / "mcp.json",
        "gemini": home_path / ".gemini" / "settings.json",
        "antigravity": home_path / ".gemini" / "antigravity" / "mcp_config.json",
    }


def _normalize_mcp_targets(
    targets: Sequence[str] | None,
    available: Mapping[str, Path],
) -> list[str]:
    if targets is None:
        return list(available.keys())
    expanded: list[str] = []
    for raw in targets:
        for part in str(raw).split(","):
            key = part.strip().lower()
            if not key:
                continue
            if key == "all":
                expanded.extend(available.keys())
                continue
            canonical = _TARGET_ALIASES.get(key, key)
            if canonical not in available:
                valid = ", ".join((*available.keys(), "all"))
                raise ValueError(f"Unknown MCP target {raw!r}. Valid targets: {valid}")
            if canonical not in expanded:
                expanded.append(canonical)
    return expanded or list(available.keys())


def _resolve_config_paths(config_paths: Mapping[str, str | Path] | None) -> dict[str, Path]:
    if config_paths is None:
        return default_mcp_config_paths()
    return {str(k): Path(v).expanduser() for k, v in config_paths.items()}


def install_mcp_config(
    targets: Sequence[str] | None = None,
    *,
    dry_run: bool = False,
    config_paths: Mapping[str, str | Path] | None = None,
    entry: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Safely merge ``mintfig`` into MCP host configuration JSON files without clobbering.

    Parameters
    ----------
    targets:
        Subset of ``("claude-code", "claude-desktop", "cursor", "gemini", "antigravity")``
        (or aliases like ``"claude"``, ``"gemini-cli"``, ``"agy"``, ``"all"``). Defaults to
        every configured target.
    dry_run:
        When ``True``, compute planned changes without creating or writing any files.
    config_paths:
        Optional mapping of target name -> config file path (ideal for tests or custom homes).
    entry:
        Optional override for the server entry (default ``{"command": "uvx", "args": ["mintfig", "mcp"]}``).
    """
    paths = _resolve_config_paths(config_paths)
    chosen = _normalize_mcp_targets(targets, paths)
    server_entry = dict(entry) if entry is not None else {
        "command": MCP_SERVER_ENTRY["command"],
        "args": list(MCP_SERVER_ENTRY["args"]),
    }

    results: list[dict[str, Any]] = []
    for target in chosen:
        cfg_path = paths[target]
        existed = cfg_path.exists()
        if existed:
            raw_text = cfg_path.read_text(encoding="utf-8").strip()
            if raw_text:
                try:
                    data = json.loads(raw_text)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"{cfg_path} contains invalid JSON: {exc}") from exc
                if not isinstance(data, dict):
                    raise ValueError(f"{cfg_path} must contain a top-level JSON object.")
            else:
                data = {}
        else:
            data = {}

        servers = data.get("mcpServers")
        if servers is None:
            servers = {}
        elif not isinstance(servers, dict):
            raise ValueError(f"{cfg_path} has a non-object 'mcpServers' key.")

        existing_entry = servers.get("mintfig")
        if existing_entry == server_entry:
            status = "unchanged"
        elif existing_entry is None:
            status = "would_install" if dry_run else "installed"
        else:
            status = "would_update" if dry_run else "updated"

        if not dry_run and status != "unchanged":
            merged_servers = dict(servers)
            merged_servers["mintfig"] = server_entry
            updated = dict(data)
            updated["mcpServers"] = merged_servers
            cfg_path.parent.mkdir(parents=True, exist_ok=True)
            cfg_path.write_text(
                json.dumps(updated, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )

        results.append(
            {
                "target": target,
                "path": str(cfg_path),
                "existed": existed,
                "status": status,
            }
        )

    return {
        "ok": True,
        "dry_run": dry_run,
        "entry": {"mintfig": server_entry},
        "results": results,
    }


def mcp_status(
    config_paths: Mapping[str, str | Path] | None = None,
) -> dict[str, Any]:
    """Inspect MCP host configs and report where ``mintfig`` is configured."""
    paths = _resolve_config_paths(config_paths)
    hosts: dict[str, dict[str, Any]] = {}
    configured_count = 0

    for target, cfg_path in paths.items():
        exists = False
        configured = False
        entry: dict[str, Any] | None = None
        error: str | None = None

        try:
            exists = cfg_path.is_file()
            if exists:
                raw_text = cfg_path.read_text(encoding="utf-8").strip()
                data = json.loads(raw_text) if raw_text else {}
                servers = data.get("mcpServers") if isinstance(data, dict) else None
                if isinstance(servers, dict) and isinstance(servers.get("mintfig"), dict):
                    configured = True
                    entry = dict(servers["mintfig"])
                    configured_count += 1
        except (OSError, json.JSONDecodeError) as exc:
            error = str(exc)

        info: dict[str, Any] = {
            "path": str(cfg_path),
            "exists": exists,
            "configured": configured,
            "entry": entry,
        }
        if error:
            info["error"] = error
        hosts[target] = info

    return {
        "configured_count": configured_count,
        "total_targets": len(hosts),
        "hosts": hosts,
    }


def print_mcp_config() -> dict[str, Any]:
    """Return the canonical ``mcpServers`` JSON config snippet for mintfig."""
    return {
        "mcpServers": {
            "mintfig": {
                "command": MCP_SERVER_ENTRY["command"],
                "args": list(MCP_SERVER_ENTRY["args"]),
            }
        }
    }


def run_stdio_server(stdin: TextIO | None = None, stdout: TextIO | None = None) -> int:
    """Instantiate :class:`MCPServer` and serve JSON-RPC 2.0 over stdio."""
    server = MCPServer()
    return server.serve(stdin=stdin, stdout=stdout)


# --------------------------------------------------------------------------- #
# CLI entry point (``mintfig mcp``)
# --------------------------------------------------------------------------- #


def cli_mcp(argv: Sequence[str] | None = None) -> int:
    """CLI entry point for ``mintfig mcp`` (stdio server, installer, status, print-config)."""
    parser = argparse.ArgumentParser(
        prog="mintfig mcp",
        description=(
            "Run the zero-dependency mintfig MCP server over stdio, or manage host MCP configs."
        ),
    )
    parser.add_argument(
        "--install",
        action="store_true",
        help="Register mintfig MCP in Claude Code, Claude Desktop, Cursor, Gemini CLI, and Antigravity.",
    )
    parser.add_argument(
        "--target",
        action="append",
        default=None,
        help=(
            "Target host(s) for --install (repeatable or comma-separated): "
            "claude-code, claude-desktop, cursor, gemini, antigravity, or all."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview --install changes without modifying any files.",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Report which MCP hosts currently have mintfig configured.",
    )
    parser.add_argument(
        "--print-config",
        action="store_true",
        help="Print the standard mcpServers JSON snippet to stdout and exit.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="Emit machine-readable JSON for --install or --status.",
    )

    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.print_config:
        print(json.dumps(print_mcp_config(), indent=2, ensure_ascii=False))
        return 0

    if args.status:
        report = mcp_status()
        if args.as_json:
            print(json.dumps(report, indent=2, ensure_ascii=False))
        else:
            print(
                f"mintfig MCP status: {report['configured_count']}/{report['total_targets']} hosts configured"
            )
            for host, info in report["hosts"].items():
                mark = "configured" if info["configured"] else ("present (not configured)" if info["exists"] else "not found")
                print(f"  {host:<16} {mark:<25} {info['path']}")
        return 0

    if args.install:
        try:
            res = install_mcp_config(targets=args.target, dry_run=args.dry_run)
        except ValueError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 2
        if args.as_json:
            print(json.dumps(res, indent=2, ensure_ascii=False))
        else:
            prefix = "[dry-run] " if args.dry_run else ""
            print(f"{prefix}mintfig MCP configuration:")
            for item in res["results"]:
                print(f"  {item['target']:<16} {item['status']:<15} {item['path']}")
        return 0

    return run_stdio_server()


if __name__ == "__main__":
    raise SystemExit(cli_mcp())
