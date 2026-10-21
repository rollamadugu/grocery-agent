from grocery_agent.models import Listing, Mode, ShoppingItem, Unit
from grocery_agent.matching import match


def _soap_listing(brand="Park Avenue", unit=Unit.COUNT, qty=5, price=150, variant="",
                  available=True, category="soap"):
    return Listing(id="l1", retailer="R", category=category, brand=brand,
                   name=f"{brand} soap", unit=unit, unit_qty=qty, price=price,
                   variant=variant, available=available)


def test_category_mismatch_rejected():
    item = ShoppingItem("i", "soap", "soap", Unit.COUNT, 10)
    assert not match(item, _soap_listing(category="shampoo")).is_candidate


def test_unit_dimension_mismatch_rejected():
    # a soap requirement in COUNT can't be satisfied by a listing measured in grams
    item = ShoppingItem("i", "soap", "soap", Unit.COUNT, 10)
    assert not match(item, _soap_listing(unit=Unit.G)).is_candidate


def test_brand_required_rejects_other_brand():
    item = ShoppingItem("i", "soap", "soap", Unit.COUNT, 10,
                        mode=Mode.BRAND, brand="Park Avenue")
    assert not match(item, _soap_listing(brand="Medimix")).is_candidate
    r = match(item, _soap_listing(brand="Park Avenue"))
    assert r.is_candidate and r.confidence == 1.0


def test_excluded_brand_rejected():
    item = ShoppingItem("i", "soap", "soap", Unit.COUNT, 10, excluded_brands=["Medimix"])
    assert not match(item, _soap_listing(brand="Medimix")).is_candidate


def test_unavailable_rejected():
    item = ShoppingItem("i", "soap", "soap", Unit.COUNT, 10)
    assert not match(item, _soap_listing(available=False)).is_candidate


def test_variant_mismatch_low_confidence_needs_confirmation():
    item = ShoppingItem("i", "soap", "soap", Unit.COUNT, 10,
                        mode=Mode.BRAND, brand="Park Avenue", variant="lime")
    r = match(item, _soap_listing(brand="Park Avenue", variant="sandal"))
    assert r.is_candidate and r.needs_confirmation


def test_max_unit_price_cap():
    item = ShoppingItem("i", "soap", "soap", Unit.COUNT, 10, max_unit_price=20)
    # 150 for a 5-pack = 30/unit -> over the 20 cap
    assert not match(item, _soap_listing(price=150, qty=5)).is_candidate
