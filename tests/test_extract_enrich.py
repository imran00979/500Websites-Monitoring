from conftest import fixture

from leadgen.enrich import enrich_from_website
from leadgen.extract import canonical_city, detect_services, parse_page
from leadgen.models import Lead


def test_parse_home_page():
    data = parse_page(fixture("acme_home.html"), "https://acmedigital.com.sa/")
    assert data.site_name == "Acme Digital"
    assert "+966112345678" in data.phones          # JSON-LD
    assert "+966551234567" in data.phones          # tel: + wa.me, deduped
    assert data.linkedin_company == ["https://www.linkedin.com/company/acme-digital-sa"]
    assert {"SEO", "Digital Marketing", "Social Media Marketing", "Paid Advertising / PPC",
            "Web Design", "Branding"} <= set(data.services)
    assert data.city_counts["Riyadh"] >= 2
    assert "https://acmedigital.com.sa/contact" in data.links
    assert not any("other-site.com" in link for link in data.links)
    assert data.emails == []  # logo@2x.png is not an email


def test_parse_about_page_founder():
    data = parse_page(fixture("acme_about.html"), "https://acmedigital.com.sa/about-us")
    assert data.founders[0] == ("Khalid Al-Otaibi", "Founder & CEO")
    assert data.linkedin_people == ["https://www.linkedin.com/in/khalid-alotaibi-123"]


def test_parse_contact_page_emails_and_phones():
    data = parse_page(fixture("acme_contact.html"), "https://acmedigital.com.sa/contact")
    assert data.emails[0] == "info@acmedigital.com.sa"  # Cloudflare-protected
    assert "sales@acmedigital.com.sa" in data.emails
    assert "920012345" in data.phones
    assert "+966501112222" in data.phones


def test_arabic_page():
    data = parse_page(fixture("noor_about.html"), "https://noor-marketing.sa/من-نحن")
    assert data.founders[0][0] == "محمد عبدالله الغامدي"
    home = parse_page(fixture("noor_home.html"), "https://noor-marketing.sa/")
    assert home.phones == ["+966509876543"]
    assert home.emails == ["info@noor-marketing.sa"]
    assert {"Digital Marketing", "SEO", "Web Design", "Branding"} <= set(home.services)
    assert home.city_counts.most_common(1)[0][0] == "Jeddah"


def test_keyword_boundaries():
    assert "SEO" not in detect_services("we love seoul and museums")
    assert canonical_city("Shailene St, Riyadh") == "Riyadh"  # 'hail' inside a word ignored


def test_enrich_from_website(fetcher):
    lead = Lead(agency_name="Best SEO Company in Riyadh", website="https://acmedigital.com.sa",
                city="Jeddah", sources=["brave"], categories=["seo"])
    enrich_from_website(lead, fetcher)
    assert lead.agency_name == "Acme Digital"  # site's own name beats search title
    assert lead.city == "Riyadh"               # site text beats the query city
    assert lead.emails[:2] == ["info@acmedigital.com.sa", "sales@acmedigital.com.sa"]
    assert lead.emails[-1] == "acme.agency@gmail.com"
    assert lead.founder_name == "Khalid Al-Otaibi"
    assert lead.founder_linkedin_url == "https://www.linkedin.com/in/khalid-alotaibi-123"
    assert lead.linkedin_company_url == "https://www.linkedin.com/company/acme-digital-sa"
    assert {"seo", "digital_marketing", "web_development", "branding", "advertising"} <= set(lead.categories)
    # contact/about pages crawled before the services page
    assert fetcher.requested[1:3] == ["https://acmedigital.com.sa/contact",
                                      "https://acmedigital.com.sa/about-us"]


def test_enrich_unreachable_site_keeps_lead(fetcher):
    lead = Lead(agency_name="Ghost", website="https://ghost.sa", phones=["+966551112222"])
    enrich_from_website(lead, fetcher)
    assert lead.agency_name == "Ghost" and lead.phones == ["+966551112222"]
