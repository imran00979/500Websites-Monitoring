"""Runs checks for every site in parallel, on a fixed interval, and sends alerts."""

from __future__ import annotations

import logging
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

import requests
from requests.adapters import HTTPAdapter

from .checks import BLANK, OK, CheckResult, check_site, pick_status
from .store import Store

log = logging.getLogger(__name__)


@dataclass
class Settings:
    interval_min: float = 10.0
    workers: int = 50
    timeout: float = 15.0
    retries: int = 1
    keep_days: float = 7.0
    alert_after: int = 2          # consecutive failed runs before an alert
    webhook_url: str | None = None  # Slack / Discord / Teams-compatible {"text": ...}
    render_blank: bool = False    # re-check blank pages in headless Chromium (needs playwright)


class Monitor:
    def __init__(self, store: Store, settings: Settings):
        self.store = store
        self.settings = settings
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._run_lock = threading.Lock()
        self.running = False
        self.progress = (0, 0)
        self.next_run_at: float | None = None
        self.last_run_at: float | None = None
        self._session = requests.Session()
        adapter = HTTPAdapter(pool_connections=settings.workers * 2,
                              pool_maxsize=settings.workers * 2)
        self._session.mount("http://", adapter)
        self._session.mount("https://", adapter)

    # --- scheduling ------------------------------------------------------------
    def start(self) -> None:
        threading.Thread(target=self._loop, name="scheduler", daemon=True).start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()

    def trigger(self) -> bool:
        """Start a run now; False if one is already in progress."""
        if self.running:
            return False
        self._wake.set()
        return True

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.run_once()
            except Exception:  # never let one bad run kill the scheduler
                log.exception("Check run failed")
            self.next_run_at = time.time() + self.settings.interval_min * 60
            self._wake.wait(self.settings.interval_min * 60)
            self._wake.clear()

    # --- a run -----------------------------------------------------------------
    def run_once(self) -> dict[str, int]:
        with self._run_lock:
            self.running = True
            try:
                return self._run()
            finally:
                self.running = False

    def _run(self) -> dict[str, int]:
        sites = self.store.site_urls()
        run_id = self.store.start_run()
        self.progress = (0, len(sites))
        started = time.time()
        log.info("Checking %d sites with %d workers", len(sites), self.settings.workers)
        counts: Counter[str] = Counter()
        changes: list[tuple[CheckResult, dict]] = []
        deferred: dict[int, CheckResult] = {}

        def save(sid: int, res: CheckResult) -> None:
            changes.append((res, self.store.record(sid, run_id, res)))
            counts[res.status] += 1

        with ThreadPoolExecutor(max_workers=self.settings.workers) as pool:
            futures = {pool.submit(self._check, url): sid for sid, url in sites}
            for done, fut in enumerate(as_completed(futures), 1):
                res = fut.result()
                # Results are saved as they arrive so the dashboard fills in live;
                # blank JS-app pages wait for the browser re-check when it is enabled.
                if self.settings.render_blank and res.status == BLANK and res.js_shell:
                    deferred[futures[fut]] = res
                else:
                    save(futures[fut], res)
                self.progress = (done, len(sites))

        if deferred:
            self._confirm_blank_in_browser(list(deferred.values()))
            for sid, res in deferred.items():
                save(sid, res)
        self.store.finish_run(run_id, dict(counts))
        self.store.prune(self.settings.keep_days)
        self.last_run_at = time.time()
        log.info("Run finished in %.0fs: %s", time.time() - started, dict(counts))
        self._alert(changes)
        return dict(counts)

    def _check(self, url: str) -> CheckResult:
        try:
            return check_site(url, timeout=self.settings.timeout, retries=self.settings.retries,
                              session=self._session)
        except Exception as exc:  # a parser bug on one site must not stop the run
            log.exception("Checker crashed on %s", url)
            return CheckResult(url=url, status="down", detail=f"Checker error: {exc}")

    def _confirm_blank_in_browser(self, suspects: list[CheckResult]) -> None:
        from .render import rendered_text_lengths
        lengths = rendered_text_lengths([r.final_url or r.url for r in suspects],
                                        timeout=self.settings.timeout)
        for res in suspects:
            n = lengths.get(res.final_url or res.url)
            if n is not None and n >= 30:
                res.issues.remove(BLANK)
                res.status = pick_status(res.issues)
                if res.status == OK:
                    res.detail = ""
            elif n is not None:
                res.detail = f"Blank page: {n} characters after rendering in a browser"

    # --- alerts ----------------------------------------------------------------
    def _alert(self, changes: list[tuple[CheckResult, dict]]) -> None:
        if not self.settings.webhook_url:
            return
        need = self.settings.alert_after
        down = [r for r, i in changes if r.status != OK and i["fail_streak"] == need]
        recovered = [r for r, i in changes
                     if r.status == OK and i["previous"] not in (None, OK)]
        if not down and not recovered:
            return
        lines = []
        if down:
            lines.append(f":red_circle: {len(down)} site(s) failing:")
            lines += [f"• {r.url} — {r.status.replace('_', ' ')}: {r.detail}" for r in down[:50]]
        if recovered:
            lines.append(f":large_green_circle: {len(recovered)} site(s) recovered:")
            lines += [f"• {r.url}" for r in recovered[:50]]
        try:
            requests.post(self.settings.webhook_url, json={"text": "\n".join(lines),
                                                            "content": "\n".join(lines)[:1900]},
                          timeout=10)
        except requests.RequestException as exc:
            log.warning("Webhook failed: %s", exc)
