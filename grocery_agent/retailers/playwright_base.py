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


def wait_for_human(page: Page, what: str) -> None:
    """Headed only: pause so the human can log in / solve a challenge."""
    print(f"\n[human-in-the-loop] {what}\n"
          f"  A browser window is open. Please handle it there, then press Enter here…")
    try:
        input()
    except EOFError:
        pass
