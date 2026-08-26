"""HTTP fetch layer with optional anti-bot proxy providers.

Carousell sits behind a Cloudflare challenge that a plain request can't pass, so
requests are routed through a scraping API (ScraperAPI by default) that renders
JS and rotates residential proxies to get the real page. Swap providers with the
SCRAPER_PROVIDER env var without touching the scraper code.

The URL-building logic (:meth:`Fetcher.build`) is pure and unit-tested; the
network call (:meth:`Fetcher.get`) is a thin wrapper around it.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, Tuple

import httpx

log = logging.getLogger(__name__)

_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-SG,en;q=0.9",
}


@dataclass(frozen=True)
class FetcherConfig:
    provider: str = "direct"      # "direct" | "scraperapi" | "scrapedo"
    api_key: str = ""
    render: bool = True           # execute JS (needed for Cloudflare)
    ultra: bool = True            # premium/residential proxies (Cloudflare)
    country: str = "sg"

    @property
    def active(self) -> bool:
        return self.provider not in ("", "direct") and bool(self.api_key)


class Fetcher:
    def __init__(self, config: FetcherConfig, timeout: float = 70.0):
        self.config = config
        # Proxy providers rendering JS can take a while; direct is quick.
        self.timeout = timeout if config.active else 20.0

    def build(self, target_url: str) -> Tuple[str, Dict[str, str]]:
        """Return the (request_url, params) to actually call for a target URL."""
        c = self.config
        if not c.active:
            return target_url, {}

        if c.provider == "scraperapi":
            params = {
                "api_key": c.api_key,
                "url": target_url,
                "country_code": c.country,
            }
            # ultra_premium already renders + uses residential proxies; only add
            # render on its own when ultra is off, to avoid burning extra credits.
            if c.ultra:
                params["ultra_premium"] = "true"
            elif c.render:
                params["render"] = "true"
            return "https://api.scraperapi.com/", params

        if c.provider == "scrapedo":
            params = {
                "token": c.api_key,
                "url": target_url,
                "geoCode": c.country,
            }
            if c.render:
                params["render"] = "true"
            if c.ultra:
                params["super"] = "true"  # residential/premium proxies
            return "http://api.scrape.do/", params

        # Unknown provider name -> fail safe to a direct fetch.
        log.warning("unknown SCRAPER_PROVIDER %r; fetching directly", c.provider)
        return target_url, {}

    def get(self, target_url: str) -> httpx.Response:
        request_url, params = self.build(target_url)
        with httpx.Client(
            headers=_BROWSER_HEADERS, timeout=self.timeout, follow_redirects=True
        ) as client:
            return client.get(request_url, params=params)

    def describe(self) -> str:
        return self.config.provider if self.config.active else "direct"


def fetcher_from_settings(settings) -> Fetcher:
    return Fetcher(
        FetcherConfig(
            provider=settings.scraper_provider,
            api_key=settings.scraper_api_key,
            render=settings.scraper_render,
            ultra=settings.scraper_ultra,
            country=settings.scraper_country,
        )
    )
