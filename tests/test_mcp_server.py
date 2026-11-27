"""Comprehensive tests for mintfig's zero-dependency JSON-RPC 2.0 MCP server & MCP App."""

from __future__ import annotations

import base64
import io
import json
import sys
import types
from pathlib import Path

import pytest

from mintfig.mcp_server import (
    APP_MIME_TYPE,
    APP_RESOURCE_URI,
    MCP_SERVER_ENTRY,
    MCP_TARGETS,
    MCPServer,
    cli_mcp,
    install_mcp_config,
    mcp_status,
    print_mcp_config,
)

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _rpc(server: MCPServer, method: str, params: dict | None = None, msg_id: int | None = 1) -> dict | None:
    req: dict = {"jsonrpc": "2.0", "method": method}
    if msg_id is not None:
        req["id"] = msg_id
    if params is not None:
        req["params"] = params
    return server.handle_message(req)


# --------------------------------------------------------------------------- #
# Protocol & Lifecycle
# --------------------------------------------------------------------------- #


def test_initialize_echoes_protocol_and_advertises_mcp_apps() -> None:
    server = MCPServer()
    resp = _rpc(
        server,
        "initialize",
        {"protocolVersion": "2025-03-26", "clientInfo": {"name": "test-client", "version": "1.0"}},
        msg_id=1,
    )
    assert resp is not None
    assert resp["jsonrpc"] == "2.0"
    assert resp["id"] == 1
    result = resp["result"]
    assert result["protocolVersion"] == "2025-03-26"
    assert result["serverInfo"]["name"] == "mintfig"
    caps = result["capabilities"]
    assert "tools" in caps
    assert "resources" in caps
    assert APP_MIME_TYPE in caps["extensions"]["io.modelcontextprotocol/ui"]["mimeTypes"]

    # Also echo older protocol version cleanly
    resp_old = _rpc(server, "initialize", {"protocolVersion": "2024-11-05"}, msg_id=2)
    assert resp_old is not None
    assert resp_old["result"]["protocolVersion"] == "2024-11-05"

    # Notification returns None (no response on stdio)
    assert _rpc(server, "notifications/initialized", {}, msg_id=None) is None

    # Ping succeeds
    ping_resp = _rpc(server, "ping", {}, msg_id=3)
    assert ping_resp == {"jsonrpc": "2.0", "id": 3, "result": {}}


def test_tools_list_and_resources_list_and_read() -> None:
    server = MCPServer()
    tools_resp = _rpc(server, "tools/list", {}, msg_id=10)
    assert tools_resp is not None
    tools = tools_resp["result"]["tools"]
    names = [t["name"] for t in tools]
    assert names == ["mint_explain", "mint_check", "mint_plot_file", "mint_card", "mint_chip"]

    by_name = {t["name"]: t for t in tools}
    for ui_tool in ("mint_explain", "mint_plot_file", "mint_card"):
        assert by_name[ui_tool]["_meta"]["ui"]["resourceUri"] == APP_RESOURCE_URI

    res_list = _rpc(server, "resources/list", {}, msg_id=11)
    assert res_list is not None
    resources = res_list["result"]["resources"]
    assert len(resources) == 1
    assert resources[0]["uri"] == APP_RESOURCE_URI
    assert resources[0]["mimeType"] == APP_MIME_TYPE

    res_read = _rpc(server, "resources/read", {"uri": APP_RESOURCE_URI}, msg_id=12)
    assert res_read is not None
    contents = res_read["result"]["contents"]
    assert len(contents) == 1
    html = contents[0]["text"]
    assert contents[0]["mimeType"] == APP_MIME_TYPE
    assert "<!DOCTYPE html>" in html
    assert "ui/initialize" in html
    assert "ui/notifications/tool-result" in html
    assert "Copy SVG" in html
    for theme_label in ("Auto", "Light", "Dark", "Mint", "Pine"):
        assert theme_label in html
    # Zero CDN / external URLs inside the interactive app shell
    assert "https://" not in html and "http://" not in html


def test_stdio_stream_dispatch_and_error_handling() -> None:
    server = MCPServer()
    lines = "\n".join(
        [
            json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-03-26"}}),
            json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
            json.dumps({"jsonrpc": "2.0", "id": 2, "method": "ping"}),
            json.dumps({"jsonrpc": "2.0", "id": 3, "method": "unknown/method"}),
            json.dumps({"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "no_such_tool", "arguments": {}}}),
            json.dumps({"jsonrpc": "2.0", "id": 5, "method": "resources/read", "params": {"uri": "ui://mintfig/missing"}}),
            "{not valid json",
        ]
    ) + "\n"
    out = io.StringIO()
    rc = server.serve(stdin=io.StringIO(lines), stdout=out)
    assert rc == 0

    responses = [json.loads(line) for line in out.getvalue().strip().splitlines()]
    assert len(responses) == 6  # notification produces no response
    assert responses[0]["id"] == 1 and "result" in responses[0]
    assert responses[1]["id"] == 2 and responses[1]["result"] == {}
    assert responses[2]["id"] == 3 and responses[2]["error"]["code"] == -32601
    assert responses[3]["id"] == 4 and responses[3]["error"]["code"] == -32602
    assert responses[4]["id"] == 5 and responses[4]["error"]["code"] == -32002
    assert responses[5]["error"]["code"] == -32700


# --------------------------------------------------------------------------- #
# All 5 Tools
# --------------------------------------------------------------------------- #


def test_tool_mint_explain_returns_braille_png_and_updates_mcp_app(tmp_path: Path) -> None:
    server = MCPServer()
    out_png = tmp_path / "explain.png"
    resp = _rpc(
        server,
        "tools/call",
        {
            "name": "mint_explain",
            "arguments": {
                "takeaway": "Checkout p99 is 4x slower than search at 1,840 ms",
                "subtitle": "API p99 latency by service",
                "source": "synthetic telemetry",
                "panels": [
                    {
                        "kind": "compare",
                        "title": "Latency by service",
                        "label": "p99 latency",
                        "unit": "ms",
                        "values": {"checkout": 1840, "search": 460, "auth": 310, "cart": 240},
                        "highlight": "checkout",
                    }
                ],
                "out": str(out_png),
            },
        },
        msg_id=20,
    )
    assert resp is not None
    result = resp["result"]
    assert result["isError"] is False
    assert result["_meta"]["ui"]["resourceUri"] == APP_RESOURCE_URI

    content = result["content"]
    assert content[0]["type"] == "text"
    assert "checkout" in content[0]["text"].lower()
    assert content[1]["type"] == "image"
    assert content[1]["mimeType"] == "image/png"
    png_bytes = base64.b64decode(content[1]["data"])
    assert png_bytes.startswith(PNG_MAGIC)
    assert out_png.is_file()

    sc = result["structuredContent"]
    assert sc["takeaway"].startswith("Checkout p99")
    assert isinstance(sc["ship"], bool)
    assert isinstance(sc["facts"], list) and len(sc["facts"]) >= 1
    assert isinstance(sc["issues"], list)
    assert "<svg" in sc["html"]

    # Live resource cache updated for ui://mintfig/figure
    res_read = _rpc(server, "resources/read", {"uri": APP_RESOURCE_URI}, msg_id=21)
    assert res_read is not None
    app_html = res_read["result"]["contents"][0]["text"]
    assert "Checkout p99" in app_html
    assert "\\u003csvg" in app_html or "<svg" in app_html


def test_tool_mint_check_audits_script_and_notebook(tmp_path: Path) -> None:
    server = MCPServer()
    script = tmp_path / "good_plot.py"
    script.write_text(
        "import matplotlib.pyplot as plt\n"
        "fig, ax = plt.subplots(figsize=(6, 4))\n"
        "ax.bar(['A', 'B', 'C'], [10, 25, 15])\n"
        "ax.set_title('B leads at 25 units', fontsize=12)\n"
        "ax.set_ylabel('Score (units)', fontsize=10)\n",
        encoding="utf-8",
    )
    resp = _rpc(
        server,
        "tools/call",
        {"name": "mint_check", "arguments": {"path": str(script), "claim": "B leads at 25"}},
        msg_id=30,
    )
    assert resp is not None
    result = resp["result"]
    assert result["isError"] is False
    sc = result["structuredContent"]
    assert sc["figure_count"] == 1
    assert isinstance(sc["ship"], bool)
    assert isinstance(sc["issues"], list)
    assert isinstance(sc["facts"], list) and len(sc["facts"]) >= 1

    # Also exercise .ipynb notebook path
    nb = tmp_path / "plot.ipynb"
    nb.write_text(
        json.dumps(
            {
                "cells": [
                    {
                        "cell_type": "code",
                        "metadata": {},
                        "source": [
                            "import matplotlib.pyplot as plt\n",
                            "fig, ax = plt.subplots(figsize=(6, 4))\n",
                            "ax.bar(['X', 'Y'], [12, 36])\n",
                            "ax.set_title('Y reaches 36')\n",
                        ],
                    }
                ],
                "metadata": {},
                "nbformat": 4,
                "nbformat_minor": 5,
            }
        ),
        encoding="utf-8",
    )
    nb_resp = _rpc(
        server,
        "tools/call",
        {"name": "mint_check", "arguments": {"path": str(nb)}},
        msg_id=31,
    )
    assert nb_resp is not None
    assert nb_resp["result"]["isError"] is False
    assert nb_resp["result"]["structuredContent"]["figure_count"] == 1


def test_tool_mint_plot_file_csv_and_junit(tmp_path: Path) -> None:
    server = MCPServer()
    csv_path = tmp_path / "bench.csv"
    csv_path.write_text(
        "service,latency_ms\n"
        "checkout,248\n"
        "payment,195\n"
        "cart,142\n"
        "catalog,98\n",
        encoding="utf-8",
    )
    resp = _rpc(
        server,
        "tools/call",
        {"name": "mint_plot_file", "arguments": {"path": str(csv_path)}},
        msg_id=40,
    )
    assert resp is not None
    result = resp["result"]
    assert result["isError"] is False
    assert result["_meta"]["ui"]["resourceUri"] == APP_RESOURCE_URI
    assert result["content"][0]["type"] == "text"
    assert result["content"][1]["type"] == "image"
    assert base64.b64decode(result["content"][1]["data"]).startswith(PNG_MAGIC)
    assert len(result["structuredContent"]["facts"]) >= 1
    assert "<svg" in result["structuredContent"]["html"]

    # JUnit XML support
    junit_path = tmp_path / "junit.xml"
    junit_path.write_text(
        '<?xml version="1.0" encoding="utf-8"?>'
        '<testsuite name="pytest" tests="3">'
        '<testcase classname="tests.api" name="test_checkout" time="0.420"/>'
        '<testcase classname="tests.api" name="test_auth" time="0.115"/>'
        '<testcase classname="tests.api" name="test_health" time="0.012"/>'
        "</testsuite>",
        encoding="utf-8",
    )
    junit_resp = _rpc(
        server,
        "tools/call",
        {"name": "mint_plot_file", "arguments": {"path": str(junit_path)}},
        msg_id=41,
    )
    assert junit_resp is not None
    assert junit_resp["result"]["isError"] is False
    assert base64.b64decode(junit_resp["result"]["content"][1]["data"]).startswith(PNG_MAGIC)

    # Hyperfine JSON support
    hf_path = tmp_path / "hyperfine.json"
    hf_path.write_text(
        json.dumps(
            {
                "results": [
                    {"command": "rg foo", "mean": 0.042, "stddev": 0.003, "median": 0.041, "min": 0.038, "max": 0.049, "times": [0.04, 0.042, 0.044]},
                    {"command": "grep -r foo", "mean": 0.312, "stddev": 0.015, "median": 0.310, "min": 0.295, "max": 0.340, "times": [0.30, 0.312, 0.325]},
                ]
            }
        ),
        encoding="utf-8",
    )
    hf_resp = _rpc(
        server,
        "tools/call",
        {"name": "mint_plot_file", "arguments": {"path": str(hf_path)}},
        msg_id=42,
    )
    assert hf_resp is not None
    assert hf_resp["result"]["isError"] is False
    assert base64.b64decode(hf_resp["result"]["content"][1]["data"]).startswith(PNG_MAGIC)


def test_tool_mint_card_returns_terminal_card_png_and_mcp_app() -> None:
    server = MCPServer()
    resp = _rpc(
        server,
        "tools/call",
        {
            "name": "mint_card",
            "arguments": {
                "takeaway": "PR #418 cuts checkout p99 latency 38% while holding 99.94% uptime",
                "subtitle": "checkout canary · 7d",
                "metrics": [
                    {"label": "p99 latency", "value": "248 ms", "delta": "-38%", "good": True, "spark": [410, 390, 310, 248]},
                    {"label": "Availability", "value": "99.94%", "delta": "+0.02 pts", "good": True},
                    {"label": "Error rate", "value": "0.06%", "delta": "-0.04 pts", "good": True},
                ],
                "panel": {
                    "kind": "compare",
                    "title": "p99 latency by endpoint",
                    "label": "p99 latency",
                    "unit": "ms",
                    "values": {"checkout": 248, "payment": 195, "cart": 142},
                    "highlight": "checkout",
                },
            },
        },
        msg_id=50,
    )
    assert resp is not None
    result = resp["result"]
    assert result["isError"] is False
    assert result["_meta"]["ui"]["resourceUri"] == APP_RESOURCE_URI
    assert result["content"][0]["type"] == "text"
    assert "248 ms" in result["content"][0]["text"]
    assert result["content"][1]["type"] == "image"
    assert base64.b64decode(result["content"][1]["data"]).startswith(PNG_MAGIC)
    sc = result["structuredContent"]
    assert sc["metrics_count"] == 3
    assert "mf-card-shell" in sc["html"]


def test_tool_mint_chip_missing_and_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    server = MCPServer()

    # Case 1: mintchip not installed -> clean helpful message
    import mintfig._chip_bridge as bridge

    monkeypatch.setattr(bridge, "import_mintchip", lambda: None)
    resp_missing = _rpc(
        server,
        "tools/call",
        {"name": "mint_chip", "arguments": {"kind": "spark", "args": [[1, 3, 2, 5]]}},
        msg_id=60,
    )
    assert resp_missing is not None
    assert resp_missing["result"]["isError"] is False
    assert resp_missing["result"]["structuredContent"]["installed"] is False
    assert "pip install mintchip" in resp_missing["result"]["content"][0]["text"]

    # Case 2: mintchip installed (stubbed module) -> renders chip & table cleanly
    class _FakeChip:
        facts = ("min=1, max=5",)

        def text(self, *, braille: bool = False) -> str:
            return "5 ⣀⣤⣶⣿" if braille else "5 ▁▄▂█"

        def markdown(self, *, braille: bool = False) -> str:
            return f"`{self.text(braille=braille)}`"

        def svg(self, *, theme: str = "auto") -> str:
            return f'<svg data-theme="{theme}"></svg>'

        def html(self, *, theme: str = "auto") -> str:
            return f'<span class="mc-chip" data-theme="{theme}">5</span>'

    class _FakeTable:
        facts = ("2 rows",)

        def text(self, *, braille: bool = False) -> str:
            return "model  acc\nA      0.92 ⣿" if braille else "model  acc\nA      0.92 █"

        def markdown(self, *, braille: bool = False) -> str:
            return "| model | acc |\n|:--|:--|\n| A | `0.92` |"

        def html(self, *, theme: str = "auto") -> str:
            return f'<table class="mc-table" data-theme="{theme}"></table>'

    fake_mc = types.ModuleType("mintchip")
    fake_mc.REGISTRY = {"spark": object()}  # type: ignore[attr-defined]
    fake_mc.spark = lambda values, **kw: _FakeChip()  # type: ignore[attr-defined]
    fake_mc.table = lambda rows, **kw: _FakeTable()  # type: ignore[attr-defined]
    fake_mc.css = lambda: ".mc-chip{display:inline}"  # type: ignore[attr-defined]

    monkeypatch.setattr(bridge, "import_mintchip", lambda: fake_mc)
    resp_ok = _rpc(
        server,
        "tools/call",
        {
            "name": "mint_chip",
            "arguments": {"kind": "spark", "args": [[1, 3, 2, 5]], "braille": True, "format": "all"},
        },
        msg_id=61,
    )
    assert resp_ok is not None
    assert resp_ok["result"]["isError"] is False
    sc = resp_ok["result"]["structuredContent"]
    assert sc["installed"] is True
    assert "⣀⣤⣶⣿" in sc["text"]
    assert "<svg" in sc["svg"]
    assert "mc-chip" in sc["html"]

    resp_tbl = _rpc(
        server,
        "tools/call",
        {
            "name": "mint_chip",
            "arguments": {
                "kind": "table",
                "args": [[{"model": "A", "acc": 0.92}]],
                "braille": True,
                "format": "markdown",
            },
        },
        msg_id=62,
    )
    assert resp_tbl is not None
    assert resp_tbl["result"]["isError"] is False
    assert "| model | acc |" in resp_tbl["result"]["content"][0]["text"]
    assert "mc-table" in resp_tbl["result"]["structuredContent"]["html"]


def test_tool_execution_error_returns_is_error_payload() -> None:
    server = MCPServer()
    resp = _rpc(
        server,
        "tools/call",
        {"name": "mint_check", "arguments": {"path": "/nonexistent/does_not_exist.py"}},
        msg_id=70,
    )
    assert resp is not None
    assert resp["result"]["isError"] is True
    assert resp["result"]["structuredContent"]["ok"] is False


# --------------------------------------------------------------------------- #
# Installer, Status & CLI
# --------------------------------------------------------------------------- #


def test_install_mcp_config_merges_safely_and_status_reports(tmp_path: Path) -> None:
    cfg_paths = {
        "claude-code": tmp_path / ".claude.json",
        "claude-desktop": tmp_path / "claude_desktop_config.json",
        "cursor": tmp_path / ".cursor" / "mcp.json",
        "gemini": tmp_path / ".gemini" / "settings.json",
        "antigravity": tmp_path / ".gemini" / "antigravity" / "mcp_config.json",
    }
    # Pre-populate claude-code with an existing server and unrelated top-level keys
    cfg_paths["claude-code"].write_text(
        json.dumps(
            {
                "theme": "dark",
                "mcpServers": {
                    "other-server": {"command": "node", "args": ["server.js"]},
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    # Dry-run leaves disk untouched
    dry = install_mcp_config(dry_run=True, config_paths=cfg_paths)
    assert dry["dry_run"] is True
    assert all(r["status"] == "would_install" for r in dry["results"])
    assert not cfg_paths["cursor"].exists()

    # Initial status: 0 configured
    before = mcp_status(config_paths=cfg_paths)
    assert before["configured_count"] == 0
    assert before["total_targets"] == len(MCP_TARGETS)
    assert before["hosts"]["claude-code"]["exists"] is True
    assert before["hosts"]["claude-code"]["configured"] is False

    # Real install into all 5 targets
    res = install_mcp_config(config_paths=cfg_paths)
    assert res["ok"] is True
    assert all(r["status"] == "installed" for r in res["results"])

    # Verify non-clobbering merge on claude-code
    merged = json.loads(cfg_paths["claude-code"].read_text(encoding="utf-8"))
    assert merged["theme"] == "dark"
    assert merged["mcpServers"]["other-server"] == {"command": "node", "args": ["server.js"]}
    assert merged["mcpServers"]["mintfig"] == MCP_SERVER_ENTRY

    # Idempotent second install -> unchanged
    again = install_mcp_config(config_paths=cfg_paths)
    assert all(r["status"] == "unchanged" for r in again["results"])

    # Status now reports all 5 configured
    after = mcp_status(config_paths=cfg_paths)
    assert after["configured_count"] == 5
    for host in MCP_TARGETS:
        assert after["hosts"][host]["configured"] is True
        assert after["hosts"][host]["entry"] == MCP_SERVER_ENTRY


def test_cli_mcp_print_config_and_status(capsys: pytest.CaptureFixture[str]) -> None:
    rc = cli_mcp(["--print-config"])
    assert rc == 0
    captured = json.loads(capsys.readouterr().out)
    assert captured == print_mcp_config()
    assert captured["mcpServers"]["mintfig"] == MCP_SERVER_ENTRY

    rc_status = cli_mcp(["--status", "--json"])
    assert rc_status == 0
    status_data = json.loads(capsys.readouterr().out)
    assert "hosts" in status_data
    assert set(status_data["hosts"].keys()) == set(MCP_TARGETS)


def test_cli_mcp_stdio_roundtrip(monkeypatch: pytest.MonkeyPatch) -> None:
    req_lines = "\n".join(
        [
            json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-03-26"}}),
            json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}),
        ]
    ) + "\n"
    out = io.StringIO()
    monkeypatch.setattr(sys, "stdin", io.StringIO(req_lines))
    monkeypatch.setattr(sys, "stdout", out)
    assert cli_mcp([]) == 0
    replies = [json.loads(line) for line in out.getvalue().strip().splitlines()]
    assert len(replies) == 2
    assert replies[0]["result"]["serverInfo"]["name"] == "mintfig"
    assert len(replies[1]["result"]["tools"]) == 5
