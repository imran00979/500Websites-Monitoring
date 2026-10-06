"""Polite HTTP client: robots.txt, per-host rate limiting, optional disk cache."""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from collections import Counter
from pathlib import Path
from urllib import robotparser
from urllib.parse import urlsplit

import requests

log = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (compatible; AgencyLeadFinder/1.0; business-contact research)"


class Fetcher:
    def __init__(
        self,
        delay: float = 1.0,
        timeout: float = 15.0,
        cache_dir: str | None = None,
        respect_robots: bool = True,
        session: requests.Session | None = None,
    ):
        self.delay = delay
        self.timeout = timeout
        self.respect_robots = respect_robots
        self.session = session or requests.Session()
        self.session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept-Language": "en,ar;q=0.8",
        })
        self.cache_dir = Path(cache_dir) if cache_dir else None
        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._robots: dict[str, robotparser.RobotFileParser | None] = {}
        self._last_hit: dict[str, float] = {}
        self._lock = threading.Lock()
        # Non-cached API requests per host, so runs can report quota usage.
        self.api_calls: Counter = Counter()

    # -- politeness -------------------------------------------------------
    def _wait_for_host(self, host: str) -> None:
        with self._lock:
            now = time.monotonic()
            ready_at = self._last_hit.get(host, 0.0) + self.delay
            self._last_hit[host] = max(now, ready_at)
        if ready_at > now:
            time.sleep(ready_at - now)

    def allowed(self, url: str) -> bool:
        if not self.respect_robots:
            return True
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin not in self._robots:
            parser = robotparser.RobotFileParser()
            try:
                resp = self.session.get(origin + "/robots.txt", timeout=self.timeout)
                if resp.status_code >= 400:
                    parser = None  # no robots.txt -> everything allowed
                else:
                    parser.parse(resp.text.splitlines())
            except requests.RequestException:
                parser = None
            self._robots[origin] = parser
        parser = self._robots[origin]
        return parser is None or parser.can_fetch(USER_AGENT, url)

    # -- caching ----------------------------------------------------------
    def _cache_path(self, key: str) -> Path | None:
        if not self.cache_dir:
            return None
        return self.cache_dir / (hashlib.sha256(key.encode()).hexdigest() + ".json")

    def _cache_get(self, key: str):
        path = self._cache_path(key)
        if path and path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return None

    def _cache_put(self, key: str, value) -> None:
        path = self._cache_path(key)
        if path:
            path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")

    # -- public API -------------------------------------------------------
    def get_html(self, url: str) -> tuple[str, str] | None:
        """Fetch a web page. Returns (final_url, html) or None."""
        cached = self._cache_get("page:" + url)
        if cached is not None:
            return (cached["url"], cached["html"]) if cached else None
        if not self.allowed(url):
            log.info("robots.txt disallows %s", url)
            return None
        self._wait_for_host(urlsplit(url).netloc)
        try:
            resp = self.session.get(url, timeout=self.timeout, allow_redirects=True)
        except requests.RequestException as exc:
            log.info("fetch failed %s: %s", url, exc)
            return None
        ctype = resp.headers.get("Content-Type", "")
        if resp.status_code != 200 or ("html" not in ctype and ctype):
            self._cache_put("page:" + url, {})
            return None
        resp.encoding = resp.encoding or resp.apparent_encoding
        result = {"url": resp.url, "html": resp.text}
        self._cache_put("page:" + url, result)
        return result["url"], result["html"]

    def api_json(self, method: str, url: str, *, cache: bool = True, **kwargs) -> dict | None:
        """Call a JSON API (no robots.txt check, still cached and rate-limited)."""
        key = "api:" + method + url + json.dumps(
            {k: v for k, v in kwargs.items() if k != "headers"}, sort_keys=True, default=str
        )
        if cache:
            cached = self._cache_get(key)
            if cached is not None:
                return cached
        host = urlsplit(url).netloc
        self._wait_for_host(host)
        with self._lock:
            self.api_calls[host] += 1
        try:
            resp = self.session.request(method, url, timeout=self.timeout, **kwargs)
        except requests.RequestException as exc:
            log.warning("API request failed %s: %s", url, exc)
            return None
        if resp.status_code != 200:
            log.warning("API %s returned %s: %s", url, resp.status_code, resp.text[:300])
            return None
        data = resp.json()
        if cache:
            self._cache_put(key, data)
        return data
