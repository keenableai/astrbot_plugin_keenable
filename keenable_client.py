"""Minimal async client for the Keenable search and fetch APIs.

Kept free of AstrBot imports so it can be tested on its own.
"""

from __future__ import annotations

import json
import re

import aiohttp

API_BASE = "https://api.keenable.ai"
# Identifies the plugin to Keenable. Requests without an API key are rejected
# unless this header is present.
APP_TITLE = "astrbot-plugin"
CONSOLE_URL = "https://keenable.ai/console"

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class KeenableError(Exception):
    """A Keenable request failed; the message is safe to show to the model."""


class KeenableClient:
    """Calls Keenable with an API key, or the keyless public endpoints without one."""

    def __init__(
        self,
        api_key: str = "",
        *,
        base_url: str = API_BASE,
        timeout_seconds: float = 30,
    ) -> None:
        self.api_key = api_key.strip()
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    async def _request(
        self,
        path: str,
        action: str,
        *,
        payload: dict | None = None,
        params: dict | None = None,
    ) -> dict:
        headers = {"X-Keenable-Title": APP_TITLE}
        url = f"{self.base_url}{path}"
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        else:
            # Keyless requests go to `<path>/public`, rate-limited per IP.
            url += "/public"

        timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)
        try:
            # trust_env picks up HTTP(S)_PROXY, which many AstrBot hosts rely on.
            async with aiohttp.ClientSession(trust_env=True, timeout=timeout) as session:
                method = "POST" if payload is not None else "GET"
                async with session.request(method, url, json=payload, params=params, headers=headers) as response:
                    if response.status == 200:
                        return await response.json(content_type=None)
                    body = await response.text()
                    raise KeenableError(self._error_message(action, response.status, body))
        except KeenableError:
            raise
        except TimeoutError as exc:
            raise KeenableError(f"Keenable {action} timed out after {self.timeout_seconds}s.") from exc
        except aiohttp.ClientError as exc:
            raise KeenableError(f"Keenable {action} failed: {exc}") from exc

    def _error_message(self, action: str, status: int, body: str) -> str:
        try:
            data = json.loads(body)
            detail = data.get("message") or data.get("error") or body
        except (ValueError, AttributeError):
            detail = body
        detail = " ".join(str(detail).split())[:300]
        if status == 429 and not self.api_key:
            return (
                f"Keenable {action} hit the keyless rate limit ({detail}). "
                f"A free API key from {CONSOLE_URL} raises it; set it in the plugin settings."
            )
        if status in (401, 403) and self.api_key:
            return f"Keenable rejected the API key ({status}): {detail}"
        return f"Keenable {action} failed with HTTP {status}: {detail}"

    async def search(
        self,
        query: str,
        *,
        max_results: int = 10,
        site: str = "",
        published_after: str = "",
        snippet_max_length: int = 500,
    ) -> list[dict]:
        """Search the web. Returns results as dicts with title, url and snippet."""
        payload: dict = {
            "query": query,
            "max_results": min(max(int(max_results), 1), 50),
            "snippet_max_length": snippet_max_length,
        }
        if site.strip():
            payload["site"] = site.strip()
        if published_after.strip():
            if not _DATE_RE.match(published_after.strip()):
                raise KeenableError("published_after must be a date in YYYY-MM-DD format.")
            payload["published_after"] = published_after.strip()

        data = await self._request("/v1/search", "web search", payload=payload)
        results = []
        for item in data.get("results") or []:
            if not item.get("url"):
                continue
            # `snippet` carries the page text; `description` is usually empty.
            # The text keeps the page's line breaks, so collapse whitespace, and
            # slice because the server treats the length as a hint.
            text = " ".join((item.get("snippet") or item.get("description") or "").split())
            results.append(
                {
                    "title": item.get("title") or "",
                    "url": item["url"],
                    "snippet": text[:snippet_max_length],
                }
            )
        return results

    async def fetch(self, url: str, *, max_chars: int = 0) -> dict:
        """Read a page as Markdown. Returns a dict with url, title and content."""
        params: dict = {"url": url}
        if max_chars > 0:
            params["max_chars"] = max_chars
        return await self._request("/v1/fetch", "page fetch", params=params)


def format_results(results: list[dict]) -> str:
    """Render search results as numbered plain text for the model."""
    blocks = []
    for i, r in enumerate(results, 1):
        blocks.append(f"[{i}] {r['title']}\nURL: {r['url']}\n{r['snippet']}".rstrip())
    return "\n\n".join(blocks)
