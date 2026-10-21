"""Playwright session management for web-UI adapters.

Principles (match the project's rules):
- Uses a PERSISTENT browser profile so your own login/session is reused; we never
  store passwords or OTPs ourselves.
- HUMAN-IN-THE-LOOP: if the site shows a CAPTCHA / bot challenge / login wall, we
  stop and let the human handle it in a visible (headed) browser. We never try to
  defeat a challenge, and never use stealth/fingerprint-spoofing.
- Read-only here: this layer extracts visible data. Cart actions are a separate,
  explicitly-capability-gated concern.
"""
from __future__ import annotations

import contextlib
import os
from typing import Iterator, Optional

from playwright.sync_api import Browser, Page, sync_playwright

DEFAULT_PROFILE = os.path.expanduser("~/.grocery-agent/pw-profile")

# text/markers that indicate a bot/login wall rather than real results
_BLOCK_MARKERS = [
    "enter the characters you see", "type the characters you see",
    "robot check", "/errors/validatecaptcha", "are you a human",
    "verify you are a human", "px-captcha", "access denied",
]


class BotChallenge(Exception):
    """Raised when the page is a CAPTCHA / bot wall and we're not headed."""


@contextlib.contextmanager
def browser_page(headless: bool = True,
                 profile_dir: str = DEFAULT_PROFILE) -> Iterator[Page]:
    os.makedirs(profile_dir, exist_ok=True)
    with sync_playwright() as pw:
        ctx = pw.chromium.launch_persistent_context(
            profile_dir,
            headless=headless,
            viewport={"width": 1280, "height": 900},
            locale="en-IN",
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        try:
            yield page
        finally:
            ctx.close()


def looks_blocked(page: Page) -> bool:
    try:
        url = (page.url or "").lower()
        body = (page.inner_text("body", timeout=2000) or "").lower()
    except Exception:
        return False
    hay = url + " " + body
    return any(m in hay for m in _BLOCK_MARKERS)


import re as _re


def price_inr(text: str):
    """Parse an INR amount like '₹1,299' or '1299.00' -> float, or None."""
    if not text:
        return None
    m = _re.search(r"[\d,]+(?:\.\d+)?", text.replace("\u20b9", ""))
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", ""))
    except ValueError:
        return None


def rupee_amount(text: str):
    """The first amount that actually FOLLOWS a ₹ sign (avoids grabbing stray
    numbers like '5 kg' or a rating). Returns float or None."""
    if not text:
        return None
    m = _re.search(r"\u20b9\s?([\d,]+(?:\.\d+)?)", text)
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", ""))
    except ValueError:
        return None


def longest_text(scope, selectors):
    """Longest inner_text among all matches of the given selectors (good for
    picking a product title over short brand/badge spans)."""
    best = ""
    for sel in selectors:
        try:
            for el in scope.query_selector_all(sel):
                t = (el.inner_text() or "").strip()
                if len(t) > len(best):
                    best = t
        except Exception:
            pass
    return best


def first_text(scope, selectors):
    for sel in selectors:
        try:
            el = scope.query_selector(sel)
            if el:
                t = (el.inner_text() or "").strip()
                if t:
                    return t
        except Exception:
            pass
    return ""


def first_attr(scope, selectors, attr):
    for sel in selectors:
        try:
            el = scope.query_selector(sel)
            if el:
                v = el.get_attribute(attr)
                if v:
                    return v
        except Exception:
            pass
    return ""


_LOC_MARKERS = ["detecting your location", "select your location", "set your location",
                "enter your location", "choose location", "deliver to", "add your location",
                "select a location", "your pincode", "set delivery location"]


def needs_location(page: Page) -> bool:
    """Quick-commerce sites (Blinkit/Instamart) show nothing until a delivery
    location is set. Detect that wall so we can ask the human instead of faking."""
    try:
        body = (page.inner_text("body", timeout=2000) or "").lower()
    except Exception:
        return False
    return any(m in body for m in _LOC_MARKERS)


_SCAN_JS = r"""
() => {
  const priceRe = /\u20b9\s?([\d,]+(?:\.\d+)?)/;
  const out = [];
  const els = Array.from(document.querySelectorAll('a,li,article,div'));
  for (const el of els) {
    const txt = (el.innerText || '').trim();
    if (!txt || txt.length > 180 || !priceRe.test(txt)) continue;
    const m = txt.match(priceRe);
    if (!m) continue;
    const lines = txt.split('\n').map(s => s.trim())
                     .filter(s => s && !priceRe.test(s));
    const title = lines.sort((a, b) => b.length - a.length)[0] || '';
    if (title.length < 6) continue;
    let href = '';
    const a = el.closest('a') || el.querySelector('a');
    if (a) href = a.href || '';
    out.push({ title, price: m[1], href });
  }
  return out.slice(0, 80);
}
"""


def js_scan(page: Page):
    """Generic, markup-agnostic scan: find small elements that contain a rupee
    price and treat their longest non-price line as the product title. Returns
    de-duplicated {title, price, href} dicts. Empty if the SPA rendered nothing."""
    try:
        raw = page.evaluate(_SCAN_JS) or []
    except Exception:
        return []
    seen, out = set(), []
    for r in raw:
        key = r["title"].lower()[:60]
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def wait_for_human(page: Page, what: str) -> None:
    """Headed only: pause so the human can log in / solve a challenge."""
    print(f"\n[human-in-the-loop] {what}\n"
          f"  A browser window is open. Please handle it there, then press Enter here…")
    try:
        input()
    except EOFError:
        pass
