"""Provider registry: which providers exist, how they are configured, how they are built.

Every provider is optional. A provider is *configured* when one of its API-key
environment variables is set. Which configured providers run is chosen with
--providers on the command line or LEADGEN_PROVIDERS in the environment;
"auto" (the default) runs every configured provider.

To add a provider: write a class with `name` and `discover(phrase, city, category)`
(and/or `search(query, max_results)` for LinkedIn lookups), then register a
ProviderSpec for it below.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

from ..http import Fetcher
from .base import DiscoveryProvider, ProviderSettings, WebSearch
from .google_places import GooglePlacesSource
from .serpapi_maps import SerpApiMapsSource
from .web_search import BraveSearch, SerpApiSearch, WebSearchSource

PROVIDERS_ENV = "LEADGEN_PROVIDERS"
LINKEDIN_PROVIDER_ENV = "LEADGEN_LINKEDIN_PROVIDER"


class ProviderConfigError(ValueError):
    """Unknown provider name, or a provider selected without its API key."""


@dataclass(frozen=True)
class ProviderSpec:
    name: str
    label: str
    env_vars: tuple[str, ...]           # first one that is set wins
    signup_url: str
    # Build the discovery provider; None if this provider cannot discover agencies.
    make_discovery: Callable[[str, Fetcher, ProviderSettings], DiscoveryProvider] | None = None
    # Build a web search engine for LinkedIn lookups; None if not supported.
    make_search: Callable[[str, Fetcher], WebSearch] | None = None
    notes: str = ""

    @property
    def capabilities(self) -> list[str]:
        caps = []
        if self.make_discovery:
            caps.append("discovery")
        if self.make_search:
            caps.append("linkedin")
        return caps

    def api_key(self, env: Mapping[str, str]) -> str:
        for var in self.env_vars:
            if env.get(var, "").strip():
                return env[var].strip()
        return ""


PROVIDERS: dict[str, ProviderSpec] = {
    spec.name: spec
    for spec in [
        ProviderSpec(
            name="places",
            label="Google Places API (Google Maps)",
            env_vars=("GOOGLE_PLACES_API_KEY", "GOOGLE_MAPS_API_KEY"),
            signup_url="https://developers.google.com/maps/documentation/places/web-service/get-api-key",
            make_discovery=lambda key, f, s: GooglePlacesSource(key, f, s),
            notes="verified name, phone, address and website; up to 60 places per query",
        ),
        ProviderSpec(
            name="serpapi_maps",
            label="Google Maps via SerpAPI",
            env_vars=("SERPAPI_API_KEY",),
            signup_url="https://serpapi.com/manage-api-key",
            make_discovery=lambda key, f, s: SerpApiMapsSource(key, f, s),
            notes="Google Maps listings without a Google Cloud project",
        ),
        ProviderSpec(
            name="serpapi",
            label="Google web results via SerpAPI",
            env_vars=("SERPAPI_API_KEY",),
            signup_url="https://serpapi.com/manage-api-key",
            make_discovery=lambda key, f, s: WebSearchSource(SerpApiSearch(key, f), s),
            make_search=lambda key, f: SerpApiSearch(key, f),
        ),
        ProviderSpec(
            name="brave",
            label="Brave Search API",
            env_vars=("BRAVE_API_KEY", "BRAVE_SEARCH_API_KEY"),
            signup_url="https://brave.com/search/api/",
            make_discovery=lambda key, f, s: WebSearchSource(BraveSearch(key, f), s),
            make_search=lambda key, f: BraveSearch(key, f),
        ),
    ]
}

# Preferred engine for LinkedIn lookups when several are configured.
LINKEDIN_PREFERENCE = ["serpapi", "brave"]


@dataclass
class ProviderSetup:
    discovery: list[DiscoveryProvider] = field(default_factory=list)
    linkedin: WebSearch | None = None
    selected: list[str] = field(default_factory=list)


def configured(env: Mapping[str, str]) -> list[str]:
    """Names of providers whose API key is present."""
    return [name for name, spec in PROVIDERS.items() if spec.api_key(env)]


def parse_names(value: str) -> list[str]:
    names = [n.strip().lower() for n in (value or "").split(",") if n.strip()]
    unknown = [n for n in names if n not in PROVIDERS and n not in ("auto", "none")]
    if unknown:
        raise ProviderConfigError(
            f"unknown provider(s): {', '.join(unknown)}; choose from {', '.join(PROVIDERS)}"
        )
    return names


def build(
    fetcher: Fetcher,
    env: Mapping[str, str],
    providers: str | None = None,
    linkedin: str | None = None,
    settings: ProviderSettings | None = None,
) -> ProviderSetup:
    """Instantiate the selected providers.

    providers: comma list, "auto" (every configured provider) or "none".
               Defaults to $LEADGEN_PROVIDERS, then "auto".
    linkedin:  provider name for LinkedIn lookups, "auto" or "none".
               Defaults to $LEADGEN_LINKEDIN_PROVIDER, then "auto".
    """
    settings = settings or ProviderSettings()
    names = parse_names(providers or env.get(PROVIDERS_ENV, "") or "auto")
    if names == ["auto"]:
        selected = [n for n in configured(env) if PROVIDERS[n].make_discovery]
    elif names == ["none"]:
        selected = []
    else:
        missing = [n for n in names if not PROVIDERS[n].api_key(env)]
        if missing:
            raise ProviderConfigError("; ".join(
                f"provider {n!r} needs {' or '.join(PROVIDERS[n].env_vars)}" for n in missing
            ))
        selected = list(dict.fromkeys(names))

    setup = ProviderSetup(selected=selected)
    for name in selected:
        spec = PROVIDERS[name]
        if spec.make_discovery:
            setup.discovery.append(spec.make_discovery(spec.api_key(env), fetcher, settings))

    li = (linkedin or env.get(LINKEDIN_PROVIDER_ENV, "") or "auto").strip().lower()
    if li == "auto":
        for name in LINKEDIN_PREFERENCE:
            if PROVIDERS[name].api_key(env):
                li = name
                break
        else:
            li = "none"
    if li != "none":
        spec = PROVIDERS.get(li)
        if not spec or not spec.make_search:
            capable = [n for n, s in PROVIDERS.items() if s.make_search]
            raise ProviderConfigError(f"LinkedIn provider must be one of: {', '.join(capable)}")
        if not spec.api_key(env):
            raise ProviderConfigError(f"LinkedIn provider {li!r} needs {' or '.join(spec.env_vars)}")
        setup.linkedin = spec.make_search(spec.api_key(env), fetcher)
    return setup


def status_table(env: Mapping[str, str]) -> str:
    """Human-readable provider status for --list-providers."""
    lines = []
    for spec in PROVIDERS.values():
        var = next((v for v in spec.env_vars if env.get(v, "").strip()), "")
        state = f"configured ({var})" if var else f"not configured: set {' or '.join(spec.env_vars)}"
        lines.append(f"  {spec.name:<13} {spec.label}")
        lines.append(f"  {'':<13} uses: {', '.join(spec.capabilities)} | {state}")
        if spec.notes:
            lines.append(f"  {'':<13} {spec.notes}")
        if not var:
            lines.append(f"  {'':<13} get a key: {spec.signup_url}")
    return "\n".join(lines)
