"""SQLite-backed persistence: seen listings, user watches and subscribers.

A tiny synchronous store is plenty here — traffic is a handful of writes every
few hours. All methods are safe to call from the bot handlers and the
scheduler because we open a short-lived connection per operation.

Note on Render: the free filesystem is ephemeral (wiped on redeploy/restart).
That only means the "seen" history resets, so you may get one repeat alert
after a deploy. Attach a Render Disk (mount at ./data) to make it durable.
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from typing import List, Optional

from ..config import Watch
from .models import Listing


class Store:
    def __init__(self, path: str):
        self.path = path
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS seen (
                    uid          TEXT PRIMARY KEY,
                    fingerprint  TEXT NOT NULL,
                    first_seen   REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS watches (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    query      TEXT NOT NULL,
                    max_price  REAL,
                    keywords   TEXT NOT NULL DEFAULT '[]',
                    created_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS subscribers (
                    chat_id    TEXT PRIMARY KEY,
                    added_at   REAL NOT NULL
                );
                """
            )

    # ---- de-duplication -------------------------------------------------
    def is_new(self, listing: Listing) -> bool:
        """Return True and record the listing if it hasn't been seen before.

        A listing whose price/title changed (new fingerprint) counts as new
        again, so price drops re-notify.
        """
        now = time.time()
        with self._conn() as conn:
            row = conn.execute(
                "SELECT fingerprint FROM seen WHERE uid = ?", (listing.uid,)
            ).fetchone()
            if row is not None and row["fingerprint"] == listing.fingerprint:
                return False
            conn.execute(
                "INSERT INTO seen (uid, fingerprint, first_seen) VALUES (?, ?, ?) "
                "ON CONFLICT(uid) DO UPDATE SET fingerprint = excluded.fingerprint",
                (listing.uid, listing.fingerprint, now),
            )
            return True

    def prune_seen(self, older_than_days: int = 30) -> int:
        cutoff = time.time() - older_than_days * 86400
        with self._conn() as conn:
            cur = conn.execute("DELETE FROM seen WHERE first_seen < ?", (cutoff,))
            return cur.rowcount

    # ---- watches --------------------------------------------------------
    def add_watch(self, watch: Watch) -> int:
        with self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO watches (query, max_price, keywords, created_at) "
                "VALUES (?, ?, ?, ?)",
                (watch.query, watch.max_price, json.dumps(watch.keywords), time.time()),
            )
            return int(cur.lastrowid)

    def list_watches(self) -> List[tuple[int, Watch]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT id, query, max_price, keywords FROM watches ORDER BY id"
            ).fetchall()
        out: List[tuple[int, Watch]] = []
        for r in rows:
            out.append(
                (
                    r["id"],
                    Watch(
                        query=r["query"],
                        max_price=r["max_price"],
                        keywords=json.loads(r["keywords"] or "[]"),
                    ),
                )
            )
        return out

    def remove_watch(self, watch_id: int) -> bool:
        with self._conn() as conn:
            cur = conn.execute("DELETE FROM watches WHERE id = ?", (watch_id,))
            return cur.rowcount > 0

    # ---- subscribers ----------------------------------------------------
    def add_subscriber(self, chat_id: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO subscribers (chat_id, added_at) VALUES (?, ?)",
                (str(chat_id), time.time()),
            )

    def remove_subscriber(self, chat_id: str) -> None:
        with self._conn() as conn:
            conn.execute("DELETE FROM subscribers WHERE chat_id = ?", (str(chat_id),))

    def list_subscribers(self) -> List[str]:
        with self._conn() as conn:
            rows = conn.execute("SELECT chat_id FROM subscribers").fetchall()
        return [r["chat_id"] for r in rows]
