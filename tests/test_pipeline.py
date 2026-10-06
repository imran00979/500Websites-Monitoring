import csv

from conftest import FakeSearch

from leadgen.dedupe import dedupe
from leadgen.export import read_csv, write_csv
from leadgen.linkedin import enrich_linkedin, name_matches
from leadgen.models import CSV_FIELDS, Lead
from leadgen.pipeline import RunConfig, run
from leadgen.sources.base import SearchResult
from leadgen.sources.google_places import GooglePlacesSource
from leadgen.sources.web_search import WebSearchSource


def test_dedupe_by_domain_phone_and_name():
    leads = [
        Lead(agency_name="Acme Digital", website="https://www.acmedigital.com.sa",
             sources=["brave"], categories=["seo"]),
        Lead(agency_name="ACME DIGITAL AGENCY", website="https://acmedigital.com.sa",
             phones=["+966551234567"], sources=["places"], address="Riyadh, Saudi Arabia",
             categories=["branding"]),
        Lead(agency_name="Acme (Instagram only)", phones=["+966551234567"], sources=["serpapi"]),
        Lead(agency_name="Acme Digital", website="https://acme-digital.ae"),  # different site
        Lead(agency_name="Noor", website="https://noor-marketing.sa"),
    ]
    out = dedupe(leads)
    assert len(out) == 3
    acme = out[0]
    assert acme.agency_name == "ACME DIGITAL AGENCY"  # Places name preferred
    assert acme.sources == ["brave", "places", "serpapi"]
    assert acme.categories == ["seo", "branding"]
    assert out[1].website == "https://acme-digital.ae"


def test_places_parsing():
    place = {
        "displayName": {"text": "Acme Digital"},
        "websiteUri": "https://www.acmedigital.com.sa/en",
        "internationalPhoneNumber": "+966 55 123 4567",
        "formattedAddress": "King Fahd Rd, Riyadh 12345, Saudi Arabia",
        "addressComponents": [{"longText": "Riyadh", "types": ["locality", "political"]}],
    }
    lead = GooglePlacesSource._to_lead(place, "Jeddah", "seo")
    assert lead.website == "https://acmedigital.com.sa"
    assert lead.city == "Riyadh" and lead.phones == ["+966551234567"]
    place["formattedAddress"] = "Dubai, United Arab Emirates"
    assert GooglePlacesSource._to_lead(place, "Jeddah", "seo") is None


def test_linkedin_lookup_via_search():
    engine = FakeSearch({
        "site:linkedin.com/company": [
            SearchResult("https://sa.linkedin.com/company/acme-pizza", "Acme Pizza | LinkedIn"),
            SearchResult("https://sa.linkedin.com/company/acme-digital-ksa", "Acme Digital | LinkedIn"),
        ],
        "site:linkedin.com/in": [
            SearchResult("https://sa.linkedin.com/in/random", "Someone - Founder - Other Co | LinkedIn"),
            SearchResult("https://sa.linkedin.com/in/fahad-q", "Fahad Al-Qahtani - Founder & CEO - Acme Digital | LinkedIn",
                         "Riyadh · Founder at Acme Digital"),
        ],
    })
    lead = Lead(agency_name="Acme Digital", website="https://acmedigital.com.sa")
    enrich_linkedin(lead, engine)
    assert lead.linkedin_company_url == "https://www.linkedin.com/company/acme-digital-ksa"
    assert lead.founder_name == "Fahad Al-Qahtani"
    assert lead.founder_title == "Founder & CEO"
    assert lead.founder_linkedin_url == "https://www.linkedin.com/in/fahad-q"
    assert not name_matches("Acme Digital", "Acme Pizza | LinkedIn")


def test_full_pipeline_to_csv(fetcher, tmp_path):
    engine = FakeSearch({
        "SEO agency Riyadh": [
            SearchResult("https://acmedigital.com.sa/", "Best SEO Company in Riyadh - Acme"),
            SearchResult("https://clutch.co/sa/seo", "Top SEO agencies"),        # directory: dropped
            SearchResult("https://noor-marketing.sa", "Noor Marketing"),
            SearchResult("https://ghost-agency.com", "Ghost Agency"),            # unreachable, no KSA evidence
        ],
        "digital marketing agency Riyadh": [
            SearchResult("https://www.acmedigital.com.sa/en", "Acme Digital"),   # duplicate
        ],
    })
    existing = [Lead(agency_name="Old Lead", website="https://old.sa", city="Dammam",
                     emails=["hi@old.sa"], sources=["seed"])]
    cfg = RunConfig(cities=["Riyadh"], categories=["seo", "digital_marketing"],
                    providers=[WebSearchSource(engine)], existing=existing,
                    arabic_queries=False, workers=2)
    leads = run(cfg, fetcher)
    names = [lead.agency_name for lead in leads]
    assert names == ["Old Lead", "نور للتسويق", "Acme Digital"]  # sorted by city: Dammam, Jeddah, Riyadh

    out = tmp_path / "leads.csv"
    write_csv(leads, str(out))
    with open(out, encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert list(rows[0].keys()) == CSV_FIELDS
    acme = rows[2]
    assert acme["website"] == "https://acmedigital.com.sa"
    assert acme["founder_name"] == "Khalid Al-Otaibi"
    assert acme["email"].startswith("info@acmedigital.com.sa; ")
    assert acme["city"] == "Riyadh"
    noor = rows[1]
    assert noor["founder_name"] == "محمد عبدالله الغامدي" and noor["city"] == "Jeddah"
    # round-trip so --existing works
    assert read_csv(str(out))[2].emails == leads[2].emails
