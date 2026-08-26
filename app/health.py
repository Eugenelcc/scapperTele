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

log = logging.getLogger(__name__)


def create_health_app(
    settings: Settings, get_application: Callable[[], Optional[Application]]
) -> Flask:
    flask_app = Flask(__name__)

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

    return flask_app
