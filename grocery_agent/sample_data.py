"""CLEARLY-LABELED SYNTHETIC DATA for development and tests only.

These are NOT real prices and must never be presented as live retailer data.
Every listing is marked source='fixture', verified=False. Real integrations
replace this via RetailerAdapter implementations.
"""
from __future__ import annotations

from typing import Dict, List, Tuple

from .models import Listing, Mode, Retailer, ShoppingItem, Unit


def sample_retailers() -> Dict[str, Retailer]:
    return {
        "Flipkart":  Retailer("Flipkart", delivery_fee=40, free_delivery_threshold=500,
                              min_order_value=0, coupon_threshold=600, coupon_amount=50),
        "AmazonNow": Retailer("AmazonNow", delivery_fee=30, free_delivery_threshold=499,
                              min_order_value=99),
        "Zepto":     Retailer("Zepto", delivery_fee=25, free_delivery_threshold=199,
                              min_order_value=100, platform_fee=10),
        "BigBasket": Retailer("BigBasket", delivery_fee=35, free_delivery_threshold=600,
                              min_order_value=0),
    }


def _L(id, retailer, category, brand, unit, unit_qty, price, disc=0.0, variant="") -> Listing:
    return Listing(id=id, retailer=retailer, category=category, brand=brand,
                   name=f"{brand} {category}", unit=unit, unit_qty=unit_qty,
                   price=price, discount_pct=disc, variant=variant,
                   source="fixture", verified=False, url=f"https://example.test/{id}")


def sample_listings() -> List[Listing]:
    """Synthetic listings across 4 retailers, mixed so the optimal plan is a split."""
    return [
        # --- soap (COUNT) : user wants 10 bars ---
        _L("fk_soap_pa", "Flipkart", "soap", "Park Avenue", Unit.COUNT, 5, 150, 0.10),   # 30/bar after disc
        _L("az_soap_pa", "AmazonNow", "soap", "Park Avenue", Unit.COUNT, 10, 320),        # 32/bar
        _L("zp_soap_pa", "Zepto", "soap", "Park Avenue", Unit.COUNT, 1, 36),              # 36/bar
        _L("bb_soap_gen", "BigBasket", "soap", "Medimix", Unit.COUNT, 4, 112),            # best-value option

        # --- cooking oil (ML) : user wants 3 L sunflower ---
        _L("fk_oil", "Flipkart", "cooking_oil", "Fortune", Unit.ML, 1000, 150, 0.0, "sunflower"),
        _L("az_oil", "AmazonNow", "cooking_oil", "Fortune", Unit.ML, 1000, 140, 0.0, "sunflower"),
        _L("bb_oil", "BigBasket", "cooking_oil", "Fortune", Unit.ML, 5000, 640, 0.0, "sunflower"),  # 128/L

        # --- rice (G) : user wants 10 kg ---
        _L("bb_rice", "BigBasket", "rice", "India Gate", Unit.G, 10000, 820),
        _L("fk_rice", "Flipkart", "rice", "India Gate", Unit.G, 5000, 430),
        _L("zp_rice", "Zepto", "rice", "Daawat", Unit.G, 5000, 445),

        # --- detergent (COUNT bars) : user wants 2 ---
        _L("zp_det", "Zepto", "detergent", "Surf Excel", Unit.COUNT, 1, 22),
        _L("fk_det", "Flipkart", "detergent", "Surf Excel", Unit.COUNT, 2, 46),

        # --- shampoo (ML) : user wants 2 bottles ~ 650 ml total ---
        _L("az_sham", "AmazonNow", "shampoo", "Clinic Plus", Unit.ML, 650, 180, 0.0, "strong"),
        _L("fk_sham", "Flipkart", "shampoo", "Clinic Plus", Unit.ML, 340, 99, 0.0, "strong"),
    ]


def sample_items() -> List[ShoppingItem]:
    """The canonical example list from the brief, as normalized items."""
    return [
        ShoppingItem("soap", "10 Park Avenue soaps", "soap", Unit.COUNT, 10,
                     mode=Mode.BRAND, brand="Park Avenue"),
        ShoppingItem("oil", "3 L cooking oil (sunflower)", "cooking_oil", Unit.ML, 3000,
                     mode=Mode.BEST_VALUE, variant="sunflower"),
        ShoppingItem("rice", "10 kg rice", "rice", Unit.G, 10000, mode=Mode.BEST_VALUE),
        ShoppingItem("detergent", "2 detergent soaps", "detergent", Unit.COUNT, 2,
                     mode=Mode.BEST_VALUE),
        ShoppingItem("shampoo", "2 shampoo bottles (~650 ml)", "shampoo", Unit.ML, 650,
                     mode=Mode.BEST_VALUE),
    ]


def sample_scenario() -> Tuple[List[ShoppingItem], List[Listing], Dict[str, Retailer]]:
    return sample_items(), sample_listings(), sample_retailers()
