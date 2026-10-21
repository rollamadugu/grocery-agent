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

import contextlib
import re
import shutil
import tempfile
from typing import List, Optional, Tuple
from urllib.parse import quote_plus

from ..models import Listing, Retailer, Unit
from ..units import parse_measure
from .base import Capabilities, RetailerAdapter, build_search_query
from .playwright_base import (browser_page, js_scan, looks_blocked, needs_location,
                              price_inr, wait_for_human)


class _QuickCommerceAdapter(RetailerAdapter):
    search_url = ""          # set by subclass, with {q}
    name = ""
    loc_input_selectors: list = []     # subclass: candidate location-search inputs
    loc_suggestion_selectors: list = []  # subclass: candidate suggestion items

    def __init__(self, headless: bool = True, max_results: int = 8,
                 location: str | None = None):
        self.headless = headless
        self.max_results = max_results
        self.location = location       # city / area typed by the user

    def _set_location(self, page, city: str) -> bool:
        """Type the user's city into the delivery-location box and pick the first
        suggestion. This just fills a normal form field the user would fill anyway.
        Returns True if an input was found and submitted."""
        inp = None
        for sel in self.loc_input_selectors:
            inp = page.query_selector(sel)
            if inp:
                break
        if inp is None:
            return False
        try:
            inp.click()
            inp.fill("")
            inp.type(city, delay=40)
            page.wait_for_timeout(2500)         # wait for autocomplete suggestions
            # prefer clicking the first real suggestion; fall back to keyboard
            clicked = False
            for sel in self.loc_suggestion_selectors:
                items = page.query_selector_all(sel)
                items = [it for it in items if (it.inner_text() or "").strip()]
                if items:
                    items[0].click()
                    clicked = True
                    break
            if not clicked:
                page.keyboard.press("ArrowDown")
                page.keyboard.press("Enter")
            page.wait_for_timeout(3500)         # let the catalog load for that area
            return True
        except Exception:
            return False

    def retailer(self) -> Retailer:
        return Retailer(self.name, delivery_fee=0.0, min_order_value=0.0, live=True)

    def capabilities(self) -> Capabilities:
        return Capabilities(product_search=True, price_retrieval=True, live=True,
                            notes="Location-walled SPA; needs delivery location set "
                                  "(headed/human). Often blocked for automation; "
                                  "reports no-data honestly when so. No cart.")

    def _open_search(self, page, query):
        page.goto(self.search_url.format(q=quote_plus(query)),
                  wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(2500)  # SPA needs a moment to render/XHR

    def _extract(self, page, query, category, brand, idp) -> List[Listing]:
        self._open_search(page, query)

        # Cloudflare / hard bot wall (common in headless) -> can't proceed honestly
        if looks_blocked(page):
            if self.headless:
                return []   # e.g. "access denied" — no data, never faked
            wait_for_human(page, f"{self.name}: the site is showing a bot/CAPTCHA "
                                 f"challenge. Please solve it in the browser.")
            self._open_search(page, query)

        # scope prices to the user's chosen city whenever one is provided
        if self.location and self._set_location(page, self.location):
            self._open_search(page, query)

        if needs_location(page) or looks_blocked(page):
            if self.headless:
                return []
            wait_for_human(page, f"{self.name}: set your delivery location "
                                 f"(city tried: {self.location or 'none'}) / sign in.")
            self._open_search(page, query)

        rows = js_scan(page)
        out: List[Listing] = []
        for i, r in enumerate(rows):
            if len(out) >= self.max_results:
                break
            price = price_inr(r["price"])
            title = r["title"]
            if price is None or not title:
                continue
            measure = parse_measure(title) or parse_measure(r.get("text", ""))
            unit_qty, unit = measure if measure is not None else (1.0, Unit.COUNT)
            out.append(Listing(id=f"{idp}_{i}", retailer=self.name, category=category,
                               brand=(brand or title.split(" ")[0]), name=title[:120],
                               unit=unit, unit_qty=unit_qty, price=price, available=True,
                               url=r.get("href") or self.search_url.format(q=quote_plus(query)),
                               verified=True, source="ui"))
        return out

    def _q(self, item):
        return build_search_query(item)

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
    loc_input_selectors = [
        "input[name='select-locality']",
        "input[placeholder*='delivery location' i]",
        "input[placeholder*='search delivery' i]",
    ]
    loc_suggestion_selectors = [
        "div[class*='LocationSearchList__LocationListContainer'] div[class*='LocationName']",
        "div[class*='LocationSearchList'] > div",
        "div[class*='address-container']",
    ]


# ---------------------------------------------------------------------------
# Instamart (instamart.in) — the standalone brand after Swiggy dropped its name
# from Instamart (rebrand, May 2026). Unlike the old swiggy.com/instamart SPA,
# this domain renders server/client results WITHOUT a Cloudflare wall and WITHOUT
# a hard location gate, so it works HEADLESS. Search is type-to-search (the ?q=
# URL param does not filter), and prices are plain numbers (no '₹' glyph), so it
# needs its own extractor rather than the shared rupee-anchored js_scan.
# ---------------------------------------------------------------------------

# For each product link, climb to the enclosing card that carries the
# measure/discount/price and return {href, lines}. Markup-agnostic (the CSS
# classes are obfuscated), so we read the card's text lines and parse in Python.
_INSTAMART_SCAN_JS = r"""
() => {
  const out = []; const seen = new Set();
  const measureRe = /\b\d+(?:\.\d+)?\s?(g|kg|ml|l|ltr|litre|litres|pieces?|piece|units?|pack|combo)\b/i;
  for (const a of Array.from(document.querySelectorAll("a[href^='/p/']"))) {
    const href = a.getAttribute('href');
    if (!href || seen.has(href)) continue; seen.add(href);
    let el = a, cardText = (a.innerText || '');
    for (let i = 0; i < 6 && el.parentElement; i++) {
      el = el.parentElement;
      const t = (el.innerText || '');
      cardText = t;
      if (/OFF/i.test(t) || measureRe.test(t)) break;
    }
    const lines = cardText.split('\n').map(s => s.trim()).filter(Boolean);
    if (lines.length) out.push({ href, lines });
  }
  return out.slice(0, 40);
}
"""

_CTRL_MINS = re.compile(r"^\d+\s*MINS?$", re.I)
_PURE_NUM = re.compile(r"^\d[\d,]*(?:\.\d+)?$")
_PCT_OFF = re.compile(r"^\d+%\s*OFF$", re.I)


def _parse_instamart_card(lines: List[str]
                          ) -> Tuple[str, Optional[Tuple[float, Unit]], Optional[float], bool]:
    """Parse one card's text lines into (name, measure, sale_price, sold_out).

    Line shape (tokens optional): [Ad] [N MINS | SOLD OUT] NAME [description]
                                  MEASURE(e.g. '500 g') [X% OFF] SALE [MRP]
    """
    sold_out = any(s.strip().upper() == "SOLD OUT" for s in lines)
    clean: List[str] = []
    for s in (x.strip() for x in lines):
        if not s or s.lower() == "ad" or s.upper() == "SOLD OUT":
            continue
        if _CTRL_MINS.match(s) or s.upper() == "ADD":
            continue
        clean.append(s)

    # measure: first SHORT standalone token that parses as a measure (avoid
    # grabbing a measure embedded inside a long product name/description).
    measure = None
    measure_idx = None
    for i, s in enumerate(clean):
        if len(s) <= 15:
            mm = parse_measure(s)
            if mm is not None:
                measure, measure_idx = mm, i
                break

    disc_idx = next((i for i, s in enumerate(clean) if _PCT_OFF.match(s)), None)
    nums = [(i, float(s.replace(",", ""))) for i, s in enumerate(clean) if _PURE_NUM.match(s)]

    sale: Optional[float] = None
    if disc_idx is not None:
        after = [v for (i, v) in nums if i > disc_idx]
        sale = after[0] if after else (nums[0][1] if nums else None)
    elif nums:
        sale = nums[0][1]

    name = ""
    for i, s in enumerate(clean):
        if i == measure_idx or (disc_idx is not None and i == disc_idx):
            continue
        if _PURE_NUM.match(s) or _PCT_OFF.match(s):
            continue
        name = s
        break

    return name, measure, sale, sold_out


# Area-suggestion rows in the "Choose area" modal are obfuscated React nodes that
# ignore synthetic .click(); a real mouse click at the row's centre works. This
# returns the on-screen centre of each candidate row (text starts with the city),
# top-most first, so we can drive page.mouse.click(x, y).
_INSTAMART_AREA_ROWS_JS = r"""
(city) => {
  const low = city.toLowerCase();
  const out = [];
  for (const el of document.querySelectorAll('li,div')) {
    const t = (el.innerText || '').trim();
    if (!t || t.length > 70) continue;
    const first = t.split('\n')[0].trim();
    if (!first.toLowerCase().includes(low)) continue;
    const r = el.getBoundingClientRect();
    if (r.width < 40 || r.height < 10 || r.height > 80) continue;  // a row, not a container
    out.push({ text: first.slice(0, 50), x: r.x + r.width / 2, y: r.y + r.height / 2 });
  }
  const seen = new Set(), uniq = [];
  for (const o of out.sort((a, b) => a.y - b.y)) {
    if (seen.has(o.text)) continue; seen.add(o.text); uniq.push(o);
  }
  return uniq.slice(0, 8);
}
"""


class InstamartAdapter(RetailerAdapter):
    name = "Instamart"
    base_url = "https://instamart.in"
    search_url = "https://instamart.in/search?q={q}"
    search_input_selectors = [
        "input[type='search']",
        "input[placeholder*='search' i]",
    ]
    # the control that opens the "Choose area" modal — differs by whether a
    # location is already set in the (persistent) profile:
    location_trigger_selectors = [
        "[data-testid='address-bar']",      # a location is set -> click to change it
        "[data-testid='search-location']",  # no location yet -> "Add your location"
        "[data-testid='DEFAULT_ADDRESS_CONTAINER']",
    ]
    area_input_selectors = [
        "input[placeholder*='area' i]",
        "input[placeholder*='street' i]",
    ]

    def __init__(self, headless: bool = True, max_results: int = 8,
                 location: str | None = None):
        self.headless = headless
        self.max_results = max_results
        # instamart.in geolocates by default but exposes a "Choose area" modal; when
        # a city is given we set it so prices are for THAT area. If setting fails we
        # fall back to the geo-default and say so (never fake city accuracy).
        self.location = location
        self._resolved_area: str | None = None   # the area actually set (for honesty)
        self._location_done = False

    def retailer(self) -> Retailer:
        return Retailer(self.name, delivery_fee=0.0, min_order_value=0.0, live=True)

    def capabilities(self) -> Capabilities:
        note = ("instamart.in (standalone Instamart brand). Works headless; "
                "type-to-search; prices are plain numbers. ")
        if self.location:
            note += (f"Delivery area set via 'Choose area' to match '{self.location}'"
                     + (f" (resolved: {self._resolved_area})." if self._resolved_area
                        else " (fell back to geo-default if not confirmed)."))
        else:
            note += "No city given -> uses the site's geo-default area."
        return Capabilities(product_search=True, price_retrieval=True, live=True,
                            notes=note + " No cart.")

    def _open_location_modal(self, page) -> bool:
        for sel in self.location_trigger_selectors:
            el = page.query_selector(sel)
            if el:
                try:
                    el.click(timeout=6000)
                    page.wait_for_timeout(2000)
                    return True
                except Exception:
                    continue
        # text fallbacks
        for txt in ("Choose area", "Add your location", "Change"):
            try:
                loc = page.get_by_text(txt, exact=False).first
                if loc.count() and loc.is_visible():
                    loc.click(timeout=6000)
                    page.wait_for_timeout(2000)
                    return True
            except Exception:
                pass
        return False

    def _current_area(self, page) -> str | None:
        try:
            el = page.query_selector("[data-testid='address-line']") or \
                 page.query_selector("[data-testid='address-bar']")
            if el:
                t = (el.inner_text() or "").strip().replace("\n", " ")
                return t or None
        except Exception:
            pass
        return None

    def _set_location(self, page, city: str) -> bool:
        """Open 'Choose area', type the city, mouse-click the first area suggestion,
        confirm. Records the resolved area. Returns True if an area was set."""
        try:
            page.goto(self.base_url + "/", wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(3500)
            if not self._open_location_modal(page):
                return False
            inp = None
            for sel in self.area_input_selectors:
                inp = page.query_selector(sel)
                if inp:
                    break
            if inp is None:
                return False
            inp.click()
            inp.fill("")
            inp.type(city, delay=80)
            page.wait_for_timeout(4500)

            rows = page.evaluate(_INSTAMART_AREA_ROWS_JS, city) or []
            if not rows:
                return False
            # Prefer the row whose text is EXACTLY the city (the city-level pick,
            # e.g. "Hyderabad") over a longer area name — a longer name can be a
            # same-named place in a DIFFERENT city (e.g. "Hyderabad Gate" is in
            # Varanasi). Only if there's no exact-city row do we take the top area.
            exact = [r for r in rows if r["text"].strip().lower() == city.strip().lower()]
            target = exact[0] if exact else rows[0]
            page.mouse.move(target["x"], target["y"])
            page.wait_for_timeout(300)
            page.mouse.click(target["x"], target["y"])
            page.wait_for_timeout(4000)

            # a city-level pick may drop into a second area list; take its top row
            if page.query_selector(self.area_input_selectors[0]):
                rows2 = page.evaluate(_INSTAMART_AREA_ROWS_JS, city) or []
                if rows2:
                    t2 = rows2[0]
                    page.mouse.move(t2["x"], t2["y"])
                    page.wait_for_timeout(300)
                    page.mouse.click(t2["x"], t2["y"])
                    page.wait_for_timeout(4000)

            # a map/confirm step often follows
            for sel in ("button:has-text('Confirm')", "[data-testid*='confirm' i]",
                        "button:has-text('Proceed')", "button:has-text('Continue')"):
                try:
                    b = page.locator(sel).first
                    if b.count() and b.is_visible():
                        b.click(timeout=6000)
                        page.wait_for_timeout(4000)
                        break
                except Exception:
                    pass

            area = self._current_area(page)
            # success if the resolved area reflects the requested city, or the
            # "Add your location" placeholder is gone
            if area and city.lower() in area.lower():
                self._resolved_area = area
                return True
            placeholder = page.query_selector("[data-testid='DEFAULT_ADDRESS_TITLE']")
            if placeholder is None:
                self._resolved_area = area
                return True
            return False
        except Exception:
            return False

    def _ensure_location(self, page) -> None:
        """Set the delivery area at most once per browser session."""
        if self._location_done or not self.location:
            return
        self._location_done = True
        ok = self._set_location(page, self.location)
        if not ok:
            self._resolved_area = None   # couldn't confirm -> geo-default (honest)

    def _run_search(self, page, query: str) -> None:
        page.goto(self.search_url.format(q=quote_plus(query)),
                  wait_until="domcontentloaded", timeout=45000)
        # Wait for the search box itself (cold starts render it late); without this
        # a cold page would skip typing and never run the real search.
        try:
            page.wait_for_selector(self.search_input_selectors[0], timeout=20000)
        except Exception:
            pass
        page.wait_for_timeout(1500)
        # The bare /search?q= page first shows a DEFAULT catalog (unrelated
        # products) and only returns real matches once the query is typed+entered.
        # Snapshot the default catalog's first product so we can wait for the
        # results to actually CHANGE, instead of racing a fixed sleep.
        try:
            before = page.eval_on_selector(
                "a[href^='/p/']", "el => el.getAttribute('href')")
        except Exception:
            before = None

        inp = None
        for sel in self.search_input_selectors:
            inp = page.query_selector(sel)
            if inp:
                break
        if inp is not None:
            try:
                inp.click()
                inp.fill("")
                inp.type(query, delay=50)
                page.wait_for_timeout(1200)
                inp.press("Enter")
            except Exception:
                pass

        # Wait until the real results replace the default catalog (first product
        # link differs from the snapshot), not merely until any links exist.
        try:
            page.wait_for_function(
                """(prev) => {
                    const ls = document.querySelectorAll("a[href^='/p/']");
                    const a = ls[0];
                    return ls.length > 2 && a && a.getAttribute('href') !== prev;
                }""",
                arg=before, timeout=20000)
        except Exception:
            pass
        page.wait_for_timeout(2500)  # let prices/measures attach to the cards

    def _scan(self, page) -> list:
        try:
            return page.evaluate(_INSTAMART_SCAN_JS) or []
        except Exception:
            return []

    def _extract(self, page, query, category, brand, idp) -> List[Listing]:
        self._run_search(page, query)

        if looks_blocked(page):
            if self.headless:
                return []   # never fabricate data for a blocked page
            wait_for_human(page, f"{self.name}: solve the challenge in the browser.")
            self._run_search(page, query)

        rows = self._scan(page)
        if not rows:                       # cold start / slow render -> one retry
            self._run_search(page, query)
            rows = self._scan(page)

        out: List[Listing] = []
        for i, r in enumerate(rows):
            if len(out) >= self.max_results:
                break
            name, measure, sale, sold_out = _parse_instamart_card(r.get("lines", []))
            if not name or sale is None or sold_out:
                continue
            unit_qty, unit = measure if measure is not None else (1.0, Unit.COUNT)
            href = r.get("href") or ""
            url = (self.base_url + href) if href.startswith("/") else (href or self.base_url)
            # derive brand from the ACTUAL product name (never stamp the requested
            # brand onto a listing — that would silently defeat brand matching)
            out.append(Listing(id=f"{idp}_{i}", retailer=self.name, category=category,
                               brand=name.split(" ")[0], name=name[:120],
                               unit=unit, unit_qty=unit_qty, price=sale, available=True,
                               url=url, verified=True, source="ui"))
        return out

    def _q(self, item) -> str:
        return build_search_query(item)

    @contextlib.contextmanager
    def _session(self):
        """A browser session for Instamart. When a city is requested we use a
        FRESH, throwaway profile so the site always starts location-less and the
        'Choose area' flow sets exactly that city (a profile that already has a
        saved area won't reliably re-open the area picker). Instamart needs no
        login, so a clean profile costs nothing."""
        if self.location:
            profile = tempfile.mkdtemp(prefix="instamart-pw-")
            try:
                with browser_page(headless=self.headless, profile_dir=profile) as page:
                    yield page
            finally:
                shutil.rmtree(profile, ignore_errors=True)
        else:
            with browser_page(headless=self.headless) as page:
                yield page

    def search(self, item) -> List[Listing]:
        with self._session() as page:
            self._ensure_location(page)
            return self._extract(page, self._q(item), item.category, item.brand or "",
                                 "instamart")

    def search_items(self, items) -> List[Listing]:
        out: List[Listing] = []
        with self._session() as page:
            self._ensure_location(page)        # set the delivery area once, up front
            for item in items:
                out.extend(self._extract(page, self._q(item), item.category,
                                         item.brand or "", f"instamart_{item.key}"))
        return out
