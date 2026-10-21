# Implementation status

_Concise status doc, updated as the project progresses._

## Done (Phase 1 — real, tested core)
- **Domain models** (`models.py`): canonical Product/Listing/ShoppingItem/Plan.
- **Unit normalization** (`units.py`): g/kg, ml/l, count; pack math; measure parsing.
- **NL parser** (`parser.py`): plain-English list → normalized items; assumptions
  (e.g. default bottle size) flagged in item text.
- **Matching** (`matching.py`): category + dimension + brand/variant + exclusions
  + price cap; confidence score + confirm threshold.
- **Cost model** (`pricing.py`): delivery, free-delivery threshold, platform fee,
  basket coupon, minimum order, pack rounding.
- **MILP optimizer** (`optimizer.py`): global split-basket minimization with order
  activation + basket charges; single-retailer baselines + savings; CBC solver.
- **Retailer adapter interface** (`retailers/base.py`) with honest `Capabilities`.
- **API + UI** (`api.py`): FastAPI `/api/plan` + mobile-friendly page; responses
  tagged `data_source: synthetic`.
- **Tests:** 22 passing (units, matching, parser, optimizer scenarios).

## Verified results
- `pytest` → 22 passed.
- Canonical list optimizes to a Flipkart+AmazonNow split, ₹1726 total,
  ₹48 saved vs the cheapest single retailer (synthetic data).

## Honest limitations / not done
- **No live retailer data yet.** All listings are labeled synthetic fixtures.
  Live integration is gated on a legitimate, ToS-permitted access path per
  retailer (see README "Honest scope"). No scraping / anti-bot evasion.
- **No cart automation yet.** The adapter interface exists; no live cart adapter
  is implemented. Checkout will always remain manual.
- Parser is rule-based (no LLM dependency in pricing/optimization); AI assist for
  ambiguous matches is a future enhancement behind the matching seam.

## Next step
Phase 2: implement one real data source behind a capability-declaring adapter
(evaluate official/affiliate APIs first), keeping every other adapter explicitly
"not available" rather than mocked.
