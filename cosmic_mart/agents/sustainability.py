"""Sustainability agent: carbon scoring plus the carbon credit bank."""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..llm import Reasoner
from ..models import ActionType, CarbonScore, OverstockAssessment, ProposedAction

_SYSTEM = (
    "You are the SUSTAINABILITY agent for Cosmic Mart. You score every proposed inventory "
    "action against a carbon cost model, evaluating the emissions footprint of transfers, "
    "shipping routes, and supplier switches.\n\n"
    "Output a normalised carbon score from 0 to 100 where HIGHER MEANS A HEAVIER CARBON "
    "BURDEN. The tradeoff agent consumes this alongside a dollar benefit, so the scale must "
    "stay consistent across actions: a long intercontinental air transfer belongs near 80-100, "
    "a regional surface transfer near 20-40, and an in-place discount near 0-10 because it "
    "moves no freight.\n\n"
    "Set credit_eligible to true only when the action genuinely emits less than the "
    "status quo of letting the stock sit and eventually be written off. Clearing stock that "
    "would otherwise be destroyed usually earns a credit even when the transfer itself emits."
)

# Rough tonne-km emission factors by transport mode, kg CO2e per tonne-km.
_FREIGHT_FACTORS = {"air": 0.60, "sea": 0.016, "road": 0.11}

# Great-circle-ish distances between market pairs, in km. Used to pick a mode.
_REGION_DISTANCE = {
    ("North America", "Europe"): 6_500,
    ("North America", "Asia"): 11_000,
    ("North America", "South America"): 6_000,
    ("Europe", "Asia"): 8_000,
    ("Europe", "Africa"): 5_000,
    ("Europe", "Middle East"): 4_500,
    ("Asia", "Oceania"): 7_500,
    ("Asia", "Middle East"): 3_500,
    ("Africa", "Middle East"): 3_000,
}


def _distance_km(origin_region: str, dest_region: str) -> float:
    if origin_region == dest_region:
        return 1_200.0
    key = (origin_region, dest_region)
    return float(_REGION_DISTANCE.get(key) or _REGION_DISTANCE.get(key[::-1]) or 9_000)


class _CarbonOut(BaseModel):
    score: float = Field(ge=0.0, le=100.0)
    drivers: list[str]
    credit_eligible: bool
    reasoning: str


class CarbonCreditBank:
    """Logs sustainability wins as credits that offset costlier green choices later."""

    def __init__(self) -> None:
        self._balance_kg = 0.0
        self._ledger: list[tuple[str, float]] = []

    @property
    def balance_kg(self) -> float:
        return round(self._balance_kg, 1)

    def credit(self, action_id: str, kg_co2e: float) -> None:
        self._balance_kg += kg_co2e
        self._ledger.append((action_id, kg_co2e))

    def debit(self, action_id: str, kg_co2e: float) -> bool:
        """Spend banked credits. Returns False when the balance cannot cover it."""
        if kg_co2e > self._balance_kg:
            return False
        self._balance_kg -= kg_co2e
        self._ledger.append((action_id, -kg_co2e))
        return True

    def entries(self) -> list[tuple[str, float]]:
        return list(self._ledger)


class SustainabilityAgent:
    def __init__(self, reasoner: Reasoner, bank: CarbonCreditBank | None = None):
        self.reasoner = reasoner
        self.bank = bank or CarbonCreditBank()

    def _emissions(self, action: ProposedAction, dest_region: str | None) -> tuple[float, str, float]:
        """Return (kg CO2e, mode, distance_km) for the proposed action."""
        if action.action != ActionType.TRANSFER or dest_region is None:
            # Discounts and holds move no freight; only marginal handling emissions.
            return round(action.units * 0.05, 1), "none", 0.0

        distance = _distance_km(action.target.market.region, dest_region)
        # Fast-depreciating gadgets are flown; everything else goes by sea or road.
        if action.target.sku.category == "gadgets" and distance > 4_000:
            mode = "air"
        elif distance > 4_000:
            mode = "sea"
        else:
            mode = "road"

        # Assume 1.2 kg shipped weight per unit including packaging.
        tonnes = action.units * 1.2 / 1000
        kg = tonnes * distance * _FREIGHT_FACTORS[mode]
        return round(kg, 1), mode, distance

    async def run(
        self,
        action: ProposedAction,
        assessment: OverstockAssessment,
        dest_region: str | None,
    ) -> CarbonScore:
        emissions, mode, distance = self._emissions(action, dest_region)

        # Emissions avoided by not writing the stock off as waste.
        avoided = action.units * 2.4 if action.action != ActionType.HOLD else 0.0

        fallback = _CarbonOut(
            score=min(100.0, round(emissions / max(1.0, action.units) * 12.0, 1)),
            drivers=[f"{mode} freight", f"{distance:,.0f} km"] if mode != "none" else ["no freight"],
            credit_eligible=avoided > emissions,
            reasoning=(
                f"{emissions:,.0f} kg CO2e via {mode} against {avoided:,.0f} kg avoided "
                f"write-off emissions."
            ),
        )

        out = await self.reasoner.think(
            system=_SYSTEM,
            payload={
                "action": action.action.value,
                "description": action.description,
                "sku": action.target.sku.name,
                "category": action.target.sku.category,
                "origin_market": action.target.market.name,
                "origin_region": action.target.market.region,
                "destination_market": action.destination_market,
                "destination_region": dest_region,
                "units": action.units,
                "transport_mode": mode,
                "distance_km": distance,
                "modelled_emissions_kg_co2e": emissions,
                "avoided_writeoff_emissions_kg_co2e": round(avoided, 1),
                "overstock_severity": assessment.severity,
                "carbon_credit_balance_kg": self.bank.balance_kg,
            },
            instruction=f"Score the carbon burden of action {action.id}.",
            schema=_CarbonOut,
            fallback=fallback,
        )

        if out.credit_eligible:
            self.bank.credit(action.id, max(0.0, avoided - emissions))

        return CarbonScore(
            score=out.score,
            emissions_kg_co2e=emissions,
            drivers=out.drivers,
            credit_eligible=out.credit_eligible,
            reasoning=out.reasoning,
        )
