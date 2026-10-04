"""Merge duplicate leads found by different queries and sources."""

from __future__ import annotations

from .models import Lead
from .normalize import dedupe_list, normalize_name, registered_domain


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
    # Google Places names/addresses are the registered business details: prefer them.
    if "google_places" in other.sources and "google_places" not in target.sources:
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


def dedupe(leads: list[Lead]) -> list[Lead]:
    merged: list[Lead] = []
    index: dict[tuple[str, str], int] = {}
    for lead in leads:
        match = None
        for key in _keys(lead):
            i = index.get(key)
            if i is not None and _compatible(merged[i], lead):
                match = i
                break
        if match is None:
            merged.append(lead)
            match = len(merged) - 1
        else:
            merge_into(merged[match], lead)
        for key in _keys(merged[match]):
            index.setdefault(key, match)
    return merged
