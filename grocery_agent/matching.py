"""Product matching: decide whether a listing can satisfy a shopping item.

Products are NOT matched just because names look similar. We check category,
measurement dimension, brand/variant (for brand-specific mode), availability and
user constraints, and return a confidence score. Low-confidence matches should be
confirmed by the user, never silently substituted.
"""
from __future__ import annotations

from dataclasses import dataclass

from .models import Listing, Mode, ShoppingItem
from .units import same_dimension

#: matches below this confidence need explicit user confirmation
CONFIRM_THRESHOLD = 0.7


@dataclass
class MatchResult:
    is_candidate: bool
    confidence: float
    reason: str

    @property
    def needs_confirmation(self) -> bool:
        return self.is_candidate and self.confidence < CONFIRM_THRESHOLD


def _norm(s: str | None) -> str:
    return (s or "").strip().lower()


def match(item: ShoppingItem, listing: Listing) -> MatchResult:
    """Can `listing` satisfy `item`? Returns candidacy + confidence + reason."""
    # hard disqualifiers --------------------------------------------------------
    if not listing.available:
        return MatchResult(False, 0.0, "listing unavailable")
    if _norm(item.category) != _norm(listing.category):
        return MatchResult(False, 0.0,
                           f"category mismatch ({item.category} != {listing.category})")
    if not same_dimension(item.unit, listing.unit):
        return MatchResult(False, 0.0,
                           f"unit dimension mismatch ({item.unit} != {listing.unit})")
    if _norm(listing.brand) in {_norm(b) for b in item.excluded_brands}:
        return MatchResult(False, 0.0, f"brand excluded ({listing.brand})")
    if item.max_unit_price is not None and listing.unit_price > item.max_unit_price:
        return MatchResult(False, 0.0,
                           f"unit price {listing.unit_price:.2f} over cap {item.max_unit_price}")

    # brand-specific mode: brand is mandatory ----------------------------------
    if item.mode == Mode.BRAND:
        if item.brand and _norm(item.brand) != _norm(listing.brand):
            return MatchResult(False, 0.0,
                               f"brand required ({item.brand}), listing is {listing.brand}")
        # variant check within the required brand
        if item.variant and _norm(item.variant) != _norm(listing.variant):
            # same brand, different variant -> candidate but low confidence
            return MatchResult(True, 0.5,
                               f"brand matches but variant differs "
                               f"({item.variant} vs {listing.variant or 'unspecified'})")
        return MatchResult(True, 1.0, "exact brand (and variant) match")

    # best-value mode: any valid brand in the category --------------------------
    conf = 0.9
    reason = "category match (best-value)"
    if item.variant:
        if _norm(item.variant) == _norm(listing.variant):
            conf = 0.95
            reason = "category + requested variant match"
        else:
            conf = 0.6
            reason = (f"variant preference not met "
                      f"({item.variant} vs {listing.variant or 'unspecified'})")
    return MatchResult(True, conf, reason)


def candidates(item: ShoppingItem, listings: list[Listing]) -> list[tuple[Listing, MatchResult]]:
    """All listings that could satisfy `item`, each with its match result."""
    out = []
    for lst in listings:
        res = match(item, lst)
        if res.is_candidate:
            out.append((lst, res))
    return out
