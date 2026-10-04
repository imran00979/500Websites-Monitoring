"""Load a user-supplied list of agency websites (one URL per line, or a CSV)."""

from __future__ import annotations

import csv
from pathlib import Path

from ..models import Lead
from ..normalize import normalize_url


def load_seeds(path: str) -> list[Lead]:
    p = Path(path)
    text = p.read_text(encoding="utf-8-sig")
    leads: list[Lead] = []
    if p.suffix.lower() == ".csv":
        for row in csv.DictReader(text.splitlines()):
            row = {k.strip().lower(): (v or "").strip() for k, v in row.items() if k}
            url = row.get("website") or row.get("url") or ""
            if url:
                leads.append(Lead(
                    agency_name=row.get("agency_name") or row.get("name") or "",
                    website=normalize_url(url),
                    city=row.get("city", ""),
                    sources=["seed"],
                ))
    else:
        for line in text.splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                leads.append(Lead(website=normalize_url(line), sources=["seed"]))
    return [lead for lead in leads if lead.website]
