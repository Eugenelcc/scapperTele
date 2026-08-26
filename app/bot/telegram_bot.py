"""Telegram bot: command handlers, scheduled scan job and alert delivery."""
from __future__ import annotations

import asyncio
import logging
from typing import List

from telegram import Update
from telegram.constants import ParseMode
from telegram.error import TelegramError
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from ..config import Settings, Watch, _parse_watch
from ..service import DealService, WatchHits
from .formatting import format_alert, format_results

log = logging.getLogger(__name__)

HELP_TEXT = (
    "🤖 <b>Deal Hunter</b> — I sniff out cheap electronics on Carousell (SG).\n\n"
    "<b>Commands</b>\n"
    "/search &lt;what&gt; — search right now, e.g. <code>/search iphone 15 pro</code>\n"
    "/watch &lt;query&gt;|&lt;maxPrice&gt;|&lt;kw1;kw2&gt; — save a recurring watch\n"
    "   e.g. <code>/watch macbook air|1400|m2;m3</code>\n"
    "/watches — list your saved watches\n"
    "/unwatch &lt;id&gt; — remove a saved watch\n"
    "/scan — run all watches now and show new deals\n"
    "/subscribe — get automatic alerts in this chat\n"
    "/unsubscribe — stop automatic alerts\n"
    "/help — show this message\n\n"
    "I also scan on a schedule and message subscribers when new deals appear."
)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    service: DealService = context.application.bot_data["service"]
    chat_id = str(update.effective_chat.id)
    service.store.add_subscriber(chat_id)
    await update.message.reply_html(
        f"👋 Hi! You're subscribed to deal alerts in this chat.\n"
        f"(your chat id is <code>{chat_id}</code>)\n\n" + HELP_TEXT
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_html(HELP_TEXT)


async def cmd_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    service: DealService = context.application.bot_data["service"]
    query = " ".join(context.args).strip()
    if not query:
        await update.message.reply_html(
            "Tell me what to look for, e.g. <code>/search iphone 15</code>"
        )
        return
    await update.message.chat.send_action("typing")
    listings = await asyncio.to_thread(service.search_once, query)
    await update.message.reply_html(
        format_results(query, listings), disable_web_page_preview=True
    )


async def cmd_watch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    service: DealService = context.application.bot_data["service"]
    spec = " ".join(context.args).strip()
    watch = _parse_watch(spec)
    if watch is None:
        await update.message.reply_html(
            "Usage: <code>/watch query|maxPrice|kw1;kw2</code>\n"
            "Example: <code>/watch iphone 15|900|256;pro</code>"
        )
        return
    watch_id = service.store.add_watch(watch)
    service.store.add_subscriber(str(update.effective_chat.id))
    await update.message.reply_html(
        f"✅ Watch #{watch_id} saved: {watch.describe()}\n"
        f"I'll alert this chat when new matches appear."
    )


async def cmd_watches(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    service: DealService = context.application.bot_data["service"]
    rows = service.store.list_watches()
    defaults = service.settings.default_watches
    lines: List[str] = []
    if defaults:
        lines.append("<b>Built-in watches</b>")
        lines += [f"• {w.describe()}" for w in defaults]
    lines.append("<b>Your watches</b>")
    if rows:
        lines += [f"#{wid} — {w.describe()}" for wid, w in rows]
    else:
        lines.append("<i>none yet — add one with /watch</i>")
    await update.message.reply_html("\n".join(lines))


async def cmd_unwatch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    service: DealService = context.application.bot_data["service"]
    if not context.args or not context.args[0].lstrip("#").isdigit():
        await update.message.reply_html("Usage: <code>/unwatch &lt;id&gt;</code>")
        return
    watch_id = int(context.args[0].lstrip("#"))
    ok = service.store.remove_watch(watch_id)
    await update.message.reply_html(
        f"🗑️ Removed watch #{watch_id}." if ok else f"No watch #{watch_id} found."
    )


async def cmd_subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    service: DealService = context.application.bot_data["service"]
    service.store.add_subscriber(str(update.effective_chat.id))
    await update.message.reply_html("🔔 Subscribed. You'll get new-deal alerts here.")


async def cmd_unsubscribe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    service: DealService = context.application.bot_data["service"]
    service.store.remove_subscriber(str(update.effective_chat.id))
    await update.message.reply_html("🔕 Unsubscribed from automatic alerts.")


async def cmd_scan(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    service: DealService = context.application.bot_data["service"]
    await update.message.chat.send_action("typing")
    hits = await asyncio.to_thread(service.run_scan)
    if not hits:
        await update.message.reply_html("No new deals since the last scan. ✅")
        return
    for hit in hits:
        await update.message.reply_html(
            format_alert(hit.watch.describe(), hit.listings),
            disable_web_page_preview=True,
        )


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Treat any non-command text as a search query."""
    service: DealService = context.application.bot_data["service"]
    query = (update.message.text or "").strip()
    if not query:
        return
    await update.message.chat.send_action("typing")
    listings = await asyncio.to_thread(service.search_once, query)
    await update.message.reply_html(
        format_results(query, listings), disable_web_page_preview=True
    )


async def broadcast_hits(app: Application, hits: List[WatchHits]) -> None:
    service: DealService = app.bot_data["service"]
    subscribers = set(service.store.list_subscribers())
    if service.settings.telegram_chat_id:
        subscribers.add(service.settings.telegram_chat_id)
    if not subscribers:
        log.info("scan produced %d hit-groups but there are no subscribers", len(hits))
        return
    for hit in hits:
        text = format_alert(hit.watch.describe(), hit.listings)
        for chat_id in list(subscribers):
            try:
                await app.bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True,
                )
            except TelegramError as exc:
                log.warning("could not message %s: %s", chat_id, exc)


async def scheduled_scan(context: ContextTypes.DEFAULT_TYPE) -> None:
    service: DealService = context.application.bot_data["service"]
    log.info("running scheduled scan")
    hits = await asyncio.to_thread(service.run_scan)
    await broadcast_hits(context.application, hits)


def build_application(settings: Settings, service: DealService) -> Application:
    app = Application.builder().token(settings.telegram_token).build()
    app.bot_data["service"] = service

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("search", cmd_search))
    app.add_handler(CommandHandler("watch", cmd_watch))
    app.add_handler(CommandHandler("watches", cmd_watches))
    app.add_handler(CommandHandler("unwatch", cmd_unwatch))
    app.add_handler(CommandHandler("scan", cmd_scan))
    app.add_handler(CommandHandler("subscribe", cmd_subscribe))
    app.add_handler(CommandHandler("unsubscribe", cmd_unsubscribe))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    interval = max(0.25, settings.scan_interval_hours) * 3600
    if app.job_queue is not None:
        app.job_queue.run_repeating(
            scheduled_scan, interval=interval, first=60, name="scheduled_scan"
        )
        log.info("scheduled scan every %.2f h", settings.scan_interval_hours)
    else:  # pragma: no cover - only if job-queue extra missing
        log.warning("job queue unavailable; scheduled scans disabled")
    return app
