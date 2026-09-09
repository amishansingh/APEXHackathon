"""Mock live signal feeds: new drops + promos, large events, and news.

Focused on North American market conditions. Deterministic per (seed, sku).
"""

from __future__ import annotations

import random
from typing import Any

from ..models import SKU

PROMOS = [
    "Flash sale — 20% off", "New model launch", "Markdown clearance",
    "Bundle promotion", "Loyalty double-points",
]
LARGE_EVENTS = [
    "Super Bowl", "Major summer concert tour", "National holiday weekend",
    "Regional trade show", "Back-to-school season",
]
NEWS = [
    "Supply route disruption reported", "Viral social moment on the category",
    "Severe weather warning", "Competitor recall", "Positive product review cycle",
]


class SignalsFeedProvider:
    """Seeded random 24h signal window scoped to a SKU."""

    def __init__(self, seed: int = 42):
        self.seed = seed

    def _rng(self, sku: SKU) -> random.Random:
        return random.Random(f"{self.seed}:signals:{sku.id}")

    async def observe(self, sku: SKU) -> dict[str, Any]:
        rng = self._rng(sku)

        def maybe(pool: list[str], p: float) -> dict[str, Any] | None:
            if rng.random() > p:
                return None
            return {
                "headline": rng.choice(pool),
                "strength": round(rng.uniform(0.3, 1.0), 2),
                "direction": rng.choice(["up", "up", "down", "neutral"]),
            }

        return {
            "sku_id": sku.id,
            "window_hours": 24,
            "promo": maybe(PROMOS, 0.6),
            "large_event": maybe(LARGE_EVENTS, 0.45),
            "news": maybe(NEWS, 0.4),
        }
