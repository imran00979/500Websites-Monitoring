"""Discovery providers and the registry that configures them."""

from .base import MAP_SOURCES, DiscoveryProvider, ProviderSettings, SearchResult, WebSearch
from .google_places import GooglePlacesSource
from .registry import PROVIDERS, ProviderConfigError, ProviderSetup, build, configured, status_table
from .seeds import load_seeds
from .serpapi_maps import SerpApiMapsSource
from .web_search import BraveSearch, SerpApiSearch, WebSearchSource

__all__ = [
    "MAP_SOURCES",
    "PROVIDERS",
    "BraveSearch",
    "DiscoveryProvider",
    "GooglePlacesSource",
    "ProviderConfigError",
    "ProviderSettings",
    "ProviderSetup",
    "SearchResult",
    "SerpApiMapsSource",
    "SerpApiSearch",
    "WebSearch",
    "WebSearchSource",
    "build",
    "configured",
    "load_seeds",
    "status_table",
]
