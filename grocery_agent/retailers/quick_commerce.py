"""Blinkit and Swiggy Instamart web-UI adapters (quick-commerce).

These are location-walled single-page apps: they show no products until a
delivery location is set, and they run heavy anti-bot protection. We detect the
location/bot wall and:
  - headed  -> ask the human to set the location, then read what renders;
  - headless -> report honestly that no data was obtained (NOT faked).

Extraction is markup-agnostic (price-anchored scan) because their CSS classes are
obfuscated and change constantly. If nothing renders, we return empty with a
clear reason. We never fabricate listings for a site that didn't serve them.
"""
from __future__ import annotations

from typing import List
from urllib.parse import quote_plus

from ..models import Listing, Retailer, Unit
from ..units import parse_measure
from .base import Capabilities, RetailerAdapter
from .playwright_base import (browser_page, js_scan, looks_blocked, needs_location,
                              price_inr, wait_for_human)


class _QuickCommerceAdapter(RetailerAdapter):
    search_url = ""          # set by subclass, with {q}
    name = ""

    def __init__(self, headless: bool = True, max_results: int = 8):
        self.headless = headless
        self.max_results = max_results

    def retailer(self) -> Retailer:
        return Retailer(self.name, delivery_fee=0.0, min_order_value=0.0, live=True)

    def capabilities(self) -> Capabilities:
        return Capabilities(product_search=True, price_retrieval=True, live=True,
                            notes="Location-walled SPA; needs delivery location set "
                                  "(headed/human). Often blocked for automation; "
                                  "reports no-data honestly when so. No cart.")

    def _extract(self, page, query, category, brand, idp) -> List[Listing]:
        page.goto(self.search_url.format(q=quote_plus(query)),
                  wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(2500)  # SPA needs a moment to render/XHR

        if needs_location(page) or looks_blocked(page):
            if self.headless:
                # honest: we did not get data (location/bot wall) — don't invent any
                return []
            wait_for_human(page, f"{self.name}: set your delivery location / sign in, "
                                 f"then search for '{query}' if needed.")
            page.wait_for_timeout(1500)

        rows = js_scan(page)
        out: List[Listing] = []
        for i, r in enumerate(rows):
            if len(out) >= self.max_results:
                break
            price = price_inr(r["price"])
            title = r["title"]
            if price is None or not title:
                continue
            measure = parse_measure(title)
            unit_qty, unit = measure if measure is not None else (1.0, Unit.COUNT)
            out.append(Listing(id=f"{idp}_{i}", retailer=self.name, category=category,
                               brand=(brand or title.split(" ")[0]), name=title[:120],
                               unit=unit, unit_qty=unit_qty, price=price, available=True,
                               url=r.get("href") or self.search_url.format(q=quote_plus(query)),
                               verified=True, source="ui"))
        return out

    def _q(self, item):
        return " ".join(x for x in [item.brand or "", item.category.replace("_", " ")] if x)

    def search(self, item) -> List[Listing]:
        with browser_page(headless=self.headless) as page:
            return self._extract(page, self._q(item), item.category, item.brand or "", "qc")

    def search_items(self, items) -> List[Listing]:
        out: List[Listing] = []
        with browser_page(headless=self.headless) as page:
            for item in items:
                out.extend(self._extract(page, self._q(item), item.category,
                                         item.brand or "", f"{self.name.lower()}_{item.key}"))
        return out


class BlinkitAdapter(_QuickCommerceAdapter):
    name = "Blinkit"
    search_url = "https://blinkit.com/s/?q={q}"


class InstamartAdapter(_QuickCommerceAdapter):
    name = "Instamart"
    search_url = "https://www.swiggy.com/instamart/search?custom_back=true&query={q}"
