from app.config import Watch
from app.core.matcher import filter_and_rank, matches
from app.core.models import Listing


def make(title, price, lid="1"):
    return Listing(
        source="carousell",
        listing_id=lid,
        title=title,
        price=price,
        currency="S$",
        url="https://x/p/" + lid,
    )


def test_price_filter():
    w = Watch(query="iphone", max_price=900)
    assert matches(make("iPhone 15", 850), w)
    assert not matches(make("iPhone 15", 950), w)
    # Unknown price is rejected when a budget is set.
    assert not matches(make("iPhone 15", None), w)


def test_keyword_filter():
    w = Watch(query="iphone", keywords=["pro", "256"])
    assert matches(make("iPhone 15 Pro", 999), w)
    assert matches(make("iPhone 15 256GB", 999), w)
    assert not matches(make("iPhone 15 Plus", 999), w)


def test_no_constraints_matches_everything():
    w = Watch(query="iphone")
    assert matches(make("anything", None), w)


def test_filter_and_rank_orders_cheapest_first():
    w = Watch(query="iphone", max_price=2000)
    listings = [
        make("iPhone A", 1200, "a"),
        make("iPhone B", 800, "b"),
        make("iPhone C", None, "c"),  # dropped: price unknown but budget set
        make("iPhone D", 1500, "d"),
    ]
    ranked = filter_and_rank(listings, w)
    assert [l.listing_id for l in ranked] == ["b", "a", "d"]
