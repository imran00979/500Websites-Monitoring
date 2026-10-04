"""Single-site health check: DNS, reachability, HTTP status and page-content errors."""

from __future__ import annotations

import re
import socket
import time
from dataclasses import asdict, dataclass, field
from urllib.parse import urlsplit

import requests
import urllib3
from bs4 import BeautifulSoup

# After a certificate failure the page is re-fetched unverified on purpose; don't warn about it.
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

USER_AGENT = "Mozilla/5.0 (compatible; WebsiteMonitor/1.0; uptime check)"
MAX_BODY_BYTES = 2_000_000

# Status codes, most severe first. The first matching one becomes the site's status.
OK = "ok"
DNS_ERROR = "dns_error"
DOWN = "down"
SSL_ERROR = "ssl_error"
DB_ERROR = "db_error"
HTTP_500 = "http_500"
SERVER_ERROR = "server_error"      # 501-599
INTERNAL_ERROR = "internal_error"  # page shows a fatal/internal error without a 500 status
NOT_FOUND = "not_found"
HTTP_ERROR = "http_error"          # other 4xx, redirect loops
BLANK = "blank"

STATUSES = [DNS_ERROR, DOWN, DB_ERROR, HTTP_500, SERVER_ERROR, INTERNAL_ERROR,
            NOT_FOUND, BLANK, SSL_ERROR, HTTP_ERROR, OK]

# "Strong" patterns are specific enough to trust anywhere in the visible text.
# "Weak" ones only count on short pages, so a blog post about SQL is not an outage.
DB_STRONG = [
    r"Error establishing a database connection",
    r"A Database Error Occurred",
    r"Database connection error \(\d+\)",
]
DB_WEAK = [
    r"SQLSTATE\[\w+\]",
    r"\bmysqli?_(?:p?connect|query)\(",
    r"Too many connections",
    r"Access denied for user '",
    r"Unable to connect to (?:the )?database",
    r"could not connect to server",
    r"\bPDOException\b",
    r"\bORA-\d{5}\b",
    r"Unknown database '",
    r"Database Error",
    r"MongoNetworkError|ECONNREFUSED 127\.0\.0\.1:(?:3306|5432|27017)",
]
INTERNAL_STRONG = [
    r"There has been a critical error on (?:this|your) website",
    r"(?:Fatal|Parse) error: .{0,400}? on line \d+",
    r"Whoops, looks like something went wrong",
    r"Server Error in '/' Application",
    r"An error occurred in the application and your page could not be served",
]
INTERNAL_WEAK = [
    r"Internal Server Error",
    r"HTTP ERROR 500",
    r"Traceback \(most recent call last\)",
    r"Uncaught (?:Error|Exception)",
]
SOFT_404_TITLE = re.compile(r"\b404\b|page not found|not found", re.I)
WEAK_MAX_TEXT = 3000
BLANK_MAX_TEXT = 30


@dataclass
class CheckResult:
    url: str
    status: str = OK
    http_code: int | None = None
    response_ms: int | None = None
    ip: str | None = None
    final_url: str | None = None
    title: str | None = None
    detail: str = ""
    issues: list[str] = field(default_factory=list)
    js_shell: bool = False  # blank page that loads scripts: may render client-side

    def to_dict(self) -> dict:
        return asdict(self)


def normalize_url(raw: str) -> str | None:
    raw = raw.strip()
    if not raw or raw.startswith("#"):
        return None
    if "://" not in raw:
        raw = "https://" + raw
    parts = urlsplit(raw)
    host = parts.hostname or ""
    if parts.scheme.lower() not in ("http", "https") or ("." not in host and host != "localhost"):
        return None
    path = parts.path or "/"
    query = f"?{parts.query}" if parts.query else ""
    return f"{parts.scheme.lower()}://{parts.netloc.lower()}{path}{query}"


def resolve_dns(host: str) -> str:
    """Return the first IP for host, raising socket.gaierror on failure."""
    infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    return infos[0][4][0]


def _first_match(patterns: list[str], text: str) -> str | None:
    for pat in patterns:
        m = re.search(pat, text, re.I | re.S)
        if m:
            return m.group(0)[:120]
    return None


def analyze_html(html: str) -> dict:
    """Extract what the classifier needs from a page body."""
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    has_scripts = bool(soup.find("script", src=True)) or len(soup.find_all("script")) > 0
    for tag in soup(["script", "style", "noscript", "template", "head"]):
        tag.decompose()
    text = " ".join(soup.get_text(" ").split())
    media = soup.find(["img", "svg", "video", "canvas", "iframe", "picture", "object", "embed", "form"])
    return {"title": title, "text": text, "has_media": media is not None, "has_scripts": has_scripts}


def classify(code: int, html: str, result: CheckResult) -> None:
    """Fill status/issues on result from an HTTP status code and page body."""
    page = analyze_html(html) if html else {"title": "", "text": "", "has_media": False,
                                            "has_scripts": False}
    result.title = page["title"][:200] or None
    text = page["text"]
    # Raw HTML too: PHP errors are sometimes printed inside <head> or before <html>.
    haystack = f"{page['title']} {text} {html[:20000] if code >= 500 else ''}"
    short = len(text) <= WEAK_MAX_TEXT

    db = _first_match(DB_STRONG, haystack) or (short and _first_match(DB_WEAK, haystack))
    internal = _first_match(INTERNAL_STRONG, haystack) or (
        short and _first_match(INTERNAL_WEAK, haystack))

    if db:
        result.issues.append(DB_ERROR)
        result.detail = f"Database error on page: “{db}”"
    if code == 500:
        result.issues.append(HTTP_500)
        result.detail = result.detail or "HTTP 500 Internal Server Error"
    elif 500 < code < 600:
        result.issues.append(SERVER_ERROR)
        result.detail = result.detail or f"HTTP {code} server error"
    if internal and code < 500:
        result.issues.append(INTERNAL_ERROR)
        result.detail = result.detail or f"Error shown on page: “{internal}”"
    if code == 404 or code == 410:
        result.issues.append(NOT_FOUND)
        result.detail = result.detail or f"HTTP {code} Not Found"
    elif code < 400 and short and SOFT_404_TITLE.search(page["title"] or ""):
        result.issues.append(NOT_FOUND)
        result.detail = result.detail or f"Soft 404: title “{page['title'][:80]}”"
    elif 400 <= code < 500:
        result.issues.append(HTTP_ERROR)
        result.detail = result.detail or f"HTTP {code}"
    if code < 400 and len(text) < BLANK_MAX_TEXT and not page["has_media"]:
        result.issues.append(BLANK)
        result.js_shell = page["has_scripts"]
        what = "no visible content" if not html.strip() else f"only {len(text)} characters of text"
        hint = " (JavaScript app shell: may render in a browser)" if result.js_shell else ""
        result.detail = result.detail or f"Blank page: {what}{hint}"

    result.status = pick_status(result.issues)


def pick_status(issues: list[str]) -> str:
    for status in STATUSES:
        if status in issues:
            return status
    return OK


def check_site(url: str, timeout: float = 15.0, retries: int = 1,
               session: requests.Session | None = None) -> CheckResult:
    result = CheckResult(url=url)
    host = urlsplit(url).hostname or ""

    try:
        result.ip = resolve_dns(host)
    except (socket.gaierror, UnicodeError) as exc:
        result.issues.append(DNS_ERROR)
        result.status = DNS_ERROR
        result.detail = f"DNS lookup failed for {host}: {exc}"
        return result

    sess = session or requests.Session()
    headers = {"User-Agent": USER_AGENT, "Accept": "text/html,*/*;q=0.8",
               "Accept-Language": "en;q=0.9,*;q=0.5"}
    verify = True
    attempt = 0
    while True:
        start = time.monotonic()
        try:
            with sess.get(url, headers=headers, timeout=timeout, allow_redirects=True,
                          stream=True, verify=verify) as resp:
                body = resp.raw.read(MAX_BODY_BYTES, decode_content=True) or b""
                result.response_ms = int((time.monotonic() - start) * 1000)
                result.http_code = resp.status_code
                result.final_url = resp.url
                encoding = resp.encoding or resp.apparent_encoding or "utf-8"
                ctype = resp.headers.get("Content-Type", "")
                html = body.decode(encoding, errors="replace") if (
                    "html" in ctype or "text" in ctype or not ctype) else "<img>"
            break
        except requests.exceptions.SSLError as exc:
            if verify:
                # Record the certificate problem, then look at the page anyway.
                result.issues.append(SSL_ERROR)
                result.detail = f"SSL certificate problem: {_short_exc(exc)}"
                verify = False
                continue
            return _fail(result, DOWN, f"TLS handshake failed: {_short_exc(exc)}")
        except requests.exceptions.TooManyRedirects:
            return _fail(result, HTTP_ERROR, "Redirect loop (too many redirects)")
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout,
                requests.exceptions.ChunkedEncodingError) as exc:
            if attempt < retries:
                attempt += 1
                time.sleep(2)
                continue
            kind = "Timed out" if isinstance(exc, requests.exceptions.Timeout) else "Connection failed"
            return _fail(result, DOWN, f"{kind}: {_short_exc(exc)}")
        except requests.exceptions.RequestException as exc:
            return _fail(result, DOWN, f"Request failed: {_short_exc(exc)}")

    ssl_detail = result.detail
    result.detail = ""
    classify(result.http_code, html, result)
    if SSL_ERROR in result.issues and result.status == SSL_ERROR:
        result.detail = ssl_detail
    elif SSL_ERROR in result.issues:
        result.detail += f" · {ssl_detail}"
    return result


def _fail(result: CheckResult, status: str, detail: str) -> CheckResult:
    result.issues.append(status)
    result.status = pick_status(result.issues)
    result.detail = detail
    return result


def _short_exc(exc: Exception) -> str:
    msg = str(exc)
    for marker in ("Caused by ", "reason: "):
        if marker in msg:
            msg = msg.split(marker, 1)[1]
    return re.sub(r"\s+", " ", msg)[:200]
