"""Web search APIs (Brave Search, SerpAPI) used to discover agency websites."""

from __future__ import annotations

import logging

from ..http import Fetcher
from ..models import Lead
from ..normalize import clean_name, is_non_agency_domain, normalize_url
from .base import SearchResult, WebSearch

log = logging.getLogger(__name__)


class BraveSearch:
    name = "brave"
    endpoint = "https://api.search.brave.com/res/v1/web/search"

    def __init__(self, api_key: str, fetcher: Fetcher):
        self.api_key = api_key
        self.fetcher = fetcher

    def search(self, query: str, max_results: int = 20) -> list[SearchResult]:
        results: list[SearchResult] = []
        headers = {"X-Subscription-Token": self.api_key, "Accept": "application/json"}
        offset = 0
        while len(results) < max_results and offset < 10:
            params = {"q": query, "count": 20, "offset": offset, "country": "SA"}
            data = self.fetcher.api_json("GET", self.endpoint, params=params, headers=headers)
            items = ((data or {}).get("web") or {}).get("results", [])
            if not items:
                break
            results += [
                SearchResult(i.get("url", ""), i.get("title", ""), i.get("description", ""))
                for i in items
            ]
            if not ((data or {}).get("query") or {}).get("more_results_available"):
                break
            offset += 1
        return results[:max_results]


class SerpApiSearch:
    name = "serpapi"
    endpoint = "https://serpapi.com/search.json"

    def __init__(self, api_key: str, fetcher: Fetcher):
        self.api_key = api_key
        self.fetcher = fetcher

    def search(self, query: str, max_results: int = 20) -> list[SearchResult]:
        results: list[SearchResult] = []
        start = 0
        while len(results) < max_results:
            params = {
                "engine": "google", "q": query, "gl": "sa", "hl": "en",
                "num": 10, "start": start, "api_key": self.api_key,
            }
            data = self.fetcher.api_json("GET", self.endpoint, params=params)
            items = (data or {}).get("organic_results", [])
            if not items:
                break
            results += [
                SearchResult(i.get("link", ""), i.get("title", ""), i.get("snippet", ""))
                for i in items
            ]
            start += 10
        return results[:max_results]


class WebSearchSource:
    """Discovery via organic search results, keeping only likely agency homepages."""

    def __init__(self, engine: WebSearch, max_results: int = 30):
        self.engine = engine
        self.name = engine.name
        self.max_results = max_results

    def discover(self, phrase: str, city: str, category: str) -> list[Lead]:
        query = f"{phrase} {city} Saudi Arabia"
        leads = []
        for r in self.engine.search(query, self.max_results):
            if not r.url or is_non_agency_domain(r.url):
                continue
            leads.append(Lead(
                agency_name=clean_name(r.title),
                website=normalize_url(r.url),
                city=city,
                categories=[category],
                sources=[self.name],
                snippet=f"{r.title} {r.snippet}",
            ))
        log.info("%s: %r -> %d", self.name, query, len(leads))
        return leads
