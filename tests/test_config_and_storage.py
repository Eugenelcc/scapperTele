import os

from app.config import _parse_watch, parse_watches
from app.core.models import Listing
from app.core.storage import Store


def test_parse_watch_full():
    w = _parse_watch("iphone 15|900|256;pro")
    assert w.query == "iphone 15"
    assert w.max_price == 900.0
    assert w.keywords == ["256", "pro"]


def test_parse_watch_query_only():
    w = _parse_watch("macbook air")
    assert w.query == "macbook air"
    assert w.max_price is None
    assert w.keywords == []


def test_parse_watch_empty():
    assert _parse_watch("   ") is None


def test_parse_watches_multiple():
    ws = parse_watches("iphone 15|900|pro , macbook air|1400|")
    assert len(ws) == 2
    assert ws[0].query == "iphone 15"
    assert ws[1].query == "macbook air"
    assert ws[1].max_price == 1400.0


def make(lid, title="iPhone", price=900.0):
    return Listing(
        source="carousell", listing_id=lid, title=title, price=price,
        currency="S$", url="https://x/p/" + lid,
    )


def test_store_dedup(tmp_path):
    store = Store(os.path.join(tmp_path, "t.db"))
    listing = make("1")
    assert store.is_new(listing) is True     # first time -> new
    assert store.is_new(listing) is False    # seen -> not new


def test_store_reprices_are_new(tmp_path):
    store = Store(os.path.join(tmp_path, "t.db"))
    assert store.is_new(make("1", price=900)) is True
    # Same id, different price -> new fingerprint -> notify again.
    assert store.is_new(make("1", price=800)) is True
    assert store.is_new(make("1", price=800)) is False


def test_store_watches_roundtrip(tmp_path):
    from app.config import Watch

    store = Store(os.path.join(tmp_path, "t.db"))
    wid = store.add_watch(Watch(query="ps5", max_price=500, keywords=["slim"]))
    rows = store.list_watches()
    assert len(rows) == 1
    assert rows[0][0] == wid
    assert rows[0][1].query == "ps5"
    assert store.remove_watch(wid) is True
    assert store.list_watches() == []


def test_store_subscribers(tmp_path):
    store = Store(os.path.join(tmp_path, "t.db"))
    store.add_subscriber("111")
    store.add_subscriber("111")  # idempotent
    store.add_subscriber("222")
    assert set(store.list_subscribers()) == {"111", "222"}
    store.remove_subscriber("111")
    assert store.list_subscribers() == ["222"]
