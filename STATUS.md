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

## Done (Phase 2 — first LIVE web-UI integration)
- **Playwright session layer** (`retailers/playwright_base.py`): persistent profile
  (your own login reused), headed/headless, human-in-the-loop on CAPTCHA/bot walls,
  no stealth/evasion, no password/OTP storage.
- **Amazon.in web adapter** (`retailers/amazon_in.py`): reads REAL, visible search
  results (name, price, URL) and normalizes pack size from the title. Honest
  capabilities (search + price only; no cart). Blocked -> surfaced, not faked.
- **Live pipeline + CLI** (`live.py`): real listings -> matching -> optimizer.
  `python -m grocery_agent.live [--headed] "<list>"`.
- **VERIFIED live:** read 16 genuine Amazon.in listings for "cooking oil / rice",
  optimizer chose 3×1L oil + 2×5kg rice = Rs 1251 with real product URLs.

## Honest limitations / not done
- **Only Amazon is a live adapter so far.** A true multi-retailer *split* needs
  more live adapters; those are added only where permitted/feasible. BigBasket/
  Flipkart next (expect some to be blocked by anti-bot — will be marked honestly).
- Amazon search doesn't expose delivery/coupon economics reliably, so that
  retailer's basket fees are conservative/approximate until read from a real cart.
- **No cart automation yet.** Interface exists; checkout always stays manual.
- Parser is rule-based; AI assist for ambiguous matches is a future seam (could use
  local Ollama).

## Next step
Add a second live adapter (BigBasket or Flipkart web) behind the same seam;
empirically record which portals cooperate vs. block. Then (only where supported)
a verified cart-preparation step.
