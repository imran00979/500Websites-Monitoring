# Saudi Agency Lead Finder

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
| `address`, `sources` | Map listing address; which providers found the agency |

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

## Try the demo first (no API keys, no internet)

```bash
pip install -r requirements.txt
python -m leadgen --demo
```

This runs the real pipeline against 25 built-in **fictional** agencies (the `.demo` domains,
people, emails and phone numbers are all invented). The demo includes:

- the same agency listed by both providers under different names;
- a Clutch directory page, an Instagram profile and a Dubai agency, all of which the tool rejects;
- a dead website and a map listing with no website;
- Cloudflare-hidden emails, Arabic sites, and founders who can only be found through LinkedIn search.

It stops at 20 agencies, as test mode would, and writes `output/demo_run.csv`. Add
`--max-agencies 0` to process all 25.

## Providers

Discovery goes through a provider registry (`leadgen/sources/registry.py`). Every provider is
optional and is turned on by setting its API key in the environment or in a `.env` file
(copy `.env.example`).

| Provider | Data | API key env var | Used for |
|---|---|---|---|
| `places` | [Google Places API (New)](https://developers.google.com/maps/documentation/places/web-service/text-search) (Google Maps) | `GOOGLE_PLACES_API_KEY` or `GOOGLE_MAPS_API_KEY` | discovery |
| `serpapi_maps` | Google Maps listings via [SerpAPI](https://serpapi.com/) | `SERPAPI_API_KEY` | discovery |
| `serpapi` | Google web results via SerpAPI | `SERPAPI_API_KEY` | discovery and LinkedIn lookups |
| `brave` | [Brave Search API](https://brave.com/search/api/) | `BRAVE_API_KEY` | discovery and LinkedIn lookups |

```bash
python -m leadgen --list-providers                # which providers are configured
python -m leadgen --providers places,brave        # run only these (or set LEADGEN_PROVIDERS)
python -m leadgen --linkedin-provider brave       # LinkedIn engine (or LEADGEN_LINKEDIN_PROVIDER)
```

By default (`auto`) every configured provider runs, and LinkedIn lookups use SerpAPI if it is
configured, otherwise Brave. Map providers (`places`, `serpapi_maps`) return verified business
listings, so their names, addresses and cities take priority when results are merged.

To add a provider, write a class with a `name` and a `discover(phrase, city, category)` method
that returns `Lead`s. Add a `search(query, max_results)` method as well if it can do LinkedIn
lookups. Then register a `ProviderSpec` for it in `registry.py`.

## Usage

**Start with a test run.** It stops after **20 Saudi agencies** and uses small result pages
(10 web results and 1 map page per query), so it costs only a few dozen API requests:

```bash
python -m leadgen --test                          # writes output/test_run.csv
```

The summary shows how many API requests each provider used. Check the CSV, then run the full
search:

```bash
# Every category, the six default cities, every configured provider
python -m leadgen -o output/saudi_agencies.csv

# Narrower run
python -m leadgen --cities Riyadh Jeddah --categories seo branding

# Every known city; keep only agencies whose site lists a target service
python -m leadgen --cities all --strict

# Enrich your own list of agency URLs (.txt with one URL per line, or .csv with a website column)
python -m leadgen --seeds my_agencies.txt --providers none

# Add new results to an earlier export, deduplicated against it
python -m leadgen --existing output/saudi_agencies.csv -o output/saudi_agencies.csv
```

The search runs in batches: it queries, enriches the new agencies, then checks whether to stop.
A capped run (`--test` or `--max-agencies N`) stops at the cap instead of using up the whole
query plan. A full run rewrites its CSV after every batch, so an interrupted run keeps what it
has collected. Queries rotate through categories and then cities, so even a small run covers
every category.

Other flags: `--english-only`, `--max-pages`, `--workers`, `--delay`, and `--cache-dir`. The
cache is on by default at `.cache/`, so re-runs don't spend API quota again. Use `-v` for
logging, and `--help` to see every option.

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest
```

The tests run offline against HTML fixtures, the demo data and fake search results. They cover
extraction, phone and email normalisation, LinkedIn matching, deduplication, provider
configuration, the test-mode cap, and the full pipeline through to CSV.

## Responsible use

- The tool collects **business contact details that agencies publish themselves**. Founder names
  and profiles are personal data under Saudi Arabia's **Personal Data Protection Law (PDPL)**.
  Use them only for legitimate B2B outreach, give recipients an easy opt-out, and don't resell
  the list.
- Follow each API provider's terms. Don't add direct scraping of LinkedIn or Google result pages.
- Founder and LinkedIn matches are heuristic. Verify them before outreach.
