"""Mock current-inventory database — the source of the SKU catalogue.

Stands in for the real inventory table. One row per (item, sub-market), each
carrying the item identification number and the item name, which is what the
Signal Processing Agent matches signals against.

Swap this for a real database by implementing `InventorySource` (three methods:
`records`, `catalogue`, `item_index`) against your table and injecting it into
the orchestrator. Agents read the records, never the source, so nothing else
changes.
"""

from __future__ import annotations

import random

from ..data import MARKETS, SKUS
from ..models import SKU, InventoryRecord

_WAREHOUSE_BY_MARKET = {
    "US": "Dallas-DC1",
    "CA": "Toronto-DC2",
    "MX": "Monterrey-DC3",
    "NA": "Denver-DC4",
}


class InventoryDatabaseProvider:
    """Seeded current-stock rows across the four North American sub-markets."""

    def __init__(self, seed: int = 42):
        self.seed = seed

    def _rng(self, item_id: str, market_code: str) -> random.Random:
        return random.Random(f"{self.seed}:inventory:{item_id}:{market_code}")

    async def records(self) -> list[InventoryRecord]:
        rows: list[InventoryRecord] = []
        for sku in SKUS:
            for market in MARKETS:
                rng = self._rng(sku.id, market.code)
                base = {"gadgets": 900, "appliances": 380, "home": 220}.get(sku.category, 300)
                on_hand = int(base * rng.uniform(0.15, 0.55))
                rows.append(
                    InventoryRecord(
                        item_id=sku.id,
                        item_name=sku.name,
                        category=sku.category,
                        sub_market=market.code,
                        warehouse=_WAREHOUSE_BY_MARKET[market.code],
                        on_hand_units=on_hand,
                        inbound_units=int(on_hand * rng.uniform(0.0, 0.4)),
                    )
                )
        return rows

    async def catalogue(self) -> list[SKU]:
        """Distinct items currently carried, in catalogue order.

        An item with no stock anywhere in any sub-market is not active inventory
        and is left out — signals are scored against what is actually carried.
        """
        rows = await self.records()
        stocked = {
            r.item_id for r in rows if r.on_hand_units > 0 or r.inbound_units > 0
        }
        return [sku for sku in SKUS if sku.id in stocked]

    async def item_index(self) -> dict[str, str]:
        """{item_id: item_name} for every active item."""
        return {sku.id: sku.name for sku in await self.catalogue()}
