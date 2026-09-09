"""The six specialist signal agents that feed the demand synthesizer."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..models import Cadence, SKUMarket, SignalKind, TriggerSignal
from .base import SignalAgent, SignalEstimate

if TYPE_CHECKING:
    pass

_PREAMBLE = (
    "You are a specialist agent inside Cosmic Mart's supply chain system. "
    "Cosmic Mart is a multi-planet retailer operating across 10 Earth markets, "
    "carrying a pre-tax loss of $7.84B driven largely by inventory misalignment. "
    "Gadgets are 77% of revenue and depreciate fast. "
    "Report only what your own domain supports. Say so with low confidence when "
    "the observations are weak; do not invent drivers that are not in the data."
)


class CulturalAgent(SignalAgent):
    kind = SignalKind.CULTURAL
    name = "cultural_intelligence"
    cadence = Cadence.MONTHLY
    first_run_lookback_days = 30
    system = (
        f"{_PREAMBLE}\n\nYou are the CULTURAL INTELLIGENCE agent. You maintain a living "
        "cultural profile per market: holidays, religious observances, regional consumer "
        "values, and cultural events. Translate cultural context into an inventory number "
        "by weighting the historical category lift against how close the observance is and "
        "how relevant the category is to gifting."
    )

    def heuristic(self, raw: dict[str, Any], target: SKUMarket) -> SignalEstimate:
        lift = float(raw["historical_category_lift_pct"])
        days = int(raw["days_until"])
        relevance = {"high": 1.0, "medium": 0.6, "low": 0.25}[raw["gifting_relevance"]]
        proximity = max(0.0, 1.0 - days / 60.0)
        return SignalEstimate(
            demand_impact_pct=round(lift * relevance * proximity, 1),
            confidence=0.5 + 0.3 * relevance,
            horizon_days=max(7, days),
            rationale=f"{raw['upcoming_observance']} in {days} days with "
            f"{relevance:.0%} category relevance.",
            drivers=[raw["upcoming_observance"]],
        )

    def generate_trigger(self, raw: dict, target: SKUMarket, estimate: SignalEstimate) -> TriggerSignal:
        return TriggerSignal(
            agent_id=self.name,
            market=target.market.code,
            event_type=raw.get("upcoming_observance", "cultural_event"),
            estimated_demand_impact=1.0 + estimate.demand_impact_pct / 100.0,
            affected_sku_categories=["gadgets", "home"],
            cadence=Cadence.MONTHLY,
            confidence_score=estimate.confidence,
        )


class WeatherAgent(SignalAgent):
    kind = SignalKind.WEATHER
    name = "weather_climate"
    cadence = Cadence.WEEKLY
    first_run_lookback_days = 7
    system = (
        f"{_PREAMBLE}\n\nYou are the WEATHER + CLIMATE agent. Map climate events to "
        "historical purchase behaviour by category and region: an early winter in Europe "
        "accelerates heating and home appliance demand; a heatwave spikes cooling and "
        "electronics. Also weigh whether extreme weather is a supply disruption risk, "
        "which suppresses achievable demand even when appetite is high."
    )

    def heuristic(self, raw: dict[str, Any], target: SKUMarket) -> SignalEstimate:
        anomaly = float(raw["temp_anomaly_c"])
        category = target.sku.category
        if category == "appliances":
            impact = abs(anomaly) * 4.5
        elif category == "gadgets":
            impact = anomaly * 1.2
        else:
            impact = anomaly * 0.6
        if raw["supply_disruption_risk"] == "elevated":
            impact -= 10.0
        return SignalEstimate(
            demand_impact_pct=round(max(-100.0, impact), 1),
            confidence=0.6,
            horizon_days=int(raw["forecast_horizon_days"]),
            rationale=f"{raw['pattern']} with a {anomaly:+.1f}C anomaly in "
            f"{raw['region']}.",
            drivers=[raw["pattern"]],
        )

    def generate_trigger(self, raw: dict, target: SKUMarket, estimate: SignalEstimate) -> TriggerSignal:
        return TriggerSignal(
            agent_id=self.name,
            market=target.market.code,
            event_type=raw.get("pattern", "weather_event"),
            estimated_demand_impact=1.0 + estimate.demand_impact_pct / 100.0,
            affected_sku_categories=["appliances", "gadgets"],
            cadence=Cadence.WEEKLY,
            confidence_score=estimate.confidence,
        )


class SocialTrendAgent(SignalAgent):
    kind = SignalKind.SOCIAL
    name = "social_trend_influencer"
    cadence = Cadence.DAILY
    first_run_lookback_days = 1
    system = (
        f"{_PREAMBLE}\n\nYou are the SOCIAL TREND + INFLUENCER agent. When a product goes "
        "viral, size the demand spike from influencer reach times the historical conversion "
        "rate, not from raw mention counts. Negative viral coverage of a competitor is an "
        "opportunity signal for the equivalent Cosmic Mart SKU. Viral spikes decay fast, so "
        "keep your horizon short."
    )

    def heuristic(self, raw: dict[str, Any], target: SKUMarket) -> SignalEstimate:
        if raw["viral_event"]:
            converted = raw["influencer_reach"] * raw["historical_conversion_rate"]
            impact = min(220.0, converted / 400.0)
            confidence, horizon = 0.55, 14
            drivers = ["viral moment"]
        else:
            impact = (float(raw["mention_velocity_24h"]) - 4.0) * 1.5
            confidence, horizon = 0.35, 21
            drivers = ["baseline social chatter"]
        if raw["competitor_sentiment"] == "negative":
            impact += 8.0
            drivers.append("competitor backlash")
        return SignalEstimate(
            demand_impact_pct=round(max(-100.0, impact), 1),
            confidence=confidence,
            horizon_days=horizon,
            rationale=f"Mention velocity {raw['mention_velocity_24h']}x with "
            f"{raw['competitor_sentiment']} competitor sentiment.",
            drivers=drivers,
        )

    def generate_trigger(self, raw: dict, target: SKUMarket, estimate: SignalEstimate) -> TriggerSignal:
        viral = raw.get("viral_event", False)
        event_type = "viral_trend" if viral else "social_signal"
        return TriggerSignal(
            agent_id=self.name,
            market=target.market.code,
            event_type=event_type,
            estimated_demand_impact=1.0 + estimate.demand_impact_pct / 100.0,
            affected_sku_categories=["gadgets"],
            cadence=Cadence.DAILY,
            confidence_score=estimate.confidence,
        )


class MacroAgent(SignalAgent):
    kind = SignalKind.MACRO
    name = "macroeconomic_signal"
    cadence = Cadence.DAILY
    first_run_lookback_days = 1
    system = (
        f"{_PREAMBLE}\n\nYou are the MACROECONOMIC SIGNAL agent. You adjust the demand "
        "baseline every other agent forecasts against. Falling consumer confidence requires "
        "a downward revision across discretionary categories; a weakening local currency "
        "raises the effective price of imported goods. Your impacts are broad and slow, so "
        "they should be smaller in magnitude but longer in horizon than event-driven ones."
    )

    def heuristic(self, raw: dict[str, Any], target: SKUMarket) -> SignalEstimate:
        confidence_gap = (float(raw["consumer_confidence_index"]) - 95.0) / 4.0
        fx_drag = float(raw["currency_move_vs_usd_pct"]) * 0.4
        inflation_drag = -max(0.0, float(raw["inflation_pct"]) - 5.0) * 0.6
        impact = confidence_gap + fx_drag + inflation_drag
        if raw["category_discretionary"]:
            impact *= 1.5
        return SignalEstimate(
            demand_impact_pct=round(max(-100.0, impact), 1),
            confidence=0.65,
            horizon_days=90,
            rationale=f"Consumer confidence {raw['consumer_confidence_index']}, "
            f"inflation {raw['inflation_pct']}%, FX {raw['currency_move_vs_usd_pct']}%.",
            drivers=["consumer confidence", "inflation"],
        )

    def generate_trigger(self, raw: dict, target: SKUMarket, estimate: SignalEstimate) -> TriggerSignal:
        return TriggerSignal(
            agent_id=self.name,
            market=target.market.code,
            event_type="macro_shift",
            estimated_demand_impact=1.0 + estimate.demand_impact_pct / 100.0,
            affected_sku_categories=["gadgets", "appliances", "home"],
            cadence=Cadence.DAILY,
            confidence_score=estimate.confidence,
        )


class LocalEventsAgent(SignalAgent):
    kind = SignalKind.LOCAL_EVENTS
    name = "local_events_news"
    cadence = Cadence.DAILY
    first_run_lookback_days = 1
    system = (
        f"{_PREAMBLE}\n\nYou are the LOCAL EVENTS + NEWS agent. You catch what cultural "
        "calendars and weather patterns miss: sports events, concerts, elections, product "
        "recalls, public health events. A competitor recall is an immediate opportunity for "
        "the equivalent Cosmic Mart SKU. When there is no event, report a near-zero impact "
        "with low confidence rather than manufacturing a signal."
    )

    def heuristic(self, raw: dict[str, Any], target: SKUMarket) -> SignalEstimate:
        if not raw["event"]:
            return SignalEstimate(
                demand_impact_pct=0.0,
                confidence=0.2,
                horizon_days=14,
                rationale="No qualifying local event detected.",
                drivers=[],
            )
        footfall_factor = min(1.0, raw["estimated_footfall"] / 250_000)
        base = 30.0 if raw["event"] == "competitor product recall" else 12.0
        return SignalEstimate(
            demand_impact_pct=round(base * footfall_factor, 1),
            confidence=0.45,
            horizon_days=max(7, int(raw["days_until"])),
            rationale=f"{raw['event']} in {raw['days_until']} days, "
            f"~{raw['estimated_footfall']:,} people affected.",
            drivers=[raw["event"]],
        )

    def generate_trigger(self, raw: dict, target: SKUMarket, estimate: SignalEstimate) -> TriggerSignal:
        event_type = raw.get("event") or "no_event"
        return TriggerSignal(
            agent_id=self.name,
            market=target.market.code,
            event_type=event_type,
            estimated_demand_impact=1.0 + estimate.demand_impact_pct / 100.0,
            affected_sku_categories=["gadgets", "home"],
            cadence=Cadence.DAILY,
            confidence_score=estimate.confidence,
        )


class SeasonalityAgent(SignalAgent):
    kind = SignalKind.SEASONALITY
    name = "seasonality_historical"
    cadence = Cadence.WEEKLY
    system = (
        f"{_PREAMBLE}\n\nYou are the SEASONALITY + HISTORICAL PATTERN agent, the long memory "
        "of the system. Your job is to distinguish genuine new demand from predictable "
        "recurring patterns, so the social trend agent does not over-correct on a seasonal "
        "spike it mistook for a viral moment. When a peak is a known recurring one, say so "
        "explicitly in your rationale and report high confidence. A wide historical standard "
        "deviation must lower your confidence."
    )

    def heuristic(self, raw: dict[str, Any], target: SKUMarket) -> SignalEstimate:
        impact = float(raw["same_period_last_year_pct_vs_baseline"])
        trend_adj = {"rising": 6.0, "flat": 0.0, "declining": -6.0}[raw["three_year_trend"]]
        spread = float(raw["historical_std_dev_pct"])
        return SignalEstimate(
            demand_impact_pct=round(impact + trend_adj, 1),
            confidence=round(max(0.3, 0.95 - spread / 100.0), 2),
            horizon_days=60,
            rationale=(
                f"{'Known recurring peak' if raw['known_recurring_peak'] else 'No recurring peak'}; "
                f"last year ran {impact:+.1f}% vs baseline on a {raw['three_year_trend']} trend."
            ),
            drivers=["seasonal baseline", f"{raw['three_year_trend']} multi-year trend"],
        )


SIGNAL_AGENT_CLASSES: list[type[SignalAgent]] = [
    CulturalAgent,
    WeatherAgent,
    SocialTrendAgent,
    MacroAgent,
    LocalEventsAgent,
]
