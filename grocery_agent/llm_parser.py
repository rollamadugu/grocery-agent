"""AI shopping-list parser backed by a LOCAL LLM (Ollama / llama3.1).

Why AI here: the rule-based parser (parser.py) only understands a fixed category
dictionary, so anything outside it (e.g. "toor dal", an unusual brand) is dropped.
A local LLM reads free text robustly and emits the SAME ShoppingItem structures.

Honest-by-design:
- Runs entirely locally via Ollama (no external API, no data leaves the machine).
- Temperature 0 + JSON-constrained output for repeatable parses.
- If Ollama is unavailable or returns unusable output, we FALL BACK to the
  rule-based parser and say so (the engine label is surfaced to the UI/CLI).
- The LLM only STRUCTURES the request. It never invents prices and the optimizer
  never depends on it.
"""
from __future__ import annotations

import json
import os
import urllib.request
from typing import List, Tuple

from .models import Mode, ShoppingItem, Unit
from .parser import parse_list
from .units import to_base

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("GROCERY_LLM_MODEL", "llama3.1:8b")

_PROMPT = """You convert a grocery shopping list written in plain English (often \
Indian groceries) into structured JSON. Return ONLY a JSON object of the form:
{"items":[{"raw_text":"...","category":"snake_case_noun","brand":"Brand or null",\
"quantity":<number>,"unit":"kg|g|l|ml|count","mode":"brand|best_value"}]}

Rules:
- category: a short snake_case canonical noun for the PRODUCT TYPE, brand removed.
  Examples: "toor dal" -> "toor_dal"; "Daawat basmati rice" -> "rice";
  "Parachute coconut oil" -> "coconut_oil"; "Park Avenue soap" -> "bath_soap".
- brand: the brand if one is explicitly named, else null. If a brand is named set
  mode="brand"; otherwise mode="best_value".
- quantity + unit = the TOTAL the user wants.
  "10 kg rice" -> quantity 10, unit "kg". "10 soaps" -> 10, "count".
  "2 L oil" -> 2, "l". "500 g dal" -> 500, "g".
  If an item is counted (e.g. "3 packets") with no weight/volume given, use unit
  "count" and that count as quantity. Do NOT guess a pack size.
- One object per distinct product. Do not invent items that aren't in the list.

Shopping list: %s
"""

# map assorted unit words the model might emit onto words units.to_base understands
_UNIT_MAP = {
    "kg": "kg", "kgs": "kg", "kilogram": "kg", "kilograms": "kg",
    "g": "g", "gm": "g", "gms": "g", "gram": "g", "grams": "g",
    "l": "l", "ltr": "l", "litre": "l", "litres": "l", "liter": "l", "liters": "l",
    "ml": "ml",
    "count": "", "piece": "", "pieces": "", "unit": "", "units": "",
    "pack": "", "packs": "", "packet": "", "packets": "", "": "",
}


def _ollama_generate(prompt: str, timeout: float = 90.0) -> str:
    body = json.dumps({
        "model": OLLAMA_MODEL, "prompt": prompt, "stream": False,
        "format": "json", "options": {"temperature": 0},
    }).encode()
    req = urllib.request.Request(
        OLLAMA_URL + "/api/generate", data=body,
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode()).get("response", "")


def _coerce_items(arr: list, fallback_text: str) -> List[ShoppingItem]:
    items: List[ShoppingItem] = []
    for i, it in enumerate(arr, 1):
        if not isinstance(it, dict):
            continue
        cat = str(it.get("category") or "").strip().lower().replace(" ", "_")
        if not cat:
            continue
        try:
            qty = float(it.get("quantity") or 1)
        except (TypeError, ValueError):
            qty = 1.0
        uword = str(it.get("unit") or "count").strip().lower()
        base_word = _UNIT_MAP.get(uword, "")
        try:
            req_qty, unit = to_base(qty, base_word)
        except ValueError:
            req_qty, unit = qty, Unit.COUNT

        brand = it.get("brand")
        if not isinstance(brand, str) or brand.strip().lower() in ("", "null", "none"):
            brand = None
        mode = Mode.BRAND if (brand or str(it.get("mode", "")).lower() == "brand") \
            else Mode.BEST_VALUE

        items.append(ShoppingItem(
            key=f"{cat}_{i}",
            text=str(it.get("raw_text") or fallback_text),
            category=cat, unit=unit, required_qty=req_qty,
            mode=mode, brand=brand))
    return items


def parse_list_smart(text: str) -> Tuple[List[ShoppingItem], str]:
    """Parse with the local LLM; fall back to the rule parser. Returns
    (items, engine_label) so callers can show which engine actually ran."""
    try:
        raw = _ollama_generate(_PROMPT % text)
        obj = json.loads(raw)
        items = _coerce_items(obj.get("items", []), text)
        if items:
            return items, f"AI (Ollama {OLLAMA_MODEL}, local)"
    except Exception:
        pass
    return parse_list(text), "rule-based (LLM unavailable)"
