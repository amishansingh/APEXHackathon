"""P1 — Seasonal Peaks agent."""

from __future__ import annotations

import hashlib
import random

from ...models import P1ImpactScore, P1Output, SKUMarket


class SeasonalPeaksAgent:
    agent_id = "seasonal_peaks"

    def _mock_raw(self, target: SKUMarket) -> dict:
        seed = int(hashlib.sha256(f"seasonal:{target.key}".encode()).hexdigest(), 16) % (2**32)
        rng = random.Random(seed)
        return {
            "same_period_last_year_pct_vs_baseline": round(rng.uniform(-20, 60), 1),
            "three_year_trend": rng.choice(["growing", "stable", "shrinking"]),
            "peak_uplift_multiplier": round(rng.uniform(1.0, 2.2), 2),
            "peak_onset_days": rng.randint(5, 45),
            "peak_duration_days": rng.randint(7, 30),
            "known_recurring_peak": rng.choice([True, True, False]),
            "historical_std_dev_pct": round(rng.uniform(5, 30), 1),
        }

    def run(self, target: SKUMarket, first_run: bool = False) -> P1Output:
        raw = self._mock_raw(target)
        trend = raw["three_year_trend"]
        trend_adj = {"growing": 0.08, "stable": 0.0, "shrinking": -0.08}[trend]
        magnitude = raw["peak_uplift_multiplier"] + trend_adj
        importance = 0.85 if raw["known_recurring_peak"] else 0.6
        longevity = raw["peak_duration_days"] / 7.0
        return P1Output(
            sku_id=target.sku.id,
            market=target.market.code,
            agent_id=self.agent_id,
            data=raw,
            impact_score=P1ImpactScore(importance=importance, magnitude=magnitude, longevity=longevity),
            risk_flag=False,
        )
