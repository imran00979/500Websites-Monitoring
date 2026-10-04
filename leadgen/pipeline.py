"""Discover -> dedupe -> enrich (website, LinkedIn) -> filter -> dedupe -> export."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

from .config import CATEGORIES
from .dedupe import dedupe
from .enrich import enrich_from_website
from .http import Fetcher
from .linkedin import enrich_linkedin
from .models import Lead
from .normalize import registered_domain
from .sources.base import WebSearch

log = logging.getLogger(__name__)


@dataclass
class RunConfig:
    cities: list[str]
    categories: list[str]
    sources: list = field(default_factory=list)      # objects with .discover()
    seeds: list[Lead] = field(default_factory=list)
    existing: list[Lead] = field(default_factory=list)
    linkedin_engine: WebSearch | None = None
    max_pages: int = 6
    workers: int = 8
    limit: int = 0
    strict: bool = False
    arabic_queries: bool = True


def discover(cfg: RunConfig) -> list[Lead]:
    leads: list[Lead] = list(cfg.seeds)
    for category in cfg.categories:
        phrases = CATEGORIES[category]
        if not cfg.arabic_queries:
            phrases = [p for p in phrases if p.isascii()]
        for city in cfg.cities:
            for phrase in phrases:
                for source in cfg.sources:
                    try:
                        leads += source.discover(phrase, city, category)
                    except Exception as exc:
                        log.warning("%s failed for %r/%s: %s", source.name, phrase, city, exc)
    return leads


def has_saudi_evidence(lead: Lead) -> bool:
    return (
        registered_domain(lead.website).endswith(".sa")
        or any(p.startswith(("+966", "9200", "800")) for p in lead.phones)
        or "saudi" in lead.address.lower()
        or "السعودية" in lead.address
        or lead.site_city_mentions > 0
    )


def is_relevant(lead: Lead, strict: bool) -> bool:
    if not lead.agency_name or not (lead.website or lead.phones or lead.emails):
        return False
    if not has_saudi_evidence(lead):
        return False
    # Strict mode: the agency's own site must advertise one of the target services.
    return bool(lead.services) if strict else True


def run(cfg: RunConfig, fetcher: Fetcher, progress=None) -> list[Lead]:
    raw = discover(cfg)
    log.info("discovered %d raw leads", len(raw))
    leads = dedupe(raw)
    log.info("%d unique leads after first dedupe", len(leads))
    if cfg.limit:
        leads = leads[: cfg.limit]

    def work(lead: Lead) -> Lead:
        enrich_from_website(lead, fetcher, cfg.max_pages)
        if cfg.linkedin_engine:
            enrich_linkedin(lead, cfg.linkedin_engine)
        return lead

    done: list[Lead] = []
    with ThreadPoolExecutor(max_workers=cfg.workers) as pool:
        futures = [pool.submit(work, lead) for lead in leads]
        for n, fut in enumerate(as_completed(futures), 1):
            try:
                done.append(fut.result())
            except Exception as exc:
                log.warning("enrichment failed: %s", exc)
            if progress:
                progress(n, len(leads))

    # Previously exported leads are merged first so their data is kept and extended.
    final = dedupe(cfg.existing + done)
    final = [lead for lead in final if is_relevant(lead, cfg.strict)]
    final.sort(key=lambda lead: (lead.city or "~", lead.agency_name.lower()))
    return final
