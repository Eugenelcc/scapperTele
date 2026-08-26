"""Flask blueprint: serves the Mini App page and its JSON API.

Every ``/api/*`` call must carry a valid Telegram ``initData`` (sent in the
``X-Telegram-Init-Data`` header by the frontend). That both authenticates the
request and tells us which chat to subscribe for alerts. Set
``WEBAPP_ALLOW_INSECURE=1`` to bypass validation for local development only.
"""
from __future__ import annotations

import functools
import logging
import os
from typing import Any, Callable, Dict, List

from flask import Blueprint, g, jsonify, request, send_from_directory

from ..config import Settings, Watch
from ..core.matcher import filter_and_rank
from ..core.models import Listing
from ..service import DealService
from .auth import InvalidInitData, user_chat_id, verify_init_data

log = logging.getLogger(__name__)

_STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")


def _listing_json(l: Listing) -> Dict[str, Any]:
    return {
        "source": l.source,
        "id": l.listing_id,
        "title": l.title,
        "price": l.price,
        "price_str": l.price_str(),
        "url": l.url,
        "location": l.location,
        "condition": l.condition,
        "image_url": l.image_url,
    }


def create_webapp_blueprint(settings: Settings, service: DealService) -> Blueprint:
    bp = Blueprint("webapp", __name__)

    def require_telegram(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            init_data = request.headers.get("X-Telegram-Init-Data", "")
            if settings.webapp_allow_insecure:
                g.chat_id = request.headers.get("X-Debug-Chat-Id") or None
                g.verified = {}
                return fn(*args, **kwargs)
            try:
                verified = verify_init_data(init_data, settings.telegram_token)
            except InvalidInitData as exc:
                log.warning("rejected webapp request: %s", exc)
                return jsonify(error="unauthorized", detail=str(exc)), 401
            g.verified = verified
            g.chat_id = user_chat_id(verified)
            return fn(*args, **kwargs)

        return wrapper

    # ---- static page ----------------------------------------------------
    @bp.get("/webapp")
    @bp.get("/webapp/")
    def index():
        return send_from_directory(_STATIC_DIR, "index.html")

    @bp.get("/webapp/<path:filename>")
    def assets(filename: str):
        return send_from_directory(_STATIC_DIR, filename)

    # ---- API ------------------------------------------------------------
    @bp.post("/api/search")
    @require_telegram
    def api_search():
        query = (request.get_json(silent=True) or {}).get("query", "").strip()
        if not query:
            return jsonify(error="query required"), 400
        listings = service.search_once(query)
        # Cheapest known price first for a nicer default order.
        listings = filter_and_rank(listings, Watch(query=query))
        return jsonify(query=query, results=[_listing_json(l) for l in listings])

    @bp.get("/api/watches")
    @require_telegram
    def api_list_watches():
        builtin = [
            {"id": None, "builtin": True, "describe": w.describe(), **_watch_json(w)}
            for w in settings.default_watches
        ]
        user = [
            {"id": wid, "builtin": False, "describe": w.describe(), **_watch_json(w)}
            for wid, w in service.store.list_watches()
        ]
        return jsonify(builtin=builtin, user=user)

    @bp.post("/api/watches")
    @require_telegram
    def api_add_watch():
        data = request.get_json(silent=True) or {}
        query = (data.get("query") or "").strip()
        if not query:
            return jsonify(error="query required"), 400
        max_price = data.get("max_price")
        try:
            max_price = float(max_price) if max_price not in (None, "") else None
        except (TypeError, ValueError):
            max_price = None
        keywords = data.get("keywords") or []
        if isinstance(keywords, str):
            keywords = [k.strip() for k in keywords.split(";") if k.strip()]
        keywords = [str(k).lower() for k in keywords]
        watch = Watch(query=query, max_price=max_price, keywords=keywords)
        wid = service.store.add_watch(watch)
        if g.chat_id:
            service.store.add_subscriber(g.chat_id)
        return jsonify(id=wid, describe=watch.describe(), **_watch_json(watch))

    @bp.delete("/api/watches/<int:watch_id>")
    @require_telegram
    def api_remove_watch(watch_id: int):
        ok = service.store.remove_watch(watch_id)
        return jsonify(removed=ok, id=watch_id)

    @bp.post("/api/scan")
    @require_telegram
    def api_scan():
        hits = service.run_scan()
        payload = [
            {
                "watch": h.watch.describe(),
                "results": [_listing_json(l) for l in h.listings],
            }
            for h in hits
        ]
        return jsonify(hits=payload)

    return bp


def _watch_json(w: Watch) -> Dict[str, Any]:
    return {"query": w.query, "max_price": w.max_price, "keywords": list(w.keywords)}
