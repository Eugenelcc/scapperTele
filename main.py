"""Entry point.

Runs two things in one process:

* A Telegram bot (long-polling) with a repeating background scan job.
* A small Flask health server bound to ``$PORT`` so Render's web service stays
  alive and so ``/scan`` can be triggered on demand.

Start locally:  python main.py
Start on Render (web service):  python main.py
"""
from __future__ import annotations

import logging
import os
import threading
from typing import Optional

from werkzeug.serving import make_server
from telegram.ext import Application

from app.bot.telegram_bot import build_application
from app.config import load_settings
from app.core.storage import Store
from app.health import create_health_app
from app.scrapers.registry import ScraperRegistry
from app.service import DealService

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("deal-hunter")

# Filled in once the bot is built, so the health server can reach the job queue.
_application: Optional[Application] = None


def _run_health_server(port: int, settings, service=None) -> None:
    flask_app = create_health_app(settings, lambda: _application, service=service)
    server = make_server("0.0.0.0", port, flask_app)
    log.info("health server listening on :%d", port)
    server.serve_forever()


def main() -> None:
    global _application
    settings = load_settings()

    if not settings.has_token:
        # No bot -> no Mini App API, but keep the health port open so Render's
        # deploy is inspectable and the missing-token error is visible.
        threading.Thread(
            target=_run_health_server, args=(settings.port, settings), daemon=True
        ).start()
        log.error(
            "TELEGRAM_BOT_TOKEN is not set (or malformed). The health server is "
            "running, but the bot will not start. Set the token in your "
            "environment / Render dashboard and redeploy."
        )
        threading.Event().wait()  # block forever; keep the health port open
        return

    store = Store(os.path.join(settings.data_dir, "deals.db"))
    registry = ScraperRegistry.from_settings(settings)
    service = DealService(settings=settings, store=store, registry=registry)
    log.info("scraper backend: %s", settings.scraper_provider)

    # Health server + Mini App (page & API) share one port with the bot.
    threading.Thread(
        target=_run_health_server,
        args=(settings.port, settings, service),
        daemon=True,
    ).start()

    application = build_application(settings, service)
    _application = application

    if settings.has_webapp:
        log.info("Mini App available at %s/webapp", settings.webapp_url)
    else:
        log.info("WEBAPP_URL not set — Mini App menu button disabled")

    log.info("starting Telegram bot (long polling)")
    application.run_polling(allowed_updates=["message"])


if __name__ == "__main__":
    main()
