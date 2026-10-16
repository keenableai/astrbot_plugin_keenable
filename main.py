"""Keenable web search for AstrBot: search the web and read pages, no API key needed."""

from __future__ import annotations

from urllib.parse import urlparse

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star
from astrbot.core.star.filter.command import GreedyStr

from .keenable_client import KeenableClient, KeenableError, format_results

try:
    from astrbot.core.provider.register import llm_tools as _llm_tools
except ImportError:
    _llm_tools = None

PLUGIN_NAME = "astrbot_plugin_keenable"
SEARCH_TOOL = "keenable_web_search"
FETCH_TOOL = "keenable_fetch_page"

DEFAULTS = {
    "api_key": "",
    "max_results": 8,
    "snippet_max_length": 500,
    "fetch_max_chars": 20000,
    "enable_fetch": True,
    "timeout_seconds": 30,
}


class KeenablePlugin(Star):
    def __init__(self, context: Context, config: dict | None = None):
        super().__init__(context)
        self.config = config or {}

    def _cfg(self, key: str):
        value = self.config.get(key, DEFAULTS[key])
        return DEFAULTS[key] if value is None else value

    def _int_cfg(self, key: str, low: int, high: int) -> int:
        try:
            value = int(self._cfg(key))
        except (TypeError, ValueError):
            value = DEFAULTS[key]
        return min(max(value, low), high)

    def _client(self) -> KeenableClient:
        return KeenableClient(
            str(self._cfg("api_key") or ""),
            timeout_seconds=self._int_cfg("timeout_seconds", 5, 120),
        )

    async def initialize(self):
        if not self._cfg("enable_fetch") and _llm_tools is not None:
            # The tool is registered at import time; take it out of the in-memory
            # registry (not the persisted on/off list) so re-enabling it in the
            # settings and reloading the plugin brings it back.
            _llm_tools.remove_func(FETCH_TOOL)
        if not str(self._cfg("api_key") or "").strip():
            logger.info(f"[{PLUGIN_NAME}] no API key set, using the keyless tier")

    async def _search(self, query: str, max_results: int = 0, site: str = "", published_after: str = "") -> str:
        if max_results <= 0:
            max_results = self._int_cfg("max_results", 1, 50)
        results = await self._client().search(
            query,
            max_results=max_results,
            site=site,
            published_after=published_after,
            snippet_max_length=self._int_cfg("snippet_max_length", 100, 4000),
        )
        if not results:
            return f"No Keenable results for: {query}"
        return format_results(results)

    async def _fetch(self, url: str, max_chars: int = 0) -> str:
        if urlparse(url).scheme.lower() not in ("http", "https"):
            return "Error: url must be an http or https URL."
        limit = self._int_cfg("fetch_max_chars", 1000, 200000)
        max_chars = limit if max_chars <= 0 else min(max_chars, limit)
        page = await self._client().fetch(url, max_chars=max_chars)
        content = (page.get("content") or "")[:max_chars]
        if not content:
            return f"Error: Keenable returned no content for {url}"
        title = page.get("title") or ""
        header = f"URL: {page.get('url') or url}\n" + (f"Title: {title}\n" if title else "")
        return f"{header}\n{content}"

    @filter.command("keenable")
    async def keenable_command(self, event: AstrMessageEvent, query: GreedyStr = ""):
        """用 Keenable 搜索网页。用法：/keenable <关键词>"""
        query = str(query or "").strip()
        if not query:
            yield event.plain_result("用法 / Usage: /keenable <query>")
            return
        try:
            text = await self._search(query, max_results=5)
        except KeenableError as exc:
            text = str(exc)
        except Exception as exc:
            logger.exception(f"[{PLUGIN_NAME}] /keenable failed: {exc}")
            text = f"Keenable search failed: {exc}"
        yield event.plain_result(text)

    @filter.llm_tool(name=SEARCH_TOOL)
    async def keenable_web_search(
        self,
        event: AstrMessageEvent,
        query: str = "",
        max_results: int = 0,
        site: str = "",
        published_after: str = "",
    ) -> str:
        """Search the web with Keenable.
        Returns ranked pages, each with its URL and an excerpt of the page text, so most
        questions can be answered from the results alone. Use it for current events,
        documentation, prices, people, companies, and anything that may have changed recently.

        Args:
            query(string): Required. A specific, self-contained search query.
            max_results(number): Optional. Number of results, 1-50. Omit or pass 0 for the default.
            site(string): Optional. Restrict results to one domain, for example "github.com".
            published_after(string): Optional. Only pages published on or after this date,
                YYYY-MM-DD. Use it for recent news.
        """
        del event
        query = str(query or "").strip()
        if not query:
            return "Error: query must be a non-empty string."
        try:
            count = int(max_results or 0)
        except (TypeError, ValueError):
            count = 0
        try:
            return await self._search(query, count, str(site or ""), str(published_after or ""))
        except KeenableError as exc:
            return f"Error: {exc}"
        except Exception as exc:
            logger.exception(f"[{PLUGIN_NAME}] {SEARCH_TOOL} failed: {exc}")
            return f"Error: Keenable search failed: {exc}"

    @filter.llm_tool(name=FETCH_TOOL)
    async def keenable_fetch_page(self, event: AstrMessageEvent, url: str = "", max_chars: int = 0) -> str:
        """Read a web page with Keenable and return its main content as Markdown.
        Use it when search excerpts are not enough or the user gives a URL.

        Args:
            url(string): Required. The http(s) URL to read.
            max_chars(number): Optional. Maximum characters of content to return.
                Omit or pass 0 for the default.
        """
        del event
        url = str(url or "").strip()
        if not url:
            return "Error: url must be a non-empty string."
        try:
            limit = int(max_chars or 0)
        except (TypeError, ValueError):
            limit = 0
        try:
            return await self._fetch(url, limit)
        except KeenableError as exc:
            return f"Error: {exc}"
        except Exception as exc:
            logger.exception(f"[{PLUGIN_NAME}] {FETCH_TOOL} failed: {exc}")
            return f"Error: Keenable page fetch failed: {exc}"
