"""Find LinkedIn company pages and founder profiles via web search results.

LinkedIn itself is never fetched: its terms prohibit scraping. We only read the
URL, title and snippet that a search API returns for `site:linkedin.com/...`
queries, which is public search-engine data.
"""

from __future__ import annotations

import logging
import re
from difflib import SequenceMatcher

from .extract import ROLE_RE, _looks_like_name
from .models import Lead
from .normalize import normalize_linkedin, normalize_name, registered_domain
from .sources.base import WebSearch

log = logging.getLogger(__name__)


def _compact(text: str) -> str:
    return re.sub(r"[\W_]+", "", normalize_name(text))


def name_matches(agency: str, text: str, domain: str = "") -> bool:
    """Does `text` (a search title/slug) refer to the agency?"""
    a, t = _compact(agency), _compact(text)
    if not a or not t:
        return False
    if a in t:
        return True
    stem = _compact(domain.split(".")[0]) if domain else ""
    if len(stem) >= 4 and stem in t:
        return True
    head = _compact(re.split(r"\s[|\-–]\s", text)[0])
    return SequenceMatcher(None, a, head).ratio() >= 0.85


def find_company_page(engine: WebSearch, lead: Lead) -> str:
    domain = registered_domain(lead.website)
    for r in engine.search(f'site:linkedin.com/company "{lead.agency_name}"', 10):
        url = normalize_linkedin(r.url)
        if "/company/" not in url:
            continue
        slug = url.rsplit("/", 1)[-1].replace("-", " ")
        if name_matches(lead.agency_name, f"{r.title} {slug}", domain) or (
            domain and domain in r.snippet.lower()
        ):
            return url
    return ""


def _parse_profile_title(title: str) -> tuple[str, str]:
    """'Ahmed Ali - Founder & CEO - Acme | LinkedIn' -> ('Ahmed Ali', 'Founder & CEO - Acme')."""
    title = re.sub(r"\s*\|\s*LinkedIn.*$", "", title).strip()
    parts = re.split(r"\s+[-–—]\s+", title, maxsplit=1)
    name = parts[0].strip()
    rest = parts[1].strip() if len(parts) > 1 else ""
    return name, rest


def find_founder(engine: WebSearch, lead: Lead) -> tuple[str, str, str]:
    """Return (name, title, profile_url) for the agency's founder/owner, or blanks."""
    domain = registered_domain(lead.website)
    if lead.founder_name:
        query = f'site:linkedin.com/in "{lead.founder_name}" "{lead.agency_name}"'
    else:
        query = f'site:linkedin.com/in (founder OR owner OR CEO) "{lead.agency_name}" Saudi'
    for r in engine.search(query, 10):
        url = normalize_linkedin(r.url)
        if "/in/" not in url:
            continue
        name, headline = _parse_profile_title(r.title)
        context = f"{headline} {r.snippet}"
        if not name_matches(lead.agency_name, context, domain):
            continue
        if lead.founder_name:
            if _compact(lead.founder_name.split()[0]) in _compact(name):
                return lead.founder_name, lead.founder_title, url
            continue
        role = ROLE_RE.search(context)
        if role and _looks_like_name(name):
            return name, headline.split(" - ")[0][:60] or role.group(0), url
    return "", "", ""


def enrich_linkedin(lead: Lead, engine: WebSearch) -> Lead:
    if not lead.agency_name:
        return lead
    try:
        if not lead.linkedin_company_url:
            lead.linkedin_company_url = find_company_page(engine, lead)
        if not lead.founder_linkedin_url:
            name, title, url = find_founder(engine, lead)
            if url:
                lead.founder_name, lead.founder_title, lead.founder_linkedin_url = name, title, url
    except Exception as exc:  # a failed lookup should never lose the lead
        log.warning("linkedin lookup failed for %s: %s", lead.agency_name, exc)
    return lead
