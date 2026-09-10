"""Mock live signal feeds: new drops + promos, large events, and news.

Focused on North American market conditions. Deterministic per (seed, sku).

Each template carries the categories it plausibly touches and the direction it
plausibly pushes demand, so a severe-weather warning raises space heaters rather
than pointing in a random direction. That matters twice over: it is what the
deterministic fallback uses, and it is the material the Signal Processing Agent
hands to Claude when a key is configured. A feed of headlines with random
directions would give the model nothing real to reason about.
"""

from __future__ import annotations

import random
from typing import Any

from ..models import SKU

# (headline, direction, categories it affects, (strength_low, strength_high))
# "*" means the signal is category-agnostic.
PROMOS: list[tuple[str, str, tuple[str, ...], tuple[float, float]]] = [
    ("Flash sale — 20% off", "up", ("*",), (0.5, 0.8)),
    ("New model launch", "up", ("gadgets",), (0.6, 0.95)),
    ("Markdown clearance on prior generation", "up", ("gadgets", "appliances"), (0.4, 0.7)),
    ("Bundle promotion", "up", ("home", "appliances"), (0.35, 0.6)),
    ("Loyalty double-points week", "up", ("*",), (0.3, 0.5)),
    ("Limited-edition colour drop", "up", ("gadgets",), (0.55, 0.85)),
    ("Trade-in rebate programme", "up", ("gadgets", "appliances"), (0.4, 0.7)),
    ("Free shipping weekend", "up", ("*",), (0.3, 0.55)),
    ("Influencer collaboration drop", "up", ("gadgets",), (0.6, 0.9)),
    ("Early-access pre-order window", "up", ("gadgets",), (0.5, 0.8)),
    ("Refurbished units sale", "up", ("gadgets", "appliances"), (0.3, 0.55)),
    ("Holiday gift bundle", "up", ("home", "gadgets"), (0.45, 0.75)),
    ("B2B volume discount", "up", ("appliances", "home"), (0.35, 0.6)),
    # Not every promotional development helps us — a rival's promo pulls demand away.
    ("Competitor undercut on price", "down", ("*",), (0.45, 0.75)),
    ("Successor model announced — buyers wait", "down", ("gadgets",), (0.5, 0.85)),
]

LARGE_EVENTS: list[tuple[str, str, tuple[str, ...], tuple[float, float]]] = [
    ("Super Bowl", "up", ("gadgets",), (0.6, 0.9)),
    ("Major summer concert tour", "up", ("gadgets",), (0.4, 0.7)),
    ("National holiday weekend", "up", ("*",), (0.5, 0.8)),
    ("Regional trade show", "up", ("appliances",), (0.3, 0.55)),
    ("Back-to-school season", "up", ("gadgets", "home"), (0.5, 0.8)),
    ("Black Friday / Cyber Monday", "up", ("*",), (0.7, 0.95)),
    ("Prime Day equivalent", "up", ("gadgets", "appliances"), (0.65, 0.9)),
    ("College graduation season", "up", ("gadgets",), (0.45, 0.7)),
    ("Tax refund spending window", "up", ("gadgets", "appliances"), (0.5, 0.75)),
    ("New Year resolution rush", "up", ("appliances", "home"), (0.4, 0.65)),
    ("Valentine's Day gifting peak", "up", ("gadgets",), (0.5, 0.8)),
    ("Mother's Day peak", "up", ("home", "appliances"), (0.5, 0.78)),
    ("Gaming convention", "up", ("gadgets",), (0.55, 0.85)),
    ("Major event cancelled", "down", ("gadgets",), (0.4, 0.7)),
    ("Post-holiday demand trough", "down", ("*",), (0.4, 0.7)),
]

NEWS: list[tuple[str, str, tuple[str, ...], tuple[float, float]]] = [
    ("Supply route disruption reported", "down", ("*",), (0.5, 0.85)),
    ("Viral social moment on the category", "up", ("gadgets",), (0.6, 0.95)),
    ("Severe weather warning", "up", ("appliances",), (0.55, 0.9)),
    ("Competitor recall", "up", ("*",), (0.4, 0.7)),
    ("Port strike affecting imports", "down", ("*",), (0.55, 0.85)),
    ("Chip shortage alert for electronics", "down", ("gadgets",), (0.5, 0.8)),
    ("Tariff increase announced on imports", "down", ("*",), (0.5, 0.8)),
    ("Influencer negative review goes viral", "down", ("gadgets",), (0.5, 0.8)),
    ("Category endorsed by major publication", "up", ("*",), (0.4, 0.7)),
    ("Raw material cost spike", "down", ("appliances", "home"), (0.45, 0.75)),
    ("Competitor out-of-stock widely reported", "up", ("*",), (0.5, 0.8)),
    ("Major retailer exclusive partnership ends", "down", ("*",), (0.4, 0.65)),
    ("Consumer spending pullback reported", "down", ("*",), (0.45, 0.75)),
    ("Category safety concern reported", "down", ("appliances", "home"), (0.5, 0.85)),
    ("Consumer confidence index drop", "down", ("*",), (0.4, 0.7)),
]

# Probability each feed produces a signal for a given item in the 24h window.
_FIRE_PROBABILITY = {"promo": 0.6, "large_event": 0.45, "news": 0.4}


def _relevant(
    pool: list[tuple[str, str, tuple[str, ...], tuple[float, float]]], category: str
) -> list[tuple[str, str, tuple[str, ...], tuple[float, float]]]:
    return [t for t in pool if "*" in t[2] or category in t[2]]


class SignalsFeedProvider:
    """Seeded random 24h signal window scoped to a SKU."""

    def __init__(self, seed: int = 42):
        self.seed = seed

    def _rng(self, sku: SKU) -> random.Random:
        return random.Random(f"{self.seed}:signals:{sku.id}")

    async def observe(self, sku: SKU) -> dict[str, Any]:
        rng = self._rng(sku)

        def maybe(pool: list, kind: str) -> dict[str, Any] | None:
            candidates = _relevant(pool, sku.category)
            if not candidates or rng.random() > _FIRE_PROBABILITY[kind]:
                return None
            headline, direction, _cats, (lo, hi) = rng.choice(candidates)
            return {
                "headline": headline,
                "direction": direction,
                "strength": round(rng.uniform(lo, hi), 2),
            }

        return {
            "sku_id": sku.id,
            "item_name": sku.name,
            "category": sku.category,
            "window_hours": 24,
            "promo": maybe(PROMOS, "promo"),
            "large_event": maybe(LARGE_EVENTS, "large_event"),
            "news": maybe(NEWS, "news"),
        }
