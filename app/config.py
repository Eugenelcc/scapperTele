"""Runtime configuration loaded from environment variables.

Values come from the process environment (Render dashboard) or a local .env
file loaded via python-dotenv. Nothing here reaches out to the network, so it
is safe to import from anywhere.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List, Optional

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover - dotenv is optional at runtime
    pass


@dataclass(frozen=True)
class Watch:
    """A saved search: what to look for and how to filter it."""

    query: str
    max_price: Optional[float] = None
    keywords: List[str] = field(default_factory=list)

    def describe(self) -> str:
        bits = [f'"{self.query}"']
        if self.max_price is not None:
            bits.append(f"under ${self.max_price:,.0f}")
        if self.keywords:
            bits.append("matching " + "/".join(self.keywords))
        return " ".join(bits)


def _parse_watch(raw: str) -> Optional[Watch]:
    """Parse one watch spec: ``query|maxPrice|kw1;kw2`` (price/keywords optional)."""
    raw = raw.strip()
    if not raw:
        return None
    parts = [p.strip() for p in raw.split("|")]
    query = parts[0]
    if not query:
        return None
    max_price: Optional[float] = None
    if len(parts) > 1 and parts[1]:
        try:
            max_price = float(parts[1].replace(",", "").replace("$", ""))
        except ValueError:
            max_price = None
    keywords: List[str] = []
    if len(parts) > 2 and parts[2]:
        keywords = [k.strip().lower() for k in parts[2].split(";") if k.strip()]
    return Watch(query=query, max_price=max_price, keywords=keywords)


def parse_watches(raw: str) -> List[Watch]:
    """Parse the comma-separated DEFAULT_WATCHES env string into Watch objects."""
    watches: List[Watch] = []
    for chunk in raw.split(","):
        watch = _parse_watch(chunk)
        if watch:
            watches.append(watch)
    return watches


def _get_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, "").strip() or default)
    except ValueError:
        return default


def _get_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "").strip() or default)
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    telegram_token: str
    telegram_chat_id: str
    scan_interval_hours: float
    default_watches: List[Watch]
    carousell_host: str
    max_results: int
    port: int
    scan_token: str
    data_dir: str
    webapp_url: str
    webapp_allow_insecure: bool
    scraper_provider: str
    scraper_api_key: str
    scraper_render: bool
    scraper_ultra: bool
    scraper_country: str
    ebay_app_id: str
    ebay_cert_id: str
    ebay_marketplace: str
    ebay_env: str
    apify_token: str
    apify_actor_id: str
    apify_query_field: str
    apify_query_as_list: bool
    apify_max_field: str
    apify_extra_input: str

    @property
    def has_token(self) -> bool:
        return bool(self.telegram_token and ":" in self.telegram_token)

    @property
    def ebay_enabled(self) -> bool:
        return bool(self.ebay_app_id and self.ebay_cert_id)

    @property
    def apify_enabled(self) -> bool:
        return bool(self.apify_token and self.apify_actor_id)

    @property
    def has_webapp(self) -> bool:
        # Telegram requires an https:// URL to launch a Web App.
        return self.webapp_url.startswith("https://")


def _webapp_url() -> str:
    """The public https URL the Mini App is served from.

    Prefer an explicit WEBAPP_URL; otherwise fall back to Render's
    auto-injected RENDER_EXTERNAL_URL. Trailing slash trimmed.
    """
    url = (
        os.environ.get("WEBAPP_URL")
        or os.environ.get("RENDER_EXTERNAL_URL")
        or ""
    ).strip().rstrip("/")
    return url


def _bool_env(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _scraper_provider(api_key: str) -> str:
    """Which fetch backend to use for anti-bot-walled sites.

    Explicit SCRAPER_PROVIDER wins; otherwise default to scraperapi when a key
    is present, else direct (which Cloudflare will block on Carousell).
    """
    provider = os.environ.get("SCRAPER_PROVIDER", "").strip().lower()
    if provider:
        return provider
    return "scraperapi" if api_key else "direct"


def load_settings() -> Settings:
    scraper_api_key = os.environ.get("SCRAPER_API_KEY", "").strip()
    return Settings(
        telegram_token=os.environ.get("TELEGRAM_BOT_TOKEN", "").strip(),
        telegram_chat_id=os.environ.get("TELEGRAM_CHAT_ID", "").strip(),
        scan_interval_hours=_get_float("SCAN_INTERVAL_HOURS", 3.0),
        default_watches=parse_watches(os.environ.get("DEFAULT_WATCHES", "")),
        carousell_host=os.environ.get("CAROUSELL_HOST", "www.carousell.sg").strip(),
        max_results=_get_int("MAX_RESULTS", 40),
        port=_get_int("PORT", 10000),
        scan_token=os.environ.get("SCAN_TOKEN", "").strip(),
        data_dir=os.environ.get("DATA_DIR", "data").strip() or "data",
        webapp_url=_webapp_url(),
        webapp_allow_insecure=os.environ.get("WEBAPP_ALLOW_INSECURE", "")
        .strip()
        .lower()
        in ("1", "true", "yes"),
        scraper_provider=_scraper_provider(scraper_api_key),
        scraper_api_key=scraper_api_key,
        # Cloudflare needs JS rendering + premium residential proxies to pass.
        scraper_render=_bool_env("SCRAPER_RENDER", True),
        scraper_ultra=_bool_env("SCRAPER_ULTRA_PREMIUM", True),
        scraper_country=os.environ.get("SCRAPER_COUNTRY", "sg").strip() or "sg",
        ebay_app_id=os.environ.get("EBAY_APP_ID", "").strip(),
        ebay_cert_id=os.environ.get("EBAY_CERT_ID", "").strip(),
        ebay_marketplace=os.environ.get("EBAY_MARKETPLACE", "EBAY_SG").strip()
        or "EBAY_SG",
        ebay_env=os.environ.get("EBAY_ENV", "production").strip().lower()
        or "production",
        apify_token=os.environ.get("APIFY_TOKEN", "").strip(),
        apify_actor_id=os.environ.get("APIFY_ACTOR_ID", "").strip(),
        apify_query_field=os.environ.get("APIFY_QUERY_FIELD", "search").strip()
        or "search",
        apify_query_as_list=_bool_env("APIFY_QUERY_AS_LIST", False),
        apify_max_field=os.environ.get("APIFY_MAX_FIELD", "maxItems").strip()
        or "maxItems",
        apify_extra_input=os.environ.get("APIFY_EXTRA_INPUT", "").strip(),
    )
