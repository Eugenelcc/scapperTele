"""Aggregate all enabled scrapers behind a single search() call."""
from __future__ import annotations

import logging
from typing import List

from ..core.models import Listing
from .apify import ApifyCarousellScraper
from .base import BaseScraper
from .carousell import CarousellScraper
from .ebay import EbayScraper
from .fetcher import Fetcher, FetcherConfig, fetcher_from_settings

log = logging.getLogger(__name__)


class ScraperRegistry:
    def __init__(self, scrapers: List[BaseScraper]):
        self.scrapers = scrapers

    @classmethod
    def default(
        cls, carousell_host: str = "www.carousell.sg", fetcher: Fetcher = None
    ) -> "ScraperRegistry":
        fetcher = fetcher or Fetcher(FetcherConfig())
        return cls([CarousellScraper(host=carousell_host, fetcher=fetcher)])

    @classmethod
    def carousell_from_settings(cls, settings) -> BaseScraper:
        """Pick the Carousell backend: Apify Actor if configured, else the
        direct/scraping-API fetch path."""
        if settings.apify_enabled:
            log.info("carousell backend: apify (%s)", settings.apify_actor_id)
            return ApifyCarousellScraper(
                token=settings.apify_token,
                actor_id=settings.apify_actor_id,
                host=settings.carousell_host,
                query_field=settings.apify_query_field,
                query_as_list=settings.apify_query_as_list,
                max_field=settings.apify_max_field,
                extra_input=settings.apify_extra_input,
            )
        log.info("carousell backend: %s fetch", settings.scraper_provider)
        return CarousellScraper(
            host=settings.carousell_host,
            fetcher=fetcher_from_settings(settings),
        )

    @classmethod
    def from_settings(cls, settings) -> "ScraperRegistry":
        scrapers: List[BaseScraper] = [cls.carousell_from_settings(settings)]
        if settings.ebay_enabled:
            scrapers.append(
                EbayScraper(
                    app_id=settings.ebay_app_id,
                    cert_id=settings.ebay_cert_id,
                    marketplace=settings.ebay_marketplace,
                    env=settings.ebay_env,
                )
            )
            log.info("ebay source enabled (%s)", settings.ebay_marketplace)
        return cls(scrapers)

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
