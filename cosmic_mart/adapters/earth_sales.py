"""Mock 4 yr Earth sales feed. Deterministic per (seed, sku) so runs are repeatable."""

from __future__ import annotations

import random
from typing import Any

from ..models import SKU

SUB_MARKETS = ["US", "CA", "MX", "NA"]
CHANNELS = ["retail", "online", "wholesale"]

_CATEGORY_BASE: dict[str, float] = {"gadgets": 380, "appliances": 160, "home": 90}

# Per-SKU monthly unit baselines — override the category default.
_SKU_BASE: dict[str, float] = {
    "GAD-1001": 420.0,   # flagship handset — high volume, strong brand pull
    "GAD-1002": 550.0,   # earbuds — accessories move fastest
    "GAD-1003": 480.0,   # smartwatch — growing YoY
    "GAD-1004": 310.0,   # tablet — mid-tier
    "GAD-1005": 260.0,   # BT speaker — impulse buy
    "GAD-1006": 190.0,   # gaming headset — enthusiast niche
    "GAD-1007": 140.0,   # action cam — specialty, slow mover
    "APP-2001": 175.0,   # AC — strong summer peak
    "APP-2002": 195.0,   # space heater — strong winter peak
    "APP-2003": 105.0,   # chest freezer — low velocity, high value
    "APP-2004": 145.0,   # air purifier — growing post-pandemic
    "HOM-3001": 95.0,    # cookware set — steady
    "HOM-3002": 210.0,   # bedding — high-volume household staple
    "HOM-3003": 80.0,    # desk lamp — slow
    "HOM-3004": 130.0,   # storage rack — seasonal (spring/fall)
}

# Per-SKU sub-market weight distributions. Keys are market codes (US, CA, MX, NA).
# SKUs not listed fall back to uniform random draws.
_SKU_SUBMARKET: dict[str, dict[str, float]] = {
    "APP-2001": {"US": 0.55, "MX": 0.25, "CA": 0.12, "NA": 0.08},  # AC: sunbelt heavy
    "APP-2002": {"CA": 0.40, "US": 0.38, "NA": 0.14, "MX": 0.08},  # heater: Canada heavy
    "APP-2003": {"US": 0.50, "CA": 0.28, "NA": 0.14, "MX": 0.08},  # freezer: cold-climate
    "GAD-1001": {"US": 0.58, "CA": 0.18, "MX": 0.15, "NA": 0.09},  # flagship: US dominant
    "GAD-1002": {"US": 0.50, "CA": 0.20, "MX": 0.18, "NA": 0.12},  # earbuds: broad spread
    "GAD-1006": {"US": 0.62, "CA": 0.18, "MX": 0.12, "NA": 0.08},  # gaming: US dominant
    "HOM-3002": {"US": 0.48, "CA": 0.22, "MX": 0.18, "NA": 0.12},  # bedding: even spread
}

SEASONALITY: dict[str, dict[str, float]] = {
    "gadgets":    {"Q1": 0.85, "Q2": 0.95, "Q3": 1.05, "Q4": 1.35},
    "appliances": {"Q1": 0.90, "Q2": 1.10, "Q3": 1.05, "Q4": 1.10},
    "home":       {"Q1": 0.80, "Q2": 1.15, "Q3": 1.00, "Q4": 1.20},
}
_DEFAULT_SEASON = {"Q1": 0.90, "Q2": 1.00, "Q3": 1.00, "Q4": 1.15}


class EarthSalesProvider:
    """Seeded random North American sales history for a SKU."""

    def __init__(self, seed: int = 42):
        self.seed = seed

    def _rng(self, sku: SKU) -> random.Random:
        return random.Random(f"{self.seed}:earth:{sku.id}")

    async def observe(self, sku: SKU) -> dict[str, Any]:
        rng = self._rng(sku)
        base = _SKU_BASE.get(sku.id) or _CATEGORY_BASE.get(sku.category, 120)
        monthly = base * rng.uniform(0.7, 1.4)

        sub_weights = _SKU_SUBMARKET.get(sku.id)
        if sub_weights:
            by_submarket = {
                m: round(monthly * sub_weights[m] * rng.uniform(0.93, 1.07), 1)
                for m in SUB_MARKETS
            }
        else:
            by_submarket = {m: round(monthly * rng.uniform(0.1, 0.45), 1) for m in SUB_MARKETS}

        season = SEASONALITY.get(sku.category, _DEFAULT_SEASON)
        by_season = {q: round(monthly * mult * rng.uniform(0.92, 1.08), 1) for q, mult in season.items()}
        return {
            "sku_id": sku.id,
            "years_of_history": 4,
            "monthly_units": round(monthly, 1),
            "by_submarket": by_submarket,
            "by_channel": {c: round(monthly * rng.uniform(0.2, 0.5), 1) for c in CHANNELS},
            "by_season": by_season,
            "trend_pct_yoy": round(rng.uniform(-8, 22), 1),
        }
