"""Extract contact details, founder, services and city from an agency web page."""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from .config import CITIES, INTERESTING_PAGE_HINTS, SERVICES
from .normalize import (
    clean_name,
    dedupe_list,
    normalize_email,
    normalize_linkedin,
    normalize_phone,
    registered_domain,
    to_ascii_digits,
)

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(
    r"(?:\+|00)\s?966[\s\-().]*\d(?:[\s\-().]*\d){7,9}"  # international
    r"|\b0[1-9](?:[\s\-]?\d){8}\b"                        # 05x / 01x national
    r"|\b9200(?:[\s\-]?\d){5}\b"                          # unified number
    r"|\b800(?:[\s\-]?\d){7}\b"                           # toll free
)

ROLE_RE = re.compile(
    r"\b(co-?\s?founder|founder|owner|ceo|chief executive officer|managing director|"
    r"managing partner|general manager)\b"
    r"|المؤسس|مؤسس|الشريك المؤسس|الرئيس التنفيذي|المدير التنفيذي|المدير العام|المالك",
    re.I,
)
# Ranking: a founder/owner beats a CEO beats a general manager.
_ROLE_RANK = [
    ("founder", 0), ("مؤسس", 0), ("owner", 1), ("المالك", 1), ("ceo", 2),
    ("chief executive", 2), ("الرئيس التنفيذي", 2), ("المدير التنفيذي", 2),
    ("managing", 3), ("general manager", 4), ("المدير العام", 4),
]
EN_NAME = r"[A-Z][a-zA-Z'\-]+(?:\s+(?:Al-|El-|al-|bin\s|ibn\s)?[A-Z][a-zA-Z'\-]+){1,3}"
AR_NAME = r"[ء-ي]{2,}(?:\s+[ء-ي]{2,}){1,3}"
_NOT_NAMES = {
    "our team", "about us", "contact us", "meet the team", "read more", "learn more",
    "saudi arabia", "digital marketing", "our services", "the founder", "our founder",
}


@dataclass
class PageData:
    emails: list[str] = field(default_factory=list)
    phones: list[str] = field(default_factory=list)
    linkedin_company: list[str] = field(default_factory=list)
    linkedin_people: list[str] = field(default_factory=list)
    founders: list[tuple[str, str]] = field(default_factory=list)  # (name, title)
    services: list[str] = field(default_factory=list)
    city_counts: Counter = field(default_factory=Counter)
    site_name: str = ""
    links: list[str] = field(default_factory=list)  # same-site pages worth crawling


def parse_page(html: str, page_url: str) -> PageData:
    soup = BeautifulSoup(html, "html.parser")
    data = PageData()

    _decode_cloudflare_emails(soup)
    jsonld = _jsonld_objects(soup)
    hrefs = [a.get("href", "") for a in soup.find_all("a", href=True)]

    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    text = to_ascii_digits(soup.get_text(" ", strip=True))
    lower_text = text.lower()

    # Emails: mailto links first (most reliable), then visible text, then JSON-LD.
    emails = [normalize_email(h) for h in hrefs if h.lower().startswith("mailto:")]
    emails += [normalize_email(e) for e in EMAIL_RE.findall(text)]
    emails += [normalize_email(o.get("email", "")) for o in jsonld if isinstance(o.get("email"), str)]
    data.emails = dedupe_list(emails)

    # Phones: tel: links, then text, then JSON-LD telephone.
    phones = [normalize_phone(h[4:]) for h in hrefs if h.lower().startswith("tel:")]
    phones += [normalize_phone(h) for h in hrefs if "wa.me/" in h or "api.whatsapp.com" in h]
    phones += [normalize_phone(m) for m in PHONE_RE.findall(text)]
    phones += [normalize_phone(str(o.get("telephone", ""))) for o in jsonld]
    data.phones = dedupe_list(phones)

    # LinkedIn links on the agency's own site.
    sameas = []
    for o in jsonld:
        same = o.get("sameAs") or []
        sameas += same if isinstance(same, list) else [same]
    for href in hrefs + [s for s in sameas if isinstance(s, str)]:
        li = normalize_linkedin(href)
        if "/company/" in li:
            data.linkedin_company.append(li)
        elif "/in/" in li:
            data.linkedin_people.append(li)
    data.linkedin_company = dedupe_list(data.linkedin_company)
    data.linkedin_people = dedupe_list(data.linkedin_people)

    data.founders = dedupe_list(_founders_from_jsonld(jsonld) + _founders_from_html(soup))
    data.services = detect_services(lower_text)
    data.city_counts = count_cities(lower_text)
    data.site_name = _site_name(soup, jsonld)
    data.links = _interesting_links(soup, page_url)
    return data


# -- services / cities -------------------------------------------------------

def _keyword_re(keyword: str) -> re.Pattern:
    if re.search(r"[a-z]", keyword):
        return re.compile(r"(?<![a-z0-9])" + re.escape(keyword) + r"(?![a-z0-9])")
    return re.compile(re.escape(keyword))


_SERVICE_RES = {s: [_keyword_re(k) for k in kws] for s, kws in SERVICES.items()}
_CITY_RES = {c: [_keyword_re(v) for v in vs] for c, vs in CITIES.items()}


def detect_services(lower_text: str) -> list[str]:
    return [s for s, regs in _SERVICE_RES.items() if any(r.search(lower_text) for r in regs)]


def count_cities(lower_text: str) -> Counter:
    counts: Counter = Counter()
    for city, regs in _CITY_RES.items():
        n = sum(len(r.findall(lower_text)) for r in regs)
        if n:
            counts[city] = n
    return counts


def canonical_city(text: str) -> str:
    counts = count_cities((text or "").lower())
    return counts.most_common(1)[0][0] if counts else ""


# -- founders ----------------------------------------------------------------

def role_rank(title: str) -> int:
    low = title.lower()
    for key, rank in _ROLE_RANK:
        if key in low:
            return rank
    return 9


def _looks_like_name(text: str) -> bool:
    text = text.strip()
    if not text or len(text) > 50 or text.lower() in _NOT_NAMES or ROLE_RE.search(text):
        return False
    return bool(re.fullmatch(EN_NAME, text) or re.fullmatch(AR_NAME, text))


def _founders_from_jsonld(objs: list[dict]) -> list[tuple[str, str]]:
    out = []
    for o in objs:
        founders = o.get("founder") or []
        for f in founders if isinstance(founders, list) else [founders]:
            name = f.get("name") if isinstance(f, dict) else f
            if isinstance(name, str) and name.strip():
                out.append((name.strip(), "Founder"))
    return out


def _founders_from_html(soup: BeautifulSoup) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    # 1) Team cards: a short element holding the role, with the name in a nearby element.
    for el in soup.find_all(string=ROLE_RE):
        role = " ".join(el.split())
        if len(role) > 60:
            continue
        node = el.parent
        candidates = []
        for sib in list(node.find_previous_siblings(limit=2)) + list(node.find_next_siblings(limit=1)):
            candidates.append(sib.get_text(" ", strip=True))
        if node.parent is not None:
            for heading in node.parent.find_all(["h2", "h3", "h4", "h5", "strong", "b"], limit=3):
                candidates.append(heading.get_text(" ", strip=True))
        for cand in candidates:
            # "Ahmed Ali, Founder" in one element
            cand = re.split(r"\s*[,|–\-]\s*(?=\S*\s*(?:co-?founder|founder|ceo|owner))", cand, flags=re.I)[0]
            if _looks_like_name(cand):
                found.append((cand.strip(), _title_case_role(role)))
                break
    # 2) Inline prose: "Ahmed Al-Harbi, Founder & CEO" / "Founder: Ahmed Al-Harbi".
    text = soup.get_text(" ", strip=True)
    role_words = r"(?:Co-?\s?Founder|Founder|CEO|Owner|Managing Director)(?:\s*(?:&|and)\s*(?:CEO|Founder|Managing Director))?"
    for m in re.finditer(rf"({EN_NAME})\s*[,–\-|]\s*(?:our\s+|the\s+)?({role_words})", text):
        if _looks_like_name(m.group(1)):
            found.append((m.group(1), m.group(2)))
    for m in re.finditer(rf"({role_words})\s*(?:[:–\-]|is|,)\s*({EN_NAME})", text):
        if _looks_like_name(m.group(2)):
            found.append((m.group(2), m.group(1)))
    for m in re.finditer(rf"(المؤسس|مؤسس الشركة|الرئيس التنفيذي|المدير العام)\s*[:\-–]?\s*(?:الأستاذ|الاستاذ|م\.|د\.)?\s*({AR_NAME})", text):
        name = " ".join(m.group(2).split()[:3])
        found.append((name, m.group(1)))
    found.sort(key=lambda f: role_rank(f[1]))
    return found


def _title_case_role(role: str) -> str:
    m = ROLE_RE.search(role)
    if not m:
        return role
    # Keep the whole short role string ("Founder & CEO"), trimmed of punctuation.
    return role.strip(" :-–|,")[:60]


# -- misc --------------------------------------------------------------------

def _decode_cloudflare_emails(soup: BeautifulSoup) -> None:
    """Cloudflare 'email protection' hides addresses in a hex XOR blob."""
    for el in soup.select("[data-cfemail]"):
        try:
            blob = bytes.fromhex(el["data-cfemail"])
            email = "".join(chr(b ^ blob[0]) for b in blob[1:])
        except (ValueError, IndexError):
            continue
        el.replace_with(email)
    for a in soup.find_all("a", href=re.compile(r"/cdn-cgi/l/email-protection#")):
        try:
            blob = bytes.fromhex(a["href"].split("#", 1)[1])
            a["href"] = "mailto:" + "".join(chr(b ^ blob[0]) for b in blob[1:])
        except (ValueError, IndexError):
            continue


def _jsonld_objects(soup: BeautifulSoup) -> list[dict]:
    objs: list[dict] = []

    def walk(node):
        if isinstance(node, dict):
            objs.append(node)
            for v in node.values():
                if isinstance(v, (dict, list)):
                    walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    for script in soup.find_all("script", type="application/ld+json"):
        try:
            walk(json.loads(script.string or ""))
        except (json.JSONDecodeError, TypeError):
            continue
    return objs


def _site_name(soup: BeautifulSoup, jsonld: list[dict]) -> str:
    for o in jsonld:
        types = o.get("@type")
        types = types if isinstance(types, list) else [types]
        if any(t in ("Organization", "LocalBusiness", "ProfessionalService", "Corporation") for t in types):
            if isinstance(o.get("name"), str) and o["name"].strip():
                return clean_name(o["name"])
    meta = soup.find("meta", property="og:site_name")
    if meta and meta.get("content", "").strip():
        return clean_name(meta["content"])
    if soup.title and soup.title.string:
        return clean_name(soup.title.string)
    return ""


def _interesting_links(soup: BeautifulSoup, page_url: str) -> list[str]:
    domain = registered_domain(page_url)
    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        full = urljoin(page_url, href).split("#")[0]
        if registered_domain(full) != domain or urlsplit(full).scheme not in ("http", "https"):
            continue
        hay = (href + " " + a.get_text(" ", strip=True)).lower()
        if any(h in hay for h in INTERESTING_PAGE_HINTS):
            links.append(full)
    return dedupe_list(links)
