"""Retailer adapter interface.

Every retailer integration implements this and HONESTLY declares what it can
actually do. The optimizer/UI only treat data as live/verified when the adapter
says so. A fixture adapter (synthetic dev data) must report live=False and must
NOT claim cart capabilities.
"""
from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import List

from ..models import Listing, Retailer, ShoppingItem


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
