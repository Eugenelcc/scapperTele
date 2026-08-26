"""Scraper interface. Add a new marketplace by subclassing BaseScraper."""
from __future__ import annotations

import abc
from typing import List

from ..core.models import Listing


class BaseScraper(abc.ABC):
    #: short, stable identifier used in Listing.source and the registry
    name: str = "base"

    @abc.abstractmethod
    def search(self, query: str, limit: int = 40) -> List[Listing]:
        """Return listings for a free-text query, newest/most-relevant first.

        Implementations must never raise for ordinary network/parse issues —
        return an empty list and log instead, so one flaky source can't break a
        multi-source scan.
        """
        raise NotImplementedError
