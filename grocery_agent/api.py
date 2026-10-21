"""FastAPI app + a minimal, mobile-friendly UI.

Honest-data notice: this slice optimizes over CLEARLY-LABELED SYNTHETIC listings
(sample_data). The response is tagged data_source="synthetic (dev fixtures)" so
nothing fake is ever presented as live retailer data. Real adapters replace the
listing source without changing the optimizer or UI.
"""
from __future__ import annotations

from typing import Dict, List

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from .matching import candidates
from .optimizer import optimize
from .parser import parse_list
from .models import Plan
from .sample_data import sample_listings, sample_retailers

app = FastAPI(title="Smart Grocery Agent", version="0.1.0")


class PlanRequest(BaseModel):
    text: str


def plan_to_dict(plan: Plan) -> dict:
    return {
        "status": plan.status,
        "total_cost": plan.total_cost,
        "baseline_single_retailer": plan.baseline_single_retailer,
        "savings_vs_best_single": plan.savings_vs_best_single,
        "notes": plan.notes,
        "baskets": [
            {
                "retailer": b.retailer,
                "item_subtotal": b.item_subtotal,
                "delivery_fee": b.delivery_fee,
                "platform_fee": b.platform_fee,
                "coupon_discount": b.coupon_discount,
                "total": b.total,
                "items": [
                    {"item": a.item_key, "brand": a.listing.brand,
                     "name": a.listing.name, "packs": a.packs,
                     "unit_price": round(a.listing.unit_price, 2),
                     "price_each": a.listing.landed_item_price, "cost": a.cost,
                     "url": a.listing.url, "verified": a.listing.verified}
                    for a in b.assignments
                ],
            }
            for b in plan.baskets
        ],
    }


@app.post("/api/plan")
def make_plan(req: PlanRequest) -> dict:
    items = parse_list(req.text)
    listings = sample_listings()
    retailers = sample_retailers()
    plan = optimize(items, listings, retailers)
    return {
        "data_source": "synthetic (dev fixtures) — NOT live retailer prices",
        "parsed_items": [
            {"key": it.key, "text": it.text, "category": it.category,
             "unit": it.unit.value, "required_qty": it.required_qty,
             "mode": it.mode.value, "brand": it.brand}
            for it in items
        ],
        "plan": plan_to_dict(plan),
    }


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    return _HTML


_HTML = """<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Smart Grocery Agent</title>
<style>
 :root{--bg:#0f1b2d;--card:#162a44;--ink:#eaf0f7;--mut:#9fb3c8;--teal:#36d3c3;--line:#294060}
 *{box-sizing:border-box} body{margin:0;background:var(--bg);color:var(--ink);
   font:16px/1.5 -apple-system,Segoe UI,Roboto,Arial;padding:16px}
 .wrap{max-width:760px;margin:0 auto}
 h1{font-size:22px;margin:.2em 0}.sub{color:var(--mut);font-size:14px;margin-bottom:14px}
 textarea{width:100%;min-height:80px;background:var(--card);color:var(--ink);
   border:1px solid var(--line);border-radius:10px;padding:12px;font-size:16px}
 button{margin-top:10px;background:var(--teal);color:#06231f;border:0;border-radius:10px;
   padding:12px 18px;font-weight:700;font-size:16px;cursor:pointer}
 .badge{display:inline-block;background:#3a2a00;color:#ffcf6b;border:1px solid #6b4e00;
   padding:2px 8px;border-radius:6px;font-size:12px;margin:8px 0}
 .card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px;margin:12px 0}
 .r{display:flex;justify-content:space-between;gap:10px}.mut{color:var(--mut)}
 .tot{font-size:20px;font-weight:800;color:var(--teal)}
 .it{border-top:1px solid var(--line);padding:8px 0;font-size:14px}
 .save{color:#7ee0a1;font-weight:700}
</style></head><body><div class="wrap">
 <h1>🛒 Smart Grocery Agent</h1>
 <div class="sub">Enter a shopping list in plain English. The agent matches products, compares
 prices and computes the lowest-cost split across retailers.</div>
 <textarea id="t">Buy 10 Park Avenue soaps, 3 packets of cooking oil, one 10 kg rice bag, 2 detergent soaps and 2 shampoo bottles</textarea>
 <button onclick="go()">Optimize my basket</button>
 <div id="out"></div>
</div>
<script>
async function go(){
 const out=document.getElementById('out'); out.innerHTML='<p class="mut">Optimizing…</p>';
 const r=await fetch('/api/plan',{method:'POST',headers:{'Content-Type':'application/json'},
   body:JSON.stringify({text:document.getElementById('t').value})});
 const d=await r.json(); const p=d.plan;
 let h='<div class="badge">⚠ '+d.data_source+'</div>';
 if(p.status!=='OPTIMAL'){h+='<div class="card">Status: '+p.status+'<br>'+(p.notes||[]).join('<br>')+'</div>';out.innerHTML=h;return;}
 h+='<div class="card"><div class="r"><div>Total payable</div><div class="tot">₹'+p.total_cost+'</div></div>';
 if(p.savings_vs_best_single>0){h+='<div class="save">Saves ₹'+p.savings_vs_best_single+' vs the cheapest single retailer</div>';}
 if(p.notes&&p.notes.length){h+='<div class="mut" style="margin-top:6px">'+p.notes.join('<br>')+'</div>';}
 h+='</div>';
 for(const b of p.baskets){
  h+='<div class="card"><div class="r"><b>'+b.retailer+'</b><b>₹'+b.total+'</b></div>';
  for(const it of b.items){
   h+='<div class="it"><div class="r"><div>'+it.packs+' × '+it.brand+' <span class="mut">('+it.name+')</span></div><div>₹'+it.cost+'</div></div>'+
      '<div class="mut">₹'+it.price_each+' each · unit ₹'+it.unit_price+'</div></div>';
  }
  h+='<div class="it mut">items ₹'+b.item_subtotal+' + delivery ₹'+b.delivery_fee+
     ' + fee ₹'+b.platform_fee+' − coupon ₹'+b.coupon_discount+'</div></div>';
 }
 out.innerHTML=h;
}
</script></body></html>"""
