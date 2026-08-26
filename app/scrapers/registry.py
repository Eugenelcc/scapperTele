"""Aggregate all enabled scrapers behind a single search() call."""
from __future__ import annotations

import logging
from typing import List

from ..core.models import Listing
from .base import BaseScraper
from .carousell import CarousellScraper

log = logging.getLogger(__name__)


class ScraperRegistry:
    def __init__(self, scrapers: List[BaseScraper]):
        self.scrapers = scrapers

    @classmethod
    def default(cls, carousell_host: str = "www.carousell.sg") -> "ScraperRegistry":
        return cls([CarousellScraper(host=carousell_host)])

    def search(self, query: str, limit: int = 40) -> List[Listing]:
        """Search every source and merge the results."""
        results: List[Listing] = []
        for scraper in self.scrapers:
            try:
                found = scraper.search(query, limit=limit)
                log.info("%s: %d results for %r", scraper.name, len(found), query)
                results.extend(found)
            except Exception as exc:  # a source must never break the others
                log.exception("%s crashed for %r: %s", scraper.name, query, exc)
        return results
