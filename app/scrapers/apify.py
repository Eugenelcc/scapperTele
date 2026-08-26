"""Carousell via an Apify Actor.

Apify Actors run a real browser (passing Cloudflare) and return structured
listings. We call the "run synchronously and get dataset items" endpoint, which
blocks until the run finishes and returns the scraped items as JSON.

Because different community Carousell Actors expect different input keys and
emit different output fields, both the input building and the output mapping are
configurable via env vars, and the mapping falls back to a tolerant field
search. Use the /debug/apify endpoint to inspect a real Actor's output and tune
APIFY_QUERY_FIELD / APIFY_EXTRA_INPUT if needed.

Docs: https://docs.apify.com/api/v2#/reference/actors/run-actor-synchronously-with-input-and-get-dataset-items
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

import httpx

from ..core.models import Listing
from .base import BaseScraper
from .carousell import parse_price

log = logging.getLogger(__name__)

_API_BASE = "https://api.apify.com/v2/acts"


def _first(node: Dict[str, Any], *keys: str) -> str:
    for k in keys:
        v = node.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def _image_from(node: Dict[str, Any]) -> str:
    for k in ("image", "imageUrl", "thumbnail", "photo"):
        v = node.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    for k in ("images", "photos"):
        v = node.get(k)
        if isinstance(v, list) and v:
            first = v[0]
            if isinstance(first, str):
                return first
            if isinstance(first, dict):
                return _first(first, "imageUrl", "url", "src")
    return ""


def item_to_listing(item: Dict[str, Any], host: str = "www.carousell.sg") -> Optional[Listing]:
    """Map one Apify dataset item (a Carousell listing) to our Listing model."""
    if not isinstance(item, dict):
        return None
    title = _first(item, "title", "name", "productName")
    if not title:
        return None

    url = _first(item, "url", "link", "productUrl", "itemUrl")
    listing_id = _first(item, "id", "listingId", "productId", "listingID")
    if not listing_id:
        # Derive a stable id from the URL's last path segment, else the URL.
        if url:
            listing_id = url.rstrip("/").split("/")[-1].split("?")[0] or url
        else:
            return None
    if not url and listing_id:
        url = f"https://{host}/p/{listing_id}"

    price = parse_price(
        item.get("price")
        if item.get("price") is not None
        else item.get("priceFormatted") or item.get("priceValue")
    )
    currency = "S$" if "sg" in host else "$"

    return Listing(
        source="carousell",
        listing_id=str(listing_id),
        title=title,
        price=price,
        currency=currency,
        url=url,
        location=_first(item, "location", "locationName", "place"),
        condition=_first(item, "condition", "conditionName"),
        image_url=_image_from(item),
    )


def extract_listings(items: List[Any], host: str, limit: int = 40) -> List[Listing]:
    """Pure mapping from an Apify dataset (list of items) to Listings. Unit-tested."""
    out: List[Listing] = []
    seen: set[str] = set()
    for item in items or []:
        listing = item_to_listing(item, host)
        if listing is None or listing.uid in seen:
            continue
        seen.add(listing.uid)
        out.append(listing)
        if len(out) >= limit:
            break
    return out


class ApifyCarousellScraper(BaseScraper):
    name = "carousell"  # same logical source, different backend

    def __init__(
        self,
        token: str,
        actor_id: str,
        host: str = "www.carousell.sg",
        query_field: str = "search",
        query_as_list: bool = False,
        max_field: str = "maxItems",
        extra_input: str = "",
        timeout: float = 180.0,
    ):
        self.token = token
        self.actor_id = actor_id
        self.host = host
        self.query_field = query_field
        self.query_as_list = query_as_list
        self.max_field = max_field
        self.extra_input = extra_input
        self.timeout = timeout

    def build_input(self, query: str, limit: int) -> Dict[str, Any]:
        payload: Dict[str, Any] = {}
        if self.extra_input:
            try:
                extra = json.loads(self.extra_input)
                if isinstance(extra, dict):
                    payload.update(extra)
            except json.JSONDecodeError:
                log.warning("APIFY_EXTRA_INPUT is not valid JSON; ignoring")
        payload[self.query_field] = [query] if self.query_as_list else query
        if self.max_field:
            payload[self.max_field] = limit
        return payload

    def _run_url(self) -> str:
        return f"{_API_BASE}/{self.actor_id}/run-sync-get-dataset-items"

    def _call(self, query: str, limit: int) -> List[Any]:
        # Auth via header (not a ?token= query param) so the token never appears
        # in request URLs, exception messages or logs.
        resp = httpx.post(
            self._run_url(),
            headers={"Authorization": f"Bearer {self.token}"},
            json=self.build_input(query, limit),
            timeout=self.timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, list) else []

    def _redact(self, text: str) -> str:
        return text.replace(self.token, "***") if self.token else text

    def search(self, query: str, limit: int = 40) -> List[Listing]:
        try:
            items = self._call(query, limit)
        except httpx.HTTPStatusError as exc:
            body = exc.response.text[:300] if exc.response is not None else ""
            log.warning(
                "apify actor failed for %r: %s | %s",
                query,
                self._redact(str(exc)),
                self._redact(body),
            )
            return []
        except Exception as exc:
            log.warning("apify actor failed for %r: %s", query, self._redact(str(exc)))
            return []
        try:
            return extract_listings(items, self.host, limit=limit)
        except Exception as exc:
            log.exception("apify parse failed for %r: %s", query, exc)
            return []

    def diagnostics(self, query: str, limit: int = 5) -> dict:
        """Fetch a few items and report raw shape so field mapping can be tuned."""
        info: dict = {
            "actor_id": self.actor_id,
            "input": self.build_input(query, limit),
        }
        try:
            items = self._call(query, limit)
        except httpx.HTTPStatusError as exc:
            info["error"] = self._redact(f"{exc}")
            if exc.response is not None:
                info["status"] = exc.response.status_code
                info["body"] = self._redact(exc.response.text[:500])
            return info
        except Exception as exc:
            info["error"] = self._redact(repr(exc))
            return info
        info["item_count"] = len(items)
        info["first_item"] = items[0] if items else None
        info["mapped"] = len(extract_listings(items, self.host, limit=limit))
        return info
