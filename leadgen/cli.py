"""Command-line entry point: python -m leadgen --help"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from .config import CATEGORIES, CITIES, DEFAULT_CITIES
from .export import read_csv, write_csv
from .http import Fetcher
from .pipeline import TEST_MODE_AGENCIES, RunConfig, RunStats, run
from .sources import ProviderConfigError, ProviderSettings, build, load_seeds, status_table
from .sources.registry import LINKEDIN_PROVIDER_ENV, PROVIDERS, PROVIDERS_ENV

DEFAULT_OUT = "output/saudi_agencies.csv"
TEST_OUT = "output/test_run.csv"
DEMO_OUT = "output/demo_run.csv"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="leadgen",
        description="Find marketing / web / SEO / branding / advertising agencies in Saudi Arabia "
        "and export deduplicated leads to CSV.",
        epilog=f"Providers: {', '.join(PROVIDERS)}. API keys are read from environment variables "
        "(or a .env file); run --list-providers to see which are configured.",
    )
    p.add_argument("-o", "--out", help=f"CSV output path (default: {DEFAULT_OUT}; "
                                         f"{TEST_OUT} with --test, {DEMO_OUT} with --demo)")
    p.add_argument("--cities", nargs="+", default=DEFAULT_CITIES, metavar="CITY",
                   help=f"cities to search (default: {' '.join(DEFAULT_CITIES)}). "
                        f"Known: {', '.join(CITIES)}; 'all' for every known city")
    p.add_argument("--categories", nargs="+", default=list(CATEGORIES), choices=list(CATEGORIES),
                   help="agency categories to search (default: all)")

    g = p.add_argument_group("providers")
    g.add_argument("--providers", help=f"comma list of discovery providers, 'auto' (every configured "
                                       f"one) or 'none'. Default: ${PROVIDERS_ENV}, else auto")
    g.add_argument("--linkedin-provider", help=f"search provider for LinkedIn lookups (brave, serpapi), "
                                               f"'auto' or 'none'. Default: ${LINKEDIN_PROVIDER_ENV}, else auto")
    g.add_argument("--no-linkedin", action="store_true", help="same as --linkedin-provider none")
    g.add_argument("--list-providers", action="store_true", help="show providers and their configuration, then exit")
    g.add_argument("--env-file", default=".env", help="file of KEY=value lines to load (default: .env)")

    g = p.add_argument_group("run size")
    g.add_argument("--test", action="store_true",
                   help=f"small trial: stop after {TEST_MODE_AGENCIES} Saudi agencies, with small "
                        "per-query result sizes to save API quota")
    g.add_argument("--max-agencies", type=int, help=f"stop after N new Saudi agencies; 0 = no cap "
                                                    f"(default: {TEST_MODE_AGENCIES} with --test/--demo, else no cap)")
    g.add_argument("--demo", action="store_true",
                   help="offline demo on built-in fictional agencies (no API keys or network needed)")

    g = p.add_argument_group("input and filtering")
    g.add_argument("--seeds", help="file of agency URLs (.txt, one per line) or .csv with a website column")
    g.add_argument("--existing", help="previous CSV to merge into (new results are deduplicated against it)")
    g.add_argument("--english-only", action="store_true", help="skip Arabic search phrases")
    g.add_argument("--strict", action="store_true", help="keep only agencies whose website lists a target service")

    g = p.add_argument_group("crawling")
    g.add_argument("--max-pages", type=int, default=6, help="pages to crawl per agency site")
    g.add_argument("--workers", type=int, default=8, help="parallel website crawls")
    g.add_argument("--delay", type=float, default=1.0, help="seconds between requests to one host")
    g.add_argument("--cache-dir", default=".cache", help="HTTP cache directory ('' to disable)")
    g.add_argument("--ignore-robots", action="store_true", help="do not honour robots.txt")
    p.add_argument("-v", "--verbose", action="store_true")
    return p


def load_env_file(path: str, env: dict) -> list[str]:
    """Load KEY=value lines into env without overriding variables already set."""
    loaded = []
    p = Path(path)
    if not p.is_file():
        return loaded
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.removeprefix("export ").split("=", 1)
        key, value = key.strip(), value.strip().strip("'\"")
        if key and key not in env:
            env[key] = value
            loaded.append(key)
    return loaded


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(levelname)s %(name)s: %(message)s")
    load_env_file(args.env_file, os.environ)

    if args.list_providers:
        print("Providers:\n" + status_table(os.environ))
        print(f"\nSelect with --providers or {PROVIDERS_ENV}; LinkedIn engine with "
              f"--linkedin-provider or {LINKEDIN_PROVIDER_ENV}.")
        return 0

    cities = list(CITIES) if [c.lower() for c in args.cities] == ["all"] else args.cities
    if args.max_agencies is not None:
        max_agencies = args.max_agencies
    else:
        max_agencies = TEST_MODE_AGENCIES if args.test or args.demo else 0
    small = args.test or args.demo
    settings = ProviderSettings(results_per_query=10, map_pages=1) if small else ProviderSettings()
    out = args.out or (DEMO_OUT if args.demo else TEST_OUT if args.test else DEFAULT_OUT)

    if args.demo:
        from .demo import DemoFetcher, demo_providers
        fetcher = DemoFetcher()
        providers, linkedin = demo_providers(settings)
        selected = ["demo_maps", "demo_search"]
        if args.no_linkedin:
            linkedin = None
    else:
        fetcher = Fetcher(delay=args.delay, cache_dir=args.cache_dir or None,
                          respect_robots=not args.ignore_robots)
        try:
            setup = build(fetcher, os.environ, providers=args.providers,
                          linkedin="none" if args.no_linkedin else args.linkedin_provider,
                          settings=settings)
        except ProviderConfigError as exc:
            print(f"error: {exc}\n\nRun with --list-providers to see what is configured.", file=sys.stderr)
            return 2
        providers, linkedin, selected = setup.discovery, setup.linkedin, setup.selected

    seeds = load_seeds(args.seeds) if args.seeds else []
    existing = read_csv(args.existing) if args.existing and os.path.exists(args.existing) else []
    if not providers and not seeds:
        print("error: no discovery provider configured.\n\nSet an API key (e.g. GOOGLE_PLACES_API_KEY) "
              "in the environment or a .env file, pass --seeds FILE, or try --demo.\n\n"
              + status_table(os.environ), file=sys.stderr)
        return 2

    mode = "DEMO (fictional data)" if args.demo else "TEST" if args.test else "FULL"
    print(f"Mode: {mode}{f' - stops after {max_agencies} agencies' if max_agencies else ''}\n"
          f"Discovery: {', '.join(selected) or 'seeds only'} | "
          f"LinkedIn: {getattr(linkedin, 'name', 'off')}\n"
          f"Cities: {', '.join(cities)} | Categories: {', '.join(args.categories)}", file=sys.stderr)

    cfg = RunConfig(
        cities=cities, categories=args.categories, providers=providers, seeds=seeds,
        existing=existing, linkedin_engine=linkedin, max_pages=args.max_pages,
        workers=args.workers, max_agencies=max_agencies, strict=args.strict,
        arabic_queries=not args.english_only,
    )
    stats = RunStats()
    leads = run(
        cfg, fetcher,
        progress=lambda msg: print("  " + msg, file=sys.stderr),
        # Large runs checkpoint after every batch so an interruption loses little.
        checkpoint=None if max_agencies else (lambda partial: write_csv(partial, out)),
        stats=stats,
    )
    write_csv(leads, out)
    print_summary(leads, out, stats, fetcher, mode)
    return 0


def print_summary(leads, out, stats, fetcher, mode) -> None:
    def count(attr):
        return sum(1 for lead in leads if getattr(lead, attr))
    print(f"\nWrote {len(leads)} agencies to {out}")
    print(f"  with email: {count('emails')}  phone: {count('phones')}  "
          f"LinkedIn page: {count('linkedin_company_url')}  founder: {count('founder_name')}  "
          f"founder LinkedIn: {count('founder_linkedin_url')}")
    print(f"  queries: {stats.queries}  candidates found: {stats.candidates}  "
          f"sites enriched: {stats.enriched}"
          + ("  (stopped early at the agency cap)" if stats.stopped_early else ""))
    if stats.per_provider:
        print("  candidates per provider: " + ", ".join(f"{k} {v}" for k, v in stats.per_provider.items()))
    if fetcher.api_calls:
        print("  paid API requests: " + ", ".join(f"{h} {n}" for h, n in fetcher.api_calls.items()))
    if mode == "TEST":
        print("\nReview the CSV. If the quality looks right, run again without --test for the full search.")
