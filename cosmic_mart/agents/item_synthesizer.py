"""Item synthesizer: maps a P3 trigger to the set of affected SKUs."""

from __future__ import annotations

from ..models import AffectedSKU, ItemSynthesizerOutput, Market, SKU, TriggerSignal

# Which categories respond to which signals
_CATEGORY_SIGNAL_RESPONSE: dict[str, list[str]] = {
    "gadgets": [
        "cultural", "weather", "social", "macro", "local_events",
        "viral_trend", "social_signal", "macro_shift", "competitor product recall",
    ],
    "appliances": ["weather", "macro", "macro_shift"],
    "home": ["cultural", "local_events", "macro_shift"],
}


class ItemSynthesizer:
    """Scopes the SKU list that P1 and P2 agents need to run against."""

    def run(self, trigger: TriggerSignal, skus: list[SKU], market: Market) -> ItemSynthesizerOutput:
        categories = set(trigger.affected_sku_categories)
        # Also include categories that respond to this event_type
        event_lower = trigger.event_type.lower()
        for cat, signals in _CATEGORY_SIGNAL_RESPONSE.items():
            if any(s in event_lower for s in signals):
                categories.add(cat)

        affected: list[AffectedSKU] = []
        for sku in skus:
            if not categories or sku.category in categories:
                affected.append(AffectedSKU(sku_id=sku.id, market=market.code, category=sku.category))

        if not affected:
            affected = [AffectedSKU(sku_id=s.id, market=market.code, category=s.category) for s in skus]

        return ItemSynthesizerOutput(affected_skus=affected, source_trigger=trigger)
