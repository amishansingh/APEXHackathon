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
    InboundShipmentsAgent,
    ItemSynthesizer,
    OverstockLossAgent,
    RealtimeStockAgent,
    SeasonalPeaksAgent,
    SellthroughVelocityAgent,
    SignalAccuracyLedger,
    SupplierLeadTimesAgent,
    SustainabilityAgent,
    TradeoffDecisionAgent,
    YoYSalesAgent,
    build_proposals,
)
from .config import SETTINGS
from .data import MARKETS_BY_CODE, SKUS, all_pairs
from .llm import Reasoner
from .models import (
    EvaluatedAction,
    OverstockAssessment,
    P1Output,
    P2Output,
    PipelineRun,
    ProposedAction,
    SignalKind,
    SKUMarket,
    SynthesizedDemand,
    TriggerSignal,
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

        # New agents
        self.item_synthesizer = ItemSynthesizer()
        self.yoy_sales = YoYSalesAgent()
        self.seasonal_peaks = SeasonalPeaksAgent()
        self.supplier_lead_times = SupplierLeadTimesAgent()
        self.realtime_stock = RealtimeStockAgent()
        self.inbound_shipments = InboundShipmentsAgent()
        self.sellthrough_velocity = SellthroughVelocityAgent()

    async def _emit(self, event: str, data: dict) -> None:
        if self.on_progress is None:
            return
        result = self.on_progress(event, data)
        if asyncio.iscoroutine(result):
            await result

    async def _build_trigger(self, agent, target: SKUMarket) -> TriggerSignal | None:
        """Generate a P3 TriggerSignal for agents that support it."""
        if not hasattr(agent, "generate_trigger"):
            return None
        raw = await agent.source.observe(target)
        estimate = agent.heuristic(raw, target)
        return agent.generate_trigger(raw, target, estimate)

    async def _forecast(
        self,
        target: SKUMarket,
        run: PipelineRun,
    ) -> SynthesizedDemand:
        async with self._gate_semaphore:
            # --- P3: Run all signal agents concurrently ---
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

            # --- P3: Generate triggers concurrently ---
            trigger_results = await asyncio.gather(
                *(self._build_trigger(a, target) for a in self.signal_agents)
            )
            triggers = [t for t in trigger_results if t is not None]

            # Pick the strongest trigger (largest deviation from 1.0)
            strongest_trigger: TriggerSignal | None = None
            if triggers:
                strongest_trigger = max(
                    triggers, key=lambda t: abs(t.estimated_demand_impact - 1.0)
                )

            if strongest_trigger is not None:
                run.p3_triggers.append(strongest_trigger)
                await self._emit(
                    "p3_trigger",
                    {
                        "agent_id": strongest_trigger.agent_id,
                        "market": strongest_trigger.market,
                        "event_type": strongest_trigger.event_type,
                        "estimated_demand_impact": strongest_trigger.estimated_demand_impact,
                        "affected_sku_categories": strongest_trigger.affected_sku_categories,
                        "first_run": strongest_trigger.first_run,
                        "confidence_score": strongest_trigger.confidence_score,
                        "cadence": strongest_trigger.cadence,
                    },
                )

                # --- Item Synthesizer ---
                item_out = self.item_synthesizer.run(
                    strongest_trigger, SKUS, target.market
                )
                run.item_synthesizer_outputs.append(item_out)
                await self._emit(
                    "item_synthesized",
                    {
                        "market": item_out.source_trigger.market,
                        "source_trigger_agent": item_out.source_trigger.agent_id,
                        "affected_sku_count": len(item_out.affected_skus),
                        "affected_skus": [
                            {"sku_id": s.sku_id, "category": s.category}
                            for s in item_out.affected_skus
                        ],
                    },
                )

            # --- P1: Historical anchor agents ---
            p1_yoy = self.yoy_sales.run(target)
            p1_seasonal = self.seasonal_peaks.run(target)
            p1_leadtime = self.supplier_lead_times.run(target)
            p1_results: list[P1Output] = [p1_yoy, p1_seasonal, p1_leadtime]

            for p1 in p1_results:
                run.p1_outputs.append(p1)
                key_data_keys = [
                    "baseline_units_30d", "trend", "yoy_growth_pct", "sellthrough_rate",
                    "peak_uplift_multiplier", "three_year_trend",
                    "recommended_order_trigger_days", "variability_score",
                ]
                await self._emit(
                    "p1_result",
                    {
                        "sku_id": p1.sku_id,
                        "market": p1.market,
                        "agent_id": p1.agent_id,
                        "impact_score": {
                            "importance": p1.impact_score.importance,
                            "magnitude": p1.impact_score.magnitude,
                            "longevity": p1.impact_score.longevity,
                        },
                        "risk_flag": p1.risk_flag,
                        "key_data": {k: v for k, v in p1.data.items() if k in key_data_keys},
                    },
                )

            # --- P2: Current stock agents ---
            p2_stock = self.realtime_stock.run(target)
            p2_inbound = self.inbound_shipments.run(target)
            p2_velocity = self.sellthrough_velocity.run(target)
            p2_results: list[P2Output] = [p2_stock, p2_inbound, p2_velocity]

            for p2 in p2_results:
                run.p2_outputs.append(p2)
                key_data_keys_p2 = [
                    "status", "units_on_hand", "days_of_supply", "divergence_ratio",
                    "current_velocity_per_day", "inbound_units", "adjusted_days_of_supply",
                ]
                await self._emit(
                    "p2_result",
                    {
                        "sku_id": p2.sku_id,
                        "market": p2.market,
                        "agent_id": p2.agent_id,
                        "hard_override": p2.hard_override,
                        "immediate_rerun_trigger": p2.immediate_rerun_trigger,
                        "key_data": {k: v for k, v in p2.data.items() if k in key_data_keys_p2},
                    },
                )

            # --- Demand synthesis ---
            baseline = await self._baseline_units(target)
            demand = await self.synthesizer.run(target, list(signals), baseline)

            # Apply P1 risk flags
            any_p1_risk = any(p.risk_flag for p in p1_results)
            if any_p1_risk:
                demand.forecast.risk_flag = True
                demand.escalate_to_human = True

            # Apply P2 hard override (out_of_stock → human_review route)
            if p2_stock.hard_override and p2_stock.data.get("status") == "out_of_stock":
                demand.forecast.route = "human_review"

            # Propagate first_run signal
            if strongest_trigger is not None and strongest_trigger.first_run:
                demand.forecast.first_run_signal = True

            await self._emit(
                "demand",
                {
                    "target": target.key,
                    "expected": demand.forecast.units_expected,
                    "low": demand.forecast.units_low,
                    "high": demand.forecast.units_high,
                    "confidence": demand.forecast.confidence,
                    "escalate": demand.escalate_to_human,
                    "risk_flag": demand.forecast.risk_flag,
                    "route": demand.forecast.route,
                },
            )
            return demand

    async def _baseline_units(self, target: SKUMarket) -> int:
        """Baseline demand for the 30-day period, from the seasonality feed."""
        raw = await self.registry.get(SignalKind.SEASONALITY).observe(target)
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

        demand = list(await asyncio.gather(*(self._forecast(t, run) for t in targets)))
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
