"""Offline demo: fictional agencies, their websites, and fake map/search providers.

`python -m leadgen --demo` runs the real pipeline (discovery, dedupe, website
crawl, LinkedIn lookup, filtering, CSV export) against this data, with no API
keys and no network. Every agency, person, domain, email and phone number
here is invented; the `.demo` domains do not exist.

The data deliberately includes the messy cases a real run meets: the same
agency found by both providers under slightly different names, a directory
listing, a non-Saudi agency, a dead website, a listing without a website,
Cloudflare-protected emails and a founder only findable through search.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .config import CATEGORIES
from .http import Fetcher
from .models import Lead
from .normalize import normalize_phone, normalize_url
from .sources.base import ProviderSettings, SearchResult
from .sources.web_search import WebSearchSource


@dataclass
class DemoAgency:
    name: str
    domain: str
    city: str
    phone: str
    email: str
    categories: list[str]
    services: str                      # sentence placed on the homepage
    founder: str = ""
    founder_title: str = "Founder & CEO"
    lang: str = "en"
    maps_name: str = ""                # name as the map listing shows it ('' = not on maps)
    in_search: bool = True
    linkedin_on_site: bool = True      # company LinkedIn linked from the site
    founder_profile_on_site: bool = False
    founder_only_on_linkedin: bool = False  # founder not on site, found via search
    cloudflare_email: bool = False
    site_up: bool = True
    has_website: bool = True
    district: str = ""
    extra_emails: list[str] = field(default_factory=list)

    @property
    def url(self) -> str:
        return f"https://{self.domain}"

    @property
    def slug(self) -> str:
        return self.domain.split(".")[0]


DM, WD, SEO, BR, AD = "digital_marketing", "web_development", "seo", "branding", "advertising"

AGENCIES: list[DemoAgency] = [
    DemoAgency("Nakhla Digital", "nakhla-digital.demo", "Riyadh", "+966 55 000 1101", "hello@nakhla-digital.demo",
               [DM, SEO], "We deliver SEO, social media marketing and Google Ads campaigns for Saudi brands.",
               founder="Faisal Al-Harbi", maps_name="Nakhla Digital Agency", district="Al Olaya",
               founder_profile_on_site=True),
    DemoAgency("Sahm Creative", "sahm-creative.demo", "Riyadh", "011 000 2202", "info@sahm-creative.demo",
               [BR, AD], "Branding, visual identity, logo design and advertising campaigns.",
               founder="Reem Al-Qahtani", founder_title="Founder & Creative Director", maps_name="Sahm Creative Studio",
               district="Al Malqa", cloudflare_email=True),
    DemoAgency("Bayan Web Studio", "bayanweb.demo", "Riyadh", "+966 50 000 3303", "projects@bayanweb.demo",
               [WD], "Web design, web development, e-commerce stores on Shopify and mobile app development.",
               founder="Omar Al-Shehri", founder_title="Co-Founder", maps_name="Bayan Web Studio", district="King Fahd Rd"),
    DemoAgency("وكالة رؤى للتسويق", "roaa-marketing.demo", "Riyadh", "٠٥٤٠٠٠٤٤٠٤", "info@roaa-marketing.demo",
               [DM, AD], "نقدم خدمات التسويق الرقمي وإدارة حسابات التواصل الاجتماعي والإعلانات الممولة في الرياض.",
               founder="سلطان بن فهد العتيبي", lang="ar", maps_name="Roaa Marketing Agency", district="Al Yasmin"),
    DemoAgency("Rankly KSA", "rankly-ksa.demo", "Riyadh", "+966 56 000 5505", "seo@rankly-ksa.demo",
               [SEO, DM], "Technical SEO, content marketing and search engine optimization audits.",
               founder="Lina Haddad", founder_only_on_linkedin=True, district="Al Sulimaniyah"),
    DemoAgency("Pixel Dune", "pixeldune.demo", "Jeddah", "+966 53 000 6606", "studio@pixeldune.demo",
               [BR, WD], "Brand identity, UI/UX design and website design for startups.",
               founder="Yousef Bakr", maps_name="Pixel Dune Design", district="Al Rawdah",
               founder_profile_on_site=True),
    DemoAgency("Red Sea Media", "redseamedia.demo", "Jeddah", "012 000 7707", "contact@redseamedia.demo",
               [AD, DM], "Advertising, media buying, video production and influencer marketing.",
               founder="Hani Al-Zahrani", founder_title="Managing Director", maps_name="Red Sea Media Advertising",
               district="Al Shati", extra_emails=["careers@redseamedia.demo"]),
    DemoAgency("موج للحلول الرقمية", "mawj-digital.demo", "Jeddah", "+966 59 000 8808", "hello@mawj-digital.demo",
               [WD, SEO], "تصميم المواقع وبرمجة المواقع وتحسين محركات البحث للشركات في جدة.",
               founder="عبدالرحمن محمد الغامدي", lang="ar", maps_name="", district="Al Zahra"),
    DemoAgency("Hijaz Growth Lab", "hijazgrowth.demo", "Jeddah", "+966 54 000 9909", "team@hijazgrowth.demo",
               [DM, SEO], "Performance marketing, PPC, SEO and conversion optimisation.",
               founder="Sara Kamal", founder_only_on_linkedin=True, maps_name="Hijaz Growth Lab", district="Al Andalus",
               linkedin_on_site=False),
    DemoAgency("Gulf Shore Branding", "gulfshore-branding.demo", "Khobar", "+966 55 000 1010", "hi@gulfshore-branding.demo",
               [BR], "Branding, packaging and graphic design for retail and F&B brands.",
               founder="Majed Al-Dossary", maps_name="Gulf Shore Branding Co.", district="Al Khobar Corniche",
               cloudflare_email=True),
    DemoAgency("Eastern Code", "easterncode.demo", "Dammam", "013 000 1111", "dev@easterncode.demo",
               [WD], "Custom web development, web apps and mobile app development for iOS and Android.",
               founder="Khalid Al-Mutairi", founder_title="CEO", maps_name="Eastern Code Software", district="Al Faisaliyah"),
    DemoAgency("Ad Wave", "adwave.demo", "Dammam", "+966 58 000 1212", "info@adwave.demo",
               [AD], "Outdoor advertising, ad campaigns and paid media.", maps_name="Ad Wave Advertising",
               in_search=False, site_up=False, district="Al Shati Al Gharbi"),
    DemoAgency("Haram Digital", "haram-digital.demo", "Mecca", "+966 50 000 1313", "info@haram-digital.demo",
               [DM, WD], "Digital marketing, social media and website design for hospitality businesses.",
               founder="Ibrahim Al-Lihyani", maps_name="Haram Digital Marketing", district="Al Aziziyah"),
    DemoAgency("Taybah Creative", "taybah-creative.demo", "Medina", "+966 56 000 1414", "studio@taybah-creative.demo",
               [BR, AD], "Branding, motion graphics, photography and advertising.",
               founder="", maps_name="Taybah Creative", district="Quba", linkedin_on_site=False),
    DemoAgency("Falak SEO", "falak-seo.demo", "Riyadh", "+966 57 000 1616", "growth@falak-seo.demo",
               [SEO], "SEO, local SEO for Google Maps and link building for e-commerce stores.",
               founder="Tariq Al-Saud", maps_name="Falak SEO Agency", district="Hittin"),
    DemoAgency("Qimma Brand House", "qimma-brand.demo", "Riyadh", "011 000 1717", "hello@qimma-brand.demo",
               [BR, AD], "Branding, brand identity, copywriting and advertising for real estate.",
               founder="Dana Al-Rashid", founder_title="Founder", maps_name="Qimma Brand House", district="Al Nakheel"),
    DemoAgency("Wadi Apps", "wadiapps.demo", "Riyadh", "+966 53 000 1818", "build@wadiapps.demo",
               [WD], "Mobile app development, web development and UI/UX design.",
               founder="Ahmed Al-Ghamdi", founder_title="CEO", maps_name="Wadi Apps", district="Al Wurud",
               founder_profile_on_site=True),
    DemoAgency("ضوء للإعلان", "dhaw-ads.demo", "Riyadh", "٠١١٠٠٠١٩١٩", "ads@dhaw-ads.demo",
               [AD, BR], "نقدم الإعلان والدعاية وتصميم الشعار والهوية البصرية في الرياض.",
               founder="نايف بن سعد الدوسري", lang="ar", maps_name="Dhaw Advertising", district="Al Murabba"),
    DemoAgency("Corniche Social", "corniche-social.demo", "Jeddah", "+966 55 000 2020", "hi@corniche-social.demo",
               [DM], "Social media marketing, content creation and influencer campaigns.",
               founder="Maha Al-Harthi", maps_name="Corniche Social Agency", district="Al Hamra",
               cloudflare_email=True),
    DemoAgency("Balad Web Works", "baladweb.demo", "Jeddah", "012 000 2121", "info@baladweb.demo",
               [WD, SEO], "WordPress and WooCommerce web development, web design and SEO.",
               founder="", maps_name="Balad Web Works", district="Al Balad", linkedin_on_site=False),
    DemoAgency("Dhahran Digital Partners", "dhahran-digital.demo", "Dammam", "+966 50 000 2222", "partners@dhahran-digital.demo",
               [DM, AD], "Digital marketing strategy, Google Ads, media buying and marketing consulting.",
               founder="Nasser Al-Qahtani", founder_title="Managing Partner", maps_name="Dhahran Digital Partners",
               district="Al Rakah"),
    DemoAgency("Oasis Pixels", "oasispixels.demo", "Khobar", "+966 56 000 2323", "create@oasispixels.demo",
               [BR, WD], "Graphic design, branding and website design.",
               founder="Rania Saad", founder_only_on_linkedin=True, maps_name="", district="Al Aqrabiyah"),
    DemoAgency("Makkah Media Lab", "makkah-medialab.demo", "Mecca", "012 000 2424", "lab@makkah-medialab.demo",
               [AD, DM], "Video production, motion graphics and advertising campaigns.",
               founder="Bilal Noor", maps_name="Makkah Media Lab", district="Al Shawqiyah"),
    DemoAgency("Uhud Digital", "uhud-digital.demo", "Medina", "+966 54 000 2525", "info@uhud-digital.demo",
               [DM, SEO, WD], "SEO, digital marketing and web development for clinics and schools.",
               founder="Hamza Al-Juhani", maps_name="Uhud Digital", district="Al Aziziyah"),
    DemoAgency("Najd Signs & Print", "", "Riyadh", "+966 55 000 1515", "", [AD],
               "", maps_name="Najd Signs & Print", in_search=False, has_website=False, district="Al Batha"),
]

# Results a real web search would also return, which the pipeline must reject.
NOISE_RESULTS = [
    SearchResult("https://clutch.co/sa/agencies/digital-marketing", "Top 10 Digital Marketing Agencies in Saudi Arabia - Clutch"),
    SearchResult("https://www.instagram.com/some.agency/", "Some Agency (@some.agency) • Instagram"),
    SearchResult("https://dune-media-dubai.demo", "Dune Media | Digital Marketing Agency Dubai"),
]
DUBAI_SITE = {
    "https://dune-media-dubai.demo": """<html><head><title>Dune Media | Dubai</title>
<meta property="og:site_name" content="Dune Media"></head><body>
<p>Digital marketing and SEO agency in Dubai, UAE. Call +971 4 000 1616</p>
<a href="mailto:hello@dune-media-dubai.demo">Email</a></body></html>""",
}

_TAGLINES = {DM: "Digital Marketing Agency", WD: "Web Development Company", SEO: "SEO Agency",
             BR: "Branding Agency", AD: "Advertising Agency"}


def _cf_encode(email: str, key: int = 0x5A) -> str:
    return bytes([key] + [ord(c) ^ key for c in email]).hex()


def _pages(a: DemoAgency) -> dict[str, str]:
    """Generate the agency's homepage, about page and contact page."""
    if not (a.has_website and a.site_up):
        return {}
    li = f'<a href="https://sa.linkedin.com/company/{a.slug}/">LinkedIn</a>' if a.linkedin_on_site else ""
    if a.lang == "ar":
        home = f"""<html lang="ar"><head><title>{a.name} | وكالة في {a.city}</title>
<meta property="og:site_name" content="{a.name}"></head><body>
<nav><a href="/من-نحن">من نحن</a> <a href="/تواصل">تواصل معنا</a></nav>
<h1>{a.name}</h1><p>{a.services}</p>
<footer>{_ar_city(a.city)}، المملكة العربية السعودية — جوال: {a.phone} {li}</footer></body></html>"""
        about = f"<html><body><p>المؤسس: {a.founder}</p><p>{_ar_city(a.city)}</p></body></html>" if a.founder else "<html><body><p>فريقنا</p></body></html>"
        contact = f"<html><body><p>البريد: {a.email}</p></body></html>"
        return {a.url: home, f"{a.url}/من-نحن": about, f"{a.url}/تواصل": contact}

    tagline = _TAGLINES[a.categories[0]]
    home = f"""<html><head><title>Home - {a.name} | Best {tagline} in {a.city}</title>
<meta property="og:site_name" content="{a.name}"></head><body>
<nav><a href="/about-us">About us</a> <a href="/contact">Contact</a></nav>
<h1>{tagline} in {a.city}</h1><p>{a.services}</p>
<footer>{a.district}, {a.city}, Saudi Arabia · <a href="tel:{a.phone}">{a.phone}</a> {li}</footer></body></html>"""
    if a.founder:
        profile = (f'<a href="https://sa.linkedin.com/in/{a.founder.lower().replace(" ", "-")}-demo/">LinkedIn</a>'
                   if a.founder_profile_on_site else "")
        about = f"""<html><body><h2>Meet the team</h2>
<div class="card"><h3>{a.founder}</h3><p>{a.founder_title}</p>{profile}</div>
<div class="card"><h3>Noura Saleh</h3><p>Account Manager</p></div>
<p>Based in {a.city}.</p></body></html>"""
    else:
        about = f"<html><body><h2>About us</h2><p>A creative team based in {a.city}.</p></body></html>"
    if a.cloudflare_email:
        email_html = f'<a href="/cdn-cgi/l/email-protection#{_cf_encode(a.email)}">[email protected]</a>'
    else:
        email_html = f'<a href="mailto:{a.email}">{a.email}</a>'
    extra = " ".join(a.extra_emails)
    contact = f"<html><body><p>Email: {email_html} {extra}</p><p>Phone: {a.phone}</p></body></html>"
    return {a.url: home, f"{a.url}/about-us": about, f"{a.url}/contact": contact}


def _ar_city(city: str) -> str:
    return {"Riyadh": "الرياض", "Jeddah": "جدة"}.get(city, city)


class DemoFetcher(Fetcher):
    """Serves the generated demo websites; never touches the network."""

    def __init__(self):
        super().__init__(delay=0, cache_dir=None, respect_robots=False)
        self.site: dict[str, str] = dict(DUBAI_SITE)
        for agency in AGENCIES:
            self.site.update(_pages(agency))
        self.pages_fetched = 0

    def get_html(self, url):
        html = self.site.get(url.rstrip("/"))
        if html is None:
            return None
        self.pages_fetched += 1
        return url.rstrip("/"), html


def _category_of(text: str) -> str:
    for category, phrases in CATEGORIES.items():
        if any(p in text for p in phrases):
            return category
    return ""


class DemoMaps:
    """Stands in for Google Places / Google Maps: verified listings with phone and address."""

    name = "demo_maps"

    def __init__(self, settings: ProviderSettings | None = None):
        self.calls = 0

    def discover(self, phrase: str, city: str, category: str) -> list[Lead]:
        self.calls += 1
        out = []
        for a in AGENCIES:
            if a.maps_name and a.city == city and category in a.categories:
                out.append(Lead(
                    agency_name=a.maps_name,
                    website=normalize_url(a.url) if a.has_website else "",
                    city=a.city,
                    phones=[normalize_phone(a.phone)],
                    categories=[category],
                    address=f"{a.district}, {a.city}, Saudi Arabia",
                    sources=[self.name],
                ))
        return out


class DemoSearch:
    """Stands in for Brave/SerpAPI: organic results plus LinkedIn search results."""

    name = "demo_search"

    def __init__(self):
        self.calls = 0

    def search(self, query: str, max_results: int = 20) -> list[SearchResult]:
        self.calls += 1
        if query.startswith("site:linkedin.com/company"):
            return [SearchResult(f"https://sa.linkedin.com/company/{a.slug}", f"{a.name} | LinkedIn")
                    for a in AGENCIES if a.name in query and a.has_website]
        if query.startswith("site:linkedin.com/in"):
            return [SearchResult(
                f"https://sa.linkedin.com/in/{a.founder.lower().replace(' ', '-')}-demo",
                f"{a.founder} - {a.founder_title} - {a.name} | LinkedIn",
                f"{a.city} · {a.founder_title} at {a.name}")
                for a in AGENCIES if a.founder_only_on_linkedin and a.name in query]
        category = _category_of(query)
        results = [SearchResult(a.url, f"Best {_TAGLINES[category]} in {a.city} - {a.name}",
                                a.services[:120])
                   for a in AGENCIES
                   if a.in_search and a.has_website and a.city in query and category in a.categories]
        if "Riyadh" in query:
            results += NOISE_RESULTS
        return results[:max_results]


def demo_providers(settings: ProviderSettings | None = None):
    """(discovery providers, LinkedIn search engine) for a demo run."""
    search = DemoSearch()
    return [DemoMaps(settings), WebSearchSource(search, settings)], search
