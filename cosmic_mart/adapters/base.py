"""Data-source contracts. Swap a mock for a real feed by implementing these."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from ..models import SKU, InventoryRecord


@runtime_checkable
class InventorySource(Protocol):
    """The current-inventory database.

    This is where the SKU catalogue comes from. The Signal Processing Agent needs
    the item identification number and item name to scope signal matching to
    active inventory, so both are first-class fields on every record rather than
    something the agent has to infer.

    To point at a real database, implement these three methods against it — no
    agent code changes, since agents consume the records, not the source.
    """

    async def records(self) -> list[InventoryRecord]:
        """Every current-inventory row."""
        ...

    async def catalogue(self) -> list[SKU]:
        """The distinct items on hand, as SKUs — the unit of work for both branches."""
        ...

    async def item_index(self) -> dict[str, str]:
        """{item_id: item_name} — the lookup the signal agents match against."""
        ...


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
