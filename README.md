# Saudi Agency Lead Finder

> **Website Monitor:** this repo also contains a dashboard that checks 1,000+ websites on a
> schedule for DNS, downtime, blank screens, database errors, 404 and 500 errors.
> See [README-monitor.md](README-monitor.md).

A command-line tool that finds **digital marketing, web development, SEO, branding and
advertising agencies in Saudi Arabia**, enriches each one from its own website and from
search results, removes duplicates, and exports a CSV.

## What it collects

| CSV column | Where it comes from |
|---|---|
| `agency_name` | Google Places business name, else the site's `og:site_name` / schema.org name |
| `website` | Places listing or search result, normalised to the homepage |
| `city` | Places address, else the Saudi city mentioned most on the agency's site |
| `linkedin_company_url` | LinkedIn link on the agency's site, else a `site:linkedin.com/company` search |
| `founder_name`, `founder_title` | schema.org `founder`, team/about pages (English and Arabic), else a `site:linkedin.com/in` search |
| `founder_linkedin_url` | LinkedIn profile link on the team page, else search results |
| `email` | `mailto:` links, page text, Cloudflare-protected addresses, schema.org; agency-domain addresses first |
| `phone` | `tel:` / WhatsApp links, page text, schema.org; normalised to `+9665…`, `+9661…`, `9200…`, `800…` |
| `services` | Keyword detection (English and Arabic) on the site: SEO, Web Development, Branding, PPC, etc. |
| `categories` | Which of the five target categories the agency matches |
| `address`, `sources` | Places address; which discovery sources found the agency |

Multi-value cells (emails, phones, services) are separated by `; `. The file is UTF-8 with a BOM,
so Excel displays Arabic names correctly.

## How it works

1. **Discover.** For each category × city it queries every configured source with English and
   Arabic phrases (for example "SEO agency in Riyadh" and "شركة سيو"). Directory, social and
   marketplace sites (Clutch, LinkedIn, Instagram and so on) are filtered out.
2. **Deduplicate.** Leads are merged when they share a website domain, a Saudi phone number,
   a LinkedIn page or a normalised name. Two leads with *different* websites are never merged.
3. **Enrich from the website.** It fetches the homepage plus up to five contact, about, team or
   services pages (Arabic paths such as `/من-نحن` and `/تواصل` included). It honours
   `robots.txt` and waits between requests to the same host.
4. **Enrich LinkedIn.** If a search API key is set, it looks for the company page and the
   founder's profile in search-engine results. LinkedIn itself is never fetched, because
   LinkedIn's terms prohibit scraping.
5. **Filter, deduplicate again, export.** A lead is kept only if there is evidence that it is in
   Saudi Arabia (a `.sa` domain, a Saudi phone number, a Saudi address, or a Saudi city mentioned
   on the site).

## Setup

```bash
pip install -r requirements.txt
```

Set at least one API key, or pass a seed list (see below):

| Env var | Source | Notes |
|---|---|---|
| `GOOGLE_PLACES_API_KEY` | [Google Places API (New)](https://developers.google.com/maps/documentation/places/web-service/text-search) | Best discovery source: verified name, phone, address, website. Up to 60 results per query. |
| `BRAVE_API_KEY` | [Brave Search API](https://brave.com/search/api/) | Discovery plus LinkedIn lookups. |
| `SERPAPI_API_KEY` | [SerpAPI](https://serpapi.com/) (Google results) | Discovery plus LinkedIn lookups. |

For the best coverage, use Places for discovery and Brave or SerpAPI for LinkedIn and the long tail.

## Usage

```bash
# Every category, the six default cities, every source that has a key
python -m leadgen -o output/saudi_agencies.csv

# Narrower run
python -m leadgen --cities Riyadh Jeddah --categories seo branding -o output/riyadh_jeddah.csv

# Every known city, and keep only agencies whose site lists a target service
python -m leadgen --cities all --strict

# Enrich your own list of agency URLs (.txt with one URL per line, or .csv with a website column)
python -m leadgen --seeds my_agencies.txt --no-linkedin

# Add new results to an earlier export, deduplicated against it
python -m leadgen --existing output/saudi_agencies.csv -o output/saudi_agencies.csv
```

Useful flags: `--limit N` (enrich only the first N unique leads, handy for a test run),
`--english-only`, `--max-pages`, `--workers`, `--delay`, `--sources places,brave`,
`--cache-dir` (on by default at `.cache/`, so re-runs don't re-spend API quota), and `-v`
for logging. Run `python -m leadgen --help` to see every option.

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest
```

The tests run offline against HTML fixtures (English and Arabic agency sites) and fake search
results. They cover extraction, phone and email normalisation, LinkedIn matching, deduplication
and the full pipeline through to CSV.

## Responsible use

- The tool collects **business contact details that agencies publish themselves**. Founder names
  and profiles are personal data under Saudi Arabia's **Personal Data Protection Law (PDPL)**.
  Use them only for legitimate B2B outreach, give recipients an easy opt-out, and don't resell
  the list.
- Follow each API provider's terms. Don't add direct scraping of LinkedIn or Google result pages.
- Founder and LinkedIn matches are heuristic. Verify them before outreach.
