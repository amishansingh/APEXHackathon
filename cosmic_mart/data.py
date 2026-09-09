"""Cosmic Mart's North American markets and its SKU catalogue."""

from __future__ import annotations

from .models import SKU, Market, SKUMarket

MARKETS: list[Market] = [
    Market(code="US", name="United States", region="North America", currency="USD"),
    Market(code="CA", name="Canada",        region="North America", currency="CAD"),
    Market(code="MX", name="Mexico",        region="North America", currency="MXN"),
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
]

MARKETS_BY_CODE = {m.code: m for m in MARKETS}
SKUS_BY_ID = {s.id: s for s in SKUS}


def all_pairs() -> list[SKUMarket]:
    """Every SKU/market pair, traversed diagonally.

    A plain nested loop makes any prefix a single SKU across markets, which
    starves the transfer logic of variety. Walking the diagonal means a short
    slice still spans several SKUs and several markets.
    """
    pairs: list[SKUMarket] = []
    for offset in range(len(SKUS) + len(MARKETS) - 1):
        for i, sku in enumerate(SKUS):
            j = offset - i
            if 0 <= j < len(MARKETS):
                pairs.append(SKUMarket(sku=sku, market=MARKETS[j]))
    return pairs


def pair(sku_id: str, market_code: str) -> SKUMarket:
    return SKUMarket(sku=SKUS_BY_ID[sku_id], market=MARKETS_BY_CODE[market_code])
