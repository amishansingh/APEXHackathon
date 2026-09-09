"""P2 — Inbound Shipments agent."""

from __future__ import annotations

import hashlib
import random

from ...models import P2Output, SKUMarket


class InboundShipmentsAgent:
    agent_id = "inbound_shipments"

    def _mock_raw(self, target: SKUMarket) -> dict:
        seed = int(hashlib.sha256(f"inbound:{target.key}".encode()).hexdigest(), 16) % (2**32)
        rng = random.Random(seed)
        inbound = rng.randint(0, 500)
        arrival_days = rng.randint(2, 21)
        daily_vel = max(1, rng.randint(5, 40))
        adj_days = inbound / daily_vel if daily_vel > 0 else 0
        on_time = rng.random() > 0.2
        return {
            "inbound_units": inbound,
            "expected_arrival_days": arrival_days,
            "adjusted_days_of_supply": round(adj_days, 1),
            "shipment_on_time": on_time,
            "supplier": f"Supplier-{rng.randint(1, 5)}",
        }

    def run(self, target: SKUMarket) -> P2Output:
        raw = self._mock_raw(target)
        return P2Output(
            sku_id=target.sku.id,
            market=target.market.code,
            agent_id=self.agent_id,
            data=raw,
            hard_override=False,
            immediate_rerun_trigger=not raw["shipment_on_time"] and raw["inbound_units"] > 200,
        )
