"""Stateful multi-turn visual memory (``mint.Session``) and multi-figure briefings (``mint.brief``).

Solves two multi-turn agent communication gaps:
1. ``Session`` maintains a persistent entity-colour ledger across figures with
   smart base-entity prefix matching (so ``"Alpha-3 (int4)"`` inherits
   ``"Alpha-3"``'s hue automatically instead of drifting to a random colour).
2. ``Brief`` composes 1–12 figures, with prose paragraphs and ``## `` section
   headings between them, into one document: a self-contained HTML page or a
   Markdown file with its PNGs. It opens with the findings at a glance (a row of
   thumbnails in HTML, a numbered list of takeaways in Markdown); each finding is
   then the figure and one caption (in Markdown also its takeaway as heading and its
   source). In HTML the facts sit in a collapsed "Numbers behind this figure" block;
   Markdown leaves them out.
"""

from __future__ import annotations

import html
import json
import math
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from ._chip_bridge import (
    SCHEME_SYNC_CSS,
    chip_css,
    is_chip,
    is_chip_item,
    is_table,
    render_prose_html,
    render_prose_markdown,
)
from ._explain.core import ExplainError, Panel
from ._explain.layout import (
    Explanation,
    _markdown_target,
    _value_range,
    explain,
    explain_from_spec,
    load,
)
from .edit import edit as _edit_figure
from .interactive import render_html_fragment
from .themes import THEMES, Theme, get_theme, relative_luminance

__all__ = ["Brief", "Session", "brief"]

_MAX_BRIEF_FIGURES = 12
_TOKEN_BOUNDARY = re.compile(r"[\s(\[\-/:,_]")
_FIGURE_SUFFIXES = (".png", ".json")
_HEADING_PREFIX = "## "


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
        fix_hint='Pass figures from mint.explain(...) or saved paths like "fig1.png".',
    )


def _names_figure(item: str) -> bool:
    """True when a string is a figure path rather than prose.

    An existing ``.png`` / ``.json`` file is a figure; so is a single token ending in
    one of those suffixes, so a mistyped path fails loudly instead of becoming a paragraph.
    """
    text = item.strip()
    if not text.lower().endswith(_FIGURE_SUFFIXES):
        return False
    return not re.search(r"\s", text) or Path(text).is_file()


def _resolve_item(
    item: Any,
) -> Any:
    """A figure, a ``mintchip`` Chip/Table, a prose block (paragraph or ``## `` heading),
    or None for an empty string."""
    if is_chip_item(item):
        return item
    if isinstance(item, str) and not _names_figure(item):
        text = item.strip()
        return text if text not in {"", _HEADING_PREFIX.strip()} else None
    return _resolve_figure(item)


def _is_heading(block: str) -> bool:
    return block.startswith(_HEADING_PREFIX)


def _heading_text(block: str) -> str:
    return block[len(_HEADING_PREFIX) :].strip()


def _md_slug(text: str, seen: dict[str, int]) -> str:
    """A Markdown heading anchor as common renderers build it (lowercase, punctuation
    dropped, spaces to hyphens), with ``-1``, ``-2`` ... for repeats."""
    base = re.sub(r"[^\w\- ]", "", text.strip().lower()).replace(" ", "-")
    n = seen.get(base, 0)
    seen[base] = n + 1
    return base if n == 0 else f"{base}-{n}"


def _caption(fig: Explanation) -> str | None:
    deliver = fig.summary().get("deliver") or {}
    caption = deliver.get("caption")
    return str(caption) if caption else None


def _round(v: float) -> float:
    return float(f"{v:.4g}")


def _span(rng: Sequence[Any]) -> str:
    """An axis range as text, with a true minus sign and "to" when a bound is negative."""
    lo, hi = (f"{_round(v):g}".replace("-", "\N{MINUS SIGN}") for v in rng[:2])
    return f"{lo} to {hi}" if "\N{MINUS SIGN}" in lo + hi else f"{lo}\N{EN DASH}{hi}"


def _scales_differ(figures: Sequence[Explanation]) -> list[dict[str, Any]]:
    """Pairs of panels in different figures with the same value label and unit but
    different axis ranges (or one log and one linear axis). Advice only.

    Same convention as the within-figure advisory in ``_explain/layout.py``: a panel
    whose value axis is hidden (labelled bars) is compared only with its own kind."""
    seen: list[tuple[int, str, Panel, tuple[str, str], tuple[float, float, str, bool]]] = []
    for fi, fig in enumerate(figures, 1):
        for key, panel in fig.panels.items():
            label = (panel.label or "").strip()
            rng = _value_range(fig, key, panel) if label else None
            if rng is not None:
                seen.append((fi, key, panel, (label.casefold(), (panel.unit or "").strip()), rng))
    out: list[dict[str, Any]] = []
    for i, (fa, ka, pa, ida, ra) in enumerate(seen):
        for fb, kb, pb, idb, rb in seen[i + 1 :]:
            if fa == fb or ida != idb or (not (ra[3] and rb[3]) and pa.kind != pb.kind):
                continue
            what = f"{pa.label}" + (f" ({pa.unit})" if pa.unit else "")
            where = f"figure {fa} panel {ka} and figure {fb} panel {kb}"
            if ra[2] != rb[2]:
                issue = "log_vs_linear"
                hint = (
                    f"{where.capitalize()} both plot {what}, one on a {ra[2]} axis and one on a "
                    f"{rb[2]} axis; ranges not compared. Use one scale for both."
                )
            else:
                tol = 0.01 * max(ra[1] - ra[0], rb[1] - rb[0])
                if all(math.isclose(x, y, abs_tol=tol) for x, y in zip(ra[:2], rb[:2], strict=True)):
                    continue
                issue = "range"
                hint = (
                    f"{where.capitalize()} both plot {what} but over "
                    f"{_span(ra)} and {_span(rb)}; "
                    "readers will compare them by eye, so give them the same range."
                )
            out.append(
                {
                    "label": pa.label,
                    "unit": pa.unit,
                    "issue": issue,
                    "panels": [
                        {"figure": f, "panel": k, "range": [_round(r[0]), _round(r[1])], "scale": r[2]}
                        for f, k, r in ((fa, ka, ra), (fb, kb, rb))
                    ],
                    "hint": hint,
                }
            )
    return out


def _md_text(text: str) -> str:
    """Text safe inside Markdown link or image brackets."""
    return text.replace("\\", "\\\\").replace("]", "\\]")


def _page_tokens(theme: Theme) -> dict[str, str]:
    line = theme.grid if theme.grid.lower() != theme.background.lower() else theme.axis
    return {"bg": theme.background, "ink": theme.ink, "muted": theme.muted, "line": line}


def _token_css(tokens: Mapping[str, str]) -> str:
    return "".join(f"--mf-page-{k}:{v};" for k, v in tokens.items())


def _numbers_html(fig: Explanation) -> str:
    """Every panel's facts in a collapsed block, or "" when the figure has none."""
    esc = html.escape
    body: list[str] = []
    for key, panel in fig.panels.items():
        if not panel.facts:
            continue
        if len(fig.panels) > 1:
            body.append(f'<p class="mf-bpanel">{esc(key)} \N{MIDDLE DOT} {esc(panel.title or panel.describe)}</p>')
        body.append("<ul>" + "".join(f"<li>{esc(fact)}</li>" for fact in panel.facts) + "</ul>")
    if not body:
        return ""
    return f'<details class="mf-bnums"><summary>Numbers behind this figure</summary>{"".join(body)}</details>'


def _finding_html(fig: Explanation, n: int, tag: str) -> str:
    """One finding: the figure with its caption under it, then the numbers behind it.

    The takeaway heading stays in the outline and as the link target but is hidden on
    screen: the figure draws the same sentence as its title, and its source in its footer.
    """
    esc = html.escape
    heading = f'<{tag} id="fig-{n}-h" class="mf-sr-only">{esc(fig.takeaway)}</{tag}>'
    figure = render_html_fragment(fig, interactive=True, facts=False, caption=_caption(fig))
    return (
        f'<section id="fig-{n}" class="mf-bfind" aria-labelledby="fig-{n}-h">'
        f"{heading}{figure}{_numbers_html(fig)}</section>"
    )


#: Page CSS after the colour tokens. Thumbnails are each figure's own layout scaled down
#: (static: no tooltips, no data line); print gives each finding its own page, keeps
#: figures whole, wraps the thumbnails and omits the collapsed numbers.
_PAGE_CSS = """*{box-sizing:border-box}
html,body{margin:0;background:var(--mf-page-bg);color:var(--mf-page-ink)}
body{padding:32px 20px 64px;font:16px/1.55 system-ui,-apple-system,"Segoe UI",Helvetica,Arial,sans-serif}
.mf-brief{max-width:700px;margin:0 auto}
.mf-bhead h1{margin:0 0 .3em;font-size:1.75rem;line-height:1.2}
.mf-bsub{margin:0 0 .8em;color:var(--mf-page-muted)}
.mf-bsum{margin:0 0 .8em;padding-left:1.2em}
.mf-bthumbs ol{list-style:none;margin:1.25em 0 2em;padding:0 0 6px;display:grid;grid-auto-flow:column;
  grid-auto-columns:minmax(150px,1fr);gap:16px;overflow-x:auto}
.mf-bthumbs a{display:block;color:inherit;text-decoration:none}
.mf-bthumbs a:hover .mf-tk,.mf-bthumbs a:focus-visible .mf-tk{text-decoration:underline}
.mf-thumb{margin-bottom:6px;pointer-events:none}
.mf-thumb svg{max-height:160px}
.mf-tk{display:block;font-size:.875rem;line-height:1.35}
.mf-n{margin-right:.4em;color:var(--mf-page-muted);font-variant-numeric:tabular-nums}
.mf-bprose{margin:0 0 1em}
.mf-mc-chip{margin:0 0 1em}
.mf-mc-wide{margin:1.25em 0;overflow-x:auto}
.mf-bh{margin:2em 0 .6em;font-size:1.4rem;line-height:1.25}
.mf-bfind{margin:1.5em 0 2.5em}
.mf-sr-only{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap}
.mf-bnums{margin-top:.8em;font-size:.9rem}
.mf-bnums summary{cursor:pointer;color:var(--mf-page-muted)}
.mf-bnums ul{margin:.2em 0 .6em;padding-left:1.2em}
.mf-bpanel{margin:.6em 0 0;font-weight:600}
.mf-bfoot{margin-top:3em;padding-top:.8em;border-top:1px solid var(--mf-page-line);font-size:.875rem;
  color:var(--mf-page-muted)}
@media print{
  html{-webkit-print-color-adjust:exact;print-color-adjust:exact}
  body{padding:0}
  .mf-brief{max-width:none}
  .mf-bpage{break-before:page}
  .mf-bpage.mf-bfirst{break-before:auto}
  .mf-bthumbs ol{grid-auto-flow:row;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));overflow:visible}
  .mf-bthumbs li,.mf-bfind .mf-root{break-inside:avoid}
  .mf-bh{break-after:avoid}
  .mf-bnums,.mf-foot,.mf-tip,.mf-data{display:none!important}
}
"""


class Session:
    """Multi-turn visual memory keeping style, palette, and entity colours aligned across figures."""

    def __init__(
        self,
        *,
        style: str | Theme = "mintfig",
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
                    if style == "mintfig" and isinstance(saved.get("style"), str):
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
        *items: Any,
        subtitle: str | None = None,
        summary: Sequence[str] | str | None = None,
        source: str | None = None,
    ) -> Brief:
        """Compose this session's figures into a cohesive :class:`Brief`.

        With no ``items``, every figure in the session, in order. ``items`` that
        include figures are the briefing as given (prose, ``mintchip`` items, and
        figures in order); items without figures come first, followed by every
        figure in the session.
        """
        has_figure = any(
            (not isinstance(it, str) and not is_chip_item(it))
            or (isinstance(it, str) and _names_figure(it))
            for it in items
        )
        has_chip = any(is_chip_item(it) for it in items)
        if not self.figures and not has_figure and not has_chip:
            raise ExplainError(
                "Session has no figures yet.",
                fix_hint="Call session.explain(...) at least once before session.brief(...).",
            )
        return brief(
            title,
            *(items if has_figure else (*items, *self.figures)),
            subtitle=subtitle,
            summary=summary,
            source=source,
            style=self.style if isinstance(self.style, str) else self.style.name,
        )


class Brief:
    """A cohesive multi-figure investigation briefing exportable to HTML or Markdown.

    ``blocks`` holds the briefing in reading order: figures, ``mintchip`` chips and
    tables, prose paragraphs (other strings), and section headings (strings starting
    with ``"## "``).
    """

    def __init__(
        self,
        title: str,
        figures: Sequence[Any],
        *,
        subtitle: str | None = None,
        summary: Sequence[str] | str | None = None,
        source: str | None = None,
        style: str | Theme | None = None,
    ) -> None:
        self.title = title
        self.blocks: list[Any] = [
            b.strip() if isinstance(b, str) else b
            for b in figures
            if not isinstance(b, str) or b.strip()
        ]
        self.figures = [b for b in self.blocks if isinstance(b, Explanation)]
        self.subtitle = subtitle
        if isinstance(summary, str):
            self.summary_points = [summary]
        elif summary is not None:
            self.summary_points = [str(s) for s in summary if str(s).strip()]
        else:
            self.summary_points = []
        self.source = source
        if style is not None:
            self.theme = get_theme(style)
        elif self.figures:
            self.theme = self.figures[0].theme
        else:
            self.theme = get_theme("mintfig")

    @property
    def ship_all(self) -> bool:
        return all(fig.ship for fig in self.figures)

    def _pages(self) -> list[list[Any]]:
        """Blocks grouped so each group ends at a figure; trailing prose joins the last group."""
        pages: list[list[Any]] = [[]]
        for block in self.blocks:
            pages[-1].append(block)
            if isinstance(block, Explanation):
                pages.append([])
        if not pages[-1]:
            pages.pop()
        elif len(pages) > 1:
            pages[-2].extend(pages.pop())
        return pages

    def _finding_levels(self) -> list[int]:
        """Heading level of each finding: 2, or 3 once a ``## `` section has begun."""
        levels: list[int] = []
        level = 2
        for block in self.blocks:
            if isinstance(block, Explanation):
                levels.append(level)
            elif isinstance(block, str) and _is_heading(block):
                level = 3
        return levels

    def to_html(self) -> str:
        """Render a self-contained HTML briefing: the findings at a glance, then each in turn.

        The page follows the reader's light or dark preference when the briefing uses
        the default style; an explicit style pins page and figures to that style's
        scheme (``data-mf-scheme`` on the root, plus ``data-mc-scheme`` when
        ``mintchip`` content is present).
        """
        esc = html.escape
        theme = self.theme
        auto = theme.name == "mintfig"
        scheme = "dark" if relative_luminance(theme.background) < 0.2 else "light"
        chip_theme = "auto" if auto else scheme
        light = _token_css(_page_tokens(theme))
        tokens = [f":root{{{light}color-scheme: {'light dark' if auto else scheme}}}"]
        if auto:
            dark = _token_css(_page_tokens(THEMES["dark"]))
            tokens += [
                f"@media (prefers-color-scheme:dark){{:root{{{dark}}}}}",
                f':root[data-mf-scheme="dark"]{{{dark}color-scheme: dark}}',
                f':root[data-mf-scheme="light"]{{{light}color-scheme: light}}',
            ]

        head = [f"<h1>{esc(self.title)}</h1>"]
        if self.subtitle:
            head.append(f'<p class="mf-bsub">{esc(self.subtitle)}</p>')
        if self.summary_points:
            head.append('<ul class="mf-bsum">' + "".join(f"<li>{esc(p)}</li>" for p in self.summary_points) + "</ul>")

        overview = ""
        if len(self.figures) > 1:
            cells = [
                f'<li><a href="#fig-{i}"><div class="mf-thumb" aria-hidden="true">'
                f"{render_html_fragment(fig, interactive=False, responsive=False)}</div>"
                f'<span class="mf-tk"><span class="mf-n">{i}</span>{esc(fig.takeaway)}</span></a></li>'
                for i, fig in enumerate(self.figures, 1)
            ]
            overview = f'<nav class="mf-bthumbs" aria-label="Findings"><ol>{"".join(cells)}</ol></nav>'

        levels = self._finding_levels()
        pages: list[str] = []
        used_mintchip = False
        n = 0
        for p, page in enumerate(self._pages()):
            parts: list[str] = []
            for block in page:
                if isinstance(block, str):
                    if _is_heading(block):
                        parts.append(f'<h2 class="mf-bh">{esc(_heading_text(block))}</h2>')
                    else:
                        paras, used_dir = render_prose_html(block, theme=chip_theme)
                        used_mintchip = used_mintchip or used_dir
                        parts.extend(f'<p class="mf-bprose">{t}</p>' for t in paras)
                    continue
                if is_table(block):
                    used_mintchip = True
                    parts.append(f'<div class="mf-mc-wide">{block.html(theme=chip_theme)}</div>')
                    continue
                if is_chip(block):
                    used_mintchip = True
                    parts.append(f'<p class="mf-bprose mf-mc-chip">{block.html(theme=chip_theme)}</p>')
                    continue
                n += 1
                parts.append(_finding_html(block, n, f"h{levels[n - 1]}"))
            pages.append(f'<div class="mf-bpage{" mf-bfirst" if p == 0 else ""}">{"".join(parts)}</div>')

        if auto:
            root_attr = ""
        elif used_mintchip:
            root_attr = f' data-mf-scheme="{scheme}" data-mc-scheme="{scheme}"'
        else:
            root_attr = f' data-mf-scheme="{scheme}"'

        mc_style = ""
        if used_mintchip:
            raw_mc_css = chip_css()
            mc_style = f"{raw_mc_css}\n{SCHEME_SYNC_CSS}" if raw_mc_css else SCHEME_SYNC_CSS

        foot = f'<footer class="mf-bfoot">Source: {esc(self.source)}</footer>' if self.source else ""
        return (
            "<!DOCTYPE html>\n"
            f'<html lang="en"{root_attr}>\n'
            "<head>\n"
            '<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            f'<meta name="color-scheme" content="{"light dark" if auto else scheme}">\n'
            f"<title>{esc(self.title)}</title>\n"
            f"<style>\n{chr(10).join(tokens)}\n{_PAGE_CSS}{mc_style}</style>\n"
            "</head>\n"
            "<body>\n"
            '<main class="mf-brief">\n'
            f'<header class="mf-bhead">{"".join(head)}</header>\n'
            f"{overview}\n"
            f"{chr(10).join(pages)}\n"
            f"{foot}\n"
            "</main>\n"
            "</body>\n"
            "</html>\n"
        )

    def to_markdown(
        self,
        *,
        image_paths: Sequence[str] | None = None,
    ) -> str:
        """Render a Markdown briefing: a numbered list of takeaways, then for each finding
        its takeaway as heading, the image, the caption in italics and the source (plus
        the table of any ``mint.table`` panel). Prose, ``## `` headings, and ``mintchip``
        chips/tables stay in place."""
        seen: dict[str, int] = {}
        _md_slug(self.title, seen)
        slugs: list[str] = []
        for block in self.blocks:
            if isinstance(block, Explanation):
                slugs.append(_md_slug(block.takeaway, seen))
            elif isinstance(block, str) and _is_heading(block):
                _md_slug(_heading_text(block), seen)

        lines: list[str] = [f"# {self.title}"]
        if self.subtitle:
            lines += ["", f"*{self.subtitle}*"]
        if self.summary_points:
            lines.append("")
            lines += [f"- {pt}" for pt in self.summary_points]
        if len(self.figures) > 1:
            lines.append("")
            lines += [
                f"{i}. [{_md_text(fig.takeaway)}](#{slug})"
                for i, (fig, slug) in enumerate(zip(self.figures, slugs, strict=True), 1)
            ]

        levels = self._finding_levels()
        idx = 0
        for block in self.blocks:
            lines.append("")
            if isinstance(block, str):
                if _is_heading(block):
                    lines.append(f"## {_heading_text(block)}")
                else:
                    rendered, _ = render_prose_markdown(block)
                    lines.append(rendered)
                continue
            if is_chip_item(block):
                lines.append(block.markdown())
                continue
            idx += 1
            lines.append(f"{'#' * levels[idx - 1]} {block.takeaway}")
            img_ref = (
                image_paths[idx - 1]
                if image_paths is not None and idx - 1 < len(image_paths)
                else (str(block.saved_path) if block.saved_path else None)
            )
            if img_ref:
                lines += ["", f"![{_md_text(block.takeaway)}]({_markdown_target(img_ref)})"]
            caption = _caption(block)
            if caption:
                lines += ["", f"*{caption}*"]
            if block.source:
                lines += ["", f"Source: {block.source}"]
            for panel in block.panels.values():
                if panel.kind == "table":
                    lines += ["", panel.to_markdown()]

        if self.source:
            lines += ["", f"Briefing source: {self.source}"]
        return "\n".join(lines) + "\n"

    def save(self, path: str | Path, *, scale: float = 2.0) -> dict[str, Any]:
        """Write the briefing as ``.html`` (self-contained) or ``.md`` (with saved figure PNGs).

        The returned dict carries ``scales_differ``: pairs of panels in different
        figures that plot the same label and unit over different axis ranges (or one
        log, one linear). It is advice; nothing is re-rendered.
        """
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        suffix = out.suffix.lower()
        assets: list[str] = []

        if suffix in {".html", ".htm"}:
            out.write_text(self.to_html(), encoding="utf-8")
            fmt_name = "html"
        elif suffix in {".md", ".markdown"}:
            rel_paths: list[str] = []
            if self.figures:
                asset_dir = out.parent / f"{out.stem}_figures"
                asset_dir.mkdir(parents=True, exist_ok=True)
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
            "scales_differ": _scales_differ(self.figures),
        }


def brief(
    title: str,
    *items: Any,
    subtitle: str | None = None,
    summary: Sequence[str] | str | None = None,
    source: str | None = None,
    style: str | Theme | None = None,
) -> Brief:
    """Compose 1–12 figures, with prose and optional ``mintchip`` chips/tables between them,
    into one HTML or Markdown briefing.

    ``items`` are read in order. A figure is an ``Explanation``, a spec dict, a
    ``Path``, or a string naming a ``.png`` / ``.json`` file; ``mintchip.Chip`` and
    ``mintchip.Table`` objects render inline / wide; any other string is a paragraph
    (with optional ``{{...}}`` mintchip directives when ``mintchip`` is installed), or
    a section heading when it starts with ``"## "``.
    """
    if not isinstance(title, str) or not title.strip():
        raise ExplainError(
            "brief() needs a non-empty title.",
            fix_hint='e.g. mint.brief("Q4 latency investigation", fig1, fig2).',
        )
    fig_count = sum(
        (not isinstance(item, str) and not is_chip_item(item))
        or (isinstance(item, str) and _names_figure(item))
        for item in items
    )
    chip_count = sum(is_chip_item(item) for item in items)
    if fig_count == 0 and chip_count == 0:
        raise ExplainError(
            "brief() needs at least one figure.",
            fix_hint="Pass one or more Explanation objects, saved mintfig PNG/JSON paths, or mintchip items; strings are prose.",
        )
    if fig_count > _MAX_BRIEF_FIGURES:
        raise ExplainError(
            f"brief() got {fig_count} figures; at most {_MAX_BRIEF_FIGURES} fit one cohesive briefing.",
            fix_hint=f"Keep at most {_MAX_BRIEF_FIGURES} key figures in one brief.",
            rule="too_many_items",
        )
    resolved = [block for block in (_resolve_item(item) for item in items) if block is not None]
    return Brief(
        title.strip(),
        resolved,
        subtitle=subtitle,
        summary=summary,
        source=source,
        style=style,
    )
