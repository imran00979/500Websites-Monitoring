"""Merge duplicate leads found by different queries and sources."""

from __future__ import annotations

from .models import Lead
from .normalize import dedupe_list, normalize_name, registered_domain
from .sources.base import MAP_SOURCES


def _keys(lead: Lead) -> list[tuple[str, str]]:
    keys = []
    domain = registered_domain(lead.website)
    if domain:
        keys.append(("domain", domain))
    keys += [("phone", p) for p in lead.phones if p.startswith("+966")]
    name = normalize_name(lead.agency_name)
    if len(name) >= 4:
        keys.append(("name", name))
    li = lead.linkedin_company_url.lower()
    if li:
        keys.append(("linkedin", li))
    return keys


def _compatible(a: Lead, b: Lead) -> bool:
    """Two leads with different websites are different agencies, whatever else matches."""
    da, db = registered_domain(a.website), registered_domain(b.website)
    return not (da and db and da != db)


def merge_into(target: Lead, other: Lead) -> None:
    # Map listing names/addresses are the registered business details: prefer them.
    if MAP_SOURCES & set(other.sources) and not MAP_SOURCES & set(target.sources):
        target.agency_name = other.agency_name or target.agency_name
        target.address = other.address or target.address
        target.city = other.city or target.city
    for attr in (
        "agency_name", "website", "city", "linkedin_company_url", "founder_name",
        "founder_title", "founder_linkedin_url", "address",
    ):
        if not getattr(target, attr) and getattr(other, attr):
            setattr(target, attr, getattr(other, attr))
    for attr in ("emails", "phones", "services", "categories", "sources"):
        setattr(target, attr, dedupe_list(getattr(target, attr) + getattr(other, attr)))
    target.snippet = f"{target.snippet} {other.snippet}".strip()
    target.site_city_mentions = max(target.site_city_mentions, other.site_city_mentions)


class LeadIndex:
    """Incremental deduplication: add leads one at a time, duplicates are merged."""

    def __init__(self):
        self.leads: list[Lead] = []
        self._index: dict[tuple[str, str], int] = {}

    def __len__(self) -> int:
        return len(self.leads)

    def add(self, lead: Lead) -> tuple[Lead, bool]:
        """Add a lead. Returns (the stored lead, True if it is a new agency)."""
        match = None
        for key in _keys(lead):
            i = self._index.get(key)
            if i is not None and _compatible(self.leads[i], lead):
                match = i
                break
        is_new = match is None
        if is_new:
            self.leads.append(lead)
            match = len(self.leads) - 1
        else:
            merge_into(self.leads[match], lead)
        for key in _keys(self.leads[match]):
            self._index.setdefault(key, match)
        return self.leads[match], is_new


def dedupe(leads: list[Lead]) -> list[Lead]:
    index = LeadIndex()
    for lead in leads:
        index.add(lead)
    return index.leads
