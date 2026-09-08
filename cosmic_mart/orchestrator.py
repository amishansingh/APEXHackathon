"""The workflow graph: signals -> synthesis -> evaluation -> tradeoff -> human gate."""

from __future__ import annotations

import asyncio
from typing import Awaitable, Callable

from .adapters.base import SourceRegistry
from .adapters.mock import build_mock_registry
from .agents import (
    SIGNAL_AGENT_CLASSES,
    CarbonCreditBank,
    DemandSynthesizer,
    FinancialReportAgent,
    HumanGate,
    OverstockLossAgent,
    SignalAccuracyLedger,
    SustainabilityAgent,
    TradeoffDecisionAgent,
    build_proposals,
)
from .config import SETTINGS
from .data import MARKETS_BY_CODE, all_pairs
from .llm import Reasoner
from .models import (
    EvaluatedAction,
    OverstockAssessment,
    PipelineRun,
    ProposedAction,
    SKUMarket,
    SynthesizedDemand,
    Verdict,
)

ProgressHook = Callable[[str, dict], Awaitable[None] | None]


class Orchestrator:
    """Owns the agent network and runs one full pass over a set of SKU/market pairs."""

    def __init__(
        self,
        reasoner: Reasoner | None = None,
        registry: SourceRegistry | None = None,
        on_progress: ProgressHook | None = None,
        max_concurrency: int = 8,
    ):
        self.reasoner = reasoner or Reasoner()
        self.registry = registry or build_mock_registry(SETTINGS.seed)
        self.on_progress = on_progress
        self._gate_semaphore = asyncio.Semaphore(max_concurrency)

        self.signal_agents = [
            cls(self.reasoner, self.registry.get(cls.kind)) for cls in SIGNAL_AGENT_CLASSES
        ]
        self.ledger = SignalAccuracyLedger()
        self.synthesizer = DemandSynthesizer(self.reasoner, self.ledger)
        self.overstock_agent = OverstockLossAgent(self.reasoner, self.registry.inventory)
        self.credit_bank = CarbonCreditBank()
        self.sustainability = SustainabilityAgent(self.reasoner, self.credit_bank)
        self.financial = FinancialReportAgent(self.reasoner)
        self.tradeoff = TradeoffDecisionAgent(self.reasoner)
        self.gate = HumanGate()

    async def _emit(self, event: str, data: dict) -> None:
        if self.on_progress is None:
            return
        result = self.on_progress(event, data)
        if asyncio.iscoroutine(result):
            await result

    async def _forecast(self, target: SKUMarket) -> SynthesizedDemand:
        async with self._gate_semaphore:
            # All six specialists observe the same target concurrently.
            signals = await asyncio.gather(*(a.run(target) for a in self.signal_agents))
            await self._emit(
                "signals",
                {
                    "target": target.key,
                    "readings": [
                        {
                            "agent": s.agent,
                            "impact_pct": s.reading.demand_impact_pct,
                            "confidence": s.reading.confidence,
                        }
                        for s in signals
                    ],
                },
            )

            baseline = await self._baseline_units(target)
            demand = await self.synthesizer.run(target, list(signals), baseline)
            await self._emit(
                "demand",
                {
                    "target": target.key,
                    "expected": demand.forecast.units_expected,
                    "low": demand.forecast.units_low,
                    "high": demand.forecast.units_high,
                    "confidence": demand.forecast.confidence,
                    "escalate": demand.escalate_to_human,
                },
            )
            return demand

    async def _baseline_units(self, target: SKUMarket) -> int:
        """Baseline demand for the 30-day period, from the seasonality feed."""
        raw = await self.registry.get(self.signal_agents[-1].kind).observe(target)
        return int(raw["baseline_weekly_units"] * 4)

    async def _assess(self, demand: SynthesizedDemand) -> OverstockAssessment:
        async with self._gate_semaphore:
            assessment = await self.overstock_agent.run(demand)
            await self._emit(
                "overstock",
                {
                    "target": assessment.target.key,
                    "excess": assessment.units_excess,
                    "daily_loss_usd": round(assessment.daily_loss.total_usd, 2),
                    "severity": assessment.severity,
                },
            )
            return assessment

    async def _evaluate(
        self, action: ProposedAction, assessment: OverstockAssessment, confidence: float
    ) -> EvaluatedAction:
        async with self._gate_semaphore:
            dest_region = (
                MARKETS_BY_CODE[action.destination_market].region
                if action.destination_market
                else None
            )
            # Sustainability and financial evaluate the same action in parallel.
            carbon, financial = await asyncio.gather(
                self.sustainability.run(action, assessment, dest_region),
                self.financial.run(action, assessment),
            )
            decision = await self.tradeoff.run(action, carbon, financial, confidence)
            await self._emit(
                "decision",
                {
                    "action_id": action.id,
                    "verdict": decision.verdict.value,
                    "net_score": decision.net_score,
                    "carbon_score": carbon.score,
                    "net_benefit_usd": financial.net_benefit_usd,
                },
            )
            return EvaluatedAction(
                action=action, carbon=carbon, financial=financial, decision=decision
            )

    async def run(self, targets: list[SKUMarket] | None = None) -> PipelineRun:
        targets = targets or all_pairs()
        run = PipelineRun()

        await self._emit("start", {"targets": len(targets)})

        demand = list(await asyncio.gather(*(self._forecast(t) for t in targets)))
        run.demand = demand

        assessments = list(await asyncio.gather(*(self._assess(d) for d in demand)))
        run.overstock = assessments

        confidence_by_key = {d.target.key: d.forecast.confidence for d in demand}
        by_key = {a.target.key: a for a in assessments}

        proposals = [
            p
            for p in build_proposals(assessments, demand)
            # Respect the feedback loop: a previously blocked idea is not re-raised.
            if not self.overstock_agent.is_blocked(p.target, p.action)
        ]
        await self._emit("proposals", {"count": len(proposals)})

        evaluated = list(
            await asyncio.gather(
                *(
                    self._evaluate(p, by_key[p.target.key], confidence_by_key[p.target.key])
                    for p in proposals
                )
            )
        )
        run.evaluated = evaluated

        for item in evaluated:
            outcome = self.gate.submit(item)
            if item.decision.verdict is Verdict.BLOCK:
                # Close the loop back to the overstock agent.
                self.overstock_agent.register_block(outcome)  # type: ignore[arg-type]

        run.gate_queue = self.gate.queue
        run.blocked = self.gate.blocked
        run.carbon_credits_kg = self.credit_bank.balance_kg

        await self._emit("complete", {"briefing": self.gate.briefing()})
        return run
