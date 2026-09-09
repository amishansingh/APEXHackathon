"""The workflow graph: trigger -> [historical branch || signals branch] ->
demand synthesizer -> order recommendation -> human in the loop.

Both branches run in parallel; the synthesizer waits for both before generating
recommendations. The historical branch is itself a map-reduce (manager shards ->
parallel workers -> merge).
"""

from __future__ import annotations

import asyncio
from typing import Awaitable, Callable

from .adapters.earth_sales import EarthSalesProvider
from .adapters.regional_data import RegionalDataProvider
from .adapters.signals_feed import SignalsFeedProvider
from .agents import (
    DemandSynthesizer,
    HistoricalManager,
    HistoricalWorker,
    HumanGate,
    MergeAndWeight,
    OrderRecommendationAgent,
    SignalProcessingAgent,
    SignalReportAgent,
)
from .config import SETTINGS
from .data import all_skus
from .llm import Reasoner
from .models import (
    MergedBaseline,
    PerItemSignalContext,
    PipelineRun,
    SKU,
    TriggerContext,
    WorkerOutput,
)

ProgressHook = Callable[[str, dict], Awaitable[None] | None]


class Orchestrator:
    """Owns the agent network and runs one full daily pass over the SKU catalogue."""

    def __init__(
        self,
        reasoner: Reasoner | None = None,
        on_progress: ProgressHook | None = None,
        seed: int | None = None,
    ):
        self.reasoner = reasoner or Reasoner()
        self.on_progress = on_progress
        seed = SETTINGS.seed if seed is None else seed

        # Historical branch
        self.manager = HistoricalManager(worker_count=SETTINGS.worker_count)
        self.worker = HistoricalWorker(
            earth=EarthSalesProvider(seed),
            regional=RegionalDataProvider(seed),
            sparse_earth_threshold=SETTINGS.sparse_earth_threshold,
        )
        self.merge = MergeAndWeight(
            earth_weight=SETTINGS.earth_data_weight,
            regional_weight=SETTINGS.regional_data_weight,
            sparse_earth_threshold=SETTINGS.sparse_earth_threshold,
        )

        # Signals branch
        self.signal_processing = SignalProcessingAgent(feed=SignalsFeedProvider(seed))
        self.signal_report = SignalReportAgent()

        # Synthesis + outputs
        self.order_agent = OrderRecommendationAgent()
        self.synthesizer = DemandSynthesizer(order_agent=self.order_agent)
        self.gate = HumanGate()

    async def _emit(self, event: str, data: dict) -> None:
        if self.on_progress is None:
            return
        result = self.on_progress(event, data)
        if asyncio.iscoroutine(result):
            await result

    async def run(self, catalogue: list[SKU] | None = None) -> PipelineRun:
        catalogue = catalogue or all_skus()
        run = PipelineRun()
        run.trigger = TriggerContext(run_id=run.run_id, sku_catalogue=catalogue)

        await self._emit(
            "trigger",
            {"run_id": run.run_id, "sku_count": len(catalogue), "reason": run.trigger.reason},
        )

        # Both branches run concurrently; synthesizer waits for both.
        merged_baselines, signal_contexts = await asyncio.gather(
            self._run_historical_branch(catalogue, run),
            self._run_signals_branch(catalogue, run),
        )
        run.merged_baselines = merged_baselines
        run.signal_contexts = signal_contexts

        await self._emit("synthesizing", {"item_count": len(merged_baselines)})
        recommendations = await self.synthesizer.run(merged_baselines, signal_contexts)
        run.order_recommendations = recommendations

        widened = sum(1 for r in recommendations if r.forecast_range.widened)
        await self._emit(
            "recommendations",
            {
                "count": len(recommendations),
                "widened": widened,
                "escalated": sum(1 for r in recommendations if r.escalation_flags),
            },
        )

        decisions = self.gate.review(recommendations)
        run.human_decisions = decisions

        await self._emit(
            "complete",
            {
                "briefing": self.gate.briefing(decisions),
                "approved": sum(1 for d in decisions if d.action == "approve"),
                "llm_calls": self.reasoner.call_count,
            },
        )
        return run

    # --- Historical branch (map-reduce) -------------------------------------

    async def _run_historical_branch(
        self, catalogue: list[SKU], run: PipelineRun
    ) -> list[MergedBaseline]:
        shards = self.manager.assign_shards(catalogue)
        await self._emit(
            "hist_shards",
            {"shards": len(shards), "sizes": [len(s.skus) for s in shards]},
        )

        worker_outputs: list[WorkerOutput] = list(
            await asyncio.gather(*(self.worker.process(shard) for shard in shards))
        )
        run.worker_outputs = worker_outputs
        await self._emit(
            "hist_workers_done",
            {
                "workers": len(worker_outputs),
                "items": sum(len(w.items) for w in worker_outputs),
            },
        )

        baselines = self.merge.run(worker_outputs)
        run.merged_baselines = baselines
        await self._emit(
            "hist_merged",
            {
                "items": len(baselines),
                "earth_weight": self.merge.earth_weight,
                "regional_weight": self.merge.regional_weight,
                "sparse_flagged": sum(
                    1 for b in baselines if "sparse_earth_data" in b.data_quality_flags
                ),
            },
        )
        return baselines

    # --- Signals branch (continuous) ----------------------------------------

    async def _run_signals_branch(
        self, catalogue: list[SKU], run: PipelineRun
    ) -> list[PerItemSignalContext]:
        processed = await self.signal_processing.run(catalogue)
        await self._emit(
            "sig_processed",
            {
                "items": len(processed),
                "signals": sum(len(p.signals) for p in processed),
            },
        )

        report = self.signal_report.run(processed)
        run.signal_contexts = report
        await self._emit(
            "sig_report",
            {
                "items": len(report),
                "conflicts": sum(1 for r in report if r.has_conflict),
            },
        )
        return report
