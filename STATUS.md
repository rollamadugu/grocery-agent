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

## Live adapters — empirical per-portal status (verified by running them)
- **Amazon.in** ✅ live — reads public search results (no login needed for prices).
- **Flipkart** ✅ live — reads public search; dismisses the login modal; ₹-anchored
  price extraction; pack size parsed from title/card.
- **Instamart (instamart.in)** ✅ live **headless, city-aware** — the standalone
  Instamart brand domain (Swiggy dropped its name, May-2026 rebrand). No Cloudflare
  and no hard location wall. Flow: open `/search?q=`, type the query + Enter (the
  `?q=` param alone does NOT filter), wait until results replace the default catalog,
  then extract (prices are plain numbers, dedicated extractor). **City now applied:**
  when a city is given we drive the "Choose area" modal (fresh throwaway profile so it
  always starts location-less → reliable), type the city, **mouse-click** the area row
  (obfuscated React ignores synthetic clicks), prefer the EXACT-city row (so
  "Hyderabad" ≠ "Hyderabad Gate, Varanasi"), confirm, and record the resolved area
  (surfaced to the UI/CLI for honesty). Verified: Hyderabad/Mumbai/Delhi/Bangalore/
  Chennai all resolve to the correct city.
- **Blinkit** ⛔ location-walled — SPA shows nothing until a delivery location is set;
  headless returns 0 and we report it honestly. Works **headed** with a city; often
  blocked by anti-bot regardless.
- **(old) Swiggy `swiggy.com/instamart`** ⛔ Cloudflare + location wall in headless —
  replaced by the `instamart.in` adapter above.
- A real multi-retailer *split* now works across Amazon + Flipkart + Instamart.

## Done (Phase 3 — local AI for the fuzzy parts)
- **AI list parser** (`llm_parser.py`): a LOCAL LLM (Ollama `llama3.1:8b`) turns free
  text into the same `ShoppingItem` structures — robust to anything outside the rule
  parser's fixed dictionary (e.g. "toor dal", arbitrary brands). Temperature 0 +
  JSON-constrained; runs entirely locally (no external API). **Falls back** to the
  rule parser if Ollama is down and the response **labels which engine ran**.
- **Where AI is / isn't used (by design):** AI for NL parsing (and, next, semantic
  matching); the **MILP optimizer stays deterministic** (provably optimal, instant —
  an LLM there would be worse, not smarter).
- Wired into the live CLI (`--location`, engine printed) and the web API live path.
- **VERIFIED:** "1 kg toor dal, 1 kg rice" (previously UNPARSEABLE) now → AI parse →
  real Instamart listings → optimal plan Rs 258 (Fortune Arhar Dal + Daawat rice),
  all `verified=True`.

## CLI / UI
- CLI: `python -m grocery_agent.live [--headed] [--location "City"] "<list>"`.
- Web UI: shopping list + **delivery city** field + **"use live prices"** toggle.
  Live mode runs Amazon/Flipkart/Instamart headless (Blinkit omitted — needs a headed
  browser; stated plainly). Synthetic demo path stays on the rule parser + fixtures.

## Done (Phase 4 — AI semantic matching + buy-vs-compare UI)
- **AI semantic matcher** (`llm_matcher.py`): `llm_candidates(item, listings)` runs
  the rule-based candidates first (availability/dimension/brand/price-cap), then a
  single batched local-LLM call judges which candidate NAMES are genuinely the
  requested product. This is essential because live adapters stamp the requested
  category onto listings, so without it a "toor dal" search would accept moong/
  masoor/chana. **Verified:** it drops non-dal junk (e.g. "Switch") a search returns.
  Fails safe: on an LLM error it keeps the rule-based set; a genuine empty verdict is
  trusted (the item is flagged, never substituted with the wrong product).
- **Optimizer** now takes a pluggable `matcher=` (default rule-based, so the synthetic
  demo + 22 tests are unchanged) and a `drop_unmatched=` flag used by live paths:
  items with no genuine match are left out WITH A NOTE instead of failing the whole
  plan or being faked.
- **Buy-vs-compare UI**: the result now shows (1) the **smart split** — exactly what
  to buy from each portal with qty, per-pack price, unit price and basket total; and
  (2) a **"whole list at one portal"** comparison — what the same full list would cost
  at each single portal (or "cannot supply every item"), the cheapest single, and how
  much the smart split **saves**. Also surfaces the parse + match engine labels.
- **Verified end-to-end (live, Hyderabad):** "1 kg rice, 1 L cooking oil" → smart
  split Amazon rice Rs137 + Instamart oil Rs173 = Rs310, **saves Rs32** vs Amazon's
  whole-basket Rs342 (Flipkart/Instamart honestly "cannot supply all").

## Honest limitations / not done
- Amazon search doesn't expose delivery/coupon economics reliably, so that
  retailer's basket fees are conservative/approximate until read from a real cart.
- **No cart automation yet.** Interface exists; checkout always stays manual.
- The 8B local model is occasionally over-strict in matching (may drop a valid
  variant); safe-fallback prevents dropping everything on error.
- `instamart.in` identity: strong circumstantial evidence it's the rebranded
  standalone Instamart; not 100% ownership-confirmed.

## City / location model (current)
- **City is OPTIONAL** overall. Amazon.in / Flipkart don't need it.
- When given, it's applied to the quick-commerce portals: **Instamart** (headless,
  via "Choose area") and **Blinkit** (headed only). All three adapters now derive a
  listing's brand from the ACTUAL product name (brand matching is meaningful).
- **Blinkit** stays CLI-`--headed` only (Cloudflare + hard location wall) — it is
  omitted from the web app, stated plainly, never faked.

## Next step
Optionally wire Blinkit's headed location flow into a desktop/CLI run end-to-end;
(only where supported) a verified cart-preparation step.
