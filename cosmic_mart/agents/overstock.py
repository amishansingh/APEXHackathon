"""Overstock loss agent: the continuous cost clock and the block feedback loop."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from ..adapters.base import InventorySource
from ..config import SETTINGS
from ..llm import Reasoner
from ..models import (
    ActionType,
    BlockRecord,
    LossComponents,
    OverstockAssessment,
    SKUMarket,
    SynthesizedDemand,
)

_SYSTEM = (
    "You are the OVERSTOCK LOSS agent for Cosmic Mart. You run a continuous cost clock on "
    "every overstocked SKU across all warehouses.\n\n"
    "The three daily loss components have already been computed for you: capital tied up in "
    "unsold goods, warehousing and storage fees, and depreciation risk. Gadgets are 77% of "
    "revenue and go stale as new models release, so depreciation dominates there.\n\n"
    "Your job is judgement, not arithmetic: classify severity and write commentary that a "
    "CFO can act on. Weigh the daily bleed against days of cover and against how much of the "
    "loss is recoverable. A large but slow-depreciating position is less urgent than a "
    "smaller gadget position going stale. If a prior proposal for this SKU was blocked, do "
    "not re-raise the same idea; acknowledge the block and reason around it."
)


class _OverstockOut(BaseModel):
    severity: Literal["none", "low", "moderate", "severe"]
    commentary: str = Field(description="Two or three sentences a CFO can act on.")


class OverstockLossAgent:
    def __init__(self, reasoner: Reasoner, inventory: InventorySource):
        self.reasoner = reasoner
        self.inventory = inventory
        self._blocks: list[BlockRecord] = []

    def register_block(self, record: BlockRecord) -> None:
        """Close the feedback loop so a rejected proposal stops recurring."""
        self._blocks.append(record)

    def blocks_for(self, target: SKUMarket) -> list[BlockRecord]:
        return [b for b in self._blocks if b.target_key == target.key]

    def is_blocked(self, target: SKUMarket, action: ActionType) -> bool:
        return any(b.target_key == target.key and b.action == action for b in self._blocks)

    def _cost_clock(self, target: SKUMarket, excess_units: int) -> LossComponents:
        cost = target.sku.unit_cost_usd
        return LossComponents(
            capital_tied_usd=round(
                excess_units * cost * SETTINGS.capital_cost_annual_rate / 365, 2
            ),
            storage_fees_usd=round(excess_units * SETTINGS.storage_cost_per_unit_day, 2),
            depreciation_usd=round(excess_units * cost * target.sku.depreciation_rate_daily, 2),
        )

    async def run(self, demand: SynthesizedDemand) -> OverstockAssessment:
        target = demand.target
        stock = await self.inventory.stock_level(target)
        on_hand = int(stock["units_on_hand"])
        available = on_hand + int(stock["units_in_transit"])

        # Excess is measured against the optimistic end of the forecast, so the
        # system only calls something overstock when even good demand leaves it unsold.
        excess = max(0, available - demand.forecast.units_high)
        daily_rate = max(1.0, float(stock["trailing_weekly_sales"]) / 7.0)
        days_of_cover = round(on_hand / daily_rate, 1)
        loss = self._cost_clock(target, excess)

        fallback = _OverstockOut(
            severity=_severity(excess, available, days_of_cover),
            commentary=(
                f"{excess:,} units above the high forecast at {days_of_cover} days of cover, "
                f"bleeding ${loss.total_usd:,.0f}/day."
            ),
        )

        out = await self.reasoner.think(
            system=_SYSTEM,
            payload={
                "sku": target.sku.name,
                "category": target.sku.category,
                "market": target.market.name,
                "warehouse": stock["warehouse"],
                "units_on_hand": on_hand,
                "units_in_transit": stock["units_in_transit"],
                "forecast_units_high": demand.forecast.units_high,
                "forecast_units_expected": demand.forecast.units_expected,
                "forecast_confidence": demand.forecast.confidence,
                "excess_units": excess,
                "days_of_cover": days_of_cover,
                "daily_loss_usd": {
                    "capital_tied": loss.capital_tied_usd,
                    "storage_fees": loss.storage_fees_usd,
                    "depreciation": loss.depreciation_usd,
                    "total": round(loss.total_usd, 2),
                },
                "prior_blocked_proposals": [
                    {"action": b.action.value, "reason": b.reason} for b in self.blocks_for(target)
                ],
            },
            instruction=(
                f"Classify the overstock severity for {target.sku.name} in "
                f"{target.market.name} and write the CFO commentary."
            ),
            schema=_OverstockOut,
            fallback=fallback,
        )

        return OverstockAssessment(
            target=target,
            units_on_hand=on_hand,
            units_excess=excess,
            daily_loss=loss,
            days_of_cover=days_of_cover,
            severity=out.severity,
            commentary=out.commentary,
        )


def _severity(excess: int, available: int, days_of_cover: float) -> Literal["none", "low", "moderate", "severe"]:
    if excess == 0:
        return "none"
    share = excess / max(1, available)
    if share > 0.4 or days_of_cover > 45:
        return "severe"
    if share > 0.2 or days_of_cover > 28:
        return "moderate"
    return "low"
