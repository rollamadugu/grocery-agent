"""AI semantic product matching backed by a LOCAL LLM (Ollama / llama3.1).

Why AI here: live adapters stamp the requested category onto every listing (so
the optimizer's category check always passes for live data). That means a search
for "toor dal" would otherwise let "moong dal", "masoor dal" or "chana" through.
A local LLM judges whether each candidate's real product NAME is actually the
thing the shopper asked for (and the right brand, when a brand is required).

Honest-by-design (same rules as the AI parser):
- Local Ollama only; temperature 0; JSON-constrained; ONE batched call per item.
- The LLM only FILTERS the rule-based candidate set (hard constraints such as
  availability, unit dimension and price cap are still enforced by matching.py).
- If Ollama is unavailable or returns unusable output, we fall back to the
  rule-based candidates unchanged (never silently drop everything).
"""
from __future__ import annotations

import json
from typing import List, Optional, Set, Tuple

from .llm_parser import _ollama_generate  # reuse the same local-Ollama client
from .matching import MatchResult, candidates
from .models import Listing, Mode, ShoppingItem

_MATCH_PROMPT = """You match grocery search results to a shopper's request. Be strict.

Request:
- product: %(product)s
- category: %(category)s
- brand required: %(brand)s
- variant/notes: %(variant)s

Candidates (index: product name):
%(cands)s

Return ONLY JSON: {"matches":[<indices of candidates that are the SAME product the shopper asked for>]}
Rules:
- Strict on product TYPE: e.g. "toor dal"/"arhar dal" match toor dal, but "moong dal",
  "masoor dal", "chana", "urad" do NOT. Sunflower oil does not match coconut oil, etc.
- If a brand is required, include only that brand.
- Different PACK SIZES of the correct product still match (size is handled elsewhere).
- Include only clear matches; when unsure, exclude.
"""


def _llm_judge(item: ShoppingItem, listings: List[Listing]) -> Optional[Set[str]]:
    """Return the set of listing ids the LLM judges to match, or None on failure."""
    lines = "\n".join(f"{i}: {l.name}" for i, l in enumerate(listings))
    prompt = _MATCH_PROMPT % {
        "product": item.text, "category": item.category,
        "brand": item.brand if (item.mode == Mode.BRAND and item.brand) else "none",
        "variant": item.variant or "none", "cands": lines,
    }
    raw = _ollama_generate(prompt)
    obj = json.loads(raw)
    idxs = obj.get("matches", [])
    keep: Set[str] = set()
    for v in idxs:
        try:
            i = int(v)
        except (TypeError, ValueError):
            continue
        if 0 <= i < len(listings):
            keep.add(listings[i].id)
    return keep


def llm_candidates(item: ShoppingItem,
                   listings: List[Listing]) -> List[Tuple[Listing, MatchResult]]:
    """Rule-based candidates, then an LLM relevance filter over their names.
    Falls back to the rule-based candidates if the LLM is unavailable/unusable."""
    base = candidates(item, listings)          # hard constraints + confidence
    if len(base) <= 1:
        return base                            # nothing to disambiguate
    try:
        keep = _llm_judge(item, [l for l, _ in base])
    except Exception:
        return base                            # LLM ERRORED -> keep rule-based set
    # LLM ran successfully: TRUST its verdict, even if it rejects everything (e.g.
    # a "soap" search that only returned skincare). Showing a wrong product as a
    # match would be dishonest; an empty result makes the plan flag that item
    # honestly rather than charging the user for the wrong thing.
    return [(l, res) for (l, res) in base if l.id in keep]
