"""Enrich a lead by crawling a handful of pages on the agency's own website."""

from __future__ import annotations

import logging
from collections import Counter
from urllib.parse import urljoin

from .config import FALLBACK_PATHS, SERVICE_TO_CATEGORY
from .extract import parse_page, role_rank
from .http import Fetcher
from .models import Lead
from .normalize import dedupe_list, is_non_agency_domain, normalize_url, registered_domain

log = logging.getLogger(__name__)

# Crawl contact/about/team pages before generic "services" pages.
_PAGE_PRIORITY = ["contact", "تواصل", "اتصل", "about", "من-نحن", "من نحن", "team", "founder", "leadership", "فريق"]


def _priority(url: str) -> int:
    low = url.lower()
    for i, hint in enumerate(_PAGE_PRIORITY):
        if hint in low:
            return i
    return len(_PAGE_PRIORITY)


def enrich_from_website(lead: Lead, fetcher: Fetcher, max_pages: int = 6) -> Lead:
    if not lead.website or is_non_agency_domain(lead.website):
        return lead
    home = fetcher.get_html(lead.website)
    if home is None and lead.website.startswith("https://"):
        home = fetcher.get_html("http://" + lead.website[len("https://"):])
    if home is None:
        log.info("could not fetch %s", lead.website)
        lead.agency_name = lead.agency_name or _name_from_domain(lead.website)
        return lead

    final_url, html = home
    if not is_non_agency_domain(final_url):
        lead.website = normalize_url(final_url)
    pages = [parse_page(html, final_url)]

    queue = sorted(pages[0].links, key=_priority)
    if not any(_priority(u) < len(_PAGE_PRIORITY) for u in queue):
        queue += [urljoin(final_url, p) for p in FALLBACK_PATHS]
    seen = {final_url.rstrip("/")}
    for url in queue:
        if len(pages) >= max_pages:
            break
        if url.rstrip("/") in seen:
            continue
        seen.add(url.rstrip("/"))
        got = fetcher.get_html(url)
        if got:
            pages.append(parse_page(got[1], got[0]))

    _merge_pages(lead, pages)
    return lead


def _merge_pages(lead: Lead, pages) -> None:
    domain = registered_domain(lead.website)

    emails = dedupe_list(lead.emails + [e for p in pages for e in p.emails])
    # Addresses on the agency's own domain first, then generic mailboxes (gmail etc).
    emails.sort(key=lambda e: (registered_domain(e.split("@")[1]) != domain,))
    lead.emails = emails

    lead.phones = dedupe_list(lead.phones + [ph for p in pages for ph in p.phones])

    if not lead.linkedin_company_url:
        companies = [c for p in pages for c in p.linkedin_company]
        if companies:
            lead.linkedin_company_url = Counter(companies).most_common(1)[0][0]

    founders = [f for p in pages for f in p.founders]
    if founders and not lead.founder_name:
        founders.sort(key=lambda f: role_rank(f[1]))
        lead.founder_name, lead.founder_title = founders[0]
    people = dedupe_list([u for p in pages for u in p.linkedin_people])
    if lead.founder_name and not lead.founder_linkedin_url:
        lead.founder_linkedin_url = _match_person_url(lead.founder_name, people)

    lead.services = dedupe_list(lead.services + [s for p in pages for s in p.services])
    lead.categories = dedupe_list(
        lead.categories + [SERVICE_TO_CATEGORY[s] for s in lead.services if s in SERVICE_TO_CATEGORY]
    )

    city_counts: Counter = Counter()
    for p in pages:
        city_counts.update(p.city_counts)
    # Places gives a verified address city; for search/seed leads trust the site's own text.
    if city_counts and ("google_places" not in lead.sources or not lead.city):
        lead.city = city_counts.most_common(1)[0][0]
    lead.site_city_mentions = sum(city_counts.values())

    # Search-result titles are often SEO copy ("Best SEO Company in Riyadh"); the site's
    # own og:site_name / schema.org name is a better agency name. Places names are kept.
    site_name = pages[0].site_name
    from_search = bool(set(lead.sources) & {"brave", "serpapi"}) and "google_places" not in lead.sources
    if site_name and (not lead.agency_name or from_search):
        lead.agency_name = site_name
    lead.agency_name = lead.agency_name or _name_from_domain(lead.website)


def _name_from_domain(url: str) -> str:
    return registered_domain(url).split(".")[0].replace("-", " ").title()


def _match_person_url(name: str, urls: list[str]) -> str:
    """Pick the /in/ URL whose slug contains the person's first and last name."""
    parts = [p.lower() for p in name.split() if p.isascii() and len(p) > 1]
    for url in urls:
        slug = url.rsplit("/", 1)[-1].lower()
        if parts and parts[0] in slug and parts[-1].replace("al-", "") in slug:
            return url
    return ""
