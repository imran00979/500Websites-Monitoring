"""Data model for an agency lead and its CSV representation."""

from __future__ import annotations

from dataclasses import dataclass, field

CSV_FIELDS = [
    "agency_name",
    "website",
    "city",
    "linkedin_company_url",
    "founder_name",
    "founder_title",
    "founder_linkedin_url",
    "email",
    "phone",
    "services",
    "categories",
    "address",
    "sources",
]

LIST_SEP = "; "


@dataclass
class Lead:
    agency_name: str = ""
    website: str = ""
    city: str = ""
    linkedin_company_url: str = ""
    founder_name: str = ""
    founder_title: str = ""
    founder_linkedin_url: str = ""
    emails: list[str] = field(default_factory=list)
    phones: list[str] = field(default_factory=list)
    services: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    address: str = ""
    sources: list[str] = field(default_factory=list)
    # Free text gathered during discovery (search snippets, Places types) that
    # helps classify the lead but is not exported.
    snippet: str = ""
    # Number of Saudi city mentions found on the agency's own website.
    site_city_mentions: int = 0

    def to_row(self) -> dict[str, str]:
        return {
            "agency_name": self.agency_name,
            "website": self.website,
            "city": self.city,
            "linkedin_company_url": self.linkedin_company_url,
            "founder_name": self.founder_name,
            "founder_title": self.founder_title,
            "founder_linkedin_url": self.founder_linkedin_url,
            "email": LIST_SEP.join(self.emails),
            "phone": LIST_SEP.join(self.phones),
            "services": LIST_SEP.join(self.services),
            "categories": LIST_SEP.join(self.categories),
            "address": self.address,
            "sources": LIST_SEP.join(self.sources),
        }

    @classmethod
    def from_row(cls, row: dict[str, str]) -> "Lead":
        def split(key: str) -> list[str]:
            return [v.strip() for v in (row.get(key) or "").split(";") if v.strip()]

        return cls(
            agency_name=row.get("agency_name", ""),
            website=row.get("website", ""),
            city=row.get("city", ""),
            linkedin_company_url=row.get("linkedin_company_url", ""),
            founder_name=row.get("founder_name", ""),
            founder_title=row.get("founder_title", ""),
            founder_linkedin_url=row.get("founder_linkedin_url", ""),
            emails=split("email"),
            phones=split("phone"),
            services=split("services"),
            categories=split("categories"),
            address=row.get("address", ""),
            sources=split("sources"),
        )
