"""Tradeoff decision agent: the convergence point of the whole system."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from ..config import SETTINGS
from ..llm import Reasoner
from ..models import (
    CarbonScore,
    FinancialBenefit,
    ProposedAction,
    TradeoffDecision,
    Verdict,
)

_SYSTEM = (
    "You are the TRADEOFF DECISION agent for Cosmic Mart, the convergence point of the "
    "supply chain system. You receive a carbon score from the sustainability agent and a "
    "dollar benefit from the financial agent, and you route the action.\n\n"
    "Net score = financial net benefit - (carbon score x the carbon price Cosmic Mart "
    "currently puts on a point of carbon burden). The arithmetic is supplied; your judgement "
    "is where the routing is genuinely contestable.\n\n"
    "Route to exactly one of three outcomes:\n"
    "- approve: the net score is clearly positive and the two scores are not in tension.\n"
    "- flag: the scores are in tension, or the forecast underneath is shaky. A near-threshold "
    "net score with a heavy carbon burden is the classic flag.\n"
    "- block: the net score is negative. The action is rejected and the reason is logged back "
    "to the overstock agent so the same proposal does not recur.\n\n"
    "Set escalation_owner to CFO for financial escalations, CSO for strategic or "
    "sustainability-contested decisions, and none for blocks. Humans decide edge cases only, "
    "so do not flag what the numbers already settle."
)


class _TradeoffOut(BaseModel):
    verdict: Literal["approve", "flag", "block"]
    reasoning: str = Field(description="Two or three sentences justifying the route.")
    escalation_owner: Literal["CFO", "CSO", "none"]


class TradeoffDecisionAgent:
    def __init__(self, reasoner: Reasoner):
        self.reasoner = reasoner

    def _score(self, carbon: CarbonScore, financial: FinancialBenefit) -> tuple[float, float]:
        penalty = round(carbon.score * SETTINGS.carbon_price_usd_per_point, 2)
        return round(financial.net_benefit_usd - penalty, 2), penalty

    def _route(self, net: float, carbon: CarbonScore, forecast_confidence: float) -> tuple[Verdict, str]:
        if net <= SETTINGS.block_threshold_usd:
            return Verdict.BLOCK, "none"
        if (
            net >= SETTINGS.approve_threshold_usd
            and carbon.score < 60
            and forecast_confidence >= SETTINGS.approve_confidence_floor
        ):
            return Verdict.APPROVE, "CFO"
        return Verdict.FLAG, "CSO" if carbon.score >= 60 else "CFO"

    async def run(
        self,
        action: ProposedAction,
        carbon: CarbonScore,
        financial: FinancialBenefit,
        forecast_confidence: float,
    ) -> TradeoffDecision:
        net, penalty = self._score(carbon, financial)
        default_verdict, default_owner = self._route(net, carbon, forecast_confidence)

        fallback = _TradeoffOut(
            verdict=default_verdict.value,
            reasoning=(
                f"Net ${net:,.0f} after a ${penalty:,.0f} carbon penalty on a "
                f"{carbon.score:.0f}-point burden, with forecast confidence "
                f"{forecast_confidence:.0%}."
            ),
            escalation_owner=default_owner,
        )

        out = await self.reasoner.think(
            system=_SYSTEM,
            payload={
                "action_id": action.id,
                "description": action.description,
                "financial": {
                    "net_benefit_usd": financial.net_benefit_usd,
                    "gross_benefit_usd": financial.gross_benefit_usd,
                    "execution_cost_usd": financial.execution_cost_usd,
                    "payback_days": financial.payback_days,
                    "reasoning": financial.reasoning,
                },
                "carbon": {
                    "score": carbon.score,
                    "emissions_kg_co2e": carbon.emissions_kg_co2e,
                    "credit_eligible": carbon.credit_eligible,
                    "drivers": carbon.drivers,
                    "reasoning": carbon.reasoning,
                },
                "carbon_price_usd_per_point": SETTINGS.carbon_price_usd_per_point,
                "carbon_penalty_usd": penalty,
                "net_score_usd": net,
                "approve_threshold_usd": SETTINGS.approve_threshold_usd,
                "underlying_forecast_confidence": forecast_confidence,
            },
            instruction=f"Route action {action.id} to approve, flag, or block.",
            schema=_TradeoffOut,
            fallback=fallback,
        )

        verdict = Verdict(out.verdict)
        owner = "none" if verdict is Verdict.BLOCK else out.escalation_owner
        return TradeoffDecision(
            verdict=verdict,
            net_score=net,
            carbon_penalty_usd=penalty,
            reasoning=out.reasoning,
            escalation_owner=owner,
        )
