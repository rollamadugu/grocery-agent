"""Canonical domain models for the grocery optimization agent.

These are the internal representations every retailer adapter normalizes INTO,
so listings from different platforms can be compared and optimized consistently.
Nothing here is retailer-specific.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional


class Unit(str, enum.Enum):
    """Base measurement dimension. All quantities are normalized to a base unit:
    COUNT (pieces), G (grams), ML (millilitres)."""
    COUNT = "count"
    G = "g"
    ML = "ml"


class Mode(str, enum.Enum):
    BRAND = "brand"            # Mode A: a specific brand/variant is required
    BEST_VALUE = "best_value"  # Mode B: cheapest valid option in the category


@dataclass
class Retailer:
    """A shopping platform and its basket-level economics."""
    name: str
    delivery_fee: float = 0.0
    free_delivery_threshold: Optional[float] = None   # subtotal >= this -> delivery free
    min_order_value: float = 0.0                       # a basket must reach this to be valid
    platform_fee: float = 0.0                          # flat handling/platform fee if used
    coupon_threshold: Optional[float] = None           # subtotal >= this unlocks a coupon
    coupon_amount: float = 0.0                          # flat amount knocked off when unlocked
    # Honest capability flags: what this adapter can ACTUALLY do (see adapters).
    live: bool = False                                 # True only for a real, permitted integration


@dataclass
class Listing:
    """One concrete product offer on one retailer, already normalized."""
    id: str
    retailer: str
    category: str                 # e.g. "soap", "cooking_oil", "rice"
    brand: str
    name: str
    unit: Unit
    unit_qty: float               # total base-unit quantity this ONE listing provides
                                  # (pack_size * pack_count): e.g. 4-bar pack -> 4 (COUNT);
                                  # a 5kg rice bag -> 5000 (G)
    price: float                  # advertised price for this listing
    discount_pct: float = 0.0     # item-level discount fraction [0,1]
    variant: str = ""             # formulation (e.g. "sunflower", "liquid"); "" = unspecified
    available: bool = True
    url: str = ""
    verified: bool = False        # True only if price was read from a live, permitted source
    source: str = "fixture"       # "fixture" (synthetic/dev) | "api" | "ui" (live)
    retrieved_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def landed_item_price(self) -> float:
        """Price after item-level discount (not including basket fees/coupons)."""
        return round(self.price * (1.0 - self.discount_pct), 2)

    @property
    def unit_price(self) -> float:
        """Price per single base unit, for apples-to-apples comparison."""
        return self.landed_item_price / self.unit_qty if self.unit_qty else float("inf")


@dataclass
class ShoppingItem:
    """One line of the user's shopping list, normalized to a base-unit requirement."""
    key: str                      # stable id for this line
    text: str                     # original phrase
    category: str
    unit: Unit
    required_qty: float           # total required, in base units (10 kg rice -> 10000 G)
    mode: Mode = Mode.BEST_VALUE
    brand: Optional[str] = None   # required brand for Mode.BRAND
    variant: Optional[str] = None
    excluded_brands: List[str] = field(default_factory=list)
    max_unit_price: Optional[float] = None


@dataclass
class Assignment:
    """How many of a listing to buy to (partly) satisfy an item."""
    item_key: str
    listing: Listing
    packs: int

    @property
    def provided_qty(self) -> float:
        return self.packs * self.listing.unit_qty

    @property
    def cost(self) -> float:
        return round(self.packs * self.listing.landed_item_price, 2)


@dataclass
class RetailerBasket:
    retailer: str
    assignments: List[Assignment] = field(default_factory=list)
    item_subtotal: float = 0.0
    delivery_fee: float = 0.0
    platform_fee: float = 0.0
    coupon_discount: float = 0.0

    @property
    def total(self) -> float:
        return round(self.item_subtotal + self.delivery_fee + self.platform_fee
                     - self.coupon_discount, 2)


@dataclass
class Plan:
    baskets: List[RetailerBasket]
    status: str                        # "OPTIMAL" | "INFEASIBLE" | ...
    total_cost: float
    baseline_single_retailer: dict = field(default_factory=dict)  # retailer -> total if all-from-one
    savings_vs_best_single: float = 0.0
    notes: List[str] = field(default_factory=list)
