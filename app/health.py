"""A tiny HTTP server so Render's web service has a port to health-check,
and so the scan can be triggered on demand (e.g. by an external cron pinger).
"""
from __future__ import annotations

import logging
from typing import Callable, Optional

from flask import Flask, jsonify, request
from telegram.ext import Application

from .bot.telegram_bot import scheduled_scan
from .config import Settings
from .service import DealService
from .webapp.api import create_webapp_blueprint

log = logging.getLogger(__name__)


def create_health_app(
    settings: Settings,
    get_application: Callable[[], Optional[Application]],
    service: Optional[DealService] = None,
) -> Flask:
    flask_app = Flask(__name__)

    # Mount the Telegram Mini App (page + JSON API) when the bot is configured.
    if service is not None:
        flask_app.register_blueprint(create_webapp_blueprint(settings, service))

    @flask_app.get("/")
    def index():
        return jsonify(service="deal-hunter", status="ok")

    @flask_app.get("/healthz")
    def healthz():
        return jsonify(ok=True)

    @flask_app.get("/scan")
    def scan():
        token = request.args.get("token", "")
        if settings.scan_token and token != settings.scan_token:
            return jsonify(error="unauthorized"), 401
        application = get_application()
        if application is None or application.job_queue is None:
            return jsonify(error="bot not ready"), 503
        application.job_queue.run_once(scheduled_scan, when=1, name="manual_scan")
        return jsonify(status="scan scheduled")

    @flask_app.get("/debug/carousell")
    def debug_carousell():
        """Diagnose why a search returns nothing. Guarded by SCAN_TOKEN.
        Example: /debug/carousell?token=YOUR_SCAN_TOKEN&q=iphone
        """
        token = request.args.get("token", "")
        if settings.scan_token and token != settings.scan_token:
            return jsonify(error="unauthorized"), 401
        from .scrapers.carousell import CarousellScraper
        from .scrapers.fetcher import fetcher_from_settings

        query = request.args.get("q", "iphone")
        scraper = CarousellScraper(
            host=settings.carousell_host, fetcher=fetcher_from_settings(settings)
        )
        return jsonify(scraper.diagnostics(query))

    return flask_app
