"""Carousell (Singapore) scraper.

Carousell renders its search results from a JSON blob embedded in the search
page (Next.js ``__NEXT_DATA__``) and also exposes an internal JSON search API.
Both change from time to time, so this scraper is deliberately defensive:

* Network + JSON extraction lives in :meth:`CarousellScraper.search`.
* The pure, unit-tested extraction from a parsed JSON document lives in
  :func:`extract_listings`, which walks the document looking for anything that
  *looks* like a listing rather than hard-coding a brittle deep path.

If Carousell restructures its payload, :func:`extract_listings` and
:func:`_looks_like_listing` are the only places you should need to touch.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import quote

from ..core.models import Listing
from .base import BaseScraper
from .fetcher import Fetcher, FetcherConfig

log = logging.getLogger(__name__)

_SCRIPT_RE = re.compile(
    r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.DOTALL
)
_STATE_RE = re.compile(
    r'window\.(?:__INITIAL_STATE__|initialState)\s*=\s*(\{.*?\})\s*;?\s*</script>',
    re.DOTALL,
)
_PRICE_RE = re.compile(r"(\d[\d,]*(?:\.\d+)?)")


def parse_price(value: Any) -> Optional[float]:
    """Best-effort numeric price from a string like ``"S$1,299"`` or a number."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str):
        return None
    if "free" in value.lower():
        return 0.0
    m = _PRICE_RE.search(value.replace(",", ""))
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def _first_str(node: Dict[str, Any], *keys: str) -> str:
    for k in keys:
        v = node.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def _looks_like_listing(node: Any) -> bool:
    """Heuristic: a dict carrying an id, a title-ish field and a price-ish field."""
    if not isinstance(node, dict):
        return False
    has_id = any(k in node for k in ("id", "listingID", "listingId"))
    has_title = any(
        isinstance(node.get(k), str) and node.get(k, "").strip()
        for k in ("title", "name")
    )
    has_price = any(k in node for k in ("price", "priceFormatted", "price_formatted"))
    return has_id and has_title and has_price


def _to_listing(node: Dict[str, Any], host: str) -> Optional[Listing]:
    listing_id = str(
        node.get("id") or node.get("listingID") or node.get("listingId") or ""
    ).strip()
    if not listing_id:
        return None
    title = _first_str(node, "title", "name")
    if not title:
        return None
    price_raw = (
        node.get("price")
        or node.get("priceFormatted")
        or node.get("price_formatted")
    )
    price = parse_price(price_raw)
    currency = "S$" if "sg" in host else "$"

    image_url = ""
    photos = node.get("photos") or node.get("images")
    if isinstance(photos, list) and photos:
        first = photos[0]
        if isinstance(first, str):
            image_url = first
        elif isinstance(first, dict):
            image_url = _first_str(first, "imageUrl", "url", "progressiveUrl")

    url = f"https://{host}/p/{listing_id}"
    return Listing(
        source="carousell",
        listing_id=listing_id,
        title=title,
        price=price,
        currency=currency,
        url=url,
        location=_first_str(node, "locationName", "location"),
        condition=_first_str(node, "condition", "conditionName"),
        image_url=image_url,
    )


def _walk(node: Any) -> Iterable[Dict[str, Any]]:
    """Yield every listing-like dict anywhere in a nested JSON document."""
    if isinstance(node, dict):
        if _looks_like_listing(node):
            yield node
        for value in node.values():
            yield from _walk(value)
    elif isinstance(node, list):
        for item in node:
            yield from _walk(item)


def extract_listings(document: Any, host: str, limit: int = 40) -> List[Listing]:
    """Pure extraction from an already-parsed JSON document. Unit-tested."""
    out: List[Listing] = []
    seen: set[str] = set()
    for node in _walk(document):
        listing = _to_listing(node, host)
        if listing is None or listing.uid in seen:
            continue
        seen.add(listing.uid)
        out.append(listing)
        if len(out) >= limit:
            break
    return out


def _json_from_html(html: str) -> Optional[Any]:
    """Pull the embedded JSON state out of a Carousell search page."""
    m = _SCRIPT_RE.search(html)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    m = _STATE_RE.search(html)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    return None


class CarousellScraper(BaseScraper):
    name = "carousell"

    def __init__(self, host: str = "www.carousell.sg", fetcher: Fetcher = None):
        self.host = host
        # Default to a plain direct fetcher (which Cloudflare will block) so the
        # scraper is usable standalone; production passes a configured one.
        self.fetcher = fetcher or Fetcher(FetcherConfig())

    def _url(self, query: str) -> str:
        # sort_by=3 -> most recent listings first.
        return f"https://{self.host}/search/{quote(query)}?sort_by=3"

    def search(self, query: str, limit: int = 40) -> List[Listing]:
        url = self._url(query)
        try:
            resp = self.fetcher.get(url)
            resp.raise_for_status()
            html = resp.text
        except Exception as exc:  # network, timeout, HTTP error
            log.warning(
                "carousell fetch failed for %r (via %s): %s",
                query,
                self.fetcher.describe(),
                exc,
            )
            return []

        document = _json_from_html(html)
        if document is None:
            log.warning("carousell: no embedded JSON found for %r", query)
            return []
        try:
            return extract_listings(document, self.host, limit=limit)
        except Exception as exc:  # never let a parse quirk break the scan
            log.exception("carousell parse failed for %r: %s", query, exc)
            return []

    def diagnostics(self, query: str) -> dict:
        """Fetch a query and report what we got, without parsing failures hiding
        the cause. Used by the /debug/carousell endpoint to tell a block apart
        from a changed-JSON-shape problem.
        """
        url = self._url(query)
        info: dict = {"url": url, "host": self.host, "fetcher": self.fetcher.describe()}
        try:
            resp = self.fetcher.get(url)
            info["status"] = resp.status_code
            info["final_url"] = str(resp.url)
            html = resp.text
        except Exception as exc:
            info["error"] = repr(exc)
            return info

        info["length"] = len(html)
        info["has_next_data"] = bool(_SCRIPT_RE.search(html))
        info["has_initial_state"] = bool(_STATE_RE.search(html))

        # Look for common bot-wall / challenge markers.
        low = html.lower()
        blockers = [
            m
            for m in (
                "perimeterx",
                "px-captcha",
                "captcha",
                "access denied",
                "are you a robot",
                "just a moment",
                "cf-challenge",
                "cloudflare",
            )
            if m in low
        ]
        if blockers:
            info["blockers"] = blockers

        document = _json_from_html(html)
        info["json_parsed"] = document is not None
        if document is not None:
            info["listing_like_nodes"] = sum(1 for _ in _walk(document))
            info["extracted_listings"] = len(extract_listings(document, self.host))

        # First bit of the body helps eyeball a challenge page vs. real HTML.
        info["snippet"] = html[:600]
        return info
