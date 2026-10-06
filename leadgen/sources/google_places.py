"""Google Places API (New) Text Search — returns name, website, phone and address."""

from __future__ import annotations

import logging

from ..config import CITY_COORDS
from ..extract import canonical_city
from ..http import Fetcher
from ..models import Lead
from ..normalize import normalize_phone, normalize_url
from .base import ProviderSettings

log = logging.getLogger(__name__)

ENDPOINT = "https://places.googleapis.com/v1/places:searchText"
FIELD_MASK = ",".join([
    "places.displayName",
    "places.websiteUri",
    "places.internationalPhoneNumber",
    "places.nationalPhoneNumber",
    "places.formattedAddress",
    "places.addressComponents",
    "places.types",
    "nextPageToken",
])


class GooglePlacesSource:
    name = "places"

    def __init__(self, api_key: str, fetcher: Fetcher, settings: ProviderSettings | None = None):
        self.api_key = api_key
        self.fetcher = fetcher
        self.settings = settings or ProviderSettings()

    def discover(self, phrase: str, city: str, category: str) -> list[Lead]:
        headers = {"X-Goog-Api-Key": self.api_key, "X-Goog-FieldMask": FIELD_MASK}
        body: dict = {
            "textQuery": f"{phrase} in {city}, Saudi Arabia",
            "regionCode": "SA",
            "languageCode": "en",
            "pageSize": 20,
        }
        if city in CITY_COORDS:
            lat, lng = CITY_COORDS[city]
            body["locationBias"] = {
                "circle": {"center": {"latitude": lat, "longitude": lng}, "radius": 30000.0}
            }
        leads: list[Lead] = []
        for _ in range(self.settings.map_pages):  # Google caps text search at 3 pages
            data = self.fetcher.api_json("POST", ENDPOINT, json=body, headers=headers)
            if not data:
                break
            for place in data.get("places", []):
                lead = self._to_lead(place, city, category)
                if lead:
                    leads.append(lead)
            token = data.get("nextPageToken")
            if not token:
                break
            body = {**body, "pageToken": token}
        log.info("places: %r in %s -> %d", phrase, city, len(leads))
        return leads

    @staticmethod
    def _to_lead(place: dict, query_city: str, category: str) -> Lead | None:
        name = (place.get("displayName") or {}).get("text", "").strip()
        if not name:
            return None
        address = place.get("formattedAddress", "")
        city = ""
        for comp in place.get("addressComponents", []):
            if "locality" in comp.get("types", []):
                city = canonical_city(comp.get("longText", "")) or comp.get("longText", "")
                break
        if "saudi" not in address.lower() and "السعودية" not in address:
            return None
        phone = normalize_phone(
            place.get("internationalPhoneNumber") or place.get("nationalPhoneNumber") or ""
        )
        return Lead(
            agency_name=name,
            website=normalize_url(place.get("websiteUri", "")),
            city=city or canonical_city(address) or query_city,
            phones=[phone] if phone else [],
            categories=[category],
            address=address,
            sources=["places"],
            snippet=" ".join(place.get("types", [])),
        )
