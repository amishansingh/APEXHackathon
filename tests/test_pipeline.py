from __future__ import annotations

import pytest

from cosmic_mart.adapters.earth_sales import EarthSalesProvider
from cosmic_mart.adapters.inventory_db import InventoryDatabaseProvider
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
    TriggerContext,
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


async def test_worker_produces_per_item_context(offline: Reasoner) -> None:
    worker = HistoricalWorker(
        EarthSalesProvider(SETTINGS.seed),
        RegionalDataProvider(SETTINGS.seed),
        reasoner=offline,
    )
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


# --- Trigger ----------------------------------------------------------------


def test_trigger_is_schedule_driven_only() -> None:
    """All runs are schedule-driven; there is no anomaly-event trigger (§2)."""
    trigger = TriggerContext(run_id="r1")
    assert trigger.reason == "daily_schedule"

    # The Literal makes an anomaly trigger a type error, not a silent string.
    with pytest.raises(ValueError):
        TriggerContext(run_id="r2", reason="anomaly_event")


async def test_run_trigger_reports_daily_schedule(offline: Reasoner) -> None:
    run = await Orchestrator(reasoner=offline).run(all_skus()[:2])
    assert run.trigger is not None
    assert run.trigger.reason == "daily_schedule"


# --- Inventory database -> SKU catalogue ------------------------------------


async def test_inventory_db_exposes_item_id_and_name() -> None:
    db = InventoryDatabaseProvider(SETTINGS.seed)
    rows = await db.records()
    assert rows
    for row in rows:
        assert row.item_id
        assert row.item_name

    index = await db.item_index()
    catalogue = await db.catalogue()
    assert index
    # Every active item is retrievable by identification number -> name.
    for sku in catalogue:
        assert index[sku.id] == sku.name


async def test_signal_processing_retrieves_catalogue_from_inventory_db(
    offline: Reasoner,
) -> None:
    """With no catalogue passed, the agent reads it from the inventory database."""
    db = InventoryDatabaseProvider(SETTINGS.seed)
    agent = SignalProcessingAgent(
        SignalsFeedProvider(SETTINGS.seed), inventory=db, reasoner=offline
    )
    processed = await agent.run()  # no catalogue argument

    expected = await db.catalogue()
    assert [p.sku.id for p in processed] == [s.id for s in expected]


# --- Signals branch ---------------------------------------------------------


async def test_signal_report_flags_internal_conflict(offline: Reasoner) -> None:
    catalogue = all_skus()[:2]
    processed = await SignalProcessingAgent(
        SignalsFeedProvider(SETTINGS.seed), reasoner=offline
    ).run(catalogue)
    # Force a conflicting pair of signals on the first item.
    processed[0].signals = [
        SignalItem(type="promo", source="promo", strength=0.8, direction="up"),
        SignalItem(type="news", source="news", strength=0.7, direction="down"),
    ]
    report = await SignalReportAgent(reasoner=offline).run(processed)
    assert report[0].has_conflict is True


async def test_signal_directions_are_coherent_with_headlines(offline: Reasoner) -> None:
    """A signal's direction follows from what it says, not a coin flip."""
    feed = SignalsFeedProvider(SETTINGS.seed)
    processed = await SignalProcessingAgent(feed, reasoner=offline).run(all_skus())

    seen = {
        s.description: s.direction for item in processed for s in item.signals
    }
    # Disruption and spending pullback lower demand wherever they appear;
    # promos and viral moments raise it.
    for headline, direction in seen.items():
        if "disruption" in headline or "pullback" in headline:
            assert direction == "down", f"{headline!r} should lower demand"
        if "Flash sale" in headline or "Viral" in headline:
            assert direction == "up", f"{headline!r} should raise demand"


# --- Synthesizer ------------------------------------------------------------


async def test_conflict_widens_the_forecast_range(offline: Reasoner) -> None:
    synth = DemandSynthesizer(reasoner=offline)
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


async def test_clean_signal_blends_without_widening(offline: Reasoner) -> None:
    synth = DemandSynthesizer(reasoner=offline)
    sku = all_skus()[0]
    baseline = MergedBaseline(
        sku=sku, weighted_baseline=100.0, earth_baseline=100.0, regional_baseline=100.0,
        data_quality_flags=[],
    )
    clean = PerItemSignalContext(sku=sku, signals=[], has_conflict=False, net_direction="neutral")
    recs = await synth.run([baseline], [clean])
    assert recs[0].forecast_range.widened is False


# --- Human gate + full run --------------------------------------------------


async def test_human_gate_approves_clean_recommendations(offline: Reasoner) -> None:
    synth = DemandSynthesizer(reasoner=offline)
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


async def test_every_recommendation_passes_through_human_review(
    offline: Reasoner,
) -> None:
    """No autonomous path: one decision per recommendation, every run."""
    run = await Orchestrator(reasoner=offline).run(all_skus())

    assert run.order_recommendations
    assert len(run.human_decisions) == len(run.order_recommendations)

    reviewed = {d.recommendation_id for d in run.human_decisions}
    assert reviewed == {r.id for r in run.order_recommendations}
    # Including the clean ones — approval is a review outcome, not a bypass.
    assert all(d.action in {"approve", "modify", "reject", "escalate"} for d in run.human_decisions)


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


# --- LLM wiring -------------------------------------------------------------


async def test_offline_reasoner_makes_no_calls_but_records_fallbacks(
    offline: Reasoner,
) -> None:
    """Offline exercises the same code path a failed API call takes."""
    await Orchestrator(reasoner=offline).run(all_skus()[:2])
    assert offline.call_count == 0
    # Every agent that would have asked Claude used its fallback instead.
    assert offline.fallback_count > 0
    assert offline.available is False


async def test_missing_credentials_degrade_to_fallbacks(monkeypatch) -> None:
    """No API key yet: the pipeline still completes, on deterministic fallbacks."""
    import anthropic

    def _no_credentials(*args, **kwargs):
        raise TypeError("Could not resolve authentication method")

    monkeypatch.setattr(anthropic, "AsyncAnthropic", _no_credentials)

    live = Reasoner(offline=False)
    assert live.available is True  # hasn't tried yet

    run = await Orchestrator(reasoner=live).run(all_skus()[:2])

    assert live.call_count == 0
    assert live.fallback_count > 0
    assert live.available is False  # tried once, then stopped trying
    assert len(run.human_decisions) == len(run.order_recommendations) == 2


async def test_api_failure_falls_back_without_crashing(monkeypatch) -> None:
    """A live key that errors mid-run must not take the pipeline down."""
    import anthropic

    class _FailingMessages:
        async def parse(self, **kwargs):
            raise anthropic.APIConnectionError(request=None)  # type: ignore[arg-type]

    class _FailingClient:
        messages = _FailingMessages()

    monkeypatch.setattr(anthropic, "AsyncAnthropic", lambda *a, **k: _FailingClient())

    live = Reasoner(offline=False)
    run = await Orchestrator(reasoner=live).run(all_skus()[:2])

    assert live.call_count == 0
    assert live.fallback_count > 0
    assert len(run.order_recommendations) == 2


async def test_request_build_failure_falls_back(monkeypatch) -> None:
    """An empty .env surfaces as a TypeError at request-build time, not at
    client construction. That must degrade, not take the run down."""
    import anthropic

    class _UnauthedMessages:
        async def parse(self, **kwargs):
            raise TypeError("Could not resolve authentication method.")

    class _UnauthedClient:
        messages = _UnauthedMessages()

    monkeypatch.setattr(anthropic, "AsyncAnthropic", lambda *a, **k: _UnauthedClient())

    live = Reasoner(offline=False)
    run = await Orchestrator(reasoner=live).run(all_skus()[:2])

    assert live.call_count == 0
    assert live.fallback_count > 0
    # Config errors don't fix themselves mid-run: try once, then stop.
    assert live.available is False
    assert len(run.human_decisions) == len(run.order_recommendations) == 2


async def test_unexpected_error_falls_back(monkeypatch) -> None:
    """Any unexpected failure still yields a typed answer, never a crash."""
    import anthropic

    class _BrokenMessages:
        async def parse(self, **kwargs):
            raise ValueError("gateway returned something unexpected")

    class _BrokenClient:
        messages = _BrokenMessages()

    monkeypatch.setattr(anthropic, "AsyncAnthropic", lambda *a, **k: _BrokenClient())

    live = Reasoner(offline=False)
    run = await Orchestrator(reasoner=live).run(all_skus()[:2])

    assert live.fallback_count > 0
    assert len(run.order_recommendations) == 2


async def test_agents_are_wired_to_the_shared_reasoner(offline: Reasoner) -> None:
    """Adding a key must light up the reasoning agents, so they must hold one."""
    orch = Orchestrator(reasoner=offline)
    assert orch.worker.reasoner is offline
    assert orch.signal_processing.reasoner is offline
    assert orch.signal_report.reasoner is offline
    assert orch.synthesizer.reasoner is offline


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
