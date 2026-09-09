"""Synthetic but plausible data for the North American trade sector.

Every event is written as an ultra-specific, self-contained headline so the
frontend can render it verbatim without templating generic language back on top.
Deterministic for a given seed.
"""

from __future__ import annotations

import hashlib
import random
from typing import Any

from ..models import SKUMarket, SignalKind
from .base import SourceRegistry

# Cultural / calendar events, per North American market. Each entry is a
# real, specific commercial or civic event with a date anchor.
_HOLIDAYS: dict[str, list[str]] = {
    "US": [
        "Black Friday shopping surge on November 28",
        "Cyber Monday online-only demand on December 1",
        "Super Bowl LIX ad-driven appliance demand on February 8",
        "Prime Day counter-programming week, July 15 to 17",
        "back-to-school appliance rush through mid-August",
        "Amazon Prime Big Deal Days on October 8 and 9",
        "Memorial Day appliance sale weekend, May 24 to 26",
        "Independence Day cookout equipment push, week of July 4",
    ],
    "CA": [
        "Boxing Day electronics blitz on December 26",
        "Canada Day long weekend cottage-prep sales on July 1",
        "Canadian Thanksgiving retail bump on October 14",
        "Victoria Day May long weekend home improvement push",
        "Family Day February long weekend indoor-goods bump",
        "Amazon.ca Prime Day mirror-event, July 15 to 17",
    ],
    "MX": [
        "El Buen Fin four-day nationwide sales event, November 15 to 18",
        "Dia de los Reyes Magos gifting peak on January 6",
        "Hot Sale online retail week, May 20 to 28",
        "Dia de Muertos household gathering peak, November 1 to 2",
        "15 de Septiembre independence celebrations driving appliance sales",
        "Navidad electronics gifting push in the last two weeks of December",
    ],
}

# Weather patterns keyed by market code so each country gets locally
# accurate scenarios instead of a shared regional bucket.
_WEATHER: dict[str, list[str]] = {
    "US": [
        "atmospheric river soaking the California coast for 10 straight days",
        "polar vortex pushing into the Midwest with wind chill at -30F",
        "Category 3 hurricane tracking toward the Gulf Coast",
        "record heatwave across Texas and Arizona, 110F for five days",
        "early lake-effect snow closing the I-90 corridor across upstate New York",
        "wildfire smoke advisories active across the Pacific Northwest",
        "Nor'easter forecast for the Northeast with 18 to 24 inch snowfall",
        "prolonged drought advisory across the Southwest",
    ],
    "CA": [
        "Ontario ice storm knocking out grid capacity across the GTA",
        "unseasonal Prairie warm spell delaying winter-tire changeover",
        "Arctic blast reaching Alberta with -40C overnight lows",
        "British Columbia atmospheric river forecast for the coast",
        "early lake-effect snow shutting the Trans-Canada Highway",
        "Yukon aurora tourism spike drawing seasonal gear purchases",
        "unusually warm Maritimes fall delaying furnace-service demand",
    ],
    "MX": [
        "Baja California heatwave pushing AC demand across Tijuana",
        "Yucatan hurricane warning for a Category 2 landfall near Cancun",
        "unseasonal cold front hitting the Monterrey manufacturing corridor",
        "central Mexico drought advisory disrupting bottled-water logistics",
        "Guadalajara summer humidity spike, dehumidifier demand climbing",
        "Pacific tropical storm forecast for the Puerto Vallarta coast",
    ],
}

# Local news / cultural events per market. Real-sounding, verifiable-shaped.
_EVENTS: dict[str, list[str]] = {
    "US": [
        "Apple Vision Pro 2 launch driving accessory demand",
        "MLB World Series Game 7 broadcast",
        "US Federal Reserve rate cut announcement of 25 basis points",
        "California right-to-repair legislation taking effect on January 1",
        "class-action settlement against a competitor cookware brand",
        "USDA product recall on a rival brand's smart appliance line",
        "Consumer Reports takedown of a competitor space heater",
        "NBA Finals Games 6 and 7 broadcast",
        "CES 2026 wrap-up with over 400 new consumer gadget announcements",
    ],
    "CA": [
        "Bank of Canada holding rate at 3.75%, signalling a January cut",
        "Toronto Auto Show week driving related electronics interest",
        "Loonie 3.2% slide against the USD raising imported-goods cost",
        "Health Canada recall on a competitor small appliance",
        "NHL trade deadline broadcast peak on March 6",
        "Montreal Formula E race weekend attracting 60,000 attendees",
    ],
    "MX": [
        "Banxico 25 basis point rate cut announcement",
        "peso holding stable, supporting import-heavy retail",
        "COFEPRIS product recall on a rival kitchen appliance line",
        "Liga MX Clausura final broadcast peak weekend",
        "Guadalajara International Book Fair driving e-reader interest",
        "Formula 1 Mexico City Grand Prix weekend, 130,000 in attendance",
    ],
}

# Ultra-specific social / influencer moments. Rendered verbatim by the UI.
_SOCIAL_VIRAL: list[str] = [
    "hashtag CleanTok viral cleaning-gadget trend hitting 180M views in 48 hours",
    "MKBHD teardown of a competitor phone reaching 12M views in a week",
    "'cozy setup' TikTok trend boosting gaming-headphone searches 340%",
    "MrBeast unboxing video featuring smartwatches at 35M views",
    "Wirecutter top-pick refresh for portable air conditioners published Tuesday",
    "viral Reddit thread in r/HomeImprovement on space heaters, 24,000 comments",
    "Marques Brownlee 'best of' phone comparison video at 18M views",
    "Instagram Reels cooking series driving cast-iron cookware interest",
]
_SOCIAL_BASELINE: list[str] = [
    "elevated mentions in r/BuyItForLife over the past 7 days",
    "steady chatter across TikTok product-review accounts",
    "declining brand mentions versus the prior 7-day window",
    "spike in YouTube long-form review coverage this week",
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
        holidays = _HOLIDAYS.get(target.market.code, ["local seasonal peak"])
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
        patterns = _WEATHER.get(target.market.code, ["seasonal norms"])
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
        viral = r.random() < 0.22
        topic = r.choice(_SOCIAL_VIRAL) if viral else r.choice(_SOCIAL_BASELINE)
        return {
            "market": target.market.name,
            "sku": target.sku.name,
            "topic": topic,
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
        has_event = r.random() < 0.45
        events = _EVENTS.get(target.market.code, [])
        return {
            "market": target.market.name,
            "sku_category": target.sku.category,
            "event": r.choice(events) if (has_event and events) else None,
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
