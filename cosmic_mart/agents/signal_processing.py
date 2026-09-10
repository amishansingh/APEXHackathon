"""Signal Processing Agent — pulls the last 24h across three feeds.

Reads the SKU catalogue from the current-inventory database (spec §4) and uses
the item identification numbers and item names to scope signal matching: signals
are scored against active inventory, not in the abstract. Deduplicates across
streams and passes item-scoped context to the Signal Report Agent.

With a key configured, Claude judges each headline's direction and strength
against the specific item. Without one, the feed's own category/direction mapping
is used unchanged — same shape, same contract.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..adapters.inventory_db import InventoryDatabaseProvider
from ..adapters.signals_feed import SignalsFeedProvider
from ..llm import Reasoner
from ..models import SKU, SignalItem
from .base import Agent

_SYSTEM = """You are the Signal Processing Agent in Cosmic Mart's demand \
forecasting pipeline, covering the North American market.

You receive one inventory item (its identification number, name and category) \
and the raw signals detected for it in the last 24 hours across three feeds: \
new drops + promos, large events, and news.

For each raw signal, decide:
- direction: "up" if it raises expected demand for THIS item, "down" if it \
lowers it, "neutral" if it does not move this item.
- strength: 0.0-1.0, how strongly it moves demand for THIS item.

Judge relevance to the specific item, not the category in general. A severe \
weather warning moves space heaters sharply and cookware barely at all. A \
supply route disruption lowers availability and therefore sales. Keep the \
headline and source unchanged; you are scoring, not rewriting. Drop nothing — \
return one entry per raw signal, using "neutral" with low strength when a \
signal does not touch this item."""


class ProcessedSignals:
    """Unified, deduplicated signal context for one SKU."""

    def __init__(self, sku: SKU, signals: list[SignalItem]):
        self.sku = sku
        self.signals = signals


class SignalAssessment(BaseModel):
    """What Claude returns for one item: the same signals, scored."""

    signals: list[SignalItem] = Field(default_factory=list)


class SignalProcessingAgent(Agent):
    name = "signal_processing"

    def __init__(
        self,
        feed: SignalsFeedProvider,
        inventory: InventoryDatabaseProvider | None = None,
        reasoner: Reasoner | None = None,
    ):
        self.feed = feed
        self.inventory = inventory or InventoryDatabaseProvider()
        self.reasoner = reasoner or Reasoner()

    async def run(self, catalogue: list[SKU] | None = None) -> list[ProcessedSignals]:
        """Process the 24h window for every active item.

        `catalogue` is optional — when omitted the agent retrieves it from the
        current-inventory database itself, which is the spec'd wiring. Callers
        that already hold a catalogue (the orchestrator, tests) pass it in to
        avoid a second read of the same rows.
        """
        if catalogue is None:
            catalogue = await self.inventory.catalogue()

        item_index = await self.inventory.item_index()

        results: list[ProcessedSignals] = []
        for sku in catalogue:
            raw = await self.feed.observe(sku)
            deterministic = self._deterministic_signals(raw)

            assessed = await self.reasoner.think(
                system=_SYSTEM,
                payload={
                    "item_id": sku.id,
                    # Falls back to the SKU's own name for an item the index
                    # does not carry, so an explicit catalogue still works.
                    "item_name": item_index.get(sku.id, sku.name),
                    "category": sku.category,
                    "window_hours": raw.get("window_hours", 24),
                    "raw_signals": [s.model_dump() for s in deterministic],
                },
                instruction=(
                    "Score each raw signal's direction and strength for this "
                    "specific inventory item."
                ),
                schema=SignalAssessment,
                fallback=SignalAssessment(signals=deterministic),
            )

            results.append(
                ProcessedSignals(sku=sku, signals=self._dedupe(assessed.signals))
            )

        total = sum(len(r.signals) for r in results)
        self._log(items=len(catalogue), signals=total, scoped_by="inventory_db")
        return results

    def _deterministic_signals(self, raw: dict) -> list[SignalItem]:
        """The feed's own reading — used as-is when Claude is unavailable."""
        signals: list[SignalItem] = []
        for kind in ("promo", "large_event", "news"):
            entry = raw.get(kind)
            if not entry:
                continue
            signals.append(
                SignalItem(
                    type=kind,  # type: ignore[arg-type]
                    source=kind,
                    strength=float(entry["strength"]),
                    direction=entry["direction"],
                    description=entry["headline"],
                )
            )
        return signals

    def _dedupe(self, signals: list[SignalItem]) -> list[SignalItem]:
        """Collapse the same headline across streams, keeping the strongest."""
        by_key: dict[str, SignalItem] = {}
        for s in signals:
            # Keyed on the headline alone: the same story can legitimately arrive
            # on two feeds (a launch as both a promo and a news item), and that
            # is exactly the duplicate worth collapsing.
            key = s.description.strip().lower()
            if key not in by_key or s.strength > by_key[key].strength:
                by_key[key] = s
        return list(by_key.values())
