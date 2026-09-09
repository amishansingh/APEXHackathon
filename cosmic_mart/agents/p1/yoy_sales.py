"""P1 — YoY Sales History agent."""

from __future__ import annotations

import hashlib
import random
from typing import Any

from ...models import P1ImpactScore, P1Output, SKUMarket


class YoYSalesAgent:
    agent_id = "yoy_sales"

    def _mock_raw(self, target: SKUMarket) -> dict[str, Any]:
        seed = int(hashlib.sha256(f"yoy:{target.key}".encode()).hexdigest(), 16) % (2**32)
        rng = random.Random(seed)
        baseline = int(target.sku.unit_price_usd * rng.uniform(8, 25))
        return {
            "baseline_units_30d": baseline,
            "sellthrough_rate": round(rng.uniform(0.55, 0.92), 2),
            "trend": rng.choice(["rising", "stable", "declining"]),
            "yoy_growth_pct": round(rng.uniform(-15, 30), 1),
            "return_rate": round(rng.uniform(0.02, 0.12), 2),
        }

    def run(self, target: SKUMarket, first_run: bool = False) -> P1Output:
        raw = self._mock_raw(target)
        trend = raw["trend"]
        importance = 0.9  # YoY is the primary anchor
        magnitude = 1.0 + raw["yoy_growth_pct"] / 100.0
        longevity = 52.0  # full year of data
        # Risk flag: declining trend with low sellthrough is concerning
        risk_flag = trend == "declining" and raw["sellthrough_rate"] < 0.65
        return P1Output(
            sku_id=target.sku.id,
            market=target.market.code,
            agent_id=self.agent_id,
            data=raw,
            impact_score=P1ImpactScore(importance=importance, magnitude=magnitude, longevity=longevity),
            risk_flag=risk_flag,
        )
