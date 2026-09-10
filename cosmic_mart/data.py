"""Cosmic Mart's North American markets and its SKU catalogue."""

from __future__ import annotations

from .models import SKU, Market, SKUMarket

MARKETS: list[Market] = [
    Market(code="US", name="United States",      region="North America", currency="USD"),
    Market(code="CA", name="Canada",             region="North America", currency="CAD"),
    Market(code="MX", name="Mexico",             region="North America", currency="MXN"),
    Market(code="NA", name="Other North America", region="North America", currency="USD"),
]

# Gadgets are 77% of revenue and depreciate fastest as new models release.
SKUS: list[SKU] = [
    SKU(
        id="GAD-1001",
        name="Nova Handset X",
        category="gadgets",
        unit_cost_usd=310.0,
        unit_price_usd=629.0,
        depreciation_rate_daily=0.0022,
    ),
    SKU(
        id="GAD-1002",
        name="Orbit Earbuds Pro",
        category="gadgets",
        unit_cost_usd=48.0,
        unit_price_usd=129.0,
        depreciation_rate_daily=0.0018,
    ),
    SKU(
        id="GAD-1003",
        name="Pulse Smartwatch 4",
        category="gadgets",
        unit_cost_usd=92.0,
        unit_price_usd=219.0,
        depreciation_rate_daily=0.0020,
    ),
    SKU(
        id="APP-2001",
        name="Halo Air Conditioner",
        category="appliances",
        unit_cost_usd=240.0,
        unit_price_usd=479.0,
        depreciation_rate_daily=0.0006,
    ),
    SKU(
        id="APP-2002",
        name="Ember Space Heater",
        category="appliances",
        unit_cost_usd=54.0,
        unit_price_usd=119.0,
        depreciation_rate_daily=0.0005,
    ),
    SKU(
        id="HOM-3001",
        name="Terra Cookware Set",
        category="home",
        unit_cost_usd=63.0,
        unit_price_usd=149.0,
        depreciation_rate_daily=0.0002,
    ),
    SKU(
        id="GAD-1004",
        name="Nebula Tablet Pro",
        category="gadgets",
        unit_cost_usd=195.0,
        unit_price_usd=449.0,
        depreciation_rate_daily=0.0019,
    ),
    SKU(
        id="GAD-1005",
        name="Quantum BT Speaker",
        category="gadgets",
        unit_cost_usd=38.0,
        unit_price_usd=89.0,
        depreciation_rate_daily=0.0014,
    ),
    SKU(
        id="GAD-1006",
        name="Stellar Gaming Headset",
        category="gadgets",
        unit_cost_usd=55.0,
        unit_price_usd=139.0,
        depreciation_rate_daily=0.0016,
    ),
    SKU(
        id="GAD-1007",
        name="VortexCam 360",
        category="gadgets",
        unit_cost_usd=72.0,
        unit_price_usd=179.0,
        depreciation_rate_daily=0.0017,
    ),
    SKU(
        id="APP-2003",
        name="Arctic Chest Freezer",
        category="appliances",
        unit_cost_usd=310.0,
        unit_price_usd=649.0,
        depreciation_rate_daily=0.0004,
    ),
    SKU(
        id="APP-2004",
        name="Zephyr Air Purifier",
        category="appliances",
        unit_cost_usd=85.0,
        unit_price_usd=199.0,
        depreciation_rate_daily=0.0006,
    ),
    SKU(
        id="HOM-3002",
        name="Luxe Bedding Bundle",
        category="home",
        unit_cost_usd=78.0,
        unit_price_usd=179.0,
        depreciation_rate_daily=0.0002,
    ),
    SKU(
        id="HOM-3003",
        name="Arcadia Desk Lamp",
        category="home",
        unit_cost_usd=29.0,
        unit_price_usd=69.0,
        depreciation_rate_daily=0.0003,
    ),
    SKU(
        id="HOM-3004",
        name="Cedar Storage Rack",
        category="home",
        unit_cost_usd=44.0,
        unit_price_usd=99.0,
        depreciation_rate_daily=0.0002,
    ),
]

MARKETS_BY_CODE = {m.code: m for m in MARKETS}
SKUS_BY_ID = {s.id: s for s in SKUS}


def all_skus() -> list[SKU]:
    """The full North American SKU catalogue — the unit of work in the new pipeline.

    The historical and signals branches are both SKU-first; sub-market breakdown
    lives inside each branch's per-item baselines rather than as a separate axis.
    """
    return list(SKUS)


def pair(sku_id: str, market_code: str) -> SKUMarket:
    return SKUMarket(sku=SKUS_BY_ID[sku_id], market=MARKETS_BY_CODE[market_code])
