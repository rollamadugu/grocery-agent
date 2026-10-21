"""Deterministic cost calculation (no AI, no guessing).

Given a retailer and an item subtotal, compute the basket-level charges exactly
as modeled: delivery (with free-delivery threshold), flat platform fee, and a
basket coupon (with its unlock threshold). Used both for reporting a solved plan
and for computing single-retailer baselines.
"""
from __future__ import annotations

import math
from typing import Dict, List

from .models import Listing, Retailer, ShoppingItem
from .matching import candidates


def packs_needed(required_qty: float, unit_qty: float) -> int:
    """Whole packs needed to meet a requirement (you can't buy half a bag)."""
    if unit_qty <= 0:
        return 0
    return math.ceil(required_qty / unit_qty)


def retailer_charges(retailer: Retailer, item_subtotal: float) -> Dict[str, float]:
    """Delivery, platform fee and coupon for a basket of the given subtotal.
    Charges are only applied when the basket is non-empty (subtotal > 0)."""
    if item_subtotal <= 0:
        return {"delivery_fee": 0.0, "platform_fee": 0.0, "coupon_discount": 0.0}

    delivery = retailer.delivery_fee
    if (retailer.free_delivery_threshold is not None
            and item_subtotal >= retailer.free_delivery_threshold):
        delivery = 0.0

    coupon = 0.0
    if (retailer.coupon_threshold is not None
            and item_subtotal >= retailer.coupon_threshold):
        coupon = retailer.coupon_amount

    return {"delivery_fee": round(delivery, 2),
            "platform_fee": round(retailer.platform_fee, 2),
            "coupon_discount": round(coupon, 2)}


def meets_min_order(retailer: Retailer, item_subtotal: float) -> bool:
    return item_subtotal >= retailer.min_order_value
