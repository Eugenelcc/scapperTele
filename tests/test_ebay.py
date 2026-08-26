import base64
import json
import os

from app.scrapers.ebay import EbayScraper, _currency_symbol, extract_listings

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def load_fixture():
    with open(os.path.join(FIXTURES, "ebay_search.json")) as f:
        return json.load(f)


def test_currency_symbols():
    assert _currency_symbol("SGD") == "S$"
    assert _currency_symbol("USD") == "US$"
    assert _currency_symbol("JPY") == "JPY "  # unknown -> code + space
    assert _currency_symbol("") == "$"


def test_extract_skips_broken_rows():
    listings = extract_listings(load_fixture())
    assert len(listings) == 2  # the empty-id row is dropped


def test_extract_fields():
    listings = extract_listings(load_fixture())
    by_id = {l.listing_id: l for l in listings}

    iphone = by_id["v1|1234567890|0"]
    assert iphone.source == "ebay"
    assert iphone.price == 999.0
    assert iphone.currency == "S$"
    assert iphone.price_str() == "S$999"
    assert iphone.url == "https://www.ebay.com/itm/1234567890"
    assert iphone.condition == "New"
    assert iphone.location == "SG"
    assert iphone.image_url.endswith("s-l500.jpg")

    mac = by_id["v1|9876543210|0"]
    assert mac.price == 1250.5
    assert mac.currency == "US$"


def test_extract_respects_limit():
    assert len(extract_listings(load_fixture(), limit=1)) == 1


def test_extract_empty_document():
    assert extract_listings({}) == []
    assert extract_listings({"itemSummaries": []}) == []


def test_basic_auth_header_encoding():
    scraper = EbayScraper(app_id="APP", cert_id="CERT")
    decoded = base64.b64decode(scraper._basic_auth()).decode()
    assert decoded == "APP:CERT"


def test_env_defaults_to_production_when_invalid():
    scraper = EbayScraper(app_id="a", cert_id="b", env="banana")
    assert scraper.env == "production"
