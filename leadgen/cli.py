"""Command-line entry point: python -m leadgen --help"""

from __future__ import annotations

import argparse
import logging
import os
import sys

from .config import CATEGORIES, CITIES, DEFAULT_CITIES
from .export import read_csv, write_csv
from .http import Fetcher
from .pipeline import RunConfig, run
from .sources import BraveSearch, GooglePlacesSource, SerpApiSearch, WebSearchSource, load_seeds


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="leadgen",
        description="Find marketing / web / SEO / branding / advertising agencies in Saudi Arabia "
        "and export deduplicated leads to CSV.",
    )
    p.add_argument("-o", "--out", default="output/saudi_agencies.csv", help="CSV output path")
    p.add_argument("--cities", nargs="+", default=DEFAULT_CITIES, metavar="CITY",
                   help=f"cities to search (default: {' '.join(DEFAULT_CITIES)}). "
                        f"Known: {', '.join(CITIES)}; 'all' for every known city")
    p.add_argument("--categories", nargs="+", default=list(CATEGORIES), choices=list(CATEGORIES),
                   help="agency categories to search (default: all)")
    p.add_argument("--sources", default="auto",
                   help="comma list of places,brave,serpapi (default: every source with an API key)")
    p.add_argument("--seeds", help="file of agency URLs (.txt, one per line) or .csv with a website column")
    p.add_argument("--existing", help="previous CSV to merge into (new results are deduplicated against it)")
    p.add_argument("--no-linkedin", action="store_true", help="skip LinkedIn company/founder lookups")
    p.add_argument("--english-only", action="store_true", help="skip Arabic search phrases")
    p.add_argument("--strict", action="store_true",
                   help="keep only agencies whose website lists a target service")
    p.add_argument("--limit", type=int, default=0, help="enrich at most N unique leads (0 = no limit)")
    p.add_argument("--max-pages", type=int, default=6, help="pages to crawl per agency site")
    p.add_argument("--workers", type=int, default=8, help="parallel website crawls")
    p.add_argument("--delay", type=float, default=1.0, help="seconds between requests to one host")
    p.add_argument("--cache-dir", default=".cache", help="HTTP cache directory ('' to disable)")
    p.add_argument("--ignore-robots", action="store_true", help="do not honour robots.txt")
    p.add_argument("-v", "--verbose", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(levelname)s %(name)s: %(message)s")

    cities = list(CITIES) if [c.lower() for c in args.cities] == ["all"] else args.cities
    fetcher = Fetcher(delay=args.delay, cache_dir=args.cache_dir or None,
                      respect_robots=not args.ignore_robots)

    keys = {
        "places": os.environ.get("GOOGLE_PLACES_API_KEY"),
        "brave": os.environ.get("BRAVE_API_KEY"),
        "serpapi": os.environ.get("SERPAPI_API_KEY"),
    }
    wanted = [k for k in keys if keys[k]] if args.sources == "auto" else [
        s.strip() for s in args.sources.split(",") if s.strip()
    ]
    sources, engines = [], []
    for name in wanted:
        if name not in keys:
            sys.exit(f"unknown source {name!r}; choose from places, brave, serpapi")
        if not keys[name]:
            sys.exit(f"source {name!r} needs its API key env var (see README)")
        if name == "places":
            sources.append(GooglePlacesSource(keys[name], fetcher))
        else:
            engine = (BraveSearch if name == "brave" else SerpApiSearch)(keys[name], fetcher)
            engines.append(engine)
            sources.append(WebSearchSource(engine))

    seeds = load_seeds(args.seeds) if args.seeds else []
    existing = read_csv(args.existing) if args.existing and os.path.exists(args.existing) else []
    if not sources and not seeds:
        sys.exit("No discovery source configured. Set GOOGLE_PLACES_API_KEY, BRAVE_API_KEY or "
                 "SERPAPI_API_KEY, or pass --seeds FILE.")

    linkedin_engine = None if args.no_linkedin or not engines else engines[0]
    if not args.no_linkedin and not engines:
        print("note: LinkedIn lookups need BRAVE_API_KEY or SERPAPI_API_KEY; only links found on "
              "agency websites will be used.", file=sys.stderr)

    cfg = RunConfig(
        cities=cities, categories=args.categories, sources=sources, seeds=seeds, existing=existing,
        linkedin_engine=linkedin_engine, max_pages=args.max_pages, workers=args.workers,
        limit=args.limit, strict=args.strict, arabic_queries=not args.english_only,
    )

    def progress(n: int, total: int) -> None:
        print(f"\renriching {n}/{total}", end="", file=sys.stderr, flush=True)

    leads = run(cfg, fetcher, progress=progress)
    print(file=sys.stderr)
    write_csv(leads, args.out)

    def count(attr):
        return sum(1 for lead in leads if getattr(lead, attr))
    print(f"Wrote {len(leads)} agencies to {args.out}\n"
          f"  with email: {count('emails')}  phone: {count('phones')}  "
          f"LinkedIn page: {count('linkedin_company_url')}  founder: {count('founder_name')}  "
          f"founder LinkedIn: {count('founder_linkedin_url')}")
    return 0
