"""Shared data types used across scrapers, storage and the bot."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Listing:
    """A single marketplace listing, normalised across sources."""

    source: str          # e.g. "carousell"
    listing_id: str      # source-native id, unique within the source
    title: str
    price: Optional[float]
    currency: str
    url: str
    location: str = ""
    condition: str = ""
    image_url: str = ""

    @property
    def uid(self) -> str:
        """Stable, globally-unique id used for de-duplication."""
        return f"{self.source}:{self.listing_id}"

    @property
    def fingerprint(self) -> str:
        """Hash of the fields that matter, so edited listings can re-notify."""
        raw = f"{self.uid}|{self.title}|{self.price}"
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]

    def price_str(self) -> str:
        if self.price is None:
            return "price n/a"
        return f"{self.currency}{self.price:,.0f}"
