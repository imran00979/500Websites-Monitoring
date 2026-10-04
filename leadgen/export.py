"""CSV import/export."""

from __future__ import annotations

import csv
from pathlib import Path

from .models import CSV_FIELDS, Lead


def write_csv(leads: list[Lead], path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    # utf-8-sig so Excel shows Arabic names correctly.
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for lead in leads:
            writer.writerow(lead.to_row())


def read_csv(path: str) -> list[Lead]:
    with open(path, newline="", encoding="utf-8-sig") as fh:
        return [Lead.from_row(row) for row in csv.DictReader(fh)]
