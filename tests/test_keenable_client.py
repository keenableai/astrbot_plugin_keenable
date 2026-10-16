"""Tests for keenable_client against a local aiohttp server standing in for the API."""

from __future__ import annotations

import json

import pytest
from aiohttp import web

from keenable_client import APP_TITLE, KeenableClient, KeenableError, format_results


class FakeKeenable:
    """Records requests and answers with a canned response."""

    def __init__(self):
        self.requests: list[dict] = []
        self.status = 200
        self.body: dict = {"results": []}

    async def handle(self, request: web.Request) -> web.Response:
        self.requests.append(
            {
                "method": request.method,
                "path": request.path,
                "headers": dict(request.headers),
                "query": dict(request.query),
                "json": await request.json() if request.can_read_body else None,
            }
        )
        return web.Response(status=self.status, text=json.dumps(self.body), content_type="application/json")


@pytest.fixture
async def server():
    fake = FakeKeenable()
    app = web.Application()
    app.router.add_route("*", "/{tail:.*}", fake.handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    fake.base_url = f"http://127.0.0.1:{port}"
    yield fake
    await runner.cleanup()


async def test_keyless_search_uses_public_endpoint_and_title(server):
    server.body = {"results": [{"title": "T", "url": "https://a.example", "snippet": "x"}]}
    await KeenableClient(base_url=server.base_url).search("q")
    req = server.requests[0]
    assert req["method"] == "POST"
    assert req["path"] == "/v1/search/public"
    assert req["headers"]["X-Keenable-Title"] == APP_TITLE
    assert "X-API-Key" not in req["headers"]
    assert req["json"] == {"query": "q", "max_results": 10, "snippet_max_length": 500}


async def test_keyed_search_uses_key_and_private_endpoint(server):
    await KeenableClient(" keen_test ", base_url=server.base_url).search("q")
    req = server.requests[0]
    assert req["path"] == "/v1/search"
    assert req["headers"]["X-API-Key"] == "keen_test"
    assert req["headers"]["X-Keenable-Title"] == APP_TITLE


async def test_search_passes_filters_and_clamps_max_results(server):
    client = KeenableClient(base_url=server.base_url)
    await client.search("q", max_results=99, site=" github.com ", published_after="2026-10-01")
    await client.search("q", max_results=-3)
    first, second = server.requests[0]["json"], server.requests[1]["json"]
    assert first["max_results"] == 50
    assert first["site"] == "github.com"
    assert first["published_after"] == "2026-10-01"
    assert second["max_results"] == 1
    assert "site" not in second and "published_after" not in second


async def test_search_rejects_malformed_date_without_calling_api(server):
    with pytest.raises(KeenableError, match="YYYY-MM-DD"):
        await KeenableClient(base_url=server.base_url).search("q", published_after="last week")
    assert server.requests == []


async def test_search_maps_snippet_collapses_whitespace_and_slices(server):
    server.body = {
        "results": [
            {
                "title": "A",
                "url": "https://a.example",
                "description": "",
                "snippet": "line one\n\n  line two " + "x" * 50,
            },
            {"title": "B", "url": "https://b.example", "description": "fallback text"},
            {"title": "no url", "snippet": "dropped"},
            {"url": "https://c.example"},
        ]
    }
    results = await KeenableClient(base_url=server.base_url).search("q", snippet_max_length=20)
    assert results == [
        {"title": "A", "url": "https://a.example", "snippet": "line one line two xx"},
        {"title": "B", "url": "https://b.example", "snippet": "fallback text"},
        {"title": "", "url": "https://c.example", "snippet": ""},
    ]


async def test_keyless_rate_limit_points_to_free_key(server):
    server.status = 429
    server.body = {"error": "Rate limit exceeded", "message": "Public API hourly limit reached. Wait 12 minutes."}
    with pytest.raises(KeenableError) as exc:
        await KeenableClient(base_url=server.base_url).search("q")
    msg = str(exc.value)
    assert "hourly limit reached" in msg
    assert "keenable.ai/console" in msg


async def test_rejected_key_is_reported_as_such(server):
    server.status = 401
    server.body = {"error": "Unauthorized", "message": "Invalid API key"}
    with pytest.raises(KeenableError, match="rejected the API key"):
        await KeenableClient("keen_bad", base_url=server.base_url).search("q")


async def test_other_errors_keep_status_and_plain_body(server):
    server.status = 500
    server.body = "not json"
    with pytest.raises(KeenableError, match="HTTP 500"):
        await KeenableClient(base_url=server.base_url).search("q")


async def test_network_error_becomes_keenable_error():
    with pytest.raises(KeenableError, match="web search failed"):
        await KeenableClient(base_url="http://127.0.0.1:9", timeout_seconds=5).search("q")


async def test_fetch_is_a_get_with_url_and_limit(server):
    server.body = {"url": "https://a.example/", "title": "A", "content": "# A"}
    page = await KeenableClient(base_url=server.base_url).fetch("https://a.example", max_chars=1000)
    req = server.requests[0]
    assert req["method"] == "GET"
    assert req["path"] == "/v1/fetch/public"
    assert req["query"] == {"url": "https://a.example", "max_chars": "1000"}
    assert page["content"] == "# A"


async def test_fetch_without_limit_sends_only_url(server):
    await KeenableClient("k", base_url=server.base_url).fetch("https://a.example")
    req = server.requests[0]
    assert req["path"] == "/v1/fetch"
    assert req["query"] == {"url": "https://a.example"}


def test_format_results_numbers_blocks():
    text = format_results(
        [
            {"title": "A", "url": "https://a.example", "snippet": "alpha"},
            {"title": "B", "url": "https://b.example", "snippet": ""},
        ]
    )
    assert text == "[1] A\nURL: https://a.example\nalpha\n\n[2] B\nURL: https://b.example"
