"""Data-source contracts. Swap a mock for a real API by implementing these."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from ..models import SKUMarket, SignalKind


@runtime_checkable
class SignalSource(Protocol):
    """Raw observations for one signal domain, before any agent interprets them."""

    kind: SignalKind

    async def observe(self, target: SKUMarket) -> dict[str, Any]:
        """Return the raw payload a signal agent will reason over."""
        ...


@runtime_checkable
class InventorySource(Protocol):
    async def stock_level(self, target: SKUMarket) -> dict[str, Any]:
        """Units on hand, in transit, and the trailing sales rate."""
        ...


class SourceRegistry:
    """Holds one source per signal domain plus the inventory feed."""

    def __init__(self, inventory: InventorySource, signals: dict[SignalKind, SignalSource]):
        self.inventory = inventory
        self.signals = signals

    def get(self, kind: SignalKind) -> SignalSource:
        return self.signals[kind]
