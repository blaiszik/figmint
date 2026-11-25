"""Stateful multi-turn visual memory (``fm.Session``) and multi-figure briefings (``fm.brief``).

Solves two multi-turn agent communication gaps:
1. ``Session`` maintains a persistent entity-colour ledger across figures with
   smart base-entity prefix matching (so ``"Alpha-3 (int4)"`` inherits
   ``"Alpha-3"``'s hue automatically instead of drifting to a random colour).
2. ``Brief`` composes 1–12 figures into a single cohesive self-contained HTML
   briefing or PR-/Artifact-ready Markdown bundle with consistent theme,
   executive takeaway index, L2/L3 narrative bullets, and exact Markdown tables.
"""

from __future__ import annotations

import html
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from ._explain.core import ExplainError, Panel
from ._explain.layout import Explanation, explain, explain_from_spec, load
from .edit import edit as _edit_figure
from .epistemic import build_narrative
from .interactive import render_html_fragment
from .themes import Theme, get_theme, relative_luminance

__all__ = ["Brief", "Session", "brief"]

_MAX_BRIEF_FIGURES = 12
_TOKEN_BOUNDARY = re.compile(r"[\s(\[\-/:,_]")


def _match_pinned_slot(item: str, ledger: Mapping[str, str]) -> str | None:
    """Find an exact or longest token-boundary prefix match in ``ledger``."""
    low = item.strip().lower()
    if not low:
        return None
    norm_ledger = {k.strip().lower(): slot for k, slot in ledger.items() if k.strip()}
    if low in norm_ledger:
        return norm_ledger[low]
    # Longest token-boundary prefix match ("alpha-3" -> "alpha-3 (int4)", "us-west" -> "us-west after")
    best_len = 0
    best_slot: str | None = None
    for base_k, slot in norm_ledger.items():
        if len(base_k) < 3 or len(base_k) <= best_len:
            continue
        if low.startswith(base_k) and len(low) > len(base_k):
            nxt = low[len(base_k)]
            if _TOKEN_BOUNDARY.match(nxt):
                best_len = len(base_k)
                best_slot = slot
    return best_slot


def _resolve_figure(item: Explanation | str | Path | Mapping[str, Any]) -> Explanation:
    if isinstance(item, Explanation):
        return item
    if isinstance(item, Mapping):
        return explain_from_spec(item)
    if isinstance(item, (str, Path)):
        return load(item)
    raise ExplainError(
        f"brief() items must be Explanation objects, PNG/JSON paths, or spec dicts; got {type(item).__name__}.",
        fix_hint='Pass figures from fm.explain(...) or saved paths like "fig1.png".',
    )


class Session:
    """Multi-turn visual memory keeping style, palette, and entity colours aligned across figures."""

    def __init__(
        self,
        *,
        style: str | Theme = "figmint",
        palette: str | None = None,
        accent: str | None = None,
        width: str | float = "chat",
        colors: Mapping[str, str] | None = None,
        state_path: str | Path | None = None,
    ) -> None:
        self.style = style
        self.palette = palette
        self.accent = accent
        self.width = width
        self.state_path = Path(state_path) if state_path is not None else None
        self.colors: dict[str, str] = {}
        self.figures: list[Explanation] = []

        if self.state_path is not None and self.state_path.exists():
            try:
                saved = json.loads(self.state_path.read_text(encoding="utf-8"))
                if isinstance(saved, Mapping):
                    for k, v in (saved.get("colors") or {}).items():
                        self.colors[str(k)] = str(v)
                    if style == "figmint" and isinstance(saved.get("style"), str):
                        self.style = saved["style"]
                    if palette is None and isinstance(saved.get("palette"), str):
                        self.palette = saved["palette"]
                    if accent is None and isinstance(saved.get("accent"), str):
                        self.accent = saved["accent"]
            except (OSError, json.JSONDecodeError):
                pass

        if colors:
            for k, v in colors.items():
                self.colors[str(k)] = str(v)

    def _save_state(self) -> None:
        if self.state_path is None:
            return
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "style": self.style.name if isinstance(self.style, Theme) else self.style,
            "palette": self.palette,
            "accent": self.accent,
            "colors": dict(self.colors),
        }
        self.state_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    def _merged_colors(
        self,
        panels: Sequence[Panel | Mapping[str, Any]],
        explicit: Mapping[str, str] | None,
    ) -> dict[str, str] | None:
        merged: dict[str, str] = {}
        # Collect candidate entity names appearing in this figure's panels
        candidates: list[str] = []
        for p in panels:
            if isinstance(p, Panel):
                candidates.extend(p.color_items)
                candidates.extend(p.color_focus)
        # First honor explicit caller pins
        if explicit:
            for k, v in explicit.items():
                merged[str(k)] = str(v)
        # Then match session ledger (exact + prefix inheritance, up to 4 pins)
        for cand in dict.fromkeys(candidates):
            if cand in merged or len(merged) >= 4:
                continue
            slot = _match_pinned_slot(cand, self.colors)
            if slot is not None:
                merged[cand] = slot
        # If no candidates matched directly (e.g. spec dicts), carry over up to 4 session pins
        if not merged and self.colors:
            for k, v in list(self.colors.items())[:4]:
                merged[k] = v
        return merged or None

    def explain(
        self,
        takeaway: str,
        *panels: Panel | Mapping[str, Any],
        colors: Mapping[str, str] | None = None,
        **kwargs: Any,
    ) -> Explanation:
        """Render an :class:`Explanation` inheriting session theme and entity colours."""
        kwargs.setdefault("style", self.style)
        if self.palette is not None:
            kwargs.setdefault("palette", self.palette)
        if self.accent is not None:
            kwargs.setdefault("accent", self.accent)
        kwargs.setdefault("width", self.width)
        merged = self._merged_colors(panels, colors)
        result = explain(takeaway, *panels, colors=merged, **kwargs)
        self._harvest(result, explicit=colors)
        self.figures.append(result)
        return result

    def edit(self, figure: Explanation | str | Path | Mapping[str, Any], **kwargs: Any) -> Explanation:
        """Edit an existing figure and record updated entity colours in this session."""
        result = _edit_figure(figure, **kwargs)
        self._harvest(result)
        self.figures.append(result)
        return result

    def _harvest(
        self,
        result: Explanation,
        *,
        explicit: Mapping[str, str] | None = None,
    ) -> None:
        if explicit:
            for k, v in explicit.items():
                self.colors[str(k)] = str(v)
        for k, slot in result.entity_colors.items():
            # Preserve earlier canonical names; add newly seen names cleanly
            self.colors.setdefault(str(k), str(slot))
        self._save_state()

    def brief(
        self,
        title: str,
        *,
        subtitle: str | None = None,
        summary: Sequence[str] | str | None = None,
        source: str | None = None,
    ) -> Brief:
        """Compose all figures created in this session into a cohesive :class:`Brief`."""
        if not self.figures:
            raise ExplainError(
                "Session has no figures yet.",
                fix_hint="Call session.explain(...) at least once before session.brief(...).",
            )
        return brief(
            title,
            *self.figures,
            subtitle=subtitle,
            summary=summary,
            source=source,
            style=self.style if isinstance(self.style, str) else self.style.name,
        )


class Brief:
    """A cohesive multi-figure investigation briefing exportable to HTML or Markdown."""

    def __init__(
        self,
        title: str,
        figures: Sequence[Explanation],
        *,
        subtitle: str | None = None,
        summary: Sequence[str] | str | None = None,
        source: str | None = None,
        style: str | Theme | None = None,
    ) -> None:
        self.title = title
        self.figures = list(figures)
        self.subtitle = subtitle
        if isinstance(summary, str):
            self.summary_points = [summary]
        elif summary is not None:
            self.summary_points = [str(s) for s in summary if str(s).strip()]
        else:
            self.summary_points = []
        self.source = source
        self.theme = get_theme(style) if style is not None else self.figures[0].theme

    @property
    def ship_all(self) -> bool:
        return all(fig.ship for fig in self.figures)

    def to_html(self) -> str:
        """Render a self-contained zero-CDN interactive HTML briefing with jump navigation."""
        theme = self.theme
        is_dark = relative_luminance(theme.background) < 0.25
        page_bg = "#0C0F14" if is_dark else "#F4F5F7"
        card_bg = theme.background
        border = "rgba(255,255,255,0.12)" if is_dark else "rgba(26,29,33,0.12)"
        accent = theme.accent_colors[0] if theme.accent_colors else theme.series_colors[0]
        esc = html.escape

        toc_items = "\n".join(
            f'<li><a href="#fig-{i + 1}"><span class="fm-bnum">{i + 1}</span>'
            f'<span>{esc(fig.takeaway)}</span></a></li>'
            for i, fig in enumerate(self.figures)
        )
        summary_html = ""
        if self.summary_points:
            bullets = "".join(f"<li>{esc(pt)}</li>" for pt in self.summary_points)
            summary_html = f'<section class="fm-bsum"><h2>Key findings</h2><ul>{bullets}</ul></section>'

        sections: list[str] = []
        for idx, fig in enumerate(self.figures, 1):
            frag = render_html_fragment(fig, interactive=True)
            sections.append(
                f'<section id="fig-{idx}" class="fm-bsec">'
                f'<div class="fm-bsec-label">Finding {idx} of {len(self.figures)}</div>'
                f"{frag}"
                f"</section>"
            )

        sub_html = f'<p class="fm-bsub">{esc(self.subtitle)}</p>' if self.subtitle else ""
        src_html = f'<footer class="fm-bfoot">Source: {esc(self.source)}</footer>' if self.source else ""

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(self.title)}</title>
<style>
  :root {{
    color-scheme: {"dark" if is_dark else "light"};
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    padding: 32px 20px 64px;
    background: {page_bg};
    color: {theme.ink};
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    line-height: 1.5;
  }}
  .fm-brief {{
    max-width: 1080px;
    margin: 0 auto;
  }}
  .fm-bhead {{
    background: {card_bg};
    border: 1px solid {border};
    border-top: 3px solid {accent};
    border-radius: 10px;
    padding: 24px 28px;
    margin-bottom: 24px;
  }}
  .fm-bhead h1 {{
    margin: 0 0 6px;
    font-size: 1.65rem;
    line-height: 1.2;
  }}
  .fm-bsub {{
    margin: 0 0 16px;
    color: {theme.muted};
    font-size: 0.98rem;
  }}
  .fm-bsum {{
    margin: 14px 0 16px;
    padding: 12px 16px;
    border-left: 3px solid {accent};
    background: {"rgba(255,255,255,0.04)" if is_dark else "rgba(0,0,0,0.03)"};
    border-radius: 0 6px 6px 0;
  }}
  .fm-bsum h2 {{
    margin: 0 0 6px;
    font-size: 0.85rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: {theme.muted};
  }}
  .fm-bsum ul {{ margin: 0; padding-left: 18px; }}
  .fm-btoc {{
    list-style: none;
    margin: 12px 0 0;
    padding: 0;
    display: grid;
    gap: 6px;
  }}
  .fm-btoc a {{
    display: flex;
    align-items: baseline;
    gap: 10px;
    text-decoration: none;
    color: {theme.ink};
    padding: 6px 8px;
    border-radius: 6px;
  }}
  .fm-btoc a:hover {{
    background: {"rgba(255,255,255,0.06)" if is_dark else "rgba(0,0,0,0.04)"};
  }}
  .fm-bnum {{
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: 22px;
    height: 22px;
    border-radius: 999px;
    background: {accent};
    color: #fff;
    font-size: 0.78rem;
    font-weight: 700;
  }}
  .fm-bsec {{
    margin-bottom: 28px;
  }}
  .fm-bsec-label {{
    font-size: 0.78rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: {theme.muted};
    margin: 0 0 8px 4px;
  }}
  .fm-bfoot {{
    margin-top: 24px;
    font-size: 0.85rem;
    color: {theme.muted};
    text-align: center;
  }}
</style>
</head>
<body>
<main class="fm-brief">
  <header class="fm-bhead">
    <h1>{esc(self.title)}</h1>
    {sub_html}
    {summary_html}
    <ol class="fm-btoc">{toc_items}</ol>
  </header>
  {"".join(sections)}
  {src_html}
</main>
</body>
</html>
"""

    def to_markdown(
        self,
        *,
        image_paths: Sequence[str] | None = None,
    ) -> str:
        """Render a PR- and Artifact-ready Markdown briefing with L2/L3 facts and tables."""
        lines: list[str] = [f"# {self.title}"]
        if self.subtitle:
            lines.append(f"\n*{self.subtitle}*")
        if self.summary_points:
            lines.append("\n## Key findings\n")
            for pt in self.summary_points:
                lines.append(f"- {pt}")

        for idx, fig in enumerate(self.figures, 1):
            lines.append(f"\n---\n\n## {idx}. {fig.takeaway}")
            if fig.subtitle:
                lines.append(f"\n*{fig.subtitle}*")
            img_ref = (
                image_paths[idx - 1]
                if image_paths is not None and idx - 1 < len(image_paths)
                else (str(fig.saved_path) if fig.saved_path else None)
            )
            if img_ref:
                lines.append(f"\n![{fig.takeaway}]({img_ref})")
            narr = build_narrative(fig.takeaway, fig.panels, subtitle=fig.subtitle, source=fig.source)
            key_bullets = [*narr["L2"][:3], *narr["L3"][:2]]
            if key_bullets:
                lines.append("")
                for b in key_bullets:
                    lines.append(f"- {b}")
            for panel in fig.panels.values():
                if panel.kind == "table":
                    lines.append("")
                    lines.append(panel.to_markdown())
            if fig.source:
                lines.append(f"\n*Source: {fig.source}*")

        if self.source:
            lines.append(f"\n---\n\n*Briefing source: {self.source}*")
        return "\n".join(lines) + "\n"

    def save(self, path: str | Path, *, scale: float = 2.0) -> dict[str, Any]:
        """Write the briefing as ``.html`` (self-contained) or ``.md`` (with saved figure PNGs)."""
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        suffix = out.suffix.lower()
        assets: list[str] = []

        if suffix in {".html", ".htm"}:
            out.write_text(self.to_html(), encoding="utf-8")
            fmt_name = "html"
        elif suffix in {".md", ".markdown"}:
            asset_dir = out.parent / f"{out.stem}_figures"
            asset_dir.mkdir(parents=True, exist_ok=True)
            rel_paths: list[str] = []
            for idx, fig in enumerate(self.figures, 1):
                png_name = f"fig_{idx:02d}.png"
                png_path = asset_dir / png_name
                fig.save(png_path, scale=scale)
                assets.append(str(png_path.resolve()))
                rel_paths.append(f"{asset_dir.name}/{png_name}")
            out.write_text(self.to_markdown(image_paths=rel_paths), encoding="utf-8")
            fmt_name = "markdown"
        else:
            raise ExplainError(
                f"Brief.save() expects a .html or .md path, got {out.suffix!r}.",
                fix_hint='Save to "brief.html" (self-contained) or "brief.md" (Markdown + PNGs).',
            )

        return {
            "path": str(out.resolve()),
            "format": fmt_name,
            "title": self.title,
            "figure_count": len(self.figures),
            "ship_all": self.ship_all,
            "figures": [
                {"index": i + 1, "takeaway": f.takeaway, "ok": f.ok, "ship": f.ship}
                for i, f in enumerate(self.figures)
            ],
            "assets": assets,
        }


def brief(
    title: str,
    *figures: Explanation | str | Path | Mapping[str, Any],
    subtitle: str | None = None,
    summary: Sequence[str] | str | None = None,
    source: str | None = None,
    style: str | Theme | None = None,
) -> Brief:
    """Compose 1–12 figures into a single HTML or Markdown investigation briefing."""
    if not isinstance(title, str) or not title.strip():
        raise ExplainError(
            "brief() needs a non-empty title.",
            fix_hint='e.g. fm.brief("Q4 latency investigation", fig1, fig2).',
        )
    if not figures:
        raise ExplainError(
            "brief() needs at least one figure.",
            fix_hint="Pass one or more Explanation objects or saved figmint PNG/JSON paths.",
        )
    if len(figures) > _MAX_BRIEF_FIGURES:
        raise ExplainError(
            f"brief() got {len(figures)} figures; at most {_MAX_BRIEF_FIGURES} fit one cohesive briefing.",
            fix_hint=f"Keep at most {_MAX_BRIEF_FIGURES} key figures in one brief.",
            rule="too_many_items",
        )
    resolved = [_resolve_figure(item) for item in figures]
    return Brief(
        title.strip(),
        resolved,
        subtitle=subtitle,
        summary=summary,
        source=source,
        style=style,
    )
