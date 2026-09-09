"""Mock 4 yr Earth sales feed. Deterministic per (seed, sku) so runs are repeatable."""

from __future__ import annotations

import random
from typing import Any

from ..models import SKU

SUB_MARKETS = ["US", "CA", "MX", "NA"]
CHANNELS = ["retail", "online", "wholesale"]


class EarthSalesProvider:
    """Seeded random North American sales history for a SKU."""

    def __init__(self, seed: int = 42):
        self.seed = seed

    def _rng(self, sku: SKU) -> random.Random:
        return random.Random(f"{self.seed}:earth:{sku.id}")

    async def observe(self, sku: SKU) -> dict[str, Any]:
        rng = self._rng(sku)
        # Gadgets move fastest; anchor the monthly base on category.
        base = {"gadgets": 380, "appliances": 160, "home": 90}.get(sku.category, 120)
        monthly = base * rng.uniform(0.7, 1.4)
        by_submarket = {m: round(monthly * rng.uniform(0.1, 0.45), 1) for m in SUB_MARKETS}
        return {
            "sku_id": sku.id,
            "years_of_history": 4,
            "monthly_units": round(monthly, 1),
            "by_submarket": by_submarket,
            "by_channel": {c: round(monthly * rng.uniform(0.2, 0.5), 1) for c in CHANNELS},
            "trend_pct_yoy": round(rng.uniform(-8, 22), 1),
        }
