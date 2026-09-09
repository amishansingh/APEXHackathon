"""P2 — Real-time Stock agent."""

from __future__ import annotations

import hashlib
import random

from ...models import P2Output, SKUMarket


class RealtimeStockAgent:
    agent_id = "realtime_stock"

    def _mock_raw(self, target: SKUMarket) -> dict:
        seed = int(hashlib.sha256(f"stock:{target.key}".encode()).hexdigest(), 16) % (2**32)
        rng = random.Random(seed)
        on_hand = rng.randint(0, 800)
        safety = int(target.sku.unit_price_usd * 2)
        if on_hand == 0:
            status = "out_of_stock"
        elif on_hand < safety * 0.3:
            status = "critical"
        elif on_hand < safety:
            status = "low"
        else:
            status = "healthy"
        daily_velocity = max(1, rng.randint(5, 40))
        days_of_supply = on_hand / daily_velocity if daily_velocity > 0 else 0
        return {
            "units_on_hand": on_hand,
            "safety_stock_threshold": safety,
            "status": status,
            "days_of_supply": round(days_of_supply, 1),
            "daily_velocity_estimate": daily_velocity,
        }

    def run(self, target: SKUMarket) -> P2Output:
        raw = self._mock_raw(target)
        hard_override = raw["status"] in ("out_of_stock", "critical")
        immediate_rerun = raw["status"] == "out_of_stock"
        return P2Output(
            sku_id=target.sku.id,
            market=target.market.code,
            agent_id=self.agent_id,
            data=raw,
            hard_override=hard_override,
            immediate_rerun_trigger=immediate_rerun,
        )
