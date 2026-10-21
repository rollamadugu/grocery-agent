"""Live shopping run: real web-UI data -> matching -> optimizer.

Collects genuine listings from live RetailerAdapters, keeps the retailer economics
each adapter declares, runs the same tested optimizer, and prints the plan. Only
adapters that report live=True contribute real data; everything is marked with its
source so nothing synthetic is passed off as live.

CLI:
    python -m grocery_agent.live "10 Park Avenue soaps, 3 L cooking oil, 10 kg rice"
    python -m grocery_agent.live --headed "<list>"      # show the browser (solve CAPTCHAs)
"""
from __future__ import annotations

import sys
from typing import Dict, List

from .models import Listing, Retailer
from .optimizer import optimize
from .llm_parser import parse_list_smart
from .llm_matcher import llm_candidates
from .retailers.amazon_in import AmazonIndiaAdapter
from .retailers.flipkart import FlipkartAdapter
from .retailers.quick_commerce import BlinkitAdapter, InstamartAdapter
from .retailers.playwright_base import BotChallenge


def default_adapters(headless: bool, location: str | None = None):
    """Build the live adapters.

    - Amazon.in / Flipkart: work headless, not location-walled.
    - Instamart (instamart.in): works headless; serves a national catalog, so the
      user's city is accepted for signature parity but not applied.
    - Blinkit: location-walled + bot-protected, so it only yields data when run
      --headed (and uses the city to scope prices); headless it reports no data.
    """
    return [AmazonIndiaAdapter(headless=headless, max_results=8),
            FlipkartAdapter(headless=headless, max_results=8),
            BlinkitAdapter(headless=headless, max_results=8, location=location),
            InstamartAdapter(headless=headless, max_results=8, location=location)]


def collect_live(text: str, location: str | None = None, headless: bool = True,
                 include_blinkit: bool = False):
    """Collect real listings programmatically (for the web API).

    Returns (items, listings, retailers, engine, source_notes). Blinkit is excluded by default because
    it needs a headed browser (a server request can't drive one honestly). Each
    adapter failure is swallowed so one blocked site doesn't sink the whole run.
    """
    items, engine = parse_list_smart(text)
    if not items:
        return [], [], {}, engine, {}
    adapters = default_adapters(headless, location)
    if not include_blinkit:
        adapters = [a for a in adapters if a.name != "Blinkit"]
    all_listings: List[Listing] = []
    retailers: Dict[str, Retailer] = {}
    source_notes: Dict[str, str] = {}
    for ad in adapters:
        try:
            found = ad.search_items(items)
            # capabilities() is read AFTER the run so it reflects the resolved
            # delivery area (honest about which area the prices are for)
            source_notes[ad.name] = ad.capabilities().notes
            if found:
                all_listings.extend(found)
                retailers[ad.name] = ad.retailer()
        except Exception as e:
            source_notes[ad.name] = f"error: {type(e).__name__}"
    return items, all_listings, retailers, engine, source_notes


def run_live(text: str, location: str | None = None, headless: bool = True) -> None:
    items, engine = parse_list_smart(text)
    if not items:
        print("Could not parse any items from:", text)
        return

    print(f"Parsed list (engine: {engine}):")
    for it in items:
        print(f"  - {it.text}  [{it.category}, need {it.required_qty}{it.unit.value}, "
              f"{it.mode.value}{', brand=' + it.brand if it.brand else ''}]")
    print(f"\nDelivery location: {location or '(none given — Blinkit needs one to show prices)'}")

    adapters = default_adapters(headless, location)
    all_listings: List[Listing] = []
    retailers: Dict[str, Retailer] = {}

    for ad in adapters:
        print(f"\nAdapter {ad.name}: live={ad.capabilities().live}")
        try:
            found = ad.search_items(items)
            all_listings.extend(found)
            retailers[ad.name] = ad.retailer()
            # read notes AFTER the run so a resolved delivery area is shown
            print(f"  {ad.capabilities().notes}")
            print(f"  read {len(found)} live listings")
        except BotChallenge as e:
            print(f"  BLOCKED: {e}")
        except Exception as e:  # network/page errors -> honest, not fatal
            print(f"  ERROR ({type(e).__name__}): {e}")

    if not all_listings:
        print("\nNo live data obtained (all adapters blocked/failed). "
              "Try --headed to solve challenges, or add more adapters.")
        return

    plan = optimize(items, all_listings, retailers, matcher=llm_candidates,
                    drop_unmatched=True)
    print(f"\n=== PLAN ({plan.status}) — data: LIVE web UI ===")
    if plan.status != "OPTIMAL":
        for n in plan.notes:
            print(" ", n)
        return
    print(f"Total payable: Rs {plan.total_cost}")
    if plan.savings_vs_best_single:
        print(f"Savings vs best single retailer: Rs {plan.savings_vs_best_single}")
    for b in plan.baskets:
        print(f"\n[{b.retailer}] Rs {b.total}  (items {b.item_subtotal} + "
              f"delivery {b.delivery_fee} + fee {b.platform_fee} - coupon {b.coupon_discount})")
        for a in b.assignments:
            print(f"   {a.item_key}: {a.packs} x {a.listing.name[:60]}  @Rs{a.listing.landed_item_price}")
            print(f"       {a.listing.url}")
    print("\nNote: only retailers that returned live data above are included. Any shown "
          "as BLOCKED/0 listings are reported honestly, not substituted with fake data.")


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    headless = True
    if "--headed" in argv:
        headless = False
        argv.remove("--headed")

    # --location "City" (or --location=City): scopes Blinkit (and is noted for
    # Instamart). Everything else is the shopping list.
    location = None
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--location":
            if i + 1 < len(argv):
                location = argv[i + 1]
                del argv[i:i + 2]
                continue
            del argv[i]
            continue
        if a.startswith("--location="):
            location = a.split("=", 1)[1]
            del argv[i]
            continue
        i += 1

    if not argv:
        print('usage: python -m grocery_agent.live [--headed] [--location "City"] '
              '"<shopping list>"')
        return
    run_live(" ".join(argv), location=location, headless=headless)


if __name__ == "__main__":
    main()
