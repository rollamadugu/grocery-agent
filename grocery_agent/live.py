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
from .parser import parse_list
from .retailers.amazon_in import AmazonIndiaAdapter
from .retailers.flipkart import FlipkartAdapter
from .retailers.quick_commerce import BlinkitAdapter, InstamartAdapter
from .retailers.playwright_base import BotChallenge


def default_adapters(headless: bool):
    return [AmazonIndiaAdapter(headless=headless, max_results=8),
            FlipkartAdapter(headless=headless, max_results=8),
            BlinkitAdapter(headless=headless, max_results=8),
            InstamartAdapter(headless=headless, max_results=8)]


def run_live(text: str, headless: bool = True) -> None:
    items = parse_list(text)
    if not items:
        print("Could not parse any items from:", text)
        return

    print("Parsed list:")
    for it in items:
        print(f"  - {it.text}  [{it.category}, need {it.required_qty}{it.unit.value}, "
              f"{it.mode.value}{', brand=' + it.brand if it.brand else ''}]")

    adapters = default_adapters(headless)
    all_listings: List[Listing] = []
    retailers: Dict[str, Retailer] = {}

    for ad in adapters:
        caps = ad.capabilities()
        print(f"\nAdapter {ad.name}: live={caps.live} ({caps.notes})")
        try:
            found = ad.search_items(items)
            all_listings.extend(found)
            retailers[ad.name] = ad.retailer()
            print(f"  read {len(found)} live listings")
        except BotChallenge as e:
            print(f"  BLOCKED: {e}")
        except Exception as e:  # network/page errors -> honest, not fatal
            print(f"  ERROR ({type(e).__name__}): {e}")

    if not all_listings:
        print("\nNo live data obtained (all adapters blocked/failed). "
              "Try --headed to solve challenges, or add more adapters.")
        return

    plan = optimize(items, all_listings, retailers)
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
    if not argv:
        print('usage: python -m grocery_agent.live [--headed] "<shopping list>"')
        return
    run_live(" ".join(argv), headless=headless)


if __name__ == "__main__":
    main()
