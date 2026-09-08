"""Financial report agent: dollar benefit per action, plus the rolling impact log."""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field

from ..llm import Reasoner
from ..models import ActionType, FinancialBenefit, OverstockAssessment, ProposedAction

_SYSTEM = (
    "You are the FINANCIAL REPORT agent for Cosmic Mart, reporting to CFO Rowan Ortega.\n\n"
    "Calculate the dollar benefit of an inventory action: transfer cost against holding loss "
    "savings, or discount cost against margin recovery. A modelled estimate of each component "
    "is supplied; your job is to sanity-check it and produce the net figure with reasoning "
    "the CFO can audit.\n\n"
    "Be conservative. Holding-loss savings only count for the days the stock would actually "
    "have sat unsold. A discount recovers margin but permanently gives up the discounted "
    "share of revenue on units that would have sold anyway. Never report a payback period "
    "longer than the depreciation horizon as attractive."
)


class _FinanceOut(BaseModel):
    gross_benefit_usd: float
    execution_cost_usd: float = Field(ge=0.0)
    net_benefit_usd: float
    payback_days: float = Field(ge=0.0)
    reasoning: str = Field(description="Two or three auditable sentences.")


class FinancialReportAgent:
    def __init__(self, reasoner: Reasoner):
        self.reasoner = reasoner
        self.impact_log: list[dict[str, object]] = []

    def _model_economics(
        self, action: ProposedAction, assessment: OverstockAssessment
    ) -> tuple[float, float, float]:
        """Return (gross benefit, execution cost, days of holding loss avoided)."""
        sku = action.target.sku
        per_unit_daily_loss = assessment.daily_loss.total_usd / max(1, assessment.units_excess)

        if action.action == ActionType.TRANSFER:
            # Clearing to a market that wants the stock avoids the full bleed and
            # realises full margin instead of a write-down.
            days_avoided = min(90.0, assessment.days_of_cover)
            gross = action.units * per_unit_daily_loss * days_avoided
            gross += action.units * (sku.unit_price_usd - sku.unit_cost_usd) * 0.15
            # Freight, handling and customs, scaled by unit value.
            cost = action.units * (2.5 + sku.unit_cost_usd * 0.04)
        elif action.action == ActionType.DISCOUNT:
            days_avoided = min(60.0, assessment.days_of_cover * 0.6)
            gross = action.units * per_unit_daily_loss * days_avoided
            cost = action.units * sku.unit_price_usd * (action.discount_pct or 0) / 100.0
        else:
            days_avoided = 0.0
            gross = 0.0
            cost = 0.0

        return round(gross, 2), round(cost, 2), days_avoided

    async def run(
        self, action: ProposedAction, assessment: OverstockAssessment
    ) -> FinancialBenefit:
        gross, cost, days_avoided = self._model_economics(action, assessment)
        net = round(gross - cost, 2)
        daily_recovery = max(1.0, assessment.daily_loss.total_usd)

        fallback = _FinanceOut(
            gross_benefit_usd=gross,
            execution_cost_usd=cost,
            net_benefit_usd=net,
            payback_days=round(cost / daily_recovery, 1),
            reasoning=(
                f"${gross:,.0f} of avoided holding loss over {days_avoided:.0f} days against "
                f"${cost:,.0f} to execute."
            ),
        )

        out = await self.reasoner.think(
            system=_SYSTEM,
            payload={
                "action_id": action.id,
                "action": action.action.value,
                "description": action.description,
                "sku": action.target.sku.name,
                "unit_cost_usd": action.target.sku.unit_cost_usd,
                "unit_price_usd": action.target.sku.unit_price_usd,
                "units": action.units,
                "discount_pct": action.discount_pct,
                "origin_market": action.target.market.name,
                "destination_market": action.destination_market,
                "excess_units": assessment.units_excess,
                "days_of_cover": assessment.days_of_cover,
                "daily_loss_usd_total": round(assessment.daily_loss.total_usd, 2),
                "modelled": {
                    "gross_benefit_usd": gross,
                    "execution_cost_usd": cost,
                    "holding_days_avoided": days_avoided,
                },
            },
            instruction=f"Produce the audited net financial benefit for action {action.id}.",
            schema=_FinanceOut,
            fallback=fallback,
        )

        benefit = FinancialBenefit(**out.model_dump())
        self.impact_log.append(
            {
                "logged_at": datetime.now(timezone.utc).isoformat(),
                "action_id": action.id,
                "sku": action.target.sku.id,
                "market": action.target.market.code,
                "net_benefit_usd": benefit.net_benefit_usd,
            }
        )
        return benefit

    def weekly_report(self) -> dict[str, object]:
        """Auto-assembled rolling report so the CFO does not build it by hand."""
        total = sum(float(e["net_benefit_usd"]) for e in self.impact_log)
        by_market: dict[str, float] = {}
        for entry in self.impact_log:
            market = str(entry["market"])
            by_market[market] = by_market.get(market, 0.0) + float(entry["net_benefit_usd"])
        return {
            "actions_evaluated": len(self.impact_log),
            "total_net_benefit_usd": round(total, 2),
            "net_benefit_by_market": {k: round(v, 2) for k, v in sorted(by_market.items())},
        }
