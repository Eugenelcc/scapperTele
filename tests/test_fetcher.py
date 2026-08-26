from app.scrapers.fetcher import Fetcher, FetcherConfig

TARGET = "https://www.carousell.sg/search/iphone?sort_by=3"


def test_direct_passthrough():
    f = Fetcher(FetcherConfig(provider="direct"))
    url, params = f.build(TARGET)
    assert url == TARGET
    assert params == {}
    assert f.describe() == "direct"


def test_no_key_falls_back_to_direct():
    # provider set but no api key -> not active -> direct
    f = Fetcher(FetcherConfig(provider="scraperapi", api_key=""))
    url, params = f.build(TARGET)
    assert url == TARGET and params == {}


def test_scraperapi_ultra_premium():
    f = Fetcher(FetcherConfig(provider="scraperapi", api_key="KEY", ultra=True, country="sg"))
    url, params = f.build(TARGET)
    assert url == "https://api.scraperapi.com/"
    assert params["api_key"] == "KEY"
    assert params["url"] == TARGET
    assert params["country_code"] == "sg"
    assert params["ultra_premium"] == "true"
    # ultra already renders; we should not also pay for a separate render flag
    assert "render" not in params
    assert f.describe() == "scraperapi"


def test_scraperapi_render_only_when_ultra_off():
    f = Fetcher(FetcherConfig(provider="scraperapi", api_key="KEY", ultra=False, render=True))
    url, params = f.build(TARGET)
    assert params.get("render") == "true"
    assert "ultra_premium" not in params


def test_scrapedo_params():
    f = Fetcher(FetcherConfig(provider="scrapedo", api_key="TOK", ultra=True, render=True, country="sg"))
    url, params = f.build(TARGET)
    assert url == "http://api.scrape.do/"
    assert params["token"] == "TOK"
    assert params["url"] == TARGET
    assert params["render"] == "true"
    assert params["super"] == "true"
    assert params["geoCode"] == "sg"


def test_unknown_provider_falls_back_direct():
    f = Fetcher(FetcherConfig(provider="mystery", api_key="KEY"))
    url, params = f.build(TARGET)
    assert url == TARGET and params == {}


def test_active_flag():
    assert Fetcher(FetcherConfig("scraperapi", "KEY")).config.active is True
    assert Fetcher(FetcherConfig("scraperapi", "")).config.active is False
    assert Fetcher(FetcherConfig("direct", "KEY")).config.active is False
