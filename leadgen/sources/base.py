from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class SearchResult:
    url: str
    title: str
    snippet: str = ""


class WebSearch(Protocol):
    """A web search API (used for discovery and LinkedIn lookups)."""

    name: str

    def search(self, query: str, max_results: int = 20) -> list[SearchResult]: ...
