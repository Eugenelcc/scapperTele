"""The deal-hunting service that ties scrapers, storage and matching together.

Both the scheduled job and the on-demand HTTP/Telegram triggers call
:meth:`DealService.run_scan`. It is source- and transport-agnostic; the bot
layer decides how to deliver the results.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List

from .config import Settings, Watch
from .core.matcher import filter_and_rank
from .core.models import Listing
from .core.storage import Store
from .scrapers.registry import ScraperRegistry

log = logging.getLogger(__name__)


@dataclass
class WatchHits:
    watch: Watch
    listings: List[Listing]  # new + matching, ranked cheapest first


class DealService:
    def __init__(self, settings: Settings, store: Store, registry: ScraperRegistry):
        self.settings = settings
        self.store = store
        self.registry = registry

    def all_watches(self) -> List[Watch]:
        """Default watches (env) plus user-added watches (DB), de-duplicated."""
        watches: List[Watch] = list(self.settings.default_watches)
        seen = {(w.query.lower(), w.max_price, tuple(w.keywords)) for w in watches}
        for _id, watch in self.store.list_watches():
            key = (watch.query.lower(), watch.max_price, tuple(watch.keywords))
            if key not in seen:
                seen.add(key)
                watches.append(watch)
        return watches

    def search_once(self, query: str) -> List[Listing]:
        """One-off search with no de-dup (used by /search)."""
        return self.registry.search(query, limit=self.settings.max_results)

    def run_scan(self) -> List[WatchHits]:
        """Scan every watch and return only listings not seen before.

        Records everything it returns as "seen" so the next scan won't repeat
        it (unless the price/title changes).
        """
        results: List[WatchHits] = []
        for watch in self.all_watches():
            found = self.registry.search(watch.query, limit=self.settings.max_results)
            ranked = filter_and_rank(found, watch)
            fresh = [l for l in ranked if self.store.is_new(l)]
            if fresh:
                log.info("watch %s -> %d new listings", watch.describe(), len(fresh))
                results.append(WatchHits(watch=watch, listings=fresh))
        # Housekeeping so the DB doesn't grow forever.
        try:
            self.store.prune_seen(older_than_days=30)
        except Exception:  # pragma: no cover - non-critical
            log.debug("prune_seen failed", exc_info=True)
        return results
