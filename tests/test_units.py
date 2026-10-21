from grocery_agent.units import to_base, parse_measure, same_dimension
from grocery_agent.models import Unit
from grocery_agent.pricing import packs_needed


def test_mass_conversion():
    assert to_base(10, "kg") == (10000, Unit.G)
    assert to_base(500, "g") == (500, Unit.G)


def test_volume_conversion():
    assert to_base(2, "l") == (2000, Unit.ML)
    assert to_base(750, "ml") == (750, Unit.ML)


def test_count_conversion():
    assert to_base(10, "bars") == (10, Unit.COUNT)
    assert to_base(3, "") == (3, Unit.COUNT)


def test_parse_measure_from_text():
    assert parse_measure("one 10 kg rice bag") == (10000, Unit.G)
    assert parse_measure("2 shampoo bottles") is None   # no explicit measure


def test_dimension_guard():
    assert same_dimension(Unit.G, Unit.G)
    assert not same_dimension(Unit.G, Unit.ML)


def test_packs_needed_rounds_up():
    assert packs_needed(10, 5) == 2      # 10 bars from 5-packs -> 2
    assert packs_needed(10000, 5000) == 2  # 10kg from 5kg bags -> 2
    assert packs_needed(650, 340) == 2   # 650ml from 340ml bottles -> 2 (overbuy)
    assert packs_needed(3, 1) == 3
