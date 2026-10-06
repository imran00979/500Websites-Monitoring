"""Search vocabulary: target categories, Saudi cities and service keywords."""

from __future__ import annotations

# Category key -> search phrases (English and Arabic) used to discover agencies.
CATEGORIES: dict[str, list[str]] = {
    "digital_marketing": ["digital marketing agency", "وكالة تسويق رقمي"],
    "web_development": ["web development company", "شركة تصميم وبرمجة مواقع"],
    "seo": ["SEO agency", "شركة سيو"],
    "branding": ["branding agency", "وكالة هوية تجارية"],
    "advertising": ["advertising agency", "وكالة إعلان"],
}

# Canonical city name -> spellings to recognise in addresses and page text.
CITIES: dict[str, list[str]] = {
    "Riyadh": ["riyadh", "الرياض"],
    "Jeddah": ["jeddah", "jedda", "jiddah", "جدة", "جده"],
    "Dammam": ["dammam", "الدمام"],
    "Khobar": ["khobar", "al khobar", "al-khobar", "alkhobar", "الخبر"],
    "Dhahran": ["dhahran", "الظهران"],
    "Mecca": ["mecca", "makkah", "مكة"],
    "Medina": ["medina", "madinah", "المدينة المنورة"],
    "Taif": ["taif", "الطائف"],
    "Abha": ["abha", "أبها", "ابها"],
    "Khamis Mushait": ["khamis mushait", "خميس مشيط"],
    "Tabuk": ["tabuk", "تبوك"],
    "Buraidah": ["buraidah", "buraydah", "بريدة"],
    "Hail": ["hail", "ha'il", "حائل"],
    "Jubail": ["jubail", "الجبيل"],
    "Al Ahsa": ["al ahsa", "al-ahsa", "hofuf", "الأحساء", "الاحساء", "الهفوف"],
    "Yanbu": ["yanbu", "ينبع"],
    "Najran": ["najran", "نجران"],
    "Jazan": ["jazan", "jizan", "جازان"],
}

# City centre (lat, lng) used to bias map searches towards the city.
CITY_COORDS: dict[str, tuple[float, float]] = {
    "Riyadh": (24.7136, 46.6753), "Jeddah": (21.5433, 39.1728), "Dammam": (26.4207, 50.0888),
    "Khobar": (26.2172, 50.1971), "Dhahran": (26.2361, 50.0393), "Mecca": (21.3891, 39.8579),
    "Medina": (24.5247, 39.5692), "Taif": (21.2703, 40.4158), "Abha": (18.2465, 42.5117),
    "Khamis Mushait": (18.3000, 42.7333), "Tabuk": (28.3835, 36.5662), "Buraidah": (26.3260, 43.9750),
    "Hail": (27.5114, 41.6900), "Jubail": (27.0046, 49.6460), "Al Ahsa": (25.3830, 49.5860),
    "Yanbu": (24.0890, 38.0637), "Najran": (17.4917, 44.1322), "Jazan": (16.8892, 42.5511),
}

# Cities searched by default (the largest agency markets).
DEFAULT_CITIES = ["Riyadh", "Jeddah", "Dammam", "Khobar", "Mecca", "Medina"]

# Canonical service -> keywords (lower-case) that indicate the agency offers it.
SERVICES: dict[str, list[str]] = {
    "SEO": ["seo", "search engine optimization", "search engine optimisation", "تحسين محركات البحث", "سيو"],
    "Digital Marketing": ["digital marketing", "online marketing", "التسويق الرقمي", "تسويق رقمي", "التسويق الإلكتروني", "تسويق الكتروني"],
    "Social Media Marketing": ["social media", "smm", "التواصل الاجتماعي", "السوشيال ميديا"],
    "Paid Advertising / PPC": ["ppc", "pay per click", "google ads", "paid ads", "paid media", "media buying", "sem", "الإعلانات الممولة", "إعلانات جوجل"],
    "Advertising": ["advertising", "advertisement", "ad campaigns", "الإعلان", "إعلانات", "دعاية"],
    "Web Development": ["web development", "website development", "web dev", "برمجة المواقع", "تطوير المواقع", "برمجة مواقع"],
    "Web Design": ["web design", "website design", "تصميم المواقع", "تصميم مواقع"],
    "E-commerce": ["e-commerce", "ecommerce", "online store", "shopify", "woocommerce", "متجر إلكتروني", "المتاجر الإلكترونية", "متاجر الكترونية"],
    "Mobile App Development": ["mobile app", "app development", "ios", "android", "تطبيقات الجوال", "تطوير التطبيقات", "تطبيقات الجوال"],
    "Branding": ["branding", "brand identity", "visual identity", "logo design", "الهوية البصرية", "الهوية التجارية", "تصميم الشعار"],
    "Graphic Design": ["graphic design", "التصميم الجرافيكي", "تصميم جرافيك"],
    "Content Marketing": ["content marketing", "content creation", "copywriting", "كتابة المحتوى", "صناعة المحتوى", "تسويق المحتوى"],
    "UI/UX Design": ["ui/ux", "ux design", "ui design", "user experience", "تجربة المستخدم"],
    "Video Production": ["video production", "motion graphics", "photography", "إنتاج الفيديو", "موشن جرافيك", "التصوير"],
    "Marketing Strategy": ["marketing strategy", "marketing consulting", "الاستراتيجية التسويقية", "استشارات تسويقية"],
    "Influencer Marketing": ["influencer", "المؤثرين"],
}

# Which services map to which of the user's target categories.
SERVICE_TO_CATEGORY: dict[str, str] = {
    "SEO": "seo",
    "Digital Marketing": "digital_marketing",
    "Social Media Marketing": "digital_marketing",
    "Content Marketing": "digital_marketing",
    "Influencer Marketing": "digital_marketing",
    "Marketing Strategy": "digital_marketing",
    "Paid Advertising / PPC": "advertising",
    "Advertising": "advertising",
    "Video Production": "advertising",
    "Web Development": "web_development",
    "Web Design": "web_development",
    "E-commerce": "web_development",
    "Mobile App Development": "web_development",
    "UI/UX Design": "web_development",
    "Branding": "branding",
    "Graphic Design": "branding",
}

# Domains that are never an agency's own website (directories, social, marketplaces).
NON_AGENCY_DOMAINS = {
    "linkedin.com", "facebook.com", "instagram.com", "twitter.com", "x.com", "tiktok.com",
    "youtube.com", "snapchat.com", "pinterest.com", "wikipedia.org", "google.com",
    "goo.gl", "bing.com", "yelp.com", "clutch.co", "goodfirms.co", "sortlist.com",
    "sortlist.co.uk", "designrush.com", "upwork.com", "fiverr.com", "freelancer.com",
    "khamsat.com", "mostaql.com", "bayt.com", "indeed.com", "glassdoor.com", "crunchbase.com",
    "tripadvisor.com", "yellowpages.com", "saudiyellowpages.com", "daleel.com", "zoominfo.com",
    "rocketreach.co", "apollo.io", "agencyspotter.com", "themanifest.com", "topdevelopers.co",
    "techbehemoths.com", "medium.com", "reddit.com", "quora.com", "amazon.com", "noon.com",
    "haraj.com.sa", "opensooq.com", "wa.me", "whatsapp.com", "t.me", "apple.com", "play.google.com",
    "behance.net", "dribbble.com", "github.com", "wordpress.com", "blogspot.com", "wixsite.com",
}

# Page-link text/href fragments worth crawling on an agency's own site.
INTERESTING_PAGE_HINTS = [
    "contact", "about", "team", "who-we-are", "our-story", "services", "leadership", "founder",
    "اتصل", "تواصل", "من-نحن", "من نحن", "فريق", "خدمات", "خدماتنا", "عن الشركة",
]

# Paths tried when the homepage does not link to contact/about pages.
FALLBACK_PATHS = ["/contact", "/contact-us", "/about", "/about-us"]
