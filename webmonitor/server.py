"""Dashboard web server: static page plus a small JSON API (standard library only)."""

from __future__ import annotations

import base64
import csv
import hmac
import io
import json
import logging
import re
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .checks import STATUSES
from .monitor import Monitor
from .store import Store

log = logging.getLogger(__name__)
STATIC = Path(__file__).parent / "static"


def make_handler(store: Store, monitor: Monitor, password: str | None):
    class Handler(BaseHTTPRequestHandler):
        server_version = "WebsiteMonitor/1.0"

        def log_message(self, fmt, *args):
            log.debug("%s %s", self.address_string(), fmt % args)

        # --- plumbing ----------------------------------------------------------
        def _authorized(self) -> bool:
            if not password:
                return True
            header = self.headers.get("Authorization", "")
            if header.startswith("Basic "):
                try:
                    _, _, given = base64.b64decode(header[6:]).decode().partition(":")
                except ValueError:
                    return False
                return hmac.compare_digest(given, password)
            return False

        def _send(self, code: int, body: bytes, ctype: str, extra: dict | None = None):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _json(self, data, code: int = 200):
            self._send(code, json.dumps(data).encode(), "application/json")

        def _body(self) -> dict:
            n = int(self.headers.get("Content-Length") or 0)
            if not n:
                return {}
            try:
                return json.loads(self.rfile.read(min(n, 5_000_000)))
            except ValueError:
                return {}

        def _guard(self) -> bool:
            if self._authorized():
                return True
            self._send(401, b"Authentication required", "text/plain",
                       {"WWW-Authenticate": 'Basic realm="Website Monitor"'})
            return False

        # --- routes ------------------------------------------------------------
        def do_GET(self):
            if not self._guard():
                return
            path = self.path.split("?", 1)[0]
            if path in ("/", "/index.html"):
                self._send(200, (STATIC / "index.html").read_bytes(), "text/html; charset=utf-8")
            elif path == "/api/state":
                self._json(state(store, monitor))
            elif m := re.fullmatch(r"/api/sites/(\d+)/history", path):
                self._json(store.history(int(m.group(1))))
            elif path == "/api/export.csv":
                self._send(200, export_csv(store), "text/csv; charset=utf-8",
                           {"Content-Disposition": 'attachment; filename="website-status.csv"'})
            else:
                self._send(404, b"Not found", "text/plain")

        def do_POST(self):
            if not self._guard():
                return
            if self.path == "/api/check-now":
                self._json({"started": monitor.trigger()})
            elif self.path == "/api/sites":
                text = str(self._body().get("urls", ""))
                added, rejected = store.add_sites(text.splitlines())
                self._json({"added": added, "rejected": rejected[:50]})
            else:
                self._send(404, b"Not found", "text/plain")

        def do_DELETE(self):
            if not self._guard():
                return
            if m := re.fullmatch(r"/api/sites/(\d+)", self.path):
                self._json({"removed": store.remove_site(int(m.group(1)))})
            else:
                self._send(404, b"Not found", "text/plain")

    return Handler


def state(store: Store, monitor: Monitor) -> dict:
    sites = store.sites()
    recent = store.recent_statuses(24)
    uptime = store.uptime(time.time() - 86400)
    for s in sites:
        s["recent"] = recent.get(s["id"], [])
        s["uptime_24h"] = uptime.get(s["id"])
    done, total = monitor.progress
    return {
        "sites": sites,
        "runs": store.runs(48),
        "statuses": STATUSES,
        "running": monitor.running,
        "progress": {"done": done, "total": total},
        "last_run_at": monitor.last_run_at,
        "next_run_at": monitor.next_run_at,
        "interval_min": monitor.settings.interval_min,
        "server_time": time.time(),
    }


def export_csv(store: Store) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["url", "status", "http_code", "response_ms", "ip", "detail", "final_url",
                "last_checked_utc", "status_since_utc"])
    iso = lambda t: datetime.fromtimestamp(t, timezone.utc).isoformat(timespec="seconds") if t else ""
    for s in store.sites():
        w.writerow([s["url"], s["last_status"] or "pending", s["last_code"] or "", s["last_ms"] or "",
                    s["last_ip"] or "", s["last_detail"] or "", s["final_url"] or "",
                    iso(s["last_checked"]), iso(s["status_since"])])
    return ("﻿" + buf.getvalue()).encode("utf-8")


def serve(store: Store, monitor: Monitor, host: str, port: int, password: str | None) -> None:
    httpd = ThreadingHTTPServer((host, port), make_handler(store, monitor, password))
    log.info("Dashboard on http://%s:%d", "localhost" if host in ("0.0.0.0", "") else host, port)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        monitor.stop()
        httpd.server_close()
