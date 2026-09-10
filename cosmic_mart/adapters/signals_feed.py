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

# Item-specific signals — only fire for the named SKU ID.
# These produce the most compelling demo moments: a reviewer sees a conflict
# that is specific to the product, not a generic category signal.
SKU_SIGNALS: dict[str, list[tuple[str, str, tuple[str, ...], tuple[float, float]]]] = {
    "GAD-1001": [
        ("Nova Handset X featured in major carrier bundle deal", "up",   ("gadgets",), (0.75, 0.95)),
        ("Nova Handset X successor model rumoured for Q1",       "down", ("gadgets",), (0.60, 0.85)),
    ],
    "GAD-1002": [
        ("Orbit Earbuds Pro wins Editor's Choice award",         "up",   ("gadgets",), (0.65, 0.90)),
        ("Counterfeit Orbit Earbuds circulating online",         "down", ("gadgets",), (0.50, 0.75)),
    ],
    "GAD-1003": [
        ("Pulse Smartwatch 4 health-tracking feature goes viral","up",   ("gadgets",), (0.70, 0.92)),
    ],
    "GAD-1004": [
        ("Nebula Tablet Pro back-to-school bundle announced",    "up",   ("gadgets",), (0.65, 0.88)),
    ],
    "GAD-1006": [
        ("Stellar Gaming Headset used at world esports finals",  "up",   ("gadgets",), (0.72, 0.93)),
    ],
    "APP-2001": [
        ("Halo AC rated #1 in Consumer Reports cooling test",    "up",   ("appliances",), (0.70, 0.90)),
        ("Heat wave forecast — cooling appliance demand spike",  "up",   ("appliances",), (0.75, 0.95)),
    ],
    "APP-2002": [
        ("Polar vortex warning issued for Midwest and Canada",   "up",   ("appliances",), (0.78, 0.96)),
        ("Ember Heater safety recall on prior generation model", "down", ("appliances",), (0.55, 0.80)),
    ],
    "APP-2003": [
        ("National Food Storage Awareness campaign",             "up",   ("appliances",), (0.50, 0.75)),
    ],
    "APP-2004": [
        ("Wildfire smoke alert issued across Pacific Northwest",  "up",  ("appliances",), (0.72, 0.94)),
        ("Zephyr Air Purifier filter shortage reported",         "down", ("appliances",), (0.55, 0.78)),
    ],
    "HOM-3001": [
        ("Terra Cookware featured on prime-time cooking show",   "up",   ("home",), (0.65, 0.88)),
    ],
    "HOM-3002": [
        ("Luxe Bedding Bundle viral TikTok review",              "up",   ("home",), (0.68, 0.92)),
    ],
    "HOM-3004": [
        ("Spring declutter trend drives storage product surge",  "up",   ("home",), (0.60, 0.82)),
    ],
}

# Probability each feed produces a signal for a given item in the 24h window.
_FIRE_PROBABILITY = {"promo": 0.70, "large_event": 0.58, "news": 0.52}
_SKU_SIGNAL_PROBABILITY = 0.72


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

        sku_specific: dict[str, Any] | None = None
        sku_pool = SKU_SIGNALS.get(sku.id)
        if sku_pool and rng.random() <= _SKU_SIGNAL_PROBABILITY:
            headline, direction, _cats, (lo, hi) = rng.choice(sku_pool)
            sku_specific = {
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
            "sku_specific": sku_specific,
        }
