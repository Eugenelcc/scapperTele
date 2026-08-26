import json
import os

from app.scrapers.carousell import (
    extract_listings,
    parse_price,
    _json_from_html,
)

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def load_fixture():
    with open(os.path.join(FIXTURES, "carousell_next_data.json")) as f:
        return json.load(f)


def test_parse_price_variants():
    assert parse_price("S$1,299") == 1299.0
    assert parse_price("$999") == 999.0
    assert parse_price("1200") == 1200.0
    assert parse_price(450) == 450.0
    assert parse_price("Free") == 0.0
    assert parse_price("negotiable") is None
    assert parse_price(None) is None


def test_extract_listings_from_next_data():
    doc = load_fixture()
    listings = extract_listings(doc, host="www.carousell.sg", limit=40)
    # The two well-formed items + the "name/priceFormatted" one = 3.
    # The price-less item and the "unrelated" node are skipped.
    titles = [l.title for l in listings]
    assert "iPhone 15 Pro 256GB Natural Titanium" in titles
    assert "MacBook Air M2 13 inch 256GB" in titles
    assert "iPhone 15 (free gift screen protector)" in titles
    assert len(listings) == 3


def test_extracted_fields():
    doc = load_fixture()
    listings = extract_listings(doc, host="www.carousell.sg")
    by_id = {l.listing_id: l for l in listings}

    iphone = by_id["1234567"]
    assert iphone.price == 1150.0
    assert iphone.currency == "S$"
    assert iphone.location == "Tampines"
    assert iphone.condition == "Lightly used"
    assert iphone.url == "https://www.carousell.sg/p/1234567"
    assert iphone.image_url == "https://img.carousell.com/a.jpg"

    macbook = by_id["7654321"]
    assert macbook.price == 1299.0
    assert macbook.image_url == "https://img.carousell.com/b.jpg"


def test_limit_is_respected():
    doc = load_fixture()
    listings = extract_listings(doc, host="www.carousell.sg", limit=1)
    assert len(listings) == 1


def test_json_from_html_next_data():
    doc = load_fixture()
    html = (
        '<html><body><script id="__NEXT_DATA__" type="application/json">'
        + json.dumps(doc)
        + "</script></body></html>"
    )
    parsed = _json_from_html(html)
    assert parsed is not None
    listings = extract_listings(parsed, host="www.carousell.sg")
    assert len(listings) == 3


def test_json_from_html_missing_returns_none():
    assert _json_from_html("<html>no data here</html>") is None
