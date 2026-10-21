"""Smart Grocery Shopping & Price-Optimization Agent.

Honest scope: the parser, product-matching, price model and the MILP cost
optimizer are real and fully tested on labeled synthetic data. Live retailer
integrations are added only where a legitimate, ToS-permitted access path
exists; every adapter declares its real capabilities and nothing synthetic is
ever presented as live/verified data.
"""
from .models import (Assignment, Listing, Mode, Plan, Retailer, RetailerBasket,
                     ShoppingItem, Unit)
from .matching import match, candidates, MatchResult, CONFIRM_THRESHOLD
from .optimizer import optimize
from .parser import parse_list

__version__ = "0.1.0"
__all__ = ["Assignment", "Listing", "Mode", "Plan", "Retailer", "RetailerBasket",
           "ShoppingItem", "Unit", "match", "candidates", "MatchResult",
           "CONFIRM_THRESHOLD", "optimize", "parse_list", "__version__"]
