"""The agent-facing skill text must stay true to the code.

Blind tests showed that most friction came from arguments the skill never
mentioned, so every public argument has to appear in it, and its example has to
run as written with nothing to fix.
"""

from __future__ import annotations

import inspect
import os
import re
from pathlib import Path

import pytest

import figmint as fm

SKILL = Path(fm.__file__).parent / "assets" / "SKILL.md"

# Deliberately left out of the skill: print targets, the save-on-build shortcut
# and an alias kept so `trend` and `relate` agree.
UNDOCUMENTED = {"target", "out", "log_y"}

FORMS = (
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
    "custom",
)


def _explain_section() -> str:
    text = SKILL.read_text(encoding="utf-8")
    start = text.index("## Explain in a Conversation")
    end = text.index("## Publication Figures")
    return text[start:end]


def _python_blocks(section: str) -> list[str]:
    return re.findall(r"```python\n(.*?)```", section, flags=re.DOTALL)


def test_skill_example_runs_verbatim_with_nothing_to_fix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    example = _python_blocks(_explain_section())[0]
    monkeypatch.chdir(tmp_path)
    scope: dict[str, object] = {}
    exec(compile(example, "SKILL.md", "exec"), scope)  # noqa: S102 - our own documentation
    capsys.readouterr()
    fig = scope["fig"]
    assert isinstance(fig, fm.Explanation)
    summary = fig.summary()
    assert summary["ok"] is True
    assert summary["issues"] == []
    assert (tmp_path / "ablation.png").exists()
    # The takeaway's numbers are checkable against the computed facts.
    facts = " ".join(f for panel in summary["panels"] for f in panel["facts"])
    assert "no retrieval" in facts and "overlap" in facts


@pytest.mark.parametrize("name", ("explain", *FORMS))
def test_every_public_argument_is_in_the_skill(name: str) -> None:
    section = _explain_section()
    signature = inspect.signature(inspect.unwrap(getattr(fm, name)))
    missing = []
    for param in signature.parameters.values():
        if param.kind is not inspect.Parameter.KEYWORD_ONLY or param.name in UNDOCUMENTED:
            continue
        if not re.search(rf"\b{re.escape(param.name)}=", section):
            missing.append(param.name)
    assert not missing, f"fm.{name} arguments missing from SKILL.md: {missing}"


def test_skill_mentions_only_arguments_that_exist() -> None:
    """Every `name=` in the argument reference block is a real argument somewhere."""
    reference = _python_blocks(_explain_section())[1]
    known: set[str] = set()
    for name in ("explain", *FORMS):
        known |= set(inspect.signature(inspect.unwrap(getattr(fm, name))).parameters)
    known |= set(inspect.signature(fm.Explanation.save).parameters)
    used = set(re.findall(r"\b([a-z_]+)=", reference))
    assert used <= known, f"SKILL.md documents unknown arguments: {sorted(used - known)}"


def test_round_trip_shown_in_the_skill(tmp_path: Path) -> None:
    fig = fm.explain(
        "Checkout p99 is 4x the next slowest service",
        fm.compare({"checkout": 1840, "search": 460, "auth": 310}, label="p99", unit="ms"),
    )
    path = tmp_path / "fig.png"
    fig.save(path)
    again = fm.load(path)
    assert again.to_spec() == fig.to_spec()
    assert fm.explain_from_spec(again.to_spec()).to_spec() == fig.to_spec()
    assert os.path.getsize(path) > 0
