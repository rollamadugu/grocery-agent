"""Optimizer scenario tests — the cases the brief specifically calls out."""
from grocery_agent.models import Listing, Mode, Retailer, ShoppingItem, Unit
from grocery_agent.optimizer import optimize


_UNIT_BY_CAT = {"rice": Unit.G, "flour": Unit.G, "cooking_oil": Unit.ML, "shampoo": Unit.ML}


def L(id, retailer, category, price, qty=1, brand="B", unit=None):
    if unit is None:
        unit = _UNIT_BY_CAT.get(category, Unit.COUNT)   # match the item's dimension
    return Listing(id=id, retailer=retailer, category=category, brand=brand,
                   name=id, unit=unit, unit_qty=qty, price=price)


def used_retailers(plan):
    return {b.retailer for b in plan.baskets}


def test_split_is_chosen_when_cheaper():
    items = [ShoppingItem("a", "a", "soap", Unit.COUNT, 1),
             ShoppingItem("b", "b", "rice", Unit.G, 1000)]
    listings = [
        L("s1", "R1", "soap", 10), L("r1", "R1", "rice", 100, qty=1000),
        L("s2", "R2", "soap", 100), L("r2", "R2", "rice", 10, qty=1000),
    ]
    retailers = {"R1": Retailer("R1"), "R2": Retailer("R2")}
    plan = optimize(items, listings, retailers)
    assert plan.status == "OPTIMAL"
    assert used_retailers(plan) == {"R1", "R2"}      # soap@R1, rice@R2
    assert plan.total_cost == 20.0


def test_delivery_fee_forces_consolidation():
    items = [ShoppingItem("a", "a", "soap", Unit.COUNT, 1),
             ShoppingItem("b", "b", "rice", Unit.G, 1000)]
    listings = [
        L("s1", "R1", "soap", 10), L("r1", "R1", "rice", 60, qty=1000),
        L("s2", "R2", "soap", 9), L("r2", "R2", "rice", 61, qty=1000),
    ]
    # high delivery each -> splitting pays two fees; consolidating pays one
    retailers = {"R1": Retailer("R1", delivery_fee=50),
                 "R2": Retailer("R2", delivery_fee=50)}
    plan = optimize(items, listings, retailers)
    assert plan.status == "OPTIMAL"
    assert len(plan.baskets) == 1                    # consolidated
    assert plan.total_cost == 120.0                  # 70 items + 50 delivery


def test_minimum_order_rules_out_a_retailer():
    items = [ShoppingItem("a", "a", "soap", Unit.COUNT, 1)]
    listings = [L("s1", "R1", "soap", 5), L("s2", "R2", "soap", 8)]
    # R1 is cheaper per item but its min order can't be met by this small basket
    retailers = {"R1": Retailer("R1", min_order_value=100),
                 "R2": Retailer("R2", min_order_value=0)}
    plan = optimize(items, listings, retailers)
    assert plan.status == "OPTIMAL"
    assert used_retailers(plan) == {"R2"}
    assert plan.total_cost == 8.0


def test_basket_coupon_flips_to_consolidation():
    items = [ShoppingItem("a", "a", "soap", Unit.COUNT, 1),
             ShoppingItem("b", "b", "rice", Unit.G, 1000)]
    listings = [
        L("s1", "R1", "soap", 60), L("r1", "R1", "rice", 60, qty=1000),
        L("s2", "R2", "soap", 55), L("r2", "R2", "rice", 70, qty=1000),
    ]
    # buying both at R1 reaches the 100 coupon threshold -> -40
    retailers = {"R1": Retailer("R1", coupon_threshold=100, coupon_amount=40),
                 "R2": Retailer("R2")}
    plan = optimize(items, listings, retailers)
    assert plan.status == "OPTIMAL"
    assert used_retailers(plan) == {"R1"}
    assert plan.total_cost == 80.0                   # 120 - 40 coupon
    assert plan.baskets[0].coupon_discount == 40.0


def test_infeasible_when_item_unavailable():
    items = [ShoppingItem("a", "a", "nonexistent", Unit.COUNT, 1)]
    listings = [L("s1", "R1", "soap", 5)]
    plan = optimize(items, listings, {"R1": Retailer("R1")})
    assert plan.status == "INFEASIBLE"


def test_mandatory_brand_is_respected_even_if_pricier():
    items = [ShoppingItem("a", "a", "soap", Unit.COUNT, 1,
                          mode=Mode.BRAND, brand="Park Avenue")]
    listings = [
        L("pa", "R1", "soap", 50, brand="Park Avenue"),
        L("md", "R2", "soap", 10, brand="Medimix"),   # cheaper, wrong brand
    ]
    retailers = {"R1": Retailer("R1"), "R2": Retailer("R2")}
    plan = optimize(items, listings, retailers)
    assert plan.status == "OPTIMAL"
    assert used_retailers(plan) == {"R1"}
    assert plan.baskets[0].assignments[0].listing.brand == "Park Avenue"
    assert plan.total_cost == 50.0


def test_free_delivery_threshold_waives_fee():
    items = [ShoppingItem("a", "a", "rice", Unit.G, 1000)]
    listings = [L("r1", "R1", "rice", 250, qty=1000)]
    # 250 >= 200 threshold -> delivery waived
    retailers = {"R1": Retailer("R1", delivery_fee=40, free_delivery_threshold=200)}
    plan = optimize(items, listings, retailers)
    assert plan.status == "OPTIMAL"
    assert plan.baskets[0].delivery_fee == 0.0
    assert plan.total_cost == 250.0
