from grocery_agent.parser import parse_list
from grocery_agent.models import Mode, Unit


def test_parses_the_canonical_list():
    text = ("Buy 10 Park Avenue soaps, 3 packets of cooking oil, "
            "one 10 kg rice bag, 2 detergent soaps and 2 shampoo bottles")
    items = parse_list(text)
    cats = {i.category: i for i in items}

    assert set(cats) == {"soap", "cooking_oil", "rice", "detergent", "shampoo"}

    # brand-specific soap
    assert cats["soap"].mode == Mode.BRAND
    assert cats["soap"].brand == "Park Avenue"
    assert cats["soap"].unit == Unit.COUNT
    assert cats["soap"].required_qty == 10

    # explicit measure wins: 10 kg -> 10000 g
    assert cats["rice"].unit == Unit.G
    assert cats["rice"].required_qty == 10000

    # count-expressed liquid uses a default size (assumption recorded in text)
    assert cats["cooking_oil"].unit == Unit.ML
    assert cats["cooking_oil"].required_qty == 3000       # 3 packets * 1000 ml
    assert "assumed" in cats["cooking_oil"].text

    assert cats["shampoo"].unit == Unit.ML
    assert cats["shampoo"].required_qty == 650            # 2 bottles * 325 ml

    assert cats["detergent"].required_qty == 2


def test_best_value_when_no_brand():
    items = parse_list("5 kg rice")
    assert items[0].mode == Mode.BEST_VALUE
    assert items[0].required_qty == 5000
