"""Unit normalization and pack math.

Everything in the system is reduced to a base unit per dimension:
  mass   -> grams (G)
  volume -> millilitres (ML)
  count  -> pieces (COUNT)

Correct unit math is what makes "a 5 kg bag" and "a 10 kg bag" comparable, and
stops a 100 g soap being treated as equal to a 125 g soap.
"""
from __future__ import annotations

import re
from typing import Tuple

from .models import Unit

_MASS = {"kg": 1000.0, "kgs": 1000.0, "kilogram": 1000.0, "kilograms": 1000.0,
         "g": 1.0, "gm": 1.0, "gms": 1.0, "gram": 1.0, "grams": 1.0}
_VOLUME = {"l": 1000.0, "ltr": 1000.0, "litre": 1000.0, "litres": 1000.0,
           "liter": 1000.0, "liters": 1000.0, "ml": 1.0, "millilitre": 1.0}
_COUNT = {"", "x", "pc", "pcs", "piece", "pieces", "unit", "units", "bar", "bars",
          "pack", "packs", "packet", "packets", "bottle", "bottles", "bag", "bags"}


def to_base(quantity: float, unit_word: str) -> Tuple[float, Unit]:
    """Convert a (quantity, unit-word) pair to (base_quantity, Unit)."""
    u = unit_word.strip().lower()
    if u in _MASS:
        return quantity * _MASS[u], Unit.G
    if u in _VOLUME:
        return quantity * _VOLUME[u], Unit.ML
    if u in _COUNT:
        return quantity, Unit.COUNT
    raise ValueError(f"unknown unit: {unit_word!r}")


_QTY_UNIT_RE = re.compile(
    r"(?P<qty>\d+(?:\.\d+)?)\s*(?P<unit>kgs?|kilograms?|gms?|grams?|g|ltr|litres?|liters?|l|ml|millilitres?)\b",
    re.IGNORECASE,
)


def parse_measure(text: str) -> Tuple[float, Unit] | None:
    """Pull the first explicit measure like '10 kg', '500g', '2 l' out of text.
    Returns (base_quantity, Unit) or None if there's no explicit measure."""
    m = _QTY_UNIT_RE.search(text)
    if not m:
        return None
    return to_base(float(m.group("qty")), m.group("unit"))


def same_dimension(a: Unit, b: Unit) -> bool:
    return a == b
