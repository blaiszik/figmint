"""Universal host detection and surface-adaptive delivery router for mintfig.

Inspects environment variables and TTY state (with zero heavy imports at module load)
to classify the active host harness and route any :class:`~mintfig.Explanation` or
JSON spec to the optimal payload for that surface:

* ``terminal_image`` — Kitty / Ghostty APC or iTerm2 / WezTerm OSC 1337 inline PNG
  (automatically wrapped in ``tmux`` DCS passthrough when ``TMUX`` is active).
* ``terminal_braille`` — High-resolution 2×4 Unicode Braille with optional 24-bit
  truecolor ANSI (respecting ``NO_COLOR`` / ``FORCE_COLOR``).
* ``terminal_ascii`` — Clean 7-bit printable ASCII for dumb or non-UTF8 terminals.
* ``notebook_html`` — Responsive interactive HTML fragment for Colab, Jupyter, and Marimo.
* ``ide_chat`` — Self-contained interactive HTML + 72-col Markdown/Braille for IDE chats
  (Antigravity, Cursor).
* ``github_pr`` — GitHub PR Markdown with image embeds and collapsible computed facts.
* ``mcp`` — MCP-ready multi-modal payload (72-col text + interactive HTML + caption).
* ``ci_plain`` — Escape-free 72-col ASCII for CI logs and headless non-TTY runs.
"""

from __future__ import annotations

import dataclasses
import os
import shutil
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

__all__ = [
    "VALID_HARNESSES",
    "VALID_SURFACES",
    "SurfaceInfo",
    "deliver_for_surface",
    "detect_surface",
]

VALID_SURFACES: frozenset[str] = frozenset(
    {
        "terminal_image",
        "terminal_braille",
        "terminal_ascii",
        "notebook_html",
        "ide_chat",
        "github_pr",
        "mcp",
        "ci_plain",
    }
)

VALID_HARNESSES: frozenset[str] = frozenset(
    {
        "claude_code",
        "antigravity",
        "cursor",
        "codex",
        "gemini_cli",
        "colab",
        "jupyter",
        "marimo",
        "github_actions",
        "kitty",
        "ghostty",
        "iterm2",
        "wezterm",
        "windows_terminal",
        "terminal",
        "unknown",
    }
)

_MIN_COLS = 56
_MAX_COLS = 132
_DEFAULT_CHAT_COLS = 72
_DEFAULT_TERM_COLS = 80

_FIXED_72_HARNESSES: frozenset[str] = frozenset(
    {
        "claude_code",
        "antigravity",
        "cursor",
        "codex",
        "gemini_cli",
        "colab",
        "jupyter",
        "marimo",
        "github_actions",
    }
)

_FIXED_72_SURFACES: frozenset[str] = frozenset(
    {
        "notebook_html",
        "ide_chat",
        "github_pr",
        "mcp",
        "ci_plain",
    }
)

_TRUECOLOR_HARNESSES: frozenset[str] = frozenset(
    {
        "kitty",
        "ghostty",
        "iterm2",
        "wezterm",
        "windows_terminal",
        "claude_code",
        "antigravity",
        "cursor",
        "codex",
        "gemini_cli",
    }
)

_TRUECOLOR_TERM_PROGRAMS: frozenset[str] = frozenset(
    {
        "kitty",
        "ghostty",
        "iterm.app",
        "wezterm",
        "vscode",
        "alacritty",
        "warpterminal",
        "hyper",
        "rio",
        "tabby",
    }
)

_DARK_TERM_PROGRAMS: frozenset[str] = frozenset(
    {
        "kitty",
        "ghostty",
        "iterm.app",
        "wezterm",
        "vscode",
        "alacritty",
        "warpterminal",
        "hyper",
        "rio",
        "cursor",
    }
)

_GITHUB_PR_EVENTS: frozenset[str] = frozenset(
    {
        "pull_request",
        "pull_request_target",
        "pull_request_review",
        "pull_request_review_comment",
    }
)

_CI_ENV_VARS: tuple[str, ...] = (
    "CI",
    "BUILDKITE",
    "GITLAB_CI",
    "CIRCLECI",
    "JENKINS_URL",
    "TF_BUILD",
    "TRAVIS",
)


@dataclasses.dataclass(frozen=True)
class SurfaceInfo:
    """Detected host environment and optimal mintfig rendering surface."""

    surface: str
    harness: str
    protocol: str
    color: bool
    truecolor: bool
    in_tmux: bool
    width_cols: int
    prefers_dark: bool
    supports_images: bool
    supports_html: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        """Serialize surface detection results for JSON and ``mintfig doctor`` output."""
        return dataclasses.asdict(self)


def _truthy(val: str | None) -> bool:
    if val is None:
        return False
    token = str(val).strip().lower()
    return token not in {"", "0", "false", "no", "off"}


def _has_env_prefix(env: Mapping[str, str], *prefixes: str) -> bool:
    for key, val in env.items():
        if not val:
            continue
        for prefix in prefixes:
            if key.startswith(prefix):
                return True
    return False


def _in_notebook_live() -> bool:
    """Lightweight stdlib-only check for an active IPython/Jupyter kernel."""
    ipython = sys.modules.get("IPython")
    if ipython is None:
        return False
    try:
        shell = ipython.get_ipython()
    except Exception:  # noqa: BLE001
        return False
    if shell is None:
        return False
    return type(shell).__name__ == "ZMQInteractiveShell" or "IPKernelApp" in getattr(
        shell, "config", {}
    )


def _detect_protocol(source: Mapping[str, str]) -> str:
    """Pure-stdlib mirror of :func:`mintfig.terminal.detect_graphics_protocol`."""
    if source.get("KITTY_WINDOW_ID") or source.get("GHOSTTY_RESOURCES_DIR"):
        return "kitty"
    term = str(source.get("TERM", "")).lower()
    term_program = str(source.get("TERM_PROGRAM", "")).lower()
    if "kitty" in term or "ghostty" in term or term_program in {"kitty", "ghostty"}:
        return "kitty"
    lc_terminal = str(source.get("LC_TERMINAL", "")).lower()
    if (
        source.get("ITERM_SESSION_ID")
        or source.get("WEZTERM_EXECUTABLE")
        or source.get("WEZTERM_PANE")
        or term_program in {"iterm.app", "wezterm"}
        or lc_terminal == "iterm2"
    ):
        return "iterm2"
    return "unicode"


def _detect_colorfgbg_dark(source: Mapping[str, str]) -> bool | None:
    """Parse ``COLORFGBG`` (e.g. ``15;0`` -> dark, ``0;15`` -> light)."""
    raw = source.get("COLORFGBG")
    if not raw:
        return None
    parts = [p.strip() for p in str(raw).split(";") if p.strip()]
    for token in reversed(parts):
        if token.isdigit():
            bg = int(token)
            if 0 <= bg <= 15:
                return bg < 7 or bg == 8
    return None


def _detect_prefers_dark(
    source: Mapping[str, str],
    *,
    surface: str,
    harness: str,
    term_program: str,
) -> bool:
    fgbg = _detect_colorfgbg_dark(source)
    if fgbg is not None:
        return fgbg

    for hint_key in ("MINTFIG_THEME", "COLOR_SCHEME", "VSCODE_THEME_KIND", "BAT_THEME"):
        hint = str(source.get(hint_key, "")).strip().lower()
        if not hint:
            continue
        if "light" in hint:
            return False
        if "dark" in hint or "pine" in hint:
            return True

    if term_program == "apple_terminal":
        return False
    if surface in {"notebook_html", "github_pr", "ci_plain"}:
        return False
    if surface in {"ide_chat", "mcp"}:
        return True
    if harness in {
        "kitty",
        "ghostty",
        "iterm2",
        "wezterm",
        "windows_terminal",
        "claude_code",
        "codex",
        "gemini_cli",
        "terminal",
    }:
        return True
    return term_program in _DARK_TERM_PROGRAMS


def _clamp_cols(cols: int) -> int:
    return max(_MIN_COLS, min(_MAX_COLS, int(cols)))


def _detect_width_cols(
    source: Mapping[str, str],
    *,
    surface: str,
    harness: str,
    live_env: bool,
) -> int:
    override = source.get("MINTFIG_WIDTH")
    if override is not None and str(override).strip().isdigit():
        return _clamp_cols(int(str(override).strip()))

    if surface in _FIXED_72_SURFACES or harness in _FIXED_72_HARNESSES:
        return _DEFAULT_CHAT_COLS

    cols_env = source.get("COLUMNS")
    if cols_env is not None and str(cols_env).strip().isdigit():
        return _clamp_cols(int(str(cols_env).strip()))

    if live_env:
        return _clamp_cols(shutil.get_terminal_size((_DEFAULT_TERM_COLS, 24)).columns)
    return _DEFAULT_TERM_COLS


def _detect_harness(
    source: Mapping[str, str],
    *,
    live_env: bool,
    is_tty: bool | None,
) -> str:
    term = str(source.get("TERM", "")).lower()
    term_program = str(source.get("TERM_PROGRAM", "")).lower()
    lc_terminal = str(source.get("LC_TERMINAL", "")).lower()

    # 1. Notebook environments
    if source.get("COLAB_RELEASE_TAG") or source.get("COLAB_GPU"):
        return "colab"
    if _truthy(source.get("MARIMO")) or _has_env_prefix(source, "MARIMO_"):
        return "marimo"
    if source.get("JPY_PARENT_PID") or (live_env and _in_notebook_live()):
        return "jupyter"

    # 2. Agent & IDE harnesses (take precedence over outer terminal emulators)
    if _truthy(source.get("ANTIGRAVITY")) or _has_env_prefix(source, "ANTIGRAVITY_", "AGY_"):
        return "antigravity"
    if _truthy(source.get("CURSOR")) or _has_env_prefix(source, "CURSOR_") or term_program == "cursor":
        return "cursor"
    if _truthy(source.get("CLAUDECODE")) or _has_env_prefix(source, "CLAUDE_CODE_"):
        return "claude_code"
    if _truthy(source.get("CODEX")) or _has_env_prefix(source, "CODEX_"):
        return "codex"
    if _truthy(source.get("GEMINI_CLI")) or _has_env_prefix(source, "GEMINI_CLI_"):
        return "gemini_cli"

    # 3. CI / GitHub Actions
    if _truthy(source.get("GITHUB_ACTIONS")):
        return "github_actions"

    # 4. Inline-graphics & modern terminal emulators
    if source.get("GHOSTTY_RESOURCES_DIR") or "ghostty" in term or term_program == "ghostty":
        return "ghostty"
    if source.get("KITTY_WINDOW_ID") or "kitty" in term or term_program == "kitty":
        return "kitty"
    if source.get("WEZTERM_EXECUTABLE") or source.get("WEZTERM_PANE") or term_program == "wezterm":
        return "wezterm"
    if source.get("ITERM_SESSION_ID") or term_program == "iterm.app" or lc_terminal == "iterm2":
        return "iterm2"
    if source.get("WT_SESSION"):
        return "windows_terminal"

    # 5. Generic CI vs generic terminal
    if any(_truthy(source.get(var)) for var in _CI_ENV_VARS):
        return "unknown"
    if term or term_program or source.get("TMUX") or is_tty is True:
        return "terminal"
    return "unknown"


def _resolve_color_flags(
    source: Mapping[str, str],
    *,
    effective_tty: bool,
    surface: str,
    harness: str,
    term: str,
    term_program: str,
) -> tuple[bool, bool]:
    # NO_COLOR takes strict precedence when set to any non-empty value.
    if source.get("NO_COLOR"):
        return False, False

    force_raw = source.get("FORCE_COLOR")
    if force_raw is not None and str(force_raw).strip() != "":
        color = str(force_raw).strip().lower() not in {"0", "false", "no", "off"}
    elif term == "dumb" or surface in {"ci_plain", "terminal_ascii"}:
        color = False
    elif harness in {"claude_code", "codex", "gemini_cli"}:
        color = effective_tty
    elif surface in {"notebook_html", "ide_chat", "github_pr", "mcp"}:
        color = False
    else:
        color = effective_tty

    if not color:
        return False, False

    colorterm = str(source.get("COLORTERM", "")).strip().lower()
    truecolor = (
        colorterm in {"truecolor", "24bit"}
        or harness in _TRUECOLOR_HARNESSES
        or term_program in _TRUECOLOR_TERM_PROGRAMS
    )
    return True, truecolor


def detect_surface(
    env: Mapping[str, str] | None = None,
    *,
    is_tty: bool | None = None,
) -> SurfaceInfo:
    """Detect the active host harness and choose the canonical mintfig surface.

    When ``env`` is passed explicitly (for example in tests or remote probes),
    detection is completely hermetic and never consults ``os.environ`` or live
    process state unless ``is_tty`` is left unspecified for live ``env=None`` calls.
    """
    live_env = env is None
    source: Mapping[str, str] = os.environ if live_env else env
    term = str(source.get("TERM", "")).lower()
    term_program = str(source.get("TERM_PROGRAM", "")).lower()
    in_tmux = bool(source.get("TMUX"))
    protocol = _detect_protocol(source)
    harness = _detect_harness(source, live_env=live_env, is_tty=is_tty)

    # Determine effective TTY without leaking test-runner stdout state into synthetic env probes.
    if is_tty is not None:
        effective_tty = bool(is_tty)
    elif live_env:
        try:
            effective_tty = bool(sys.stdout.isatty())
        except Exception:  # noqa: BLE001
            effective_tty = False
    else:
        is_ci = any(_truthy(source.get(var)) for var in _CI_ENV_VARS)
        effective_tty = (
            not is_ci
            and term != "dumb"
            and harness
            in {
                "kitty",
                "ghostty",
                "iterm2",
                "wezterm",
                "windows_terminal",
                "terminal",
                "claude_code",
                "codex",
                "gemini_cli",
            }
        )

    force_raw = source.get("FORCE_COLOR")
    force_color_on = (
        not bool(source.get("NO_COLOR"))
        and force_raw is not None
        and str(force_raw).strip().lower() not in {"", "0", "false", "no", "off"}
    )

    is_mcp = _truthy(source.get("MINTFIG_MCP")) or _truthy(source.get("MCP_SERVER"))

    # Select canonical surface, capabilities, and human-readable reason.
    if is_mcp:
        surface = "mcp"
        supports_images = True
        supports_html = True
        reason = (
            f"MCP server context ({harness}) supporting image content and interactive MCP App HTML"
            if harness != "unknown"
            else "MCP server context supporting image content and interactive MCP App HTML"
        )
    elif harness in {"colab", "jupyter", "marimo"}:
        surface = "notebook_html"
        supports_images = True
        supports_html = True
        label = {"colab": "Google Colab", "jupyter": "Jupyter", "marimo": "Marimo"}[harness]
        reason = f"{label} notebook environment supports rich interactive HTML fragments"
    elif harness in {"antigravity", "cursor"}:
        surface = "ide_chat"
        supports_images = True
        supports_html = True
        label = "Antigravity" if harness == "antigravity" else "Cursor"
        reason = f"{label} IDE chat supports markdown, images, and interactive HTML"
    elif harness in {"claude_code", "codex", "gemini_cli"}:
        label = {
            "claude_code": "Claude Code",
            "codex": "OpenAI Codex",
            "gemini_cli": "Gemini CLI",
        }[harness]
        if term == "dumb":
            surface = "terminal_ascii"
            reason = f"{label} with TERM=dumb falls back to clean 72-col ASCII"
        else:
            surface = "terminal_braille"
            reason = f"{label} CLI harness renders crisp 72-col Unicode Braille charts"
        supports_images = False
        supports_html = False
    elif harness == "github_actions":
        event = str(source.get("GITHUB_EVENT_NAME", "")).strip().lower()
        if (
            event in _GITHUB_PR_EVENTS
            or bool(source.get("GITHUB_STEP_SUMMARY"))
            or bool(source.get("GITHUB_PR_NUMBER"))
        ):
            surface = "github_pr"
            supports_images = True
            supports_html = False
            reason = "GitHub Actions PR/summary context supports PR Markdown with image cards"
        else:
            surface = "ci_plain"
            supports_images = False
            supports_html = False
            reason = "GitHub Actions log environment uses escape-free 72-col plain ASCII"
    elif harness in {"kitty", "ghostty", "iterm2", "wezterm"}:
        label = {
            "kitty": "Kitty",
            "ghostty": "Ghostty",
            "iterm2": "iTerm2",
            "wezterm": "WezTerm",
        }[harness]
        if effective_tty:
            surface = "terminal_image"
            supports_images = True
            supports_html = False
            tmux_note = " via tmux passthrough" if in_tmux else ""
            reason = f"{label} terminal supports inline {protocol} graphics{tmux_note}"
        elif force_color_on:
            surface = "terminal_braille"
            supports_images = False
            supports_html = False
            reason = f"{label} non-TTY stream with FORCE_COLOR falls back to Unicode Braille"
        else:
            surface = "terminal_ascii"
            supports_images = False
            supports_html = False
            reason = f"{label} non-TTY stream avoids raw escapes and falls back to ASCII"
    elif harness in {"windows_terminal", "terminal"}:
        label = "Windows Terminal" if harness == "windows_terminal" else "Terminal"
        if term == "dumb":
            surface = "terminal_ascii"
            reason = f"{label} with TERM=dumb uses clean printable ASCII"
        elif effective_tty or force_color_on:
            surface = "terminal_braille"
            tmux_note = " inside tmux" if in_tmux else ""
            reason = f"{label}{tmux_note} supports 2x4 Unicode Braille terminal charts"
        else:
            surface = "terminal_ascii"
            reason = f"{label} non-TTY stream falls back to clean ASCII"
        supports_images = False
        supports_html = False
    else:
        surface = "ci_plain"
        supports_images = False
        supports_html = False
        if any(_truthy(source.get(var)) for var in _CI_ENV_VARS):
            reason = "CI environment uses escape-free 72-col plain ASCII"
        else:
            reason = "Headless or unknown non-TTY host defaults to escape-free 72-col plain ASCII"

    color, truecolor = _resolve_color_flags(
        source,
        effective_tty=effective_tty,
        surface=surface,
        harness=harness,
        term=term,
        term_program=term_program,
    )
    width_cols = _detect_width_cols(
        source,
        surface=surface,
        harness=harness,
        live_env=live_env,
    )
    prefers_dark = _detect_prefers_dark(
        source,
        surface=surface,
        harness=harness,
        term_program=term_program,
    )

    return SurfaceInfo(
        surface=surface,
        harness=harness,
        protocol=protocol,
        color=color,
        truecolor=truecolor,
        in_tmux=in_tmux,
        width_cols=width_cols,
        prefers_dark=prefers_dark,
        supports_images=supports_images,
        supports_html=supports_html,
        reason=reason,
    )


def _format_markdown_payload(
    exp: Any,
    *,
    target_surface: str,
    caption: str,
    plain_text: str,
    image_path: str | None,
) -> str:
    alt = str(exp.takeaway).replace("\\", "\\\\").replace("]", "\\]")
    lines: list[str] = []
    if image_path is not None and Path(image_path).suffix.lower() not in {".html", ".htm"}:
        lines.append(f"![{alt}]({image_path})")
        lines.append("")
        lines.append(caption)
    else:
        lines.append(f"**{exp.takeaway}**")
        lines.append("")
        lines.append("```text")
        lines.append(plain_text)
        lines.append("```")
        if caption and caption != exp.takeaway:
            lines.append("")
            lines.append(caption)

    if target_surface == "github_pr":
        facts: list[str] = []
        multi = len(exp.panels) > 1
        for key, panel in exp.panels.items():
            label = panel.title or f"Panel {key}"
            for fact in panel.facts:
                text = str(fact).strip()
                if not text:
                    continue
                facts.append(f"- **{label}:** {text}" if multi else f"- {text}")
        if facts:
            lines.append("")
            lines.append("<details>")
            lines.append("<summary>Computed facts</summary>")
            lines.append("")
            lines.extend(facts)
            lines.append("")
            lines.append("</details>")
    return "\n".join(lines)


def deliver_for_surface(
    explanation: Any,
    *,
    surface: str = "auto",
    out: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    is_tty: bool | None = None,
    width: int | str | None = None,
) -> dict[str, Any]:
    """Route an :class:`~mintfig.Explanation` or spec dict to the optimal surface payload.

    Returns a dictionary containing:
    ``surface``, ``harness``, ``mode``, ``text``, ``markdown``, ``caption``, ``html``,
    ``image_path``, and ``inline_escape`` (plus ``surface_info``).
    """
    surface_norm = surface.strip().lower()
    if surface_norm != "auto" and surface_norm not in VALID_SURFACES:
        valid = ", ".join(sorted({"auto", *VALID_SURFACES}))
        raise ValueError(f"Unknown surface {surface!r}. Choose one of: {valid}.")

    # Lazy imports keep `from mintfig.surface import detect_surface` pure stdlib.
    import matplotlib.pyplot as plt

    from ._explain.layout import Explanation, _caption, explain_from_spec
    from .interactive import render_html, render_html_fragment
    from .terminal import (
        _explanation_to_png_bytes,
        encode_iterm2_png,
        encode_kitty_png,
        render_terminal,
        wrap_tmux_passthrough,
    )

    owned_exp = False
    if isinstance(explanation, Explanation):
        exp = explanation
    elif isinstance(explanation, Mapping):
        exp = explain_from_spec(explanation)
        owned_exp = True
    else:
        raise TypeError(
            "Expected an Explanation or a spec mapping, "
            f"got {type(explanation).__name__}."
        )

    try:
        info = detect_surface(env, is_tty=is_tty)
        target_surface = info.surface if surface_norm == "auto" else surface_norm

        if width is None:
            if surface_norm != "auto" and target_surface in _FIXED_72_SURFACES:
                resolved_width = _DEFAULT_CHAT_COLS
            else:
                resolved_width = info.width_cols
        elif isinstance(width, str):
            token = width.strip().lower()
            if token == "auto":
                resolved_width = info.width_cols
            else:
                try:
                    resolved_width = max(40, int(token))
                except ValueError as exc:
                    raise ValueError(
                        f"width must be an integer or 'auto', got {width!r}."
                    ) from exc
        else:
            resolved_width = max(40, int(width))

        image_path: str | None = None
        png_bytes: bytes | None = None
        saved_html: str | None = None

        if out is not None:
            out_path = Path(out)
            exp.save(out_path, log=False)
            resolved_out = out_path.resolve()
            image_path = str(resolved_out)
            suffix = resolved_out.suffix.lower()
            if suffix == ".png":
                png_bytes = resolved_out.read_bytes()
            elif suffix in {".html", ".htm"}:
                saved_html = resolved_out.read_text(encoding="utf-8")

        html_payload: str | None = saved_html
        inline_escape: str | None = None

        if target_surface == "terminal_image":
            proto = info.protocol if info.protocol in {"kitty", "iterm2"} else "kitty"
            mode = proto
            if png_bytes is None:
                png_bytes = _explanation_to_png_bytes(exp)
            seq = encode_kitty_png(png_bytes) if proto == "kitty" else encode_iterm2_png(png_bytes)
            inline_escape = wrap_tmux_passthrough(seq) if info.in_tmux else seq
            text = render_terminal(
                exp,
                width=resolved_width,
                color=info.color,
                ascii_only=False,
                high_res=True,
            )
            plain_text = (
                text
                if not info.color
                else render_terminal(
                    exp,
                    width=resolved_width,
                    color=False,
                    ascii_only=False,
                    high_res=True,
                )
            )
        elif target_surface == "terminal_braille":
            mode = "braille"
            text = render_terminal(
                exp,
                width=resolved_width,
                color=info.color,
                ascii_only=False,
                high_res=True,
            )
            plain_text = (
                text
                if not info.color
                else render_terminal(
                    exp,
                    width=resolved_width,
                    color=False,
                    ascii_only=False,
                    high_res=True,
                )
            )
        elif target_surface in {"terminal_ascii", "ci_plain"}:
            mode = "ascii"
            text = render_terminal(
                exp,
                width=resolved_width,
                color=False,
                ascii_only=True,
                high_res=False,
            )
            plain_text = text
        elif target_surface == "notebook_html":
            mode = "html"
            if html_payload is None:
                html_payload = render_html_fragment(exp)
            text = render_terminal(
                exp,
                width=resolved_width,
                color=False,
                ascii_only=False,
                high_res=True,
            )
            plain_text = text
        elif target_surface == "ide_chat":
            mode = "html"
            if html_payload is None:
                html_payload = render_html(exp)
            text = render_terminal(
                exp,
                width=resolved_width,
                color=False,
                ascii_only=False,
                high_res=True,
            )
            plain_text = text
        elif target_surface == "mcp":
            mode = "mcp"
            if html_payload is None:
                html_payload = render_html(exp)
            text = render_terminal(
                exp,
                width=resolved_width,
                color=False,
                ascii_only=False,
                high_res=True,
            )
            plain_text = text
        else:  # github_pr
            mode = "markdown"
            text = render_terminal(
                exp,
                width=resolved_width,
                color=False,
                ascii_only=False,
                high_res=True,
            )
            plain_text = text

        caption = _caption(exp.takeaway, exp.panels)
        markdown = _format_markdown_payload(
            exp,
            target_surface=target_surface,
            caption=caption,
            plain_text=plain_text,
            image_path=image_path,
        )

        return {
            "surface": target_surface,
            "harness": info.harness,
            "mode": mode,
            "text": text,
            "markdown": markdown,
            "caption": caption,
            "html": html_payload,
            "image_path": image_path,
            "inline_escape": inline_escape,
            "surface_info": info.to_dict(),
        }
    finally:
        if owned_exp:
            plt.close(exp.fig)
