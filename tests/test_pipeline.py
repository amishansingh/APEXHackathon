from __future__ import annotations

import pytest

from cosmic_mart.adapters.mock import build_mock_registry
from cosmic_mart.agents import SIGNAL_AGENT_CLASSES, CarbonCreditBank, SignalAccuracyLedger
from cosmic_mart.agents.human_gate import HumanGate
from cosmic_mart.agents.tradeoff import TradeoffDecisionAgent
from cosmic_mart.config import SETTINGS
from cosmic_mart.data import all_pairs, pair
from cosmic_mart.llm import Reasoner
from cosmic_mart.models import (
    ActionType,
    CarbonScore,
    EvaluatedAction,
    FinancialBenefit,
    ProposedAction,
    SignalKind,
    Verdict,
)
from cosmic_mart.orchestrator import Orchestrator


@pytest.fixture
def offline() -> Reasoner:
    return Reasoner(offline=True)


async def test_every_signal_agent_produces_a_reading(offline: Reasoner) -> None:
    registry = build_mock_registry(SETTINGS.seed)
    target = pair("GAD-1001", "IN")

    for cls in SIGNAL_AGENT_CLASSES:
        signal = await cls(offline, registry.get(cls.kind)).run(target)
        assert signal.reading.kind is cls.kind
        assert -100 <= signal.reading.demand_impact_pct <= 300
        assert 0.0 <= signal.reading.confidence <= 1.0
        assert signal.reading.rationale


async def test_pipeline_runs_end_to_end(offline: Reasoner) -> None:
    orchestrator = Orchestrator(reasoner=offline)
    run = await orchestrator.run(all_pairs()[:6])

    assert len(run.demand) == 6
    assert len(run.overstock) == 6
    for d in run.demand:
        assert d.forecast.units_low <= d.forecast.units_expected <= d.forecast.units_high
    # Every evaluated action lands in exactly one of the two outcome lists.
    assert len(run.evaluated) == len(run.gate_queue) + len(run.blocked)
    assert offline.call_count == 0


async def test_offline_run_is_deterministic() -> None:
    first = await Orchestrator(reasoner=Reasoner(offline=True)).run(all_pairs()[:4])
    second = await Orchestrator(reasoner=Reasoner(offline=True)).run(all_pairs()[:4])
    assert [d.forecast.units_expected for d in first.demand] == [
        d.forecast.units_expected for d in second.demand
    ]


def test_cost_clock_has_three_components(offline: Reasoner) -> None:
    from cosmic_mart.agents.overstock import OverstockLossAgent

    registry = build_mock_registry(SETTINGS.seed)
    agent = OverstockLossAgent(offline, registry.inventory)
    loss = agent._cost_clock(pair("GAD-1001", "US"), 1_000)

    assert loss.capital_tied_usd > 0
    assert loss.storage_fees_usd > 0
    assert loss.depreciation_usd > 0
    assert loss.total_usd == pytest.approx(
        loss.capital_tied_usd + loss.storage_fees_usd + loss.depreciation_usd
    )


def test_gadgets_depreciate_faster_than_home_goods(offline: Reasoner) -> None:
    from cosmic_mart.agents.overstock import OverstockLossAgent

    agent = OverstockLossAgent(offline, build_mock_registry(1).inventory)
    gadget = agent._cost_clock(pair("GAD-1001", "US"), 1_000).depreciation_usd
    home = agent._cost_clock(pair("HOM-3001", "US"), 1_000).depreciation_usd
    assert gadget > home


async def test_negative_net_score_blocks(offline: Reasoner) -> None:
    agent = TradeoffDecisionAgent(offline)
    action = ProposedAction(
        id="ACT-001",
        action=ActionType.TRANSFER,
        target=pair("GAD-1001", "US"),
        units=500,
        destination_market="JP",
        description="test",
    )
    decision = await agent.run(
        action,
        CarbonScore(
            score=95.0,
            emissions_kg_co2e=40_000,
            drivers=["air freight"],
            credit_eligible=False,
            reasoning="long-haul air",
        ),
        FinancialBenefit(
            gross_benefit_usd=10_000,
            execution_cost_usd=4_000,
            net_benefit_usd=6_000,
            payback_days=12,
            reasoning="modest",
        ),
        forecast_confidence=0.8,
    )
    # A 95-point carbon burden costs far more than $6k of benefit.
    assert decision.verdict is Verdict.BLOCK
    assert decision.net_score < 0
    assert decision.escalation_owner == "none"


async def test_block_feeds_back_and_suppresses_reproposal(offline: Reasoner) -> None:
    from cosmic_mart.agents.overstock import OverstockLossAgent

    gate = HumanGate()
    overstock = OverstockLossAgent(offline, build_mock_registry(1).inventory)
    target = pair("GAD-1002", "BR")
    action = ProposedAction(
        id="ACT-009",
        action=ActionType.DISCOUNT,
        target=target,
        units=100,
        discount_pct=15,
        description="test",
    )
    evaluated = EvaluatedAction(
        action=action,
        carbon=CarbonScore(
            score=5, emissions_kg_co2e=10, drivers=[], credit_eligible=True, reasoning="x"
        ),
        financial=FinancialBenefit(
            gross_benefit_usd=1, execution_cost_usd=2, net_benefit_usd=-1, payback_days=0,
            reasoning="x",
        ),
        decision=await TradeoffDecisionAgent(offline).run(
            action,
            CarbonScore(
                score=5, emissions_kg_co2e=10, drivers=[], credit_eligible=True, reasoning="x"
            ),
            FinancialBenefit(
                gross_benefit_usd=1, execution_cost_usd=2, net_benefit_usd=-1, payback_days=0,
                reasoning="x",
            ),
            forecast_confidence=0.9,
        ),
    )
    record = gate.submit(evaluated)
    assert evaluated.decision.verdict is Verdict.BLOCK

    assert not overstock.is_blocked(target, ActionType.DISCOUNT)
    overstock.register_block(record)
    assert overstock.is_blocked(target, ActionType.DISCOUNT)


def test_carbon_credit_bank_cannot_overdraw() -> None:
    bank = CarbonCreditBank()
    bank.credit("ACT-001", 500.0)
    assert bank.balance_kg == 500.0
    assert bank.debit("ACT-002", 200.0) is True
    assert bank.balance_kg == 300.0
    assert bank.debit("ACT-003", 900.0) is False
    assert bank.balance_kg == 300.0


def test_ledger_reweights_toward_accuracy() -> None:
    ledger = SignalAccuracyLedger()
    before = ledger.weight(SignalKind.SOCIAL)
    for _ in range(5):
        ledger.record(SignalKind.SOCIAL, predicted_pct=80.0, actual_pct=5.0)
    assert ledger.weight(SignalKind.SOCIAL) < before


def test_low_confidence_forecast_escalates() -> None:
    from cosmic_mart.agents.synthesizer import DemandSynthesizer
    from cosmic_mart.models import AttributedSignal, Cadence, SignalReading

    synth = DemandSynthesizer(Reasoner(offline=True))
    # Two agents in direct opposition should widen the band and cut confidence.
    signals = [
        AttributedSignal(
            reading=SignalReading(
                kind=SignalKind.SOCIAL,
                demand_impact_pct=120.0,
                confidence=0.4,
                horizon_days=14,
                rationale="viral",
            ),
            agent="social_trend_influencer",
            cadence=Cadence.REAL_TIME,
        ),
        AttributedSignal(
            reading=SignalReading(
                kind=SignalKind.MACRO,
                demand_impact_pct=-60.0,
                confidence=0.4,
                horizon_days=90,
                rationale="recession",
            ),
            agent="macroeconomic_signal",
            cadence=Cadence.WEEKLY,
        ),
    ]
    forecast = synth._blend(signals, baseline=1_000)
    assert forecast.confidence < SETTINGS.escalation_confidence_floor
    assert len(forecast.conflicting_signals) == 2
