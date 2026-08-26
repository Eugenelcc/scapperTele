"""Render listings as Telegram HTML messages."""
from __future__ import annotations

from html import escape
from typing import List

from ..core.models import Listing


def format_listing(listing: Listing) -> str:
    title = escape(listing.title)
    price = escape(listing.price_str())
    line = f'💰 <b>{price}</b> — <a href="{escape(listing.url)}">{title}</a>'
    meta_bits = []
    if listing.condition:
        meta_bits.append(escape(listing.condition))
    if listing.location:
        meta_bits.append("📍 " + escape(listing.location))
    if meta_bits:
        line += "\n   " + " · ".join(meta_bits)
    return line


def format_results(query: str, listings: List[Listing], limit: int = 8) -> str:
    if not listings:
        return f"No results found for <b>{escape(query)}</b> right now. 🕵️"
    header = f"🔎 Top matches for <b>{escape(query)}</b>:"
    body = "\n\n".join(format_listing(l) for l in listings[:limit])
    footer = ""
    if len(listings) > limit:
        footer = f"\n\n…and {len(listings) - limit} more."
    return f"{header}\n\n{body}{footer}"


def format_alert(watch_desc: str, listings: List[Listing], limit: int = 6) -> str:
    header = f"🚨 <b>New deals</b> for {escape(watch_desc)}:"
    body = "\n\n".join(format_listing(l) for l in listings[:limit])
    footer = ""
    if len(listings) > limit:
        footer = f"\n\n…and {len(listings) - limit} more new ones."
    return f"{header}\n\n{body}{footer}"
