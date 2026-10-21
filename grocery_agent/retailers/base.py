"""Retailer adapter interface.

Every retailer integration implements this and HONESTLY declares what it can
actually do. The optimizer/UI only treat data as live/verified when the adapter
says so. A fixture adapter (synthetic dev data) must report live=False and must
NOT claim cart capabilities.
"""
from __future__ import annotations

import abc
import re
from dataclasses import dataclass
from typing import List

from ..models import Listing, Retailer, ShoppingItem


def build_search_query(item: ShoppingItem) -> str:
    """Generic portal search query for any item: brand + product type + every
    qualifier the AI captured (size/variety/style/form/scent...), de-duplicated.
    This is domain-agnostic — the qualifiers come from the parsed item, never from
    per-product rules — so e.g. 'Huggies diapers NB tape style' is searched as
    'Huggies diapers newborn tape' without special-casing diapers. Falls back to
    the shopper's raw phrase (annotations stripped) if nothing structured exists."""
    words: List[str] = []
    seen = set()
    for chunk in (item.brand or "", item.category.replace("_", " "),
                  getattr(item, "variant", "") or ""):
        for w in chunk.split():
            if w.lower() not in seen:
                seen.add(w.lower())
                words.append(w)
    q = " ".join(words).strip()
    if q:
        return q
    return re.sub(r"\[[^\]]*\]", "", item.text or "").strip()


@dataclass
class Capabilities:
    """What an adapter can genuinely do. Default: nothing — opt in explicitly."""
    product_search: bool = False
    price_retrieval: bool = False
    stock_check: bool = False
    cart_read: bool = False
    cart_add: bool = False
    cart_verify: bool = False
    live: bool = False          # True only for a real, ToS-permitted integration
    notes: str = ""


class RetailerAdapter(abc.ABC):
    name: str

    @abc.abstractmethod
    def retailer(self) -> Retailer:
        """Basket economics (fees, thresholds, min order)."""

    @abc.abstractmethod
    def capabilities(self) -> Capabilities:
        """Honest declaration of what this adapter can do."""

    @abc.abstractmethod
    def search(self, item: ShoppingItem) -> List[Listing]:
        """Return normalized listings that might satisfy `item`.
        Fixture adapters return synthetic data marked source='fixture'.
        Live adapters must only return data obtained through permitted means."""

    def add_to_cart(self, listing: Listing, packs: int):
        raise NotImplementedError(
            f"{self.name}: cart automation is not supported/permitted by this adapter")
