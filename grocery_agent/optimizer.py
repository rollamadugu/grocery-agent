"""Global shopping-cost optimizer (Mixed-Integer Linear Program).

Minimizes the TOTAL payable amount across all retailers for the whole list:

    total = sum(item costs) + delivery + platform fees - basket coupons

subject to: every item's required quantity is met (in whole packs), each used
retailer meets its minimum order, free-delivery thresholds and basket coupons
are only credited when their subtotal thresholds are actually reached, and only
candidate listings (per the matching engine) may satisfy an item.

It explicitly supports SPLIT shopping (different items from different retailers)
and models order activation + basket-level charges, so the cheapest *basket* is
chosen, not merely the cheapest per-item listings. Solved exactly with CBC.
"""
from __future__ import annotations

from typing import Dict, List

import pulp

from .matching import candidates
from .models import (Assignment, Listing, Plan, Retailer, RetailerBasket,
                     ShoppingItem)
from .pricing import packs_needed, retailer_charges, meets_min_order


def _candidate_map(items, listings, matcher=candidates):
    """item_key -> list of candidate listings (per the matching engine).

    `matcher(item, listings) -> list[(Listing, MatchResult)]` is pluggable so a
    semantic (LLM) matcher can replace the default rule-based one without
    changing the optimization."""
    cmap = {}
    for it in items:
        cmap[it.key] = [lst for lst, _res in matcher(it, listings)]
    return cmap


def optimize(items: List[ShoppingItem], listings: List[Listing],
             retailers: Dict[str, Retailer], matcher=candidates,
             drop_unmatched: bool = False) -> Plan:
    cmap = _candidate_map(items, listings, matcher)
    notes: List[str] = []

    # feasibility pre-check: every item needs at least one candidate
    missing = [it for it in items if not cmap[it.key]]
    if missing and not drop_unmatched:
        return Plan(baskets=[], status="INFEASIBLE", total_cost=0.0,
                    notes=[f"No available listing can satisfy '{missing[0].text}'."])
    if missing:  # drop_unmatched: price what matched, flag the rest honestly
        for it in missing:
            notes.append(f"No genuine match found for '{it.text}' on the live "
                         f"portals — left out of the plan (not substituted).")
        items = [it for it in items if cmap[it.key]]
        if not items:
            return Plan(baskets=[], status="INFEASIBLE", total_cost=0.0, notes=notes)

    by_id = {l.id: l for l in listings}
    listings_at = {r: [l for l in listings if l.retailer == r] for r in retailers}

    prob = pulp.LpProblem("grocery_basket", pulp.LpMinimize)

    # ---- decision variables --------------------------------------------------
    # packs of listing l bought for item i (integer >= 0), only for candidates
    x = {}
    ub = {}
    for it in items:
        for l in cmap[it.key]:
            cap = packs_needed(it.required_qty, l.unit_qty)  # never need more than this
            ub[(it.key, l.id)] = cap
            x[(it.key, l.id)] = pulp.LpVariable(
                f"x_{it.key}_{l.id}", lowBound=0, upBound=cap, cat="Integer")

    z = {r: pulp.LpVariable(f"z_{r}", cat="Binary") for r in retailers}        # retailer used
    fdel = {r: pulp.LpVariable(f"free_{r}", cat="Binary") for r in retailers}  # delivery waived
    cpn = {r: pulp.LpVariable(f"coupon_{r}", cat="Binary") for r in retailers} # coupon unlocked
    deliv = {r: pulp.LpVariable(f"deliv_{r}", lowBound=0) for r in retailers}  # delivery paid

    def subtotal(r):
        terms = []
        for l in listings_at[r]:
            for it in items:
                if (it.key, l.id) in x:
                    terms.append(x[(it.key, l.id)] * l.landed_item_price)
        return pulp.lpSum(terms)

    def packs_at(r):
        return pulp.lpSum(x[(it.key, l.id)] for l in listings_at[r]
                          for it in items if (it.key, l.id) in x)

    # ---- constraints ---------------------------------------------------------
    # 1) demand: whole packs must cover each item's required quantity
    for it in items:
        prob += (pulp.lpSum(x[(it.key, l.id)] * l.unit_qty for l in cmap[it.key])
                 >= it.required_qty), f"demand_{it.key}"

    for r, ret in retailers.items():
        packs = packs_at(r)
        sub = subtotal(r)
        bigm = sum(ub[(it.key, l.id)] for l in listings_at[r]
                   for it in items if (it.key, l.id) in x) or 1

        # 2) link retailer-active z_r to whether anything is bought there
        prob += packs <= bigm * z[r], f"active_hi_{r}"
        prob += z[r] <= packs, f"active_lo_{r}"

        # 3) minimum order: if used, subtotal must reach min_order_value
        if ret.min_order_value > 0:
            prob += sub >= ret.min_order_value * z[r], f"minorder_{r}"

        # 4) delivery with free-delivery threshold
        if ret.free_delivery_threshold is not None:
            # may only claim "free" if subtotal actually reaches the threshold
            prob += sub >= ret.free_delivery_threshold * fdel[r], f"freethresh_{r}"
            prob += fdel[r] <= z[r], f"free_needs_active_{r}"
            prob += deliv[r] >= ret.delivery_fee * (z[r] - fdel[r]), f"deliv_{r}"
        else:
            prob += deliv[r] >= ret.delivery_fee * z[r], f"deliv_{r}"
            prob += fdel[r] == 0, f"nofree_{r}"

        # 5) basket coupon: only credited when subtotal reaches its threshold
        if ret.coupon_threshold is not None and ret.coupon_amount > 0:
            prob += sub >= ret.coupon_threshold * cpn[r], f"coupthresh_{r}"
            prob += cpn[r] <= z[r], f"coupon_needs_active_{r}"
        else:
            prob += cpn[r] == 0, f"nocoupon_{r}"

    # ---- objective -----------------------------------------------------------
    item_cost = pulp.lpSum(x[(it.key, l.id)] * by_id[l.id].landed_item_price
                           for it in items for l in cmap[it.key])
    platform = pulp.lpSum(retailers[r].platform_fee * z[r] for r in retailers)
    delivery_total = pulp.lpSum(deliv[r] for r in retailers)
    coupon_total = pulp.lpSum(retailers[r].coupon_amount * cpn[r] for r in retailers)
    prob += item_cost + platform + delivery_total - coupon_total

    prob.solve(pulp.PULP_CBC_CMD(msg=0))
    status = pulp.LpStatus[prob.status]
    if status != "Optimal":
        return Plan(baskets=[], status=status.upper(), total_cost=0.0,
                    notes=[f"Solver status: {status}. No feasible allocation under the "
                           "given constraints (check minimum orders / availability)."])

    # ---- rebuild the plan from the solution (recompute charges deterministically)
    baskets: List[RetailerBasket] = []
    for r, ret in retailers.items():
        assigns = []
        for it in items:
            for l in cmap[it.key]:
                if l.retailer != r:          # only this retailer's listings
                    continue
                v = x[(it.key, l.id)].value()
                if v and round(v) > 0:
                    assigns.append(Assignment(it.key, by_id[l.id], int(round(v))))
        if not assigns:
            continue
        item_sub = round(sum(a.cost for a in assigns), 2)
        ch = retailer_charges(ret, item_sub)
        baskets.append(RetailerBasket(
            retailer=r, assignments=assigns, item_subtotal=item_sub,
            delivery_fee=ch["delivery_fee"], platform_fee=ch["platform_fee"],
            coupon_discount=ch["coupon_discount"]))

    total = round(sum(b.total for b in baskets), 2)

    # ---- baseline: cost if everything came from ONE retailer -----------------
    baseline = _single_retailer_baselines(items, listings, retailers, cmap)
    feasible_singles = {r: c for r, c in baseline.items() if c is not None}
    savings = 0.0
    if feasible_singles:
        best_single = min(feasible_singles.values())
        savings = round(best_single - total, 2)

    if len(baskets) > 1:
        notes.append(f"Split across {len(baskets)} retailers to minimize the total bill.")
    if not feasible_singles:
        notes.append("No single retailer can fulfil the whole list on its own.")

    return Plan(baskets=baskets, status="OPTIMAL", total_cost=total,
                baseline_single_retailer=baseline,
                savings_vs_best_single=savings, notes=notes)


def _single_retailer_baselines(items, listings, retailers, cmap):
    """For each retailer, cost of buying the WHOLE list there alone (cheapest
    candidate per item at that retailer), or None if it can't fulfil everything
    / can't meet its minimum order."""
    out = {}
    for r, ret in retailers.items():
        sub = 0.0
        feasible = True
        for it in items:
            here = [l for l in cmap[it.key] if l.retailer == r]
            if not here:
                feasible = False
                break
            best = min(here, key=lambda l: l.unit_price)
            sub += packs_needed(it.required_qty, best.unit_qty) * best.landed_item_price
        if not feasible:
            out[r] = None
            continue
        sub = round(sub, 2)
        if not meets_min_order(ret, sub):
            out[r] = None
            continue
        ch = retailer_charges(ret, sub)
        out[r] = round(sub + ch["delivery_fee"] + ch["platform_fee"] - ch["coupon_discount"], 2)
    return out
