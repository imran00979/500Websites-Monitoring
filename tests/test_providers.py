import pytest

from leadgen.cli import load_env_file, main
from leadgen.demo import AGENCIES, DemoFetcher, demo_providers
from leadgen.export import read_csv
from leadgen.http import Fetcher
from leadgen.pipeline import RunConfig, RunStats, query_plan, run
from leadgen.sources import (
    BraveSearch,
    GooglePlacesSource,
    ProviderConfigError,
    ProviderSettings,
    SerpApiMapsSource,
    SerpApiSearch,
    build,
    configured,
)


@pytest.fixture
def net_fetcher():
    return Fetcher(delay=0, cache_dir=None, respect_robots=False)


def test_auto_selects_every_configured_provider(net_fetcher):
    env = {"GOOGLE_MAPS_API_KEY": "g", "SERPAPI_API_KEY": "s"}  # alias for the Places key
    setup = build(net_fetcher, env)
    assert setup.selected == ["places", "serpapi_maps", "serpapi"]
    assert isinstance(setup.discovery[0], GooglePlacesSource)
    assert isinstance(setup.discovery[1], SerpApiMapsSource)
    assert isinstance(setup.linkedin, SerpApiSearch)  # serpapi preferred for LinkedIn


def test_nothing_configured_is_not_an_error(net_fetcher):
    setup = build(net_fetcher, {})
    assert setup.discovery == [] and setup.linkedin is None
    assert configured({}) == []


def test_explicit_selection_and_env_selection(net_fetcher):
    env = {"GOOGLE_PLACES_API_KEY": "g", "BRAVE_API_KEY": "b"}
    assert build(net_fetcher, env, providers="places").selected == ["places"]
    assert build(net_fetcher, {**env, "LEADGEN_PROVIDERS": "brave"}).selected == ["brave"]
    # the command-line flag beats the environment variable
    assert build(net_fetcher, {**env, "LEADGEN_PROVIDERS": "brave"}, providers="places").selected == ["places"]
    assert build(net_fetcher, env, providers="none").discovery == []


def test_linkedin_provider_choice(net_fetcher):
    env = {"BRAVE_API_KEY": "b", "SERPAPI_API_KEY": "s"}
    assert isinstance(build(net_fetcher, env, linkedin="brave").linkedin, BraveSearch)
    assert build(net_fetcher, env, linkedin="none").linkedin is None
    with pytest.raises(ProviderConfigError, match="must be one of"):
        build(net_fetcher, env, linkedin="places")


def test_config_errors(net_fetcher):
    with pytest.raises(ProviderConfigError, match="unknown provider"):
        build(net_fetcher, {}, providers="bing")
    with pytest.raises(ProviderConfigError, match="needs SERPAPI_API_KEY"):
        build(net_fetcher, {}, providers="serpapi_maps")


def test_settings_reach_providers(net_fetcher):
    settings = ProviderSettings(results_per_query=10, map_pages=1)
    setup = build(net_fetcher, {"GOOGLE_PLACES_API_KEY": "g", "BRAVE_API_KEY": "b"}, settings=settings)
    places, brave = setup.discovery
    assert places.settings.map_pages == 1 and brave.max_results == 10


def test_serpapi_maps_parsing():
    place = {"title": "Nakhla Digital", "address": "Al Olaya, Riyadh 12211, Saudi Arabia",
             "phone": "+966 55 000 1101", "website": "https://www.nakhla-digital.demo/en",
             "type": "Marketing agency"}
    lead = SerpApiMapsSource._to_lead(place, "Jeddah", "seo")
    assert (lead.website, lead.city, lead.phones) == (
        "https://nakhla-digital.demo", "Riyadh", ["+966550001101"])
    assert SerpApiMapsSource._to_lead({**place, "website": "https://instagram.com/nakhla"},
                                      "Riyadh", "seo").website == ""
    assert SerpApiMapsSource._to_lead({"title": "X", "address": "Dubai, UAE", "phone": "+971 4 000 0000"},
                                      "Riyadh", "seo") is None


def test_query_plan_rotates_categories_then_cities():
    cfg = RunConfig(cities=["Riyadh", "Jeddah"], categories=["seo", "branding"], arabic_queries=False)
    plan = list(query_plan(cfg))
    assert [(c, cat) for _, c, cat in plan] == [
        ("Riyadh", "seo"), ("Riyadh", "branding"), ("Jeddah", "seo"), ("Jeddah", "branding")]


def test_env_file_does_not_override(tmp_path):
    f = tmp_path / ".env"
    f.write_text("# keys\nBRAVE_API_KEY='abc'\nexport SERPAPI_API_KEY=def\nEMPTY\n")
    env = {"SERPAPI_API_KEY": "already-set"}
    assert load_env_file(str(f), env) == ["BRAVE_API_KEY"]
    assert env == {"SERPAPI_API_KEY": "already-set", "BRAVE_API_KEY": "abc"}


def _demo_cfg(max_agencies):
    providers, linkedin = demo_providers(ProviderSettings(results_per_query=10, map_pages=1))
    return RunConfig(cities=["Riyadh", "Jeddah", "Dammam", "Khobar", "Mecca", "Medina"],
                     categories=["digital_marketing", "web_development", "seo", "branding", "advertising"],
                     providers=providers, linkedin_engine=linkedin, max_agencies=max_agencies, workers=4)


def test_test_mode_stops_at_cap_and_saves_queries():
    capped, full = RunStats(), RunStats()
    leads = run(_demo_cfg(20), DemoFetcher(), stats=capped)
    assert len(leads) == 20 and capped.stopped_early
    everything = run(_demo_cfg(0), DemoFetcher(), stats=full)
    assert len(everything) == len(AGENCIES)       # every fictional Saudi agency, Dubai one dropped
    assert capped.queries < full.queries / 2      # the cap really saves API calls
    assert not any("dubai" in lead.website for lead in everything)
    assert not any("clutch" in lead.website or "instagram" in lead.website for lead in everything)
    by_site = {lead.website: lead for lead in everything}
    assert by_site["https://roaa-marketing.demo"].founder_name == "سلطان بن فهد العتيبي"
    assert by_site["https://sahm-creative.demo"].emails == ["info@sahm-creative.demo"]  # Cloudflare
    assert by_site["https://rankly-ksa.demo"].founder_linkedin_url.endswith("/in/lina-haddad-demo")


def test_demo_end_to_end_via_cli(tmp_path, capsys):
    out = tmp_path / "demo.csv"
    assert main(["--demo", "-o", str(out), "--env-file", ""]) == 0
    assert len(read_csv(str(out))) == 20
    assert "stopped early" in capsys.readouterr().out
