"""Opt-in local visual lab notebook (``.mintfig/``) for figure provenance and memory.

Nothing is created automatically until a user opts in via ``mintfig log --init``
(or ``mint.notebook.init()``). Once ``.mintfig/config.json`` exists in a project
root, ``fig.save(...)`` quietly logs each figure's artifact, spec JSON, computed
facts, source hashes, git commit, and ship status into an append-only
``.mintfig/index.jsonl`` ledger and refreshes a zero-CDN ``.mintfig/index.html``
lab notebook viewer.
"""

from __future__ import annotations

import base64
import datetime
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

NOTEBOOK_DIRNAME = ".mintfig"
CONFIG_FILENAME = "config.json"
INDEX_FILENAME = "index.jsonl"
HTML_FILENAME = "index.html"
SESSION_FILENAME = "session.json"
ARTIFACTS_DIRNAME = "artifacts"
SCHEMA_VERSION = "0.1"

_SLUG_RE = re.compile(r"[^a-z0-9]+")
_SOURCE_PATH_RE = re.compile(r"(?:[\w./-]+\.(?:csv|tsv|json|jsonl|parquet|xlsx|txt|log|py))", re.IGNORECASE)


def _now_iso() -> str:
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def _slug(text: str, max_len: int = 28) -> str:
    cleaned = _SLUG_RE.sub("-", text.lower()).strip("-")
    return (cleaned[:max_len].strip("-")) or "figure"


def _sha256_file(path: Path, max_bytes: int = 50 * 1024 * 1024) -> str | None:
    try:
        if not path.is_file() or path.stat().st_size > max_bytes:
            return None
        h = hashlib.sha256()
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()[:16]
    except OSError:
        return None


def _git_info(cwd: Path) -> tuple[str | None, str | None, Path | None]:
    """Return ``(short_commit, branch, git_dir)`` if ``cwd`` is inside a git repo."""
    cur = cwd.resolve()
    git_root: Path | None = None
    for parent in (cur, *cur.parents):
        if (parent / ".git").exists():
            git_root = parent
            break
    if git_root is None:
        return None, None, None
    git_dir = git_root / ".git"
    commit = None
    branch = None
    try:
        p1 = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=git_root,
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        if p1.returncode == 0 and p1.stdout.strip():
            commit = p1.stdout.strip()
        p2 = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=git_root,
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        if p2.returncode == 0 and p2.stdout.strip():
            branch = p2.stdout.strip()
    except OSError:
        pass
    return commit, branch, git_dir


def _add_git_exclude(repo_root: Path) -> bool:
    """Append ``.mintfig/`` to ``.git/info/exclude`` so git status stays completely clean."""
    git_dir = repo_root / ".git"
    if not git_dir.is_dir():
        return False
    exclude = git_dir / "info" / "exclude"
    try:
        exclude.parent.mkdir(parents=True, exist_ok=True)
        existing = exclude.read_text(encoding="utf-8") if exclude.exists() else ""
        lines = {ln.strip() for ln in existing.splitlines()}
        if ".mintfig/" in lines or ".mintfig" in lines:
            return False
        sep = "" if (not existing or existing.endswith("\n")) else "\n"
        exclude.write_text(
            f"{existing}{sep}# mintfig local visual lab notebook\n.mintfig/\n",
            encoding="utf-8",
        )
        return True
    except OSError:
        return False


def find_notebook(start: str | Path | None = None) -> Path | None:
    """Locate an initialized ``.mintfig`` directory from ``start`` upward (returns ``None`` if opted out)."""
    if os.environ.get("MINTFIG_NO_LOG", "").strip().lower() in {"1", "true", "yes"}:
        return None
    env_dir = os.environ.get("MINTFIG_NOTEBOOK", "").strip()
    if env_dir:
        cand = Path(env_dir).expanduser().resolve()
        cfg = cand / CONFIG_FILENAME
        if cfg.is_file():
            try:
                data = json.loads(cfg.read_text(encoding="utf-8"))
                return cand if data.get("auto_capture", True) else None
            except (OSError, json.JSONDecodeError):
                return cand
        return None

    cur = Path(start).resolve() if start is not None else Path.cwd().resolve()
    if cur.is_file():
        cur = cur.parent
    home = Path.home().resolve()
    for parent in (cur, *cur.parents):
        cand = parent / NOTEBOOK_DIRNAME
        cfg = cand / CONFIG_FILENAME
        if cfg.is_file():
            try:
                data = json.loads(cfg.read_text(encoding="utf-8"))
                return cand if data.get("auto_capture", True) else None
            except (OSError, json.JSONDecodeError):
                return cand
        if (parent / ".git").exists() or parent == home:
            break
    return None


def init(
    root: str | Path | None = None,
    *,
    auto_capture: bool = True,
    git_exclude: bool = True,
    title: str | None = None,
) -> Path:
    """Initialize an opt-in ``.mintfig/`` visual lab notebook under ``root`` (default cwd)."""
    base = Path(root).resolve() if root is not None else Path.cwd().resolve()
    nb_dir = base if base.name == NOTEBOOK_DIRNAME else (base / NOTEBOOK_DIRNAME)
    (nb_dir / ARTIFACTS_DIRNAME).mkdir(parents=True, exist_ok=True)

    cfg_path = nb_dir / CONFIG_FILENAME
    cfg: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "title": title or f"{nb_dir.parent.name} — mintfig lab notebook",
        "created_at": _now_iso(),
        "auto_capture": bool(auto_capture),
    }
    if cfg_path.is_file():
        try:
            old = json.loads(cfg_path.read_text(encoding="utf-8"))
            if isinstance(old, dict):
                old.update({"auto_capture": bool(auto_capture)})
                if title:
                    old["title"] = title
                cfg = old
        except (OSError, json.JSONDecodeError):
            pass
    cfg_path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    idx_path = nb_dir / INDEX_FILENAME
    if not idx_path.exists():
        idx_path.write_text("", encoding="utf-8")

    if git_exclude:
        _add_git_exclude(nb_dir.parent)

    build_index_html(nb_dir)
    return nb_dir


def list_entries(
    notebook_dir: str | Path | None = None,
    *,
    query: str | None = None,
    tag: str | None = None,
    ship_only: bool = False,
    last: int | None = None,
) -> list[dict[str, Any]]:
    """Read entries from ``.mintfig/index.jsonl`` (newest first when ``last`` is set, else chronological)."""
    nb = Path(notebook_dir).resolve() if notebook_dir is not None else find_notebook()
    if nb is None:
        return []
    idx_path = nb / INDEX_FILENAME
    if not idx_path.is_file():
        return []

    entries: list[dict[str, Any]] = []
    for raw in idx_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            entries.append(item)

    if ship_only:
        entries = [e for e in entries if e.get("ship") is True]
    if tag:
        want_tag = tag.strip().lower()
        entries = [
            e for e in entries if any(str(t).lower() == want_tag for t in (e.get("tags") or []))
        ]
    if query:
        q = query.strip().lower()
        entries = [
            e
            for e in entries
            if q
            in " ".join(
                [
                    str(e.get("id", "")),
                    str(e.get("takeaway", "")),
                    str(e.get("subtitle", "")),
                    str(e.get("source", "")),
                    str(e.get("script", "")),
                    str(e.get("note", "")),
                    " ".join(str(f) for f in (e.get("facts") or [])),
                    " ".join(str(t) for t in (e.get("tags") or [])),
                ]
            ).lower()
        ]
    if last is not None and last > 0:
        entries = entries[-last:]
    return entries


def _detect_calling_script(project_root: Path) -> str | None:
    argv0 = sys.argv[0] if sys.argv else ""
    if not argv0 or argv0 in {"-c", "-m", "-"}:
        return None
    p = Path(argv0)
    if p.suffix.lower() != ".py":
        return None
    try:
        return str(p.resolve().relative_to(project_root.resolve()))
    except ValueError:
        return str(p)


def _collect_sources(
    source_text: str | None,
    explicit_files: Iterable[str | Path] | None,
    project_root: Path,
) -> list[dict[str, Any]]:
    seen: set[str] = set()
    candidates: list[Path] = []
    if explicit_files:
        for item in explicit_files:
            candidates.append(Path(item))
    if source_text:
        for m in _SOURCE_PATH_RE.finditer(source_text):
            candidates.append(Path(m.group(0)))

    out: list[dict[str, Any]] = []
    for raw_p in candidates:
        resolved = raw_p if raw_p.is_absolute() else (Path.cwd() / raw_p)
        if not resolved.is_file():
            alt = project_root / raw_p
            if alt.is_file():
                resolved = alt
        if not resolved.is_file():
            continue
        key = str(resolved.resolve())
        if key in seen:
            continue
        seen.add(key)
        try:
            rel = str(resolved.resolve().relative_to(project_root.resolve()))
        except ValueError:
            rel = str(resolved.resolve())
        out.append({"path": rel, "sha256": _sha256_file(resolved)})
    return out


def _update_session_colors(nb_dir: Path, colors: Mapping[str, Any] | None) -> None:
    if not colors:
        return
    sess_path = nb_dir / SESSION_FILENAME
    data: dict[str, Any] = {"colors": {}}
    if sess_path.is_file():
        try:
            loaded = json.loads(sess_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                data = loaded
        except (OSError, json.JSONDecodeError):
            pass
    ledger = data.setdefault("colors", {})
    if isinstance(ledger, dict):
        for name, val in colors.items():
            if isinstance(name, str) and name.strip() and isinstance(val, str):
                ledger[name] = val
    data["updated_at"] = _now_iso()
    sess_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _make_entry_id(takeaway: str, ts: datetime.datetime) -> str:
    stamp = ts.strftime("%Y%m%d_%H%M%S")
    digest = hashlib.sha256(f"{ts.isoformat()}:{takeaway}".encode()).hexdigest()[:6]
    return f"{stamp}_{digest}_{_slug(takeaway, 22)}"


def log_explanation(
    exp: Any,
    saved_path: str | Path,
    *,
    summary: Mapping[str, Any] | None = None,
    notebook_dir: str | Path | None = None,
    source_files: Iterable[str | Path] | None = None,
    note: str | None = None,
    tags: Iterable[str] | None = None,
    rebuild_html: bool = True,
) -> dict[str, Any] | None:
    """Append a saved ``mint.explain`` figure into ``.mintfig/`` (returns ``None`` if no notebook)."""
    saved = Path(saved_path).resolve()
    nb_dir = Path(notebook_dir).resolve() if notebook_dir is not None else find_notebook(saved.parent)
    if nb_dir is None:
        return None
    # Avoid recursive logging if the caller saved directly inside .mintfig/artifacts/
    try:
        saved.relative_to(nb_dir)
        return None
    except ValueError:
        pass

    project_root = nb_dir.parent
    now = datetime.datetime.now().astimezone()
    takeaway = str(getattr(exp, "takeaway", "") or "Untitled figure")
    entry_id = _make_entry_id(takeaway, now)

    artifacts_dir = nb_dir / ARTIFACTS_DIRNAME
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    ext = saved.suffix.lower() or ".png"
    art_rel = f"{ARTIFACTS_DIRNAME}/{entry_id}{ext}"
    if saved.is_file():
        shutil.copy2(saved, nb_dir / art_rel)

    spec_rel: str | None = None
    try:
        spec_dict = exp.to_spec()
        spec_rel = f"{ARTIFACTS_DIRNAME}/{entry_id}.json"
        (nb_dir / spec_rel).write_text(
            json.dumps(spec_dict, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    except Exception:  # noqa: BLE001
        spec_rel = None

    summ = dict(summary) if summary is not None else exp.summary()
    facts: list[str] = []
    panel_kinds: list[str] = []
    for p in summ.get("panels") or []:
        if isinstance(p, dict):
            if p.get("kind"):
                panel_kinds.append(str(p["kind"]))
            for f in p.get("facts") or []:
                facts.append(str(f))

    commit, branch, _ = _git_info(project_root)
    source_text = getattr(exp, "source", None)
    sources = _collect_sources(source_text, source_files, project_root)
    merged_tags = sorted({*panel_kinds, *(str(t) for t in (tags or ()))})

    try:
        orig_rel = str(saved.relative_to(project_root))
    except ValueError:
        orig_rel = str(saved)

    entry: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "id": entry_id,
        "ts": now.isoformat(timespec="seconds"),
        "takeaway": takeaway,
        "subtitle": getattr(exp, "subtitle", None) or "",
        "ship": bool(summ.get("ship", False)),
        "issues": [
            f"{i.get('rule', 'issue')}: {i.get('message', '')}"
            for i in (summ.get("issues") or [])
            if isinstance(i, dict)
        ],
        "facts": facts[:12],
        "source": source_text or "",
        "sources": sources,
        "script": _detect_calling_script(project_root),
        "git_commit": commit,
        "git_branch": branch,
        "artifact": art_rel,
        "artifact_kind": ext.lstrip("."),
        "spec_file": spec_rel,
        "original_path": orig_rel,
        "display": summ.get("display") or {},
        "tags": merged_tags,
        "note": note or (getattr(exp, "note", None) or ""),
    }

    with (nb_dir / INDEX_FILENAME).open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")

    _update_session_colors(nb_dir, summ.get("colors"))

    if rebuild_html:
        build_index_html(nb_dir)
    return entry


def log_file(
    artifact_path: str | Path,
    *,
    takeaway: str | None = None,
    source: str | None = None,
    source_files: Iterable[str | Path] | None = None,
    script: str | None = None,
    ship: bool | None = None,
    facts: Iterable[str] | None = None,
    note: str | None = None,
    tags: Iterable[str] | None = None,
    notebook_dir: str | Path | None = None,
    rebuild_html: bool = True,
) -> dict[str, Any]:
    """Manually log any PNG, SVG, or HTML artifact (including plain Matplotlib) into ``.mintfig/``."""
    src = Path(artifact_path).resolve()
    if not src.is_file():
        raise FileNotFoundError(f"Artifact not found: {src}")

    nb_dir = Path(notebook_dir).resolve() if notebook_dir is not None else find_notebook(src.parent)
    if nb_dir is None:
        nb_dir = init(Path.cwd())

    # If the PNG carries an embedded mintfig spec, recover takeaway/source/facts automatically
    embedded_spec: dict[str, Any] | None = None
    if src.suffix.lower() == ".png":
        try:
            from ._explain.layout import load as _load_exp

            exp = _load_exp(src)
            embedded_spec = exp.to_spec()
            takeaway = takeaway or exp.takeaway
            source = source or exp.source
            if facts is None:
                facts = [f for p in exp.panels.values() for f in p.facts]
            if ship is None:
                ship = bool(exp.summary().get("ship", True))
        except Exception:  # noqa: BLE001
            embedded_spec = None

    project_root = nb_dir.parent
    now = datetime.datetime.now().astimezone()
    label = takeaway or src.stem.replace("_", " ")
    entry_id = _make_entry_id(label, now)

    artifacts_dir = nb_dir / ARTIFACTS_DIRNAME
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    ext = src.suffix.lower() or ".png"
    art_rel = f"{ARTIFACTS_DIRNAME}/{entry_id}{ext}"
    shutil.copy2(src, nb_dir / art_rel)

    spec_rel: str | None = None
    if embedded_spec is not None:
        spec_rel = f"{ARTIFACTS_DIRNAME}/{entry_id}.json"
        (nb_dir / spec_rel).write_text(
            json.dumps(embedded_spec, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    commit, branch, _ = _git_info(project_root)
    sources = _collect_sources(source, source_files, project_root)
    try:
        orig_rel = str(src.relative_to(project_root))
    except ValueError:
        orig_rel = str(src)

    entry: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "id": entry_id,
        "ts": now.isoformat(timespec="seconds"),
        "takeaway": label,
        "subtitle": "",
        "ship": True if ship is None else bool(ship),
        "issues": [],
        "facts": [str(f) for f in (facts or ())][:12],
        "source": source or "",
        "sources": sources,
        "script": script or _detect_calling_script(project_root),
        "git_commit": commit,
        "git_branch": branch,
        "artifact": art_rel,
        "artifact_kind": ext.lstrip("."),
        "spec_file": spec_rel,
        "original_path": orig_rel,
        "display": {},
        "tags": sorted({str(t) for t in (tags or (ext.lstrip("."),))}),
        "note": note or "",
    }

    with (nb_dir / INDEX_FILENAME).open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")

    if rebuild_html:
        build_index_html(nb_dir)
    return entry


def _inline_preview(nb_dir: Path, entry: Mapping[str, Any], max_bytes: int = 350_000) -> str | None:
    rel = entry.get("artifact")
    if not isinstance(rel, str) or not rel:
        return None
    p = nb_dir / rel
    if not p.is_file() or p.stat().st_size > max_bytes:
        return None
    ext = p.suffix.lower()
    if ext == ".png":
        b64 = base64.b64encode(p.read_bytes()).decode("ascii")
        return f"data:image/png;base64,{b64}"
    if ext == ".svg":
        b64 = base64.b64encode(p.read_bytes()).decode("ascii")
        return f"data:image/svg+xml;base64,{b64}"
    return None


def build_index_html(
    notebook_dir: str | Path,
    *,
    embed_previews: bool = True,
) -> Path:
    """Regenerate the zero-CDN interactive ``.mintfig/index.html`` lab notebook viewer."""
    nb_dir = Path(notebook_dir).resolve()
    cfg_path = nb_dir / CONFIG_FILENAME
    title = f"{nb_dir.parent.name} — mintfig lab notebook"
    if cfg_path.is_file():
        try:
            title = str(json.loads(cfg_path.read_text(encoding="utf-8")).get("title") or title)
        except (OSError, json.JSONDecodeError):
            pass

    entries = list(reversed(list_entries(nb_dir)))  # newest first
    payload_rows: list[dict[str, Any]] = []
    for e in entries:
        row = dict(e)
        if embed_previews:
            row["_preview"] = _inline_preview(nb_dir, e)
        payload_rows.append(row)

    safe_json = json.dumps(
        {"title": title, "generated_at": _now_iso(), "entries": payload_rows},
        ensure_ascii=False,
    ).replace("</", "<\\/")

    doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title, quote=True)}</title>
<style>
  :root {{
    --bg: #fafbf9; --card: #ffffff; --ink: #171b21; --muted: #5a6472;
    --border: #e1e6ed; --accent: #148660; --accent-soft: #e8f7f1;
    --warn: #c43e2e; --warn-soft: #fdeeed; --mono: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  }}
  [data-theme="dark"] {{
    --bg: #0f141e; --card: #161d2b; --ink: #edf1f7; --muted: #93a1b8;
    --border: #263147; --accent: #34d8a0; --accent-soft: #122d27;
    --warn: #ff6b79; --warn-soft: #311722;
  }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; background: var(--bg); color: var(--ink); font: 14px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; }}
  .wrap {{ max-width: 1080px; margin: 0 auto; padding: 24px 20px 48px; }}
  header {{ display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 12px; padding-bottom: 16px; border-bottom: 1px solid var(--border); }}
  h1 {{ margin: 0; font-size: 1.35rem; letter-spacing: -0.015em; }}
  .sub {{ color: var(--muted); font-size: 0.85rem; margin-top: 2px; }}
  .controls {{ display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin: 16px 0 20px; }}
  input[type="search"] {{ flex: 1 1 240px; padding: 7px 11px; border-radius: 8px; border: 1px solid var(--border); background: var(--card); color: var(--ink); font: inherit; }}
  .btn {{ padding: 6px 11px; border-radius: 8px; border: 1px solid var(--border); background: var(--card); color: var(--ink); font: 500 12.5px/1.2 inherit; cursor: pointer; }}
  .btn.active {{ border-color: var(--accent); color: var(--accent); background: var(--accent-soft); }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(460px, 1fr)); gap: 18px; }}
  @media (max-width: 540px) {{ .grid {{ grid-template-columns: 1fr; }} }}
  .card {{ background: var(--card); border: 1px solid var(--border); border-radius: 12px; overflow: hidden; display: flex; flex-direction: column; }}
  .card-head {{ padding: 14px 16px 10px; display: flex; justify-content: space-between; gap: 10px; align-items: flex-start; }}
  .takeaway {{ font-weight: 700; font-size: 0.98rem; line-height: 1.32; }}
  .badge {{ flex: 0 0 auto; font-family: var(--mono); font-size: 11px; font-weight: 700; padding: 2px 8px; border-radius: 999px; }}
  .badge.ship {{ background: var(--accent-soft); color: var(--accent); }}
  .badge.fix {{ background: var(--warn-soft); color: var(--warn); }}
  .preview {{ padding: 6px 14px 10px; background: #ffffff; border-top: 1px solid var(--border); border-bottom: 1px solid var(--border); }}
  .preview img {{ width: 100%; height: auto; display: block; border-radius: 4px; }}
  .preview-link {{ display: block; padding: 20px 16px; text-align: center; color: var(--accent); font-family: var(--mono); font-size: 12.5px; text-decoration: none; }}
  .meta {{ padding: 10px 16px 14px; font-size: 12px; color: var(--muted); display: flex; flex-direction: column; gap: 6px; }}
  .meta-row {{ display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }}
  .pill {{ font-family: var(--mono); font-size: 11px; padding: 1px 7px; border-radius: 5px; border: 1px solid var(--border); }}
  details summary {{ cursor: pointer; color: var(--ink); font-weight: 500; }}
  ul.facts {{ margin: 6px 0 2px; padding-left: 18px; }}
  .empty {{ padding: 48px 20px; text-align: center; color: var(--muted); border: 1px dashed var(--border); border-radius: 12px; }}
  .copy-msg {{ color: var(--accent); font-family: var(--mono); font-size: 11px; }}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <div>
      <h1 id="nb-title"></h1>
      <div class="sub" id="nb-sub"></div>
    </div>
    <button id="theme-btn" class="btn" type="button">Toggle theme</button>
  </header>
  <div class="controls">
    <input id="q" type="search" placeholder="Filter takeaways, facts, sources, scripts, commits…">
    <button class="btn active" data-filter="all" type="button">All</button>
    <button class="btn" data-filter="ship" type="button">Ship ✓</button>
    <button class="btn" data-filter="fix" type="button">Needs fix</button>
  </div>
  <div id="grid" class="grid"></div>
</div>
<script id="nb-data" type="application/json">{safe_json}</script>
<script>
(function() {{
  const DATA = JSON.parse(document.getElementById("nb-data").textContent);
  const root = document.documentElement;
  function syncTheme() {{
    const cls = root.classList;
    if (cls.contains("light")) root.setAttribute("data-theme", "light");
    else if (cls.contains("dark")) root.setAttribute("data-theme", "dark");
    else if (window.matchMedia) root.setAttribute("data-theme", window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
  }}
  syncTheme();
  window.addEventListener("themechange", syncTheme);
  document.getElementById("theme-btn").onclick = () => {{
    root.setAttribute("data-theme", root.getAttribute("data-theme") === "dark" ? "light" : "dark");
  }};

  const esc = (s) => String(s == null ? "" : s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
  document.getElementById("nb-title").textContent = DATA.title;
  document.getElementById("nb-sub").textContent = `${{DATA.entries.length}} figure(s) logged · updated ${{DATA.generated_at}}`;

  let mode = "all";
  const qEl = document.getElementById("q");
  document.querySelectorAll("[data-filter]").forEach((b) => {{
    b.onclick = () => {{
      mode = b.dataset.filter;
      document.querySelectorAll("[data-filter]").forEach((x) => x.classList.toggle("active", x === b));
      render();
    }};
  }});
  qEl.oninput = render;

  function render() {{
    const q = qEl.value.trim().toLowerCase();
    const list = DATA.entries.filter((e) => {{
      if (mode === "ship" && !e.ship) return false;
      if (mode === "fix" && e.ship) return false;
      if (!q) return true;
      const hay = [e.id, e.takeaway, e.subtitle, e.source, e.script, e.git_commit, e.note, ...(e.facts||[]), ...(e.tags||[])].join(" ").toLowerCase();
      return hay.includes(q);
    }});
    const grid = document.getElementById("grid");
    if (!list.length) {{
      grid.innerHTML = '<div class="empty">No matching figures logged yet. Save a figure with <code>mint.explain(...).save(...)</code> or run <code>mintfig log --add fig.png</code>.</div>';
      return;
    }}
    grid.innerHTML = list.map((e, i) => {{
      const preview = e._preview
        ? `<div class="preview"><a href="${{esc(e.artifact)}}" target="_blank"><img src="${{e._preview}}" alt="${{esc(e.takeaway)}}"></a></div>`
        : `<div class="preview"><a class="preview-link" href="${{esc(e.artifact)}}" target="_blank">Open interactive artifact (${{esc(e.artifact)}}) →</a></div>`;
      const srcs = (e.sources||[]).map((s) => `<span class="pill">${{esc(s.path)}} (${{esc(s.sha256||"")}})</span>`).join("");
      const facts = (e.facts||[]).length
        ? `<details><summary>Computed facts (${{e.facts.length}})</summary><ul class="facts">${{e.facts.map((f) => `<li>${{esc(f)}}</li>`).join("")}}</ul></details>`
        : "";
      const cite = `${{e.id}} · ${{e.takeaway}}${{e.git_commit ? " · @" + e.git_commit : ""}}`;
      return `<article class="card">
        <div class="card-head">
          <div class="takeaway">${{esc(e.takeaway)}}</div>
          <span class="badge ${{e.ship ? "ship" : "fix"}}">${{e.ship ? "ship ✓" : "fix first"}}</span>
        </div>
        ${{preview}}
        <div class="meta">
          <div class="meta-row">
            <span class="pill">${{esc(e.ts.replace("T"," ").slice(0,19))}}</span>
            ${{e.git_commit ? `<span class="pill">${{esc(e.git_branch||"git")}}@${{esc(e.git_commit)}}</span>` : ""}}
            ${{(e.tags||[]).map((t) => `<span class="pill">${{esc(t)}}</span>`).join("")}}
          </div>
          ${{e.source ? `<div>Source: ${{esc(e.source)}}</div>` : ""}}
          ${{srcs ? `<div class="meta-row">${{srcs}}</div>` : ""}}
          ${{e.script ? `<div>Script: <code>${{esc(e.script)}}</code></div>` : ""}}
          ${{facts}}
          <div class="meta-row">
            <button class="btn" type="button" data-cite="${{esc(cite)}}" data-idx="${{i}}">Copy citation</button>
            ${{e.spec_file ? `<a class="btn" href="${{esc(e.spec_file)}}" target="_blank" style="text-decoration:none">spec.json</a>` : ""}}
            <span class="copy-msg" id="cm-${{i}}"></span>
          </div>
        </div>
      </article>`;
    }}).join("");
    grid.querySelectorAll("[data-cite]").forEach((b) => {{
      b.onclick = () => {{
        const txt = b.dataset.cite;
        if (navigator.clipboard) navigator.clipboard.writeText(txt).catch(() => {{}});
        const msg = document.getElementById("cm-" + b.dataset.idx);
        if (msg) msg.textContent = "copied";
      }};
    }});
  }}
  render();
}})();
</script>
</body>
</html>
"""
    out = nb_dir / HTML_FILENAME
    out.write_text(doc, encoding="utf-8")
    return out


def format_log_table(entries: list[dict[str, Any]]) -> str:
    """Compact human-readable terminal table for ``mintfig log``."""
    if not entries:
        return "No figures logged yet. Run `mintfig log --init` to enable `.mintfig/` in this project."
    lines = []
    for e in reversed(entries):
        mark = "SHIP" if e.get("ship") else "FIX "
        ts = str(e.get("ts", ""))[:16].replace("T", " ")
        sha = f" @{e['git_commit']}" if e.get("git_commit") else ""
        take = str(e.get("takeaway", ""))[:76]
        lines.append(f"[{mark}] {ts}{sha}  {e.get('id', '')[:22]}  {take}")
    return "\n".join(lines)
