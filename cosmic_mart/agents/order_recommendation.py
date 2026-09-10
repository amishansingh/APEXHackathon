"""Order Recommendation — packages a synthesized forecast into an executable order.

Contents (§6): recommended action (rebalance / reorder / hold), quantity,
supplier, warehouse routing, confidence score, forecast range. Passed to the
Human in the Loop for final review before execution.
"""

from __future__ import annotations

from ..models import EscalationFlag, ForecastRange, OrderRecommendation, SKU
from .base import Agent

_SUPPLIERS: dict[str, list[str]] = {
    "gadgets":    ["Helios Components", "Apex Electronics Ltd.", "NovaTech Supply Chain"],
    "appliances": ["Meridian Assembly", "Cardinal HVAC Group",   "Solaris Manufacturing"],
    "home":       ["Terra Goods Co.",   "Hestia Home Supply",    "Crestwood Imports"],
}
_WAREHOUSES = {
    "US": "Dallas-DC1",
    "CA": "Toronto-DC2",
    "MX": "Monterrey-DC3",
    "NA": "Denver-DC4",
}
# SKUs with a primary warehouse other than Dallas-DC1 (US default).
_PRIMARY_WAREHOUSE: dict[str, str] = {
    "APP-2002": "Toronto-DC2",   # heater: Canada primary
    "APP-2003": "Toronto-DC2",   # chest freezer: cold-climate primary
    "GAD-1002": "Dallas-DC1",
    "HOM-3002": "Dallas-DC1",
}


class OrderRecommendationAgent(Agent):
    name = "order_recommendation"

    def decide_action(self, *, baseline: float, expected: int) -> tuple[str, int]:
        """Pick the action and the quantity it commits.

        Split out from `package` so the synthesizer can size its escalation
        flags against the order actually being proposed. Valuing the forecast
        instead flagged holds — which order nothing — as high-value orders.
        """
        if expected > baseline * 1.05:
            return "reorder", expected
        if expected < baseline * 0.95:
            return "rebalance", max(0, round(baseline - expected))
        return "hold", 0

    def package(
        self,
        *,
        sku: SKU,
        action: str,
        quantity: int,
        forecast_range: ForecastRange,
        confidence: float,
        divergence: float,
        conflict_summary: str | None,
        escalation_flags: list[EscalationFlag],
        data_quality_flags: list[str],
        hist_weight: float,
        sig_weight: float,
        reasoning: str,
    ) -> OrderRecommendation:
        supplier_pool = _SUPPLIERS.get(sku.category, ["General Supply Co."])
        supplier = supplier_pool[hash(sku.id) % len(supplier_pool)] if action == "reorder" else None
        warehouse = _PRIMARY_WAREHOUSE.get(sku.id, _WAREHOUSES["US"]) if action != "hold" else None

        return OrderRecommendation(
            sku=sku,
            action=action,  # type: ignore[arg-type]
            quantity=quantity,
            supplier=supplier,
            warehouse=warehouse,
            forecast_range=forecast_range,
            confidence=round(confidence, 3),
            escalation_flags=escalation_flags,
            data_quality_flags=list(data_quality_flags),
            conflict_summary=conflict_summary,
            divergence_score=round(divergence, 3),
            hist_weight=hist_weight,
            sig_weight=sig_weight,
            reasoning=reasoning,
        )
