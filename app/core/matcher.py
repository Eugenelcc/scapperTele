"""Filtering and ranking of listings against a Watch."""
from __future__ import annotations

from typing import List

from ..config import Watch
from .models import Listing


def matches(listing: Listing, watch: Watch) -> bool:
    """True if a listing satisfies a watch's price and keyword constraints."""
    if watch.max_price is not None:
        # Listings without a price can't be confirmed under budget -> drop them.
        if listing.price is None or listing.price > watch.max_price:
            return False
    if watch.keywords:
        haystack = listing.title.lower()
        if not any(kw in haystack for kw in watch.keywords):
            return False
    return True


def filter_and_rank(listings: List[Listing], watch: Watch) -> List[Listing]:
    """Keep matching listings, cheapest (known price) first."""
    kept = [l for l in listings if matches(l, watch)]

    def sort_key(l: Listing):
        # Priced items ascending; unpriced items last.
        return (0, l.price) if l.price is not None else (1, 0.0)

    return sorted(kept, key=sort_key)
