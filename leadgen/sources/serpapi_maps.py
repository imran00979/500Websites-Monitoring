"""Google Maps results through SerpAPI (engine=google_maps).

Gives Google Maps listings (name, website, phone, address) without a Google
Cloud project; it uses the same SERPAPI_API_KEY as the web search provider.
"""

from __future__ import annotations

import logging

from ..config import CITY_COORDS
from ..extract import canonical_city
from ..http import Fetcher
from ..models import Lead
from ..normalize import is_non_agency_domain, normalize_phone, normalize_url
from .base import ProviderSettings

log = logging.getLogger(__name__)

ENDPOINT = "https://serpapi.com/search.json"


class SerpApiMapsSource:
    name = "serpapi_maps"

    def __init__(self, api_key: str, fetcher: Fetcher, settings: ProviderSettings | None = None):
        self.api_key = api_key
        self.fetcher = fetcher
        self.settings = settings or ProviderSettings()

    def discover(self, phrase: str, city: str, category: str) -> list[Lead]:
        params = {
            "engine": "google_maps", "type": "search", "q": f"{phrase} {city}",
            "hl": "en", "gl": "sa", "api_key": self.api_key,
        }
        if city in CITY_COORDS:
            lat, lng = CITY_COORDS[city]
            params["ll"] = f"@{lat},{lng},12z"
        leads: list[Lead] = []
        for page in range(self.settings.map_pages):
            data = self.fetcher.api_json("GET", ENDPOINT, params={**params, "start": page * 20})
            results = (data or {}).get("local_results", [])
            for place in results:
                lead = self._to_lead(place, city, category)
                if lead:
                    leads.append(lead)
            if len(results) < 20:
                break
        log.info("serpapi_maps: %r in %s -> %d", phrase, city, len(leads))
        return leads

    @staticmethod
    def _to_lead(place: dict, query_city: str, category: str) -> Lead | None:
        name = (place.get("title") or "").strip()
        address = place.get("address") or ""
        phone = normalize_phone(place.get("phone") or "")
        website = place.get("website") or ""
        if not name:
            return None
        # Maps listings outside KSA (no Saudi phone and no Saudi city in the address) are skipped.
        if not phone and not canonical_city(address):
            return None
        if website and is_non_agency_domain(website):
            website = ""  # an Instagram/Linktree "website" is not the agency's site
        types = place.get("types") or [place.get("type", "")]
        return Lead(
            agency_name=name,
            website=normalize_url(website),
            city=canonical_city(address) or query_city,
            phones=[phone] if phone else [],
            categories=[category],
            address=address,
            sources=["serpapi_maps"],
            snippet=" ".join(t for t in types if t),
        )
