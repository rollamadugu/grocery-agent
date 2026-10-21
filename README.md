# Smart Grocery Shopping & Price-Optimization Agent

![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![Tests](https://img.shields.io/badge/tests-22%20passing-brightgreen)
![Optimizer](https://img.shields.io/badge/optimizer-MILP%20(CBC)-success)
![License](https://img.shields.io/badge/license-MIT-green)

Enter a shopping list in plain English. The agent normalizes it, matches real
product attributes (brand, variant, pack size, net quantity), and computes the
**lowest-cost way to split the basket across multiple retailers** — accounting
for delivery fees, free-delivery thresholds, minimum orders and basket coupons.

> **"10 Park Avenue soaps, 3 packets of cooking oil, a 10 kg rice bag, 2 detergent
> soaps and 2 shampoo bottles"** → an optimized, itemized plan across retailers,
> with the total, the per-retailer breakdown, and the savings vs. buying it all
> from one place.

## Honest scope (read this)

The hard, valuable core is **real and fully tested**:
- natural-language list parsing,
- unit normalization + product matching (with a confidence score),
- a price/fee/coupon cost model,
- a **Mixed-Integer Linear Program** (CBC solver) that finds the cheapest
  *basket allocation* — split shopping, not just the cheapest per item.

What is **not** pretended to be real: live retailer prices. This slice runs on
**clearly-labeled synthetic fixtures** (`sample_data.py`), and every API response
is tagged `data_source: synthetic`. Live retailer integration is deliberately
constrained — most Indian grocery platforms' terms of service prohibit scraping
and automated carts, and they run anti-bot protection. So live data is added
**only** via adapters with a legitimate, permitted access path, and each adapter
honestly declares its real capabilities (`retailers/base.py`). Nothing synthetic
is ever shown as verified/live. A failed or unsupported action is never reported
as success.

## Run it

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

pytest                                  # 22 tests
uvicorn grocery_agent.api:app --reload  # open http://127.0.0.1:8000
```

## What the optimizer actually does

Minimizes the **total payable amount** for the whole list:

```
total = Σ item costs  +  delivery  +  platform fees  −  basket coupons
```

subject to: each item's required quantity met in whole packs; each used retailer
meets its minimum order; free-delivery and coupon credits only apply when their
subtotal thresholds are genuinely reached; only listings the matching engine
accepts (right category, dimension, brand for brand-mode) can satisfy an item.
It explicitly models **order activation** and **basket-level charges**, so it can
decide that splitting is cheaper — or that one basket wins because a coupon or a
free-delivery threshold unlocks. Solved exactly with CBC.

## Architecture (modular, maps to the brief)

```
grocery_agent/
  models.py        canonical Product/Listing/Item/Plan representations
  units.py         unit normalization (g/kg, ml/l, count) + pack math
  parser.py        natural-language list -> normalized items (assumptions flagged)
  matching.py      product equivalence + confidence (+ confirm threshold)
  pricing.py       deterministic fee/coupon/min-order cost model
  optimizer.py     MILP global cost optimizer (split shopping)   <-- core
  retailers/base.py  RetailerAdapter interface + honest Capabilities
  sample_data.py   CLEARLY-LABELED synthetic listings (dev/test only)
  api.py           FastAPI app + mobile-friendly UI
tests/             22 tests incl. the brief's tricky scenarios
```

## Tested scenarios (the ones that actually matter)

- splitting is cheaper → split is chosen
- delivery fees make splitting worse → consolidate
- a minimum order rules out an otherwise-cheapest retailer
- a basket coupon flips the optimal allocation
- an item is unavailable → reported infeasible, not faked
- a mandatory brand is respected even when a cheaper other-brand exists
- free-delivery threshold waives the fee
- unit/dimension safety: a count is never matched to a weight

## Roadmap

- **Phase 1 (done):** engine + UI on synthetic fixtures, fully tested.
- **Phase 2:** one legitimate data source (official/affiliate API where obtainable),
  behind a capability-declaring adapter.
- **Phase 3+:** more adapters only where permitted; cart prep where supported;
  checkout always manual.

## License

MIT. Author: Krishnasai Rollamadugu.
