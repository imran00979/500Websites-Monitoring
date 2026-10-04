"""Normalisation helpers for URLs, domains, names, phones and emails."""

from __future__ import annotations

import re
import unicodedata
from urllib.parse import urlsplit, urlunsplit

from .config import NON_AGENCY_DOMAINS

_SECOND_LEVEL = {"com", "net", "org", "edu", "gov", "sch", "med", "co", "ac"}

_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


def to_ascii_digits(text: str) -> str:
    return text.translate(_ARABIC_DIGITS)


def normalize_url(url: str) -> str:
    """Return a canonical homepage-style URL (scheme + host, lower-case, no www)."""
    url = (url or "").strip()
    if not url:
        return ""
    if "://" not in url:
        url = "https://" + url
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if not host:
        return ""
    if host.startswith("www."):
        host = host[4:]
    scheme = parts.scheme if parts.scheme in ("http", "https") else "https"
    return urlunsplit((scheme, host, "", "", ""))


def registered_domain(url: str) -> str:
    """Best-effort registrable domain: 'https://www.foo.com.sa/x' -> 'foo.com.sa'."""
    if not url:
        return ""
    if "://" not in url:
        url = "https://" + url
    host = (urlsplit(url).hostname or "").lower().rstrip(".")
    labels = [label for label in host.split(".") if label]
    if len(labels) < 2:
        return host
    if len(labels) >= 3 and len(labels[-1]) == 2 and labels[-2] in _SECOND_LEVEL:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


def is_non_agency_domain(url: str) -> bool:
    domain = registered_domain(url)
    if domain in NON_AGENCY_DOMAINS:
        return True
    host = (urlsplit(url if "://" in url else "https://" + url).hostname or "").lower()
    return any(host == d or host.endswith("." + d) for d in NON_AGENCY_DOMAINS)


_LEGAL_WORDS = {
    "agency", "company", "co", "ltd", "llc", "inc", "est", "establishment", "group",
    "the", "for", "and", "&", "sa", "ksa", "saudi", "arabia", "limited",
    "شركة", "مؤسسة", "وكالة", "للتسويق", "المحدودة", "ذات", "مسؤولية",
}


def normalize_name(name: str) -> str:
    """Comparison key for an agency name (case/punctuation/legal-suffix insensitive)."""
    text = unicodedata.normalize("NFKC", name or "").lower()
    text = re.sub(r"[^\w\s&]", " ", text)
    words = [w for w in text.split() if w not in _LEGAL_WORDS]
    return " ".join(words)


def clean_name(name: str) -> str:
    """Tidy a display name taken from a page title or search result."""
    name = re.sub(r"\s+", " ", name or "").strip()
    # "Acme | Digital Marketing Agency in Riyadh" -> "Acme"
    for sep in (" | ", " – ", " — ", " - ", " :: ", " · "):
        if sep in name:
            name = name.split(sep)[0].strip()
    return name[:120]


# Saudi numbers: mobile +966 5XXXXXXXX, landline +966 1XXXXXXXX, unified 9200XXXXX,
# toll free 800XXXXXXX.
def normalize_phone(raw: str) -> str:
    """Return an E.164-style Saudi number, a unified/toll-free number, or '' if invalid."""
    digits = re.sub(r"\D", "", to_ascii_digits(raw or ""))
    if digits.startswith("00966"):
        digits = digits[2:]
    if digits.startswith("9660"):  # +966 (0)5x...
        digits = "966" + digits[4:]
    if digits.startswith("966"):
        national = digits[3:]
    elif digits.startswith("0") and len(digits) == 10:
        national = digits[1:]
    elif digits.startswith("9200") and len(digits) == 9:
        return digits
    elif digits.startswith("800") and len(digits) == 10:
        return digits
    elif len(digits) == 9 and digits.startswith("5"):
        national = digits
    else:
        return ""
    if len(national) != 9:
        return ""
    if national.startswith("5") or re.match(r"1[1-7]", national):
        return "+966" + national
    return ""


_BAD_EMAIL_PARTS = (
    "example.", "sentry", "wixpress", "domain.com", "email.com", "yourdomain", "yoursite",
    "@2x", "godaddy", "schema.org", "w3.org", "placeholder", "test@", "user@", "name@",
)
_BAD_EMAIL_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".css", ".js")


def normalize_email(raw: str) -> str:
    email = (raw or "").strip().strip(".,;:'\"<>()[]").lower()
    if email.startswith("mailto:"):
        email = email[7:].split("?")[0]
    if not re.fullmatch(r"[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}", email):
        return ""
    if email.endswith(_BAD_EMAIL_SUFFIXES) or any(p in email for p in _BAD_EMAIL_PARTS):
        return ""
    return email


def normalize_linkedin(url: str) -> str:
    """Canonical https://www.linkedin.com/company/<slug> or /in/<slug> URL, or ''."""
    m = re.search(r"linkedin\.com/(company|in|school)/([^/?#\s\"'<>]+)", url or "", re.I)
    if not m:
        return ""
    kind, slug = m.group(1).lower(), m.group(2)
    if kind == "school":
        kind = "company"
    return f"https://www.linkedin.com/{kind}/{slug.rstrip('.,')}"


def dedupe_list(items) -> list:
    seen, out = set(), []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out
