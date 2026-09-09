from __future__ import annotations

import pytest

from cosmic_mart.adapters.earth_sales import EarthSalesProvider
from cosmic_mart.adapters.regional_data import RegionalDataProvider
from cosmic_mart.adapters.signals_feed import SignalsFeedProvider
from cosmic_mart.agents import (
    DemandSynthesizer,
    HistoricalManager,
    HistoricalWorker,
    HumanGate,
    MergeAndWeight,
    SignalProcessingAgent,
    SignalReportAgent,
)
from cosmic_mart.config import SETTINGS
from cosmic_mart.data import all_skus
from cosmic_mart.llm import Reasoner
from cosmic_mart.models import (
    MergedBaseline,
    PerItemSignalContext,
    SignalItem,
)
from cosmic_mart.orchestrator import Orchestrator


@pytest.fixture
def offline() -> Reasoner:
    return Reasoner(offline=True)


# --- Historical branch ------------------------------------------------------


def test_manager_shards_cover_the_whole_catalogue() -> None:
    catalogue = all_skus()
    shards = HistoricalManager(worker_count=3).assign_shards(catalogue)
    assert 1 <= len(shards) <= 3
    sharded = [s.id for shard in shards for s in shard.skus]
    assert sorted(sharded) == sorted(s.id for s in catalogue)


async def test_worker_produces_per_item_context() -> None:
    worker = HistoricalWorker(EarthSalesProvider(SETTINGS.seed), RegionalDataProvider(SETTINGS.seed))
    shards = HistoricalManager(worker_count=2).assign_shards(all_skus())
    output = await worker.process(shards[0])
    assert output.items
    for item in output.items:
        assert item.earth_baseline >= 0
        assert item.regional_baseline >= 0


def test_merge_applies_earth_and_regional_weights() -> None:
    worker_out = _fake_worker_output(earth=100.0, regional=200.0)
    merged = MergeAndWeight(earth_weight=0.9, regional_weight=0.1).run([worker_out])
    assert len(merged) == 1
    b = merged[0]
    # earth (with unit YoY factor) * 0.9 + regional * 0.1
    assert b.weighted_baseline == pytest.approx(100.0 * 0.9 + 200.0 * 0.1, abs=1.0)


def test_merge_flags_sparse_earth_data() -> None:
    worker_out = _fake_worker_output(earth=10.0, regional=200.0)
    merged = MergeAndWeight(sparse_earth_threshold=50.0).run([worker_out])
    assert "sparse_earth_data" in merged[0].data_quality_flags


# --- Signals branch ---------------------------------------------------------


async def test_signal_report_flags_internal_conflict() -> None:
    catalogue = all_skus()[:2]
    processed = await SignalProcessingAgent(SignalsFeedProvider(SETTINGS.seed)).run(catalogue)
    # Force a conflicting pair of signals on the first item.
    processed[0].signals = [
        SignalItem(type="promo", source="promo", strength=0.8, direction="up"),
        SignalItem(type="news", source="news", strength=0.7, direction="down"),
    ]
    report = SignalReportAgent().run(processed)
    assert report[0].has_conflict is True


# --- Synthesizer ------------------------------------------------------------


async def test_conflict_widens_the_forecast_range() -> None:
    synth = DemandSynthesizer()
    sku = all_skus()[0]
    baseline = MergedBaseline(
        sku=sku, weighted_baseline=100.0, earth_baseline=100.0, regional_baseline=100.0,
        data_quality_flags=[],
    )
    conflicted = PerItemSignalContext(
        sku=sku,
        signals=[
            SignalItem(type="promo", source="promo", strength=0.9, direction="up"),
            SignalItem(type="news", source="news", strength=0.8, direction="down"),
        ],
        has_conflict=True,
        net_direction="up",
    )
    recs = await synth.run([baseline], [conflicted])
    assert recs[0].forecast_range.widened is True
    fr = recs[0].forecast_range
    assert fr.units_low <= fr.units_expected <= fr.units_high


async def test_clean_signal_blends_without_widening() -> None:
    synth = DemandSynthesizer()
    sku = all_skus()[0]
    baseline = MergedBaseline(
        sku=sku, weighted_baseline=100.0, earth_baseline=100.0, regional_baseline=100.0,
        data_quality_flags=[],
    )
    clean = PerItemSignalContext(sku=sku, signals=[], has_conflict=False, net_direction="neutral")
    recs = await synth.run([baseline], [clean])
    assert recs[0].forecast_range.widened is False


# --- Human gate + full run --------------------------------------------------


async def test_human_gate_approves_clean_recommendations() -> None:
    synth = DemandSynthesizer()
    sku = all_skus()[0]
    baseline = MergedBaseline(
        sku=sku, weighted_baseline=100.0, earth_baseline=100.0, regional_baseline=100.0,
        data_quality_flags=[],
    )
    clean = PerItemSignalContext(sku=sku, signals=[], has_conflict=False, net_direction="neutral")
    recs = await synth.run([baseline], [clean])
    decisions = HumanGate().review(recs)
    assert decisions[0].action in {"approve", "modify", "escalate", "reject"}
    assert not recs[0].escalation_flags
    assert decisions[0].action == "approve"


async def test_pipeline_runs_end_to_end(offline: Reasoner) -> None:
    orchestrator = Orchestrator(reasoner=offline)
    run = await orchestrator.run(all_skus()[:6])

    assert len(run.merged_baselines) == 6
    assert len(run.order_recommendations) == 6
    assert len(run.human_decisions) == 6
    for r in run.order_recommendations:
        fr = r.forecast_range
        assert fr.units_low <= fr.units_expected <= fr.units_high
    assert offline.call_count == 0


async def test_offline_run_is_deterministic() -> None:
    first = await Orchestrator(reasoner=Reasoner(offline=True)).run(all_skus()[:4])
    second = await Orchestrator(reasoner=Reasoner(offline=True)).run(all_skus()[:4])
    assert [r.forecast_range.units_expected for r in first.order_recommendations] == [
        r.forecast_range.units_expected for r in second.order_recommendations
    ]


# --- helpers ----------------------------------------------------------------


def _fake_worker_output(earth: float, regional: float):
    from cosmic_mart.models import PerItemDemandContext, WorkerOutput

    sku = all_skus()[0]
    return WorkerOutput(
        shard_id=0,
        worker_id="worker-0",
        items=[
            PerItemDemandContext(
                sku=sku,
                earth_baseline=earth,
                regional_baseline=regional,
                yoy_adjustments=[],
                data_quality_flags=[],
            )
        ],
    )
