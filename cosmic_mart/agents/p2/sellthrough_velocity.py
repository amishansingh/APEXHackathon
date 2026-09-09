"""P2 — Sell-through Velocity agent."""

from __future__ import annotations

import hashlib
import random

from ...models import P2Output, SKUMarket


class SellthroughVelocityAgent:
    agent_id = "sellthrough_velocity"

    def _mock_raw(self, target: SKUMarket) -> dict:
        seed = int(hashlib.sha256(f"velocity:{target.key}".encode()).hexdigest(), 16) % (2**32)
        rng = random.Random(seed)
        forecast_vel = max(1, rng.randint(8, 35))
        current_vel = max(0, forecast_vel * rng.uniform(0.3, 2.5))
        divergence = current_vel / forecast_vel if forecast_vel > 0 else 1.0
        units_on_hand = rng.randint(50, 500)
        stockout_days = units_on_hand / current_vel if current_vel > 0 else 999
        return {
            "current_velocity_per_day": round(current_vel, 1),
            "forecast_velocity_per_day": forecast_vel,
            "divergence_ratio": round(divergence, 2),
            "projected_stockout_days": round(stockout_days, 1),
        }

    def run(self, target: SKUMarket) -> P2Output:
        raw = self._mock_raw(target)
        # Divergence > 2x triggers immediate re-run
        immediate_rerun = raw["divergence_ratio"] > 2.0
        return P2Output(
            sku_id=target.sku.id,
            market=target.market.code,
            agent_id=self.agent_id,
            data=raw,
            hard_override=False,
            immediate_rerun_trigger=immediate_rerun,
        )
