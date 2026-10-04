"""Command line: `serve` runs the scheduler and dashboard, `check` runs once and prints."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from concurrent.futures import ThreadPoolExecutor

from .checks import OK, check_site, normalize_url
from .monitor import Monitor, Settings
from .server import serve
from .store import Store


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m webmonitor", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("serve", help="check sites on a schedule and serve the dashboard")
    s.add_argument("--sites", help="text/CSV file of URLs to import at start (one per line)")
    s.add_argument("--db", default=os.environ.get("MONITOR_DB", "data/monitor.db"))
    s.add_argument("--host", default="127.0.0.1", help="use 0.0.0.0 to expose on the network")
    s.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8080)))
    s.add_argument("--interval", type=float, default=10, help="minutes between runs (default 10)")
    s.add_argument("--workers", type=int, default=50, help="parallel checks (default 50)")
    s.add_argument("--timeout", type=float, default=15, help="seconds per request (default 15)")
    s.add_argument("--keep-days", type=float, default=7, help="history retention (default 7)")
    s.add_argument("--alert-after", type=int, default=2,
                   help="consecutive failed runs before a webhook alert (default 2)")
    s.add_argument("--webhook", default=os.environ.get("MONITOR_WEBHOOK"),
                   help="Slack/Discord/Teams webhook URL for alerts")
    s.add_argument("--password", default=os.environ.get("MONITOR_PASSWORD"),
                   help="require HTTP Basic auth (any username) for the dashboard")
    s.add_argument("--render-blank", action="store_true",
                   help="re-check blank JavaScript pages in headless Chromium (needs playwright)")

    c = sub.add_parser("check", help="check URLs once and print results")
    c.add_argument("urls", nargs="*", help="URLs to check")
    c.add_argument("--sites", help="file of URLs")
    c.add_argument("--workers", type=int, default=50)
    c.add_argument("--timeout", type=float, default=15)
    c.add_argument("--json", action="store_true", help="print JSON lines")

    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("urllib3").setLevel(logging.ERROR)

    if args.cmd == "check":
        return _check(args)

    store = Store(args.db)
    if args.sites:
        with open(args.sites, encoding="utf-8-sig") as fh:
            added, rejected = store.add_sites(_url_lines(fh.read()))
        logging.info("Imported %d new sites from %s (%d rejected)", added, args.sites, len(rejected))
    settings = Settings(interval_min=args.interval, workers=args.workers, timeout=args.timeout,
                        keep_days=args.keep_days, alert_after=args.alert_after,
                        webhook_url=args.webhook, render_blank=args.render_blank)
    monitor = Monitor(store, settings)
    monitor.start()
    serve(store, monitor, args.host, args.port, args.password)
    return 0


def _url_lines(text: str) -> list[str]:
    """Accept plain lists or CSVs: keep the first cell that looks like a URL/domain."""
    out = []
    for line in text.splitlines():
        cells = [c.strip().strip('"') for c in line.split(",")]
        url = next((c for c in cells if "." in c and " " not in c), None)
        if url:
            out.append(url)
    return out


def _check(args) -> int:
    urls = list(args.urls)
    if args.sites:
        with open(args.sites, encoding="utf-8-sig") as fh:
            urls += _url_lines(fh.read())
    urls = [u for u in (normalize_url(x) for x in urls) if u]
    if not urls:
        print("No URLs given", file=sys.stderr)
        return 2
    bad = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for res in pool.map(lambda u: check_site(u, timeout=args.timeout), urls):
            bad += res.status != OK
            if args.json:
                print(json.dumps(res.to_dict()))
            else:
                code = res.http_code or "-"
                ms = f"{res.response_ms}ms" if res.response_ms is not None else "-"
                print(f"{res.status:<15} {code!s:<4} {ms:>7}  {res.url}  {res.detail}")
    return 1 if bad else 0
