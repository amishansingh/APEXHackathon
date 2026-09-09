"""Data-source contracts. Swap a mock for a real feed by implementing these."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from ..models import SKU


@runtime_checkable
class EarthSalesSource(Protocol):
    """4 yr North American transactional history, by SKU / sub-market / channel."""

    async def observe(self, sku: SKU) -> dict[str, Any]:
        ...


@runtime_checkable
class RegionalDataSource(Protocol):
    """25 yr sales history from the 10 most structurally similar interplanetary regions."""

    async def observe(self, sku: SKU) -> dict[str, Any]:
        ...


@runtime_checkable
class SignalsFeedSource(Protocol):
    """Live signal feeds: new drops + promos, large events, and news."""

    async def observe(self, sku: SKU) -> dict[str, Any]:
        ...
