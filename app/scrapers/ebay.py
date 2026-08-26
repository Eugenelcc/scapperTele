"""eBay Browse API source — free, official, no bot-wall.

Uses the OAuth *client credentials* flow (application token, no user login) and
the Browse API's ``item_summary/search`` endpoint. Get free keys at
https://developer.ebay.com → create an app → copy the App ID (Client ID) and
Cert ID (Client Secret).

As with Carousell, the pure JSON→Listing mapping (:func:`extract_listings`) is
unit-tested; the network calls are thin wrappers.
"""
from __future__ import annotations

import base64
import logging
import threading
import time
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import httpx

from ..core.models import Listing
from .base import BaseScraper

log = logging.getLogger(__name__)

_ENDPOINTS = {
    "production": {
        "oauth": "https://api.ebay.com/identity/v1/oauth2/token",
        "browse": "https://api.ebay.com/buy/browse/v1/item_summary/search",
    },
    "sandbox": {
        "oauth": "https://api.sandbox.ebay.com/identity/v1/oauth2/token",
        "browse": "https://api.sandbox.ebay.com/buy/browse/v1/item_summary/search",
    },
}

_CURRENCY_SYMBOLS = {
    "SGD": "S$",
    "USD": "US$",
    "GBP": "£",
    "EUR": "€",
    "AUD": "A$",
    "HKD": "HK$",
    "MYR": "RM",
}


def _currency_symbol(code: str) -> str:
    return _CURRENCY_SYMBOLS.get(code, (code + " ") if code else "$")


def _to_listing(item: Dict[str, Any]) -> Optional[Listing]:
    item_id = str(item.get("itemId") or item.get("legacyItemId") or "").strip()
    title = (item.get("title") or "").strip()
    if not item_id or not title:
        return None

    price_obj = item.get("price") or {}
    price = None
    try:
        if price_obj.get("value") is not None:
            price = float(price_obj["value"])
    except (TypeError, ValueError):
        price = None
    currency = _currency_symbol(price_obj.get("currency", ""))

    image = item.get("image") or {}
    image_url = image.get("imageUrl", "") if isinstance(image, dict) else ""

    location = ""
    loc = item.get("itemLocation")
    if isinstance(loc, dict):
        location = loc.get("country", "") or ""

    return Listing(
        source="ebay",
        listing_id=item_id,
        title=title,
        price=price,
        currency=currency,
        url=item.get("itemWebUrl", "") or "",
        location=location,
        condition=item.get("condition", "") or "",
        image_url=image_url,
    )


def extract_listings(document: Dict[str, Any], limit: int = 40) -> List[Listing]:
    """Pure mapping from a Browse API search response to Listings. Unit-tested."""
    items = document.get("itemSummaries") or []
    out: List[Listing] = []
    seen: set[str] = set()
    for item in items:
        listing = _to_listing(item)
        if listing is None or listing.uid in seen:
            continue
        seen.add(listing.uid)
        out.append(listing)
        if len(out) >= limit:
            break
    return out


class EbayScraper(BaseScraper):
    name = "ebay"

    def __init__(
        self,
        app_id: str,
        cert_id: str,
        marketplace: str = "EBAY_SG",
        env: str = "production",
        timeout: float = 20.0,
    ):
        self.app_id = app_id
        self.cert_id = cert_id
        self.marketplace = marketplace
        self.env = env if env in _ENDPOINTS else "production"
        self.timeout = timeout
        self._token: Optional[str] = None
        self._token_expiry: float = 0.0
        self._lock = threading.Lock()

    # ---- OAuth ----------------------------------------------------------
    def _basic_auth(self) -> str:
        raw = f"{self.app_id}:{self.cert_id}".encode()
        return base64.b64encode(raw).decode()

    def _get_token(self) -> Optional[str]:
        with self._lock:
            if self._token and time.time() < self._token_expiry - 60:
                return self._token
            try:
                resp = httpx.post(
                    _ENDPOINTS[self.env]["oauth"],
                    headers={
                        "Authorization": f"Basic {self._basic_auth()}",
                        "Content-Type": "application/x-www-form-urlencoded",
                    },
                    data={
                        "grant_type": "client_credentials",
                        "scope": "https://api.ebay.com/oauth/api_scope",
                    },
                    timeout=self.timeout,
                )
                resp.raise_for_status()
                payload = resp.json()
            except Exception as exc:
                body = ""
                if isinstance(exc, httpx.HTTPStatusError) and exc.response is not None:
                    body = exc.response.text[:300]
                log.warning("ebay oauth failed: %s | %s", exc, body)
                return None
            self._token = payload.get("access_token")
            self._token_expiry = time.time() + float(payload.get("expires_in", 7200))
            return self._token

    # ---- search ---------------------------------------------------------
    def search(self, query: str, limit: int = 40) -> List[Listing]:
        token = self._get_token()
        if not token:
            return []
        url = (
            f"{_ENDPOINTS[self.env]['browse']}"
            f"?q={quote(query)}&limit={min(int(limit), 200)}"
        )
        try:
            resp = httpx.get(
                url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-EBAY-C-MARKETPLACE-ID": self.marketplace,
                    "Content-Type": "application/json",
                },
                timeout=self.timeout,
            )
            resp.raise_for_status()
            document = resp.json()
        except httpx.HTTPStatusError as exc:
            body = exc.response.text[:300] if exc.response is not None else ""
            log.warning("ebay search failed for %r: %s | %s", query, exc, body)
            return []
        except Exception as exc:
            log.warning("ebay search failed for %r: %s", query, exc)
            return []
        try:
            return extract_listings(document, limit=limit)
        except Exception as exc:
            log.exception("ebay parse failed for %r: %s", query, exc)
            return []
