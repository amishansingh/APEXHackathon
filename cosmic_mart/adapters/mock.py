"""Synthetic but plausible data. Deterministic for a given seed."""

from __future__ import annotations

import hashlib
import random
from typing import Any

from ..models import SKUMarket, SignalKind
from .base import SourceRegistry

_HOLIDAYS = {
    "IN": ["Diwali", "Holi", "Eid al-Fitr"],
    "US": ["Thanksgiving", "Black Friday", "Independence Day"],
    "BR": ["Carnival", "Festa Junina"],
    "GB": ["Boxing Day", "Bank Holiday Monday"],
    "DE": ["Weihnachtsmarkt", "Oktoberfest"],
    "NG": ["Eid al-Adha", "Independence Day"],
    "ZA": ["Heritage Day", "Freedom Day"],
    "JP": ["Golden Week", "Obon"],
    "AE": ["Ramadan", "National Day"],
    "AU": ["Australia Day", "Boxing Day"],
}

_WEATHER = {
    "North America": ["early cold snap", "mild autumn", "record rainfall"],
    "South America": ["heatwave", "humid spell", "unseasonal storms"],
    "Europe": ["early winter", "cold front", "mild spell"],
    "Africa": ["dry season onset", "heatwave", "heavy rains"],
    "Asia": ["monsoon surge", "heatwave", "typhoon warning"],
    "Middle East": ["extreme heat advisory", "sandstorm", "mild evenings"],
    "Oceania": ["bushfire risk", "cyclone watch", "warm dry spell"],
}

_EVENTS = [
    "national football final",
    "major music festival",
    "general election",
    "competitor product recall",
    "public health advisory",
    "large tech conference",
]


def _rng(seed: int, *parts: str) -> random.Random:
    digest = hashlib.sha256("|".join((str(seed), *parts)).encode()).hexdigest()
    return random.Random(int(digest[:16], 16))


class _Base:
    def __init__(self, seed: int):
        self.seed = seed

    def _r(self, target: SKUMarket, salt: str) -> random.Random:
        return _rng(self.seed, salt, target.sku.id, target.market.code)


class MockCulturalSource(_Base):
    kind = SignalKind.CULTURAL

    async def observe(self, target: SKUMarket) -> dict[str, Any]:
        r = self._r(target, "cultural")
        holidays = _HOLIDAYS.get(target.market.code, ["Local festival"])
        upcoming = r.choice(holidays)
        return {
            "market": target.market.name,
            "sku_category": target.sku.category,
            "upcoming_observance": upcoming,
            "days_until": r.randint(3, 45),
            "historical_category_lift_pct": round(r.uniform(-5, 60), 1),
            "gifting_relevance": r.choice(["high", "medium", "low"]),
        }


class MockWeatherSource(_Base):
    kind = SignalKind.WEATHER

    async def observe(self, target: SKUMarket) -> dict[str, Any]:
        r = self._r(target, "weather")
        patterns = _WEATHER.get(target.market.region, ["seasonal norms"])
        return {
            "market": target.market.name,
            "region": target.market.region,
            "sku_category": target.sku.category,
            "pattern": r.choice(patterns),
            "temp_anomaly_c": round(r.uniform(-6, 8), 1),
            "forecast_horizon_days": r.choice([7, 14, 30]),
            "supply_disruption_risk": r.choice(["none", "none", "low", "elevated"]),
        }


class MockSocialSource(_Base):
    kind = SignalKind.SOCIAL

    async def observe(self, target: SKUMarket) -> dict[str, Any]:
        r = self._r(target, "social")
        viral = r.random() < 0.18
        return {
            "market": target.market.name,
            "sku": target.sku.name,
            "mention_velocity_24h": round(r.uniform(0.5, 12.0), 2),
            "viral_event": viral,
            "influencer_reach": r.randint(50_000, 9_000_000) if viral else 0,
            "historical_conversion_rate": round(r.uniform(0.001, 0.02), 4),
            "competitor_sentiment": r.choice(["negative", "neutral", "neutral", "positive"]),
        }


class MockMacroSource(_Base):
    kind = SignalKind.MACRO

    async def observe(self, target: SKUMarket) -> dict[str, Any]:
        r = self._r(target, "macro")
        return {
            "market": target.market.name,
            "gdp_growth_pct": round(r.uniform(-2.0, 7.0), 2),
            "inflation_pct": round(r.uniform(1.0, 22.0), 2),
            "consumer_confidence_index": round(r.uniform(58, 118), 1),
            "unemployment_pct": round(r.uniform(2.5, 14.0), 1),
            "currency_move_vs_usd_pct": round(r.uniform(-12, 6), 2),
            "category_discretionary": target.sku.category in {"gadgets", "home"},
        }


class MockLocalEventsSource(_Base):
    kind = SignalKind.LOCAL_EVENTS

    async def observe(self, target: SKUMarket) -> dict[str, Any]:
        r = self._r(target, "events")
        has_event = r.random() < 0.4
        return {
            "market": target.market.name,
            "sku_category": target.sku.category,
            "event": r.choice(_EVENTS) if has_event else None,
            "days_until": r.randint(1, 30) if has_event else None,
            "estimated_footfall": r.randint(5_000, 400_000) if has_event else 0,
        }


class MockSeasonalitySource(_Base):
    kind = SignalKind.SEASONALITY

    async def observe(self, target: SKUMarket) -> dict[str, Any]:
        r = self._r(target, "seasonality")
        return {
            "market": target.market.name,
            "sku": target.sku.name,
            "baseline_weekly_units": r.randint(400, 6_000),
            "same_period_last_year_pct_vs_baseline": round(r.uniform(-25, 45), 1),
            "three_year_trend": r.choice(["rising", "flat", "declining"]),
            "known_recurring_peak": r.choice([True, False]),
            "historical_std_dev_pct": round(r.uniform(6, 34), 1),
        }


class MockInventorySource(_Base):
    async def stock_level(self, target: SKUMarket) -> dict[str, Any]:
        r = self._r(target, "inventory")
        weekly_sales = r.randint(200, 4_000)
        # Overstock is the stated problem, so skew on-hand above a healthy cover.
        cover_weeks = r.uniform(1.0, 9.0)
        return {
            "units_on_hand": int(weekly_sales * cover_weeks),
            "units_in_transit": r.randint(0, weekly_sales),
            "trailing_weekly_sales": weekly_sales,
            "warehouse": f"{target.market.code}-DC1",
        }


def build_mock_registry(seed: int) -> SourceRegistry:
    return SourceRegistry(
        inventory=MockInventorySource(seed),
        signals={
            SignalKind.CULTURAL: MockCulturalSource(seed),
            SignalKind.WEATHER: MockWeatherSource(seed),
            SignalKind.SOCIAL: MockSocialSource(seed),
            SignalKind.MACRO: MockMacroSource(seed),
            SignalKind.LOCAL_EVENTS: MockLocalEventsSource(seed),
            SignalKind.SEASONALITY: MockSeasonalitySource(seed),
        },
    )
