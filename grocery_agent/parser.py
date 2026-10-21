"""Natural-language shopping-list parser (deterministic first pass).

Turns "Buy 10 Park Avenue soaps, 3 packets of cooking oil, one 10 kg rice bag,
2 detergent soaps and 2 shampoo bottles" into normalized ShoppingItems.

This is a rule-based parser: transparent and testable. Ambiguous phrases are a
good place to later add AI assistance, but pricing/optimization never depend on
the LLM. Any assumption (e.g. a default bottle size) is recorded on the item text
so the UI can surface it for confirmation.
"""
from __future__ import annotations

import re
from typing import List, Optional

from .models import Mode, ShoppingItem, Unit
from .units import parse_measure

_NUM_WORDS = {
    "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
    "twelve": 12, "a dozen": 12, "dozen": 12,
}

# category keyword -> canonical category + base unit for count-expressed liquids
_CATEGORIES = {
    "soap": ("soap", Unit.COUNT, None),
    "cooking oil": ("cooking_oil", Unit.ML, 1000),  # 1 packet ~ 1 L (assumption)
    "oil": ("cooking_oil", Unit.ML, 1000),
    "rice": ("rice", Unit.G, None),
    "detergent": ("detergent", Unit.COUNT, None),
    "shampoo": ("shampoo", Unit.ML, 325),           # 1 bottle ~ 325 ml (assumption)
    "flour": ("flour", Unit.G, None),
    "atta": ("flour", Unit.G, None),
}

_BRANDS = ["Park Avenue", "Fortune", "Surf Excel", "India Gate", "Daawat",
           "Clinic Plus", "Medimix", "Tide", "Ariel", "Saffola"]


def _leading_quantity(frag: str) -> float:
    m = re.match(r"\s*(\d+(?:\.\d+)?)", frag)
    if m:
        return float(m.group(1))
    words = frag.lower().split()
    if words and words[0] in _NUM_WORDS:
        return float(_NUM_WORDS[words[0]])
    return 1.0


def _find_brand(frag: str) -> Optional[str]:
    low = frag.lower()
    for b in _BRANDS:
        if b.lower() in low:
            return b
    return None


def _find_category(frag: str):
    low = frag.lower()
    # prefer multi-word keys first ("cooking oil" before "oil")
    for kw in sorted(_CATEGORIES, key=lambda k: -len(k)):
        if kw in low:
            return _CATEGORIES[kw]
    return None


def parse_list(text: str) -> List[ShoppingItem]:
    text = re.sub(r"^\s*(please\s+)?(buy|get|order|add)\b", "", text.strip(),
                  flags=re.IGNORECASE)
    fragments = re.split(r",|\band\b", text, flags=re.IGNORECASE)

    items: List[ShoppingItem] = []
    i = 0
    for frag in fragments:
        frag = frag.strip()
        if not frag:
            continue
        cat = _find_category(frag)
        if not cat:
            continue
        category, unit, default_size = cat
        brand = _find_brand(frag)

        measure = parse_measure(frag)      # explicit "10 kg", "3 l", "500 g"?
        note = ""
        if measure is not None:
            required_qty, unit = measure
        elif unit in (Unit.G, Unit.ML) and default_size:
            count = _leading_quantity(frag)
            required_qty = count * default_size
            note = f" [assumed {int(default_size)}{unit.value}/unit]"
        else:
            required_qty = _leading_quantity(frag)
            unit = Unit.COUNT

        i += 1
        items.append(ShoppingItem(
            key=f"{category}_{i}",
            text=frag + note,
            category=category,
            unit=unit,
            required_qty=required_qty,
            mode=Mode.BRAND if brand else Mode.BEST_VALUE,
            brand=brand,
        ))
    return items
