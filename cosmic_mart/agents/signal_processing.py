"""Signal Processing Agent — always-on, pulls the last 24h across three feeds.

Runs continuously, independent of the daily trigger. Uses the SKU catalogue to
scope signal matching so signals are scored against active inventory, not in the
abstract. Deduplicates across streams and passes item-scoped context downstream.
"""

from __future__ import annotations

from ..adapters.signals_feed import SignalsFeedProvider
from ..models import SKU, SignalItem
from .base import Agent


class ProcessedSignals:
    """Unified, deduplicated signal context for one SKU."""

    def __init__(self, sku: SKU, signals: list[SignalItem]):
        self.sku = sku
        self.signals = signals


class SignalProcessingAgent(Agent):
    name = "signal_processing"

    def __init__(self, feed: SignalsFeedProvider):
        self.feed = feed

    async def run(self, catalogue: list[SKU]) -> list[ProcessedSignals]:
        results: list[ProcessedSignals] = []
        for sku in catalogue:
            raw = await self.feed.observe(sku)
            signals: list[SignalItem] = []
            for kind, sig_type in (("promo", "promo"), ("large_event", "large_event"), ("news", "news")):
                entry = raw.get(kind)
                if not entry:
                    continue
                signals.append(
                    SignalItem(
                        type=sig_type,  # type: ignore[arg-type]
                        source=kind,
                        strength=float(entry["strength"]),
                        direction=entry["direction"],
                        description=entry["headline"],
                    )
                )
            results.append(ProcessedSignals(sku=sku, signals=self._dedupe(signals)))
        total = sum(len(r.signals) for r in results)
        self._log(skus=len(catalogue), signals=total)
        return results

    def _dedupe(self, signals: list[SignalItem]) -> list[SignalItem]:
        """Collapse identical headlines, keeping the strongest reading."""
        by_key: dict[tuple[str, str], SignalItem] = {}
        for s in signals:
            key = (s.type, s.description)
            if key not in by_key or s.strength > by_key[key].strength:
                by_key[key] = s
        return list(by_key.values())
