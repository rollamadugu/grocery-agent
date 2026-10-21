"""Flipkart web-UI adapter.

Reads the public search results page. Flipkart pops a login modal on load (we
dismiss it with Escape, we do NOT log in for you) and uses obfuscated, frequently
changing CSS classes — so we extract robustly: each product tile is a
`div[data-id]`; the title comes from the product link, the price from the first
rupee amount in the tile. Blocked/empty is reported honestly, never faked.
"""
from __future__ import annotations

from typing import List
from urllib.parse import quote_plus

from ..models import Listing, Retailer, Unit
from ..units import parse_measure
from .base import Capabilities, RetailerAdapter
from .playwright_base import (BotChallenge, browser_page, first_attr, longest_text,
                              looks_blocked, rupee_amount, wait_for_human)

SEARCH_URL = "https://www.flipkart.com/search?q={q}"
_CARD = "div[data-id]"
_LINK = ["a[href*='/p/']"]


class FlipkartAdapter(RetailerAdapter):
    name = "Flipkart"

    def __init__(self, headless: bool = True, max_results: int = 8):
        self.headless = headless
        self.max_results = max_results

    def retailer(self) -> Retailer:
        return Retailer(self.name, delivery_fee=0.0, min_order_value=0.0, live=True)

    def capabilities(self) -> Capabilities:
        return Capabilities(product_search=True, price_retrieval=True, live=True,
                            notes="Public search via web UI; dismisses login modal; "
                                  "no cart. Obfuscated markup -> robust extraction.")

    def _extract(self, page, query, category, brand, idp) -> List[Listing]:
        out: List[Listing] = []
        page.goto(SEARCH_URL.format(q=quote_plus(query)),
                  wait_until="domcontentloaded", timeout=45000)
        # dismiss the login modal if present
        try:
            page.keyboard.press("Escape")
            page.wait_for_timeout(500)
        except Exception:
            pass
        if looks_blocked(page):
            if self.headless:
                raise BotChallenge("Flipkart returned a bot/login wall (headless).")
            wait_for_human(page, "Flipkart showed a login/CAPTCHA wall.")
        try:
            page.wait_for_selector(_CARD, timeout=12000)
        except Exception:
            return out  # no results / not rendered
        for i, card in enumerate(page.query_selector_all(_CARD)):
            if len(out) >= self.max_results:
                break
            href = first_attr(card, _LINK, "href")
            if not href or "/p/" not in href:
                continue
            title = (first_attr(card, _LINK, "title")
                     or longest_text(card, _LINK + ["a", "div"]))
            title = (title or "").split("\n")[0].strip()   # drop rating/badge lines
            price = rupee_amount(card.inner_text())          # must follow a ₹ sign
            if not title or price is None:
                continue
            measure = parse_measure(title) or parse_measure(card.inner_text())
            unit_qty, unit = measure if measure is not None else (1.0, Unit.COUNT)
            url = href if href.startswith("http") else f"https://www.flipkart.com{href}"
            out.append(Listing(id=f"{idp}_{i}", retailer=self.name, category=category,
                               brand=(brand or title.split(" ")[0]), name=title[:120],
                               unit=unit, unit_qty=unit_qty, price=price,
                               available=True, url=url, verified=True, source="ui"))
        return out

    def _q(self, item):
        return " ".join(x for x in [item.brand or "", item.category.replace("_", " ")] if x)

    def search(self, item) -> List[Listing]:
        with browser_page(headless=self.headless) as page:
            return self._extract(page, self._q(item), item.category, item.brand or "", "fk")

    def search_items(self, items) -> List[Listing]:
        out: List[Listing] = []
        with browser_page(headless=self.headless) as page:
            for item in items:
                out.extend(self._extract(page, self._q(item), item.category,
                                         item.brand or "", f"fk_{item.key}"))
        return out
