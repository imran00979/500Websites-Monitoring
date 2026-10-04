"""SQLite storage for sites, check history and run summaries."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path

from .checks import OK, CheckResult, normalize_url

SCHEMA = """
CREATE TABLE IF NOT EXISTS sites (
    id INTEGER PRIMARY KEY,
    url TEXT NOT NULL UNIQUE,
    added_at REAL NOT NULL,
    last_status TEXT,
    last_code INTEGER,
    last_ms INTEGER,
    last_ip TEXT,
    last_detail TEXT,
    last_title TEXT,
    final_url TEXT,
    last_checked REAL,
    status_since REAL,
    fail_streak INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS checks (
    id INTEGER PRIMARY KEY,
    site_id INTEGER NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    run_id INTEGER,
    checked_at REAL NOT NULL,
    status TEXT NOT NULL,
    http_code INTEGER,
    response_ms INTEGER,
    detail TEXT
);
CREATE INDEX IF NOT EXISTS checks_site_time ON checks(site_id, checked_at);
CREATE INDEX IF NOT EXISTS checks_time ON checks(checked_at);
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY,
    started_at REAL NOT NULL,
    finished_at REAL,
    counts TEXT
);
"""

SITE_COLUMNS = ("id, url, last_status, last_code, last_ms, last_ip, last_detail, last_title, "
                "final_url, last_checked, status_since, fail_streak")


class Store:
    def __init__(self, path: str | Path):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(self.path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA foreign_keys=ON")
        self._db.executescript(SCHEMA)

    def _q(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._db.execute(sql, params).fetchall()

    def _w(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        with self._lock, self._db:
            return self._db.execute(sql, params)

    # --- sites -----------------------------------------------------------------
    def add_sites(self, lines: list[str]) -> tuple[int, list[str]]:
        """Add URLs (one per entry); returns (added count, rejected entries)."""
        added, rejected = 0, []
        now = time.time()
        with self._lock, self._db:
            for line in lines:
                for raw in line.replace(",", " ").split():
                    url = normalize_url(raw)
                    if not url:
                        if raw.strip() and not raw.startswith("#"):
                            rejected.append(raw)
                        continue
                    cur = self._db.execute(
                        "INSERT OR IGNORE INTO sites(url, added_at) VALUES (?, ?)", (url, now))
                    added += cur.rowcount
        return added, rejected

    def remove_site(self, site_id: int) -> bool:
        return self._w("DELETE FROM sites WHERE id = ?", (site_id,)).rowcount > 0

    def sites(self) -> list[dict]:
        rows = self._q(f"SELECT {SITE_COLUMNS} FROM sites ORDER BY url")
        return [dict(r) for r in rows]

    def site_urls(self) -> list[tuple[int, str]]:
        return [(r["id"], r["url"]) for r in self._q("SELECT id, url FROM sites ORDER BY id")]

    def site(self, site_id: int) -> dict | None:
        rows = self._q(f"SELECT {SITE_COLUMNS} FROM sites WHERE id = ?", (site_id,))
        return dict(rows[0]) if rows else None

    # --- checks ----------------------------------------------------------------
    def record(self, site_id: int, run_id: int | None, res: CheckResult) -> dict:
        """Store one result; returns {'previous': status, 'fail_streak': n}."""
        now = time.time()
        with self._lock, self._db:
            prev = self._db.execute(
                "SELECT last_status, status_since, fail_streak FROM sites WHERE id = ?",
                (site_id,)).fetchone()
            if prev is None:  # removed while the run was in flight
                return {"previous": None, "fail_streak": 0}
            since = prev["status_since"] if prev["last_status"] == res.status else now
            streak = 0 if res.status == OK else prev["fail_streak"] + 1
            self._db.execute(
                "INSERT INTO checks(site_id, run_id, checked_at, status, http_code, response_ms,"
                " detail) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (site_id, run_id, now, res.status, res.http_code, res.response_ms, res.detail))
            self._db.execute(
                "UPDATE sites SET last_status=?, last_code=?, last_ms=?, last_ip=?, last_detail=?,"
                " last_title=?, final_url=?, last_checked=?, status_since=?, fail_streak=?"
                " WHERE id=?",
                (res.status, res.http_code, res.response_ms, res.ip, res.detail, res.title,
                 res.final_url, now, since, streak, site_id))
        return {"previous": prev["last_status"], "fail_streak": streak}

    def history(self, site_id: int, limit: int = 100) -> list[dict]:
        rows = self._q(
            "SELECT checked_at, status, http_code, response_ms, detail FROM checks"
            " WHERE site_id = ? ORDER BY checked_at DESC LIMIT ?", (site_id, limit))
        return [dict(r) for r in rows]

    def recent_statuses(self, per_site: int = 24) -> dict[int, list[str]]:
        """Last N statuses per site, oldest first, for the dashboard's history strip."""
        rows = self._q(
            "SELECT site_id, status FROM (SELECT site_id, status, checked_at, ROW_NUMBER()"
            " OVER (PARTITION BY site_id ORDER BY checked_at DESC) AS rn FROM checks)"
            " WHERE rn <= ? ORDER BY site_id, checked_at", (per_site,))
        out: dict[int, list[str]] = {}
        for r in rows:
            out.setdefault(r["site_id"], []).append(r["status"])
        return out

    def uptime(self, since: float) -> dict[int, float]:
        rows = self._q(
            "SELECT site_id, AVG(status = 'ok') AS up FROM checks WHERE checked_at >= ?"
            " GROUP BY site_id", (since,))
        return {r["site_id"]: round(r["up"] * 100, 2) for r in rows}

    def prune(self, keep_days: float) -> int:
        cutoff = time.time() - keep_days * 86400
        n = self._w("DELETE FROM checks WHERE checked_at < ?", (cutoff,)).rowcount
        self._w("DELETE FROM runs WHERE started_at < ?", (cutoff,))
        return n

    # --- runs ------------------------------------------------------------------
    def start_run(self) -> int:
        return self._w("INSERT INTO runs(started_at) VALUES (?)", (time.time(),)).lastrowid

    def finish_run(self, run_id: int, counts: dict[str, int]) -> None:
        self._w("UPDATE runs SET finished_at = ?, counts = ? WHERE id = ?",
                (time.time(), json.dumps(counts), run_id))

    def runs(self, limit: int = 48) -> list[dict]:
        rows = self._q(
            "SELECT id, started_at, finished_at, counts FROM runs WHERE finished_at IS NOT NULL"
            " ORDER BY id DESC LIMIT ?", (limit,))
        return [{**dict(r), "counts": json.loads(r["counts"] or "{}")} for r in reversed(rows)]
