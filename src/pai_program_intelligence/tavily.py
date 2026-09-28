"""Tavily Search/Extract adapter for the source-layer ResearchClient protocol.

Credentials come from the process environment or explicit secret injection;
this module does not read project files or log request headers.
"""

from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .schemas import ErrorCode
from .sources import (
    FetchedPage,
    SearchHit,
    SourceLayerError,
    _canonical_url,
    _official_domains,
)


_API_ROOT = "https://api.tavily.com"
_MAX_RESPONSE_BYTES = 4_000_000


class TavilyResearchClient:
    def __init__(self, api_key: str | None = None, *, timeout: float = 30) -> None:
        key = api_key or os.environ.get("TAVILY_API_KEY") or os.environ.get("WEB_SEARCH_API_KEY")
        if not key:
            raise ValueError("Set TAVILY_API_KEY or WEB_SEARCH_API_KEY in the process environment")
        if not 1 <= timeout <= 60:
            raise ValueError("timeout must be between 1 and 60 seconds")
        self._api_key = key
        self._timeout = timeout

    def _post(self, endpoint: str, payload: dict[str, object]) -> dict[str, object]:
        request = Request(
            f"{_API_ROOT}/{endpoint}",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self._timeout) as response:
                data = response.read(_MAX_RESPONSE_BYTES + 1)
        except HTTPError as exc:
            if exc.code in {429, 432, 433}:
                raise SourceLayerError(ErrorCode.RATE_LIMITED, "Tavily request limit reached") from None
            raise SourceLayerError(ErrorCode.PROVIDER_ERROR, "Tavily request failed") from None
        except (URLError, TimeoutError, OSError):
            raise SourceLayerError(ErrorCode.PROVIDER_ERROR, "Tavily is unavailable") from None
        if len(data) > _MAX_RESPONSE_BYTES:
            raise SourceLayerError(ErrorCode.PROVIDER_ERROR, "Tavily response is too large")
        try:
            result = json.loads(data)
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise SourceLayerError(ErrorCode.PROVIDER_ERROR, "Tavily returned invalid JSON") from None
        if not isinstance(result, dict):
            raise SourceLayerError(ErrorCode.PROVIDER_ERROR, "Tavily returned an invalid response")
        return result

    async def search(self, query: str, *, limit: int = 10, domains=()) -> list[SearchHit]:
        if not isinstance(query, str) or not query.strip() or type(limit) is not int or not 1 <= limit <= 20:
            raise SourceLayerError(ErrorCode.INVALID_REQUEST, "A query and a limit from 1 to 20 are required")
        trusted_domains = _official_domains(domains)
        payload: dict[str, object] = {
            "query": query,
            "max_results": limit,
            "search_depth": "basic",
            "include_answer": False,
            "include_raw_content": False,
            "include_domains": list(trusted_domains),
            "include_domains_mode": "restrict",
        }
        response = await asyncio.to_thread(self._post, "search", payload)
        results = response.get("results")
        if not isinstance(results, list):
            raise SourceLayerError(ErrorCode.PROVIDER_ERROR, "Tavily search results are invalid")
        hits = []
        for item in results:
            if not isinstance(item, dict) or not isinstance(item.get("url"), str):
                continue
            hits.append(
                SearchHit(
                    url=item["url"],
                    title=item.get("title") if isinstance(item.get("title"), str) else "",
                    snippet=item.get("content") if isinstance(item.get("content"), str) else "",
                )
            )
        return hits

    async def fetch(self, url: str) -> FetchedPage:
        canonical = _canonical_url(url)
        if canonical is None:
            raise SourceLayerError(ErrorCode.UNSUPPORTED_SOURCE, "URL is not a public HTTP(S) page")
        response = await asyncio.to_thread(
            self._post,
            "extract",
            {"urls": [canonical], "extract_depth": "basic", "format": "markdown"},
        )
        results = response.get("results")
        if not isinstance(results, list):
            raise SourceLayerError(ErrorCode.PROVIDER_ERROR, "Tavily extraction results are invalid")
        if not results or not isinstance(results[0], dict):
            raise SourceLayerError(ErrorCode.SOURCE_UNAVAILABLE, "Tavily could not extract this page")
        result = results[0]
        reported_url = result.get("url")
        raw_content = result.get("raw_content")
        if not isinstance(reported_url, str) or not isinstance(raw_content, str) or not raw_content.strip():
            raise SourceLayerError(ErrorCode.SOURCE_UNAVAILABLE, "Tavily returned no readable page text")
        return FetchedPage(
            reported_url=reported_url,
            title="",
            text=raw_content,
            fetched_at=datetime.now(timezone.utc).isoformat(),
        )
