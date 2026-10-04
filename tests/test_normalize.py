import pytest

from leadgen.normalize import (
    clean_name,
    is_non_agency_domain,
    normalize_email,
    normalize_linkedin,
    normalize_name,
    normalize_phone,
    normalize_url,
    registered_domain,
)


@pytest.mark.parametrize("raw,expected", [
    ("+966 55 123 4567", "+966551234567"),
    ("00966551234567", "+966551234567"),
    ("+966 (0) 50 111 2222", "+966501112222"),
    ("055-123-4567", "+966551234567"),
    ("٠٥٠٩٨٧٦٥٤٣", "+966509876543"),
    ("011 234 5678", "+966112345678"),
    ("9200 12345", "920012345"),
    ("800 123 4567", "8001234567"),
    ("+971 4 123 4567", ""),   # UAE
    ("12345", ""),
    ("+966 9 1234 5678", ""),  # invalid prefix
])
def test_normalize_phone(raw, expected):
    assert normalize_phone(raw) == expected


def test_urls_and_domains():
    assert normalize_url("WWW.Acme.com.sa/en/contact?x=1") == "https://acme.com.sa"
    assert registered_domain("https://blog.acme.com.sa/x") == "acme.com.sa"
    assert registered_domain("https://www.acme.sa") == "acme.sa"
    assert registered_domain("https://sub.acme.io") == "acme.io"
    assert is_non_agency_domain("https://sa.linkedin.com/company/x")
    assert is_non_agency_domain("https://clutch.co/sa/agencies")
    assert not is_non_agency_domain("https://acme.com.sa")


def test_emails():
    assert normalize_email("mailto:Info@Acme.SA?subject=hi") == "info@acme.sa"
    assert normalize_email("logo@2x.png") == ""
    assert normalize_email("you@example.com") == ""
    assert normalize_email("not-an-email") == ""


def test_names_and_linkedin():
    assert normalize_name("Acme Digital Agency Co. Ltd") == normalize_name("ACME Digital")
    assert clean_name("Acme Digital | Best SEO Company in Riyadh") == "Acme Digital"
    assert normalize_linkedin("https://sa.linkedin.com/company/acme-sa/about/") == \
        "https://www.linkedin.com/company/acme-sa"
    assert normalize_linkedin("https://www.linkedin.com/in/khalid-123?trk=x") == \
        "https://www.linkedin.com/in/khalid-123"
    assert normalize_linkedin("https://acme.com") == ""
