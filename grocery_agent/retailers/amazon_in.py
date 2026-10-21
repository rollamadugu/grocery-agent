"""Amazon.in web-UI adapter: reads REAL, visible search-result prices.

This drives the public search results page (prices are visible without login).
If Amazon shows a bot/CAPTCHA wall, we surface that honestly instead of pretending
we got data: headed -> let the human solve it; headless -> raise BotChallenge.

Nothing is fabricated: every Listing is marked source='ui', verified=True, and
carries the exact product URL it was read from.
"""
from __future__ import annotations

import re
from typing import List
from urllib.parse import quote_plus

from ..models import Listing, Unit
from ..units import parse_measure
from .base import Capabilities, RetailerAdapter
from ..models import Retailer
from .playwright_base import BotChallenge, browser_page, looks_blocked, wait_for_human

SEARCH_URL = "https://www.amazon.in/s?k={q}"

# result card -> fields (semantic-ish; Amazon markup shifts, so we keep fallbacks)
_CARD = 'div[data-component-type="s-search-result"]'
_TITLE = ["[data-cy='title-recipe'] h2 span", "h2 span", "h2",
          "a[href*='/dp/'] span", "a.s-line-clamp-2 span"]
_PRICE = ["span.a-price span.a-offscreen", "span.a-price-whole"]
_LINK = ["a[href*='/dp/']", "h2 a", "a.a-link-normal.s-no-outline"]


def _longest_text(card, selectors):
    """Return the LONGEST text among all matches — the product title is longer
    than the brand/badge spans that share similar selectors."""
    best = ""
    for sel in selectors:
        for el in card.query_selector_all(sel):
            t = (el.inner_text() or "").strip()
            if len(t) > len(best):
                best = t
    return best


def _first_text(card, selectors):
    for sel in selectors:
        el = card.query_selector(sel)
        if el:
            t = (el.inner_text() or "").strip()
            if t:
                return t
    return ""


def _first_attr(card, selectors, attr):
    for sel in selectors:
        el = card.query_selector(sel)
        if el:
            v = el.get_attribute(attr)
            if v:
                return v
    return ""


def _price_to_float(text: str):
    m = re.search(r"[\d,]+(?:\.\d+)?", text.replace("\u20b9", ""))
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", ""))
    except ValueError:
        return None


class AmazonIndiaAdapter(RetailerAdapter):
    name = "Amazon"

    def __init__(self, headless: bool = True, max_results: int = 8):
        self.headless = headless
        self.max_results = max_results

    def retailer(self) -> Retailer:
        # NOTE: delivery/coupon economics are not reliably scrapeable from search;
        # left conservative and clearly approximate until read from a real basket.
        return Retailer(self.name, delivery_fee=0.0, min_order_value=0.0, live=True)

    def capabilities(self) -> Capabilities:
        return Capabilities(product_search=True, price_retrieval=True, live=True,
                            notes="Reads public search results via web UI. "
                                  "No login needed for prices. No cart automation. "
                                  "Blocked by CAPTCHA -> human solves (headed).")

    def _extract_on_page(self, page, query: str, category: str,
                         brand: str, idprefix: str) -> List[Listing]:
        listings: List[Listing] = []
        page.goto(SEARCH_URL.format(q=quote_plus(query)),
                  wait_until="domcontentloaded", timeout=45000)

        if looks_blocked(page):
            if self.headless:
                raise BotChallenge(
                    "Amazon.in returned a bot/CAPTCHA wall (headless). "
                    "Re-run headed so you can solve it.")
            wait_for_human(page, "Amazon showed a CAPTCHA / sign-in wall.")

        try:
            page.wait_for_selector(_CARD, timeout=15000)
        except Exception:
            if looks_blocked(page):
                raise BotChallenge("Amazon.in blocked the request (no results).")
            return listings  # genuinely no results

        for i, card in enumerate(page.query_selector_all(_CARD)):
            if len(listings) >= self.max_results:
                break
            title = _longest_text(card, _TITLE)
            price = _price_to_float(_first_text(card, _PRICE))
            href = _first_attr(card, _LINK, "href")
            if not title or price is None:
                continue  # sponsored/empty card -> skip, don't invent data
            measure = parse_measure(title)
            unit_qty, unit = measure if measure is not None else (1.0, Unit.COUNT)
            url = href if href.startswith("http") else f"https://www.amazon.in{href}"
            listings.append(Listing(
                id=f"{idprefix}_{i}", retailer=self.name, category=category,
                # brand from the ACTUAL product title (not the requested brand —
                # stamping the request would silently defeat brand matching)
                brand=title.split(" ")[0], name=title[:120],
                unit=unit, unit_qty=unit_qty, price=price,
                available=True, url=url, verified=True, source="ui"))
        return listings

    def search_text(self, query: str, category: str, brand: str = "") -> List[Listing]:
        with browser_page(headless=self.headless) as page:
            return self._extract_on_page(page, query, category, brand, "amazon")

    def _query_for(self, item) -> str:
        return " ".join(x for x in [item.brand or "", item.category.replace("_", " ")] if x)

    def search(self, item) -> List[Listing]:
        return self.search_text(self._query_for(item), item.category, item.brand or "")

    def search_items(self, items) -> List[Listing]:
        """Reuse ONE browser session for the whole shopping list (faster, and only
        one login/CAPTCHA if challenged)."""
        out: List[Listing] = []
        with browser_page(headless=self.headless) as page:
            for item in items:
                out.extend(self._extract_on_page(
                    page, self._query_for(item), item.category,
                    item.brand or "", f"amazon_{item.key}"))
        return out
