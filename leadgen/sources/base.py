"""Interfaces shared by every provider."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from ..models import Lead


# Providers whose results are verified business listings (Google Maps data). Their
# name, address and city are preferred over web-search guesses.
MAP_SOURCES = frozenset({"places", "serpapi_maps", "demo_maps"})
# Providers whose leads come from organic web results (titles are often SEO copy).
SEARCH_SOURCES = frozenset({"brave", "serpapi", "demo_search"})


@dataclass
class SearchResult:
    url: str
    title: str
    snippet: str = ""


@dataclass
class ProviderSettings:
    """Per-query result budget. Test mode uses a smaller budget to save API quota."""

    results_per_query: int = 30   # web search results read per query
    map_pages: int = 3            # map result pages per query (20 places per page)


class DiscoveryProvider(Protocol):
    """Turns one (search phrase, city, category) query into candidate leads."""

    name: str

    def discover(self, phrase: str, city: str, category: str) -> list["Lead"]: ...


class WebSearch(Protocol):
    """A web search API. Used for discovery and for LinkedIn lookups."""

    name: str

    def search(self, query: str, max_results: int = 20) -> list[SearchResult]: ...
