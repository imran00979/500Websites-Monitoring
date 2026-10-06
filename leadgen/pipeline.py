"""Discover -> dedupe -> enrich (website, LinkedIn) -> filter -> dedupe -> export.

Work happens in batches: run queries until a batch of new unique candidates is
ready, enrich that batch, then check the stop condition. This lets a capped run
(test mode: 20 agencies) stop after a few queries instead of spending the
whole query plan's API quota, and lets large runs checkpoint their CSV.
"""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from .config import CATEGORIES
from .dedupe import LeadIndex, dedupe
from .enrich import enrich_from_website
from .http import Fetcher
from .linkedin import enrich_linkedin
from .models import Lead
from .normalize import registered_domain
from .sources.base import DiscoveryProvider, WebSearch

log = logging.getLogger(__name__)

TEST_MODE_AGENCIES = 20


@dataclass
class RunConfig:
    cities: list[str]
    categories: list[str]
    providers: list[DiscoveryProvider] = field(default_factory=list)
    seeds: list[Lead] = field(default_factory=list)
    existing: list[Lead] = field(default_factory=list)
    linkedin_engine: WebSearch | None = None
    max_pages: int = 6
    workers: int = 8
    max_agencies: int = 0      # stop once this many new Saudi agencies are kept (0 = no cap)
    strict: bool = False
    arabic_queries: bool = True


@dataclass
class RunStats:
    queries: int = 0
    candidates: int = 0
    enriched: int = 0
    per_provider: Counter = field(default_factory=Counter)
    stopped_early: bool = False


def query_plan(cfg: RunConfig) -> Iterator[tuple[str, str, str]]:
    """(phrase, city, category) in an order that spreads early results.

    Consecutive queries rotate through categories, then cities, then phrasings,
    so a small test run already samples every category and several cities.
    """
    phrase_lists = {
        c: [p for p in CATEGORIES[c] if cfg.arabic_queries or p.isascii()] for c in cfg.categories
    }
    rounds = max((len(v) for v in phrase_lists.values()), default=0)
    for i in range(rounds):
        for city in cfg.cities:
            for category in cfg.categories:
                if i < len(phrase_lists[category]):
                    yield phrase_lists[category][i], city, category


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


def _finalize(cfg: RunConfig, enriched: list[Lead]) -> list[Lead]:
    new = [lead for lead in dedupe(enriched) if is_relevant(lead, cfg.strict)]
    if cfg.max_agencies:
        new = new[: cfg.max_agencies]
    # Previously exported leads go first so their data is kept and extended.
    final = [lead for lead in dedupe(cfg.existing + new) if is_relevant(lead, cfg.strict)]
    final.sort(key=lambda lead: (lead.city or "~", lead.agency_name.lower()))
    return final


def run(
    cfg: RunConfig,
    fetcher: Fetcher,
    progress: Callable[[str], None] | None = None,
    checkpoint: Callable[[list[Lead]], None] | None = None,
    stats: RunStats | None = None,
) -> list[Lead]:
    stats = stats if stats is not None else RunStats()
    say = progress or (lambda msg: None)
    batch_size = max(cfg.workers * 2, 10)
    if cfg.max_agencies:
        batch_size = min(batch_size, cfg.max_agencies)

    index = LeadIndex()           # every candidate seen so far, deduplicated
    for lead in cfg.existing:     # don't re-enrich agencies already in the old CSV
        index.add(lead)
    pending: list[Lead] = []
    enriched: list[Lead] = []

    def add_candidates(leads: list[Lead]) -> None:
        for lead in leads:
            stats.candidates += 1
            merged, is_new = index.add(lead)
            if is_new:
                pending.append(merged)

    def kept_count() -> int:
        return sum(1 for lead in dedupe(list(enriched)) if is_relevant(lead, cfg.strict))

    def enrich_batch(batch: list[Lead]) -> None:
        def work(lead: Lead) -> Lead:
            enrich_from_website(lead, fetcher, cfg.max_pages)
            if cfg.linkedin_engine:
                enrich_linkedin(lead, cfg.linkedin_engine)
            return lead

        with ThreadPoolExecutor(max_workers=cfg.workers) as pool:
            for lead in pool.map(_safe(work), batch):
                if lead is not None:
                    enriched.append(lead)
        stats.enriched += len(batch)

    def done() -> bool:
        return bool(cfg.max_agencies) and kept_count() >= cfg.max_agencies

    add_candidates(cfg.seeds)
    plan = query_plan(cfg)
    plan_exhausted = not cfg.providers
    while True:
        # 1) Run queries until a batch of new candidates is ready. When capped, only
        #    gather as many as are still needed, so no quota is spent past the cap.
        wanted = batch_size
        if cfg.max_agencies:
            wanted = max(1, min(batch_size, cfg.max_agencies - kept_count()))
        while not plan_exhausted and len(pending) < wanted:
            try:
                phrase, city, category = next(plan)
            except StopIteration:
                plan_exhausted = True
                break
            for provider in cfg.providers:
                try:
                    found = provider.discover(phrase, city, category)
                except Exception as exc:  # one failing provider must not stop the run
                    log.warning("%s failed for %r/%s: %s", provider.name, phrase, city, exc)
                    continue
                stats.queries += 1
                stats.per_provider[provider.name] += len(found)
                add_candidates(found)

        if not pending:
            break
        # 2) Enrich the batch.
        batch, pending[:] = pending[:wanted], pending[wanted:]
        enrich_batch(batch)
        say(f"queries run: {stats.queries}  candidates: {len(index)}  "
            f"enriched: {stats.enriched}  kept: {kept_count()}")
        if checkpoint:
            checkpoint(_finalize(cfg, enriched))
        # 3) Stop as soon as the cap is reached.
        if done():
            stats.stopped_early = not plan_exhausted or bool(pending)
            break

    return _finalize(cfg, enriched)


def _safe(fn):
    def wrapper(lead):
        try:
            return fn(lead)
        except Exception as exc:
            log.warning("enrichment failed for %s: %s", lead.website or lead.agency_name, exc)
            return lead
    return wrapper
