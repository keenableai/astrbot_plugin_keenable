"""Tests for the AstrBot side: tool registration, config handling, tool and command output.

Skipped unless AstrBot is importable (run them from an AstrBot checkout's environment).
"""

from __future__ import annotations

import importlib
from unittest.mock import MagicMock

import pytest


class FakeClient:
    """Stands in for KeenableClient and records calls."""

    def __init__(self, errors_module, *, results=None, page=None, error=None):
        self.errors = errors_module
        self.results = results if results is not None else []
        self.page = page or {}
        self.error = error
        self.calls: list[tuple] = []

    async def search(self, query, **kwargs):
        self.calls.append(("search", query, kwargs))
        if self.error:
            raise self.errors.KeenableError(self.error)
        return self.results

    async def fetch(self, url, **kwargs):
        self.calls.append(("fetch", url, kwargs))
        if self.error:
            raise self.errors.KeenableError(self.error)
        return self.page


@pytest.fixture
def make_plugin(plugin_main):
    client_mod = importlib.import_module("astrbot_plugin_keenable.keenable_client")

    def make(config=None, **client_kwargs):
        plugin = plugin_main.KeenablePlugin(MagicMock(), config or {})
        fake = FakeClient(client_mod, **client_kwargs)
        plugin._client = lambda: fake
        return plugin, fake

    return make


def test_tools_are_registered_with_parameter_schemas(plugin_main):
    from astrbot.core.provider.register import llm_tools

    search = llm_tools.get_func("keenable_web_search")
    fetch = llm_tools.get_func("keenable_fetch_page")
    assert search is not None and fetch is not None
    props = search.parameters["properties"]
    assert {k: v["type"] for k, v in props.items()} == {
        "query": "string",
        "max_results": "number",
        "site": "string",
        "published_after": "string",
    }
    assert {k: v["type"] for k, v in fetch.parameters["properties"].items()} == {
        "url": "string",
        "max_chars": "number",
    }
    assert "Search the web with Keenable" in search.description


async def test_search_tool_formats_results_and_uses_config_defaults(make_plugin):
    plugin, fake = make_plugin(
        {"max_results": 3, "snippet_max_length": 200},
        results=[{"title": "A", "url": "https://a.example", "snippet": "alpha"}],
    )
    out = await plugin.keenable_web_search(MagicMock(), query="  q  ", site="x.org", published_after="2026-10-01")
    assert out == "[1] A\nURL: https://a.example\nalpha"
    assert fake.calls == [
        ("search", "q", {"max_results": 3, "site": "x.org", "published_after": "2026-10-01", "snippet_max_length": 200})
    ]


async def test_search_tool_honours_model_count_and_bad_config(make_plugin):
    plugin, fake = make_plugin({"max_results": "lots", "snippet_max_length": None})
    await plugin.keenable_web_search(MagicMock(), query="q", max_results=12)
    await plugin.keenable_web_search(MagicMock(), query="q", max_results="junk")
    assert fake.calls[0][2]["max_results"] == 12
    assert fake.calls[0][2]["snippet_max_length"] == 500
    assert fake.calls[1][2]["max_results"] == 8


async def test_search_tool_reports_empty_query_no_results_and_errors(make_plugin):
    plugin, fake = make_plugin()
    assert (await plugin.keenable_web_search(MagicMock(), query=" ")).startswith("Error: query")
    assert fake.calls == []
    assert await plugin.keenable_web_search(MagicMock(), query="q") == "No Keenable results for: q"
    plugin, _ = make_plugin(error="Keenable web search hit the keyless rate limit")
    assert await plugin.keenable_web_search(MagicMock(), query="q") == (
        "Error: Keenable web search hit the keyless rate limit"
    )


async def test_fetch_tool_caps_content_and_adds_header(make_plugin):
    plugin, fake = make_plugin(
        {"fetch_max_chars": 1000},
        page={"url": "https://a.example/", "title": "A", "content": "x" * 5000},
    )
    out = await plugin.keenable_fetch_page(MagicMock(), url="https://a.example", max_chars=50000)
    assert fake.calls == [("fetch", "https://a.example", {"max_chars": 1000})]
    assert out == "URL: https://a.example/\nTitle: A\n\n" + "x" * 1000


async def test_fetch_tool_rejects_bad_urls_and_reports_empty_pages(make_plugin):
    plugin, fake = make_plugin(page={"content": ""})
    assert (await plugin.keenable_fetch_page(MagicMock(), url="")).startswith("Error: url must be a non-empty")
    assert (await plugin.keenable_fetch_page(MagicMock(), url="file:///etc/passwd")).startswith(
        "Error: url must be an http"
    )
    assert fake.calls == []
    assert await plugin.keenable_fetch_page(MagicMock(), url="https://a.example") == (
        "Error: Keenable returned no content for https://a.example"
    )


async def test_command_replies_with_results_or_usage(make_plugin):
    plugin, fake = make_plugin(results=[{"title": "A", "url": "https://a.example", "snippet": "alpha"}])
    event = MagicMock()
    event.plain_result.side_effect = lambda text: text
    assert [r async for r in plugin.keenable_command(event, "")] == ["用法 / Usage: /keenable <query>"]
    assert [r async for r in plugin.keenable_command(event, "q")] == ["[1] A\nURL: https://a.example\nalpha"]
    assert fake.calls[0][2]["max_results"] == 5


async def test_disabling_fetch_unregisters_the_tool(plugin_main, make_plugin):
    from astrbot.core.provider.register import llm_tools

    plugin, _ = make_plugin({"enable_fetch": False})
    await plugin.initialize()
    assert llm_tools.get_func("keenable_fetch_page") is None
    assert llm_tools.get_func("keenable_web_search") is not None
    # A reload (what AstrBot does after a settings change) registers it again.
    importlib.reload(plugin_main)
    assert llm_tools.get_func("keenable_fetch_page") is not None
