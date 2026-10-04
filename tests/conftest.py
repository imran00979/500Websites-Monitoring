import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from leadgen.http import Fetcher  # noqa: E402
from leadgen.sources.base import SearchResult  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures"


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


SITE = {
    "https://acmedigital.com.sa": "acme_home.html",
    "https://acmedigital.com.sa/about-us": "acme_about.html",
    "https://acmedigital.com.sa/contact": "acme_contact.html",
    "https://noor-marketing.sa": "noor_home.html",
    "https://noor-marketing.sa/من-نحن": "noor_about.html",
}


class FakeFetcher(Fetcher):
    """Serves fixture pages instead of hitting the network."""

    def __init__(self):
        super().__init__(delay=0, cache_dir=None, respect_robots=False)
        self.requested: list[str] = []

    def get_html(self, url):
        self.requested.append(url)
        name = SITE.get(url.rstrip("/"))
        return (url, fixture(name)) if name else None


class FakeSearch:
    name = "brave"

    def __init__(self, results: dict[str, list[SearchResult]]):
        self.results = results
        self.queries: list[str] = []

    def search(self, query, max_results=20):
        self.queries.append(query)
        for key, results in self.results.items():
            if key in query:
                return results[:max_results]
        return []


@pytest.fixture
def fetcher():
    return FakeFetcher()
