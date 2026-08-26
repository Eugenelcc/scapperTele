from app.scrapers.apify import (
    ApifyCarousellScraper,
    extract_listings,
    item_to_listing,
)

HOST = "www.carousell.sg"


def test_item_to_listing_common_fields():
    item = {
        "id": "111",
        "title": "iPhone 15 Pro 256GB",
        "price": "S$1,150",
        "url": "https://www.carousell.sg/p/iphone-111/",
        "images": ["https://img/a.jpg"],
        "location": "Tampines",
        "condition": "Lightly used",
    }
    l = item_to_listing(item, HOST)
    assert l.source == "carousell"
    assert l.listing_id == "111"
    assert l.price == 1150.0
    assert l.currency == "S$"
    assert l.url.endswith("/p/iphone-111/")
    assert l.image_url == "https://img/a.jpg"
    assert l.location == "Tampines"


def test_item_numeric_price_and_derived_id():
    item = {
        "title": "MacBook Air M2",
        "price": 1299,
        "url": "https://www.carousell.sg/p/macbook-999?x=1",
        "image": "https://img/b.jpg",
    }
    l = item_to_listing(item, HOST)
    assert l.price == 1299.0
    assert l.listing_id == "macbook-999"  # derived from URL last segment
    assert l.image_url == "https://img/b.jpg"


def test_item_missing_title_dropped():
    assert item_to_listing({"price": "S$10", "id": "1"}, HOST) is None


def test_item_no_url_builds_from_id():
    l = item_to_listing({"title": "AirPods", "id": "abc", "price": 100}, HOST)
    assert l.url == "https://www.carousell.sg/p/abc"


def test_extract_dedups_and_limits():
    items = [
        {"id": "1", "title": "iPhone A", "price": 100},
        {"id": "1", "title": "iPhone A dup", "price": 100},  # same id -> dropped
        {"id": "2", "title": "iPhone B", "price": 200},
    ]
    out = extract_listings(items, HOST)
    assert [l.listing_id for l in out] == ["1", "2"]
    assert len(extract_listings(items, HOST, limit=1)) == 1


def test_build_input_defaults():
    s = ApifyCarousellScraper(token="T", actor_id="u~a")
    payload = s.build_input("iphone 15", 40)
    assert payload == {"search": "iphone 15", "maxItems": 40}


def test_build_input_query_as_list_and_extra():
    s = ApifyCarousellScraper(
        token="T",
        actor_id="u~a",
        query_field="queries",
        query_as_list=True,
        max_field="maxItems",
        extra_input='{"country": "SG", "proxy": {"useApifyProxy": true}}',
    )
    payload = s.build_input("macbook", 10)
    assert payload["queries"] == ["macbook"]
    assert payload["maxItems"] == 10
    assert payload["country"] == "SG"
    assert payload["proxy"] == {"useApifyProxy": True}


def test_build_input_bad_extra_json_ignored():
    s = ApifyCarousellScraper(token="T", actor_id="u~a", extra_input="{not json}")
    payload = s.build_input("x", 5)
    assert payload == {"search": "x", "maxItems": 5}


def test_run_url():
    s = ApifyCarousellScraper(token="T", actor_id="epctex~carousell-scraper")
    assert s._run_url() == (
        "https://api.apify.com/v2/acts/epctex~carousell-scraper/"
        "run-sync-get-dataset-items"
    )
