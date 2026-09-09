"""Order Recommendation — packages a synthesized forecast into an executable order.

Contents (§6): recommended action (rebalance / reorder / hold), quantity,
supplier, warehouse routing, confidence score, forecast range. Passed to the
Human in the Loop for final review before execution.
"""

from __future__ import annotations

from ..models import EscalationFlag, ForecastRange, OrderRecommendation, SKU
from .base import Agent

_SUPPLIERS = {
    "gadgets": "Helios Components",
    "appliances": "Meridian Assembly",
    "home": "Terra Goods Co.",
}
_WAREHOUSES = {
    "US": "Dallas-DC1",
    "CA": "Toronto-DC2",
    "MX": "Monterrey-DC3",
    "NA": "Denver-DC4",
}


class OrderRecommendationAgent(Agent):
    name = "order_recommendation"

    def package(
        self,
        *,
        sku: SKU,
        baseline: float,
        forecast_range: ForecastRange,
        confidence: float,
        divergence: float,
        conflict_summary: str | None,
        escalation_flags: list[EscalationFlag],
        hist_weight: float,
        sig_weight: float,
        reasoning: str,
    ) -> OrderRecommendation:
        expected = forecast_range.units_expected
        if expected > baseline * 1.05:
            action = "reorder"
            quantity = expected
        elif expected < baseline * 0.95:
            action = "rebalance"
            quantity = max(0, round(baseline - expected))
        else:
            action = "hold"
            quantity = 0

        supplier = _SUPPLIERS.get(sku.category) if action == "reorder" else None
        warehouse = _WAREHOUSES["US"] if action != "hold" else None

        return OrderRecommendation(
            sku=sku,
            action=action,  # type: ignore[arg-type]
            quantity=quantity,
            supplier=supplier,
            warehouse=warehouse,
            forecast_range=forecast_range,
            confidence=round(confidence, 3),
            escalation_flags=escalation_flags,
            conflict_summary=conflict_summary,
            divergence_score=round(divergence, 3),
            hist_weight=hist_weight,
            sig_weight=sig_weight,
            reasoning=reasoning,
        )
