"""P1 — Supplier Lead Times agent."""

from __future__ import annotations

import hashlib
import random
from datetime import date, timedelta

from ...models import P1ImpactScore, P1Output, SKUMarket


class SupplierLeadTimesAgent:
    agent_id = "supplier_lead_times"

    def _mock_raw(self, target: SKUMarket) -> dict:
        seed = int(hashlib.sha256(f"leadtime:{target.key}".encode()).hexdigest(), 16) % (2**32)
        rng = random.Random(seed)
        quoted = rng.randint(7, 45)
        actual = quoted + rng.randint(-3, 14)
        trigger_days = actual + rng.randint(3, 10)
        return {
            "quoted_lead_time_days": quoted,
            "actual_lead_time_days": actual,
            "variability_score": round(rng.uniform(0.1, 0.8), 2),
            "recommended_order_trigger_days": trigger_days,
            "route": f"{target.market.region}-warehouse",
        }

    def run(self, target: SKUMarket, first_run: bool = False) -> P1Output:
        raw = self._mock_raw(target)
        # Higher variability = more important to plan ahead
        importance = 0.5 + raw["variability_score"] * 0.4
        # Lead time doesn't directly change demand magnitude
        magnitude = 1.0
        longevity = raw["recommended_order_trigger_days"] / 7.0
        order_trigger_date = (date.today() + timedelta(days=raw["recommended_order_trigger_days"])).isoformat()
        raw["order_trigger_date"] = order_trigger_date
        return P1Output(
            sku_id=target.sku.id,
            market=target.market.code,
            agent_id=self.agent_id,
            data=raw,
            impact_score=P1ImpactScore(importance=importance, magnitude=magnitude, longevity=longevity),
            risk_flag=False,
        )
