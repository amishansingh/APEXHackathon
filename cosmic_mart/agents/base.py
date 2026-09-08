"""Shared scaffolding for the six signal agents."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field

from ..adapters.base import SignalSource
from ..config import SETTINGS
from ..llm import Reasoner
from ..models import AttributedSignal, Cadence, SignalKind, SignalReading, SKUMarket


class SignalEstimate(BaseModel):
    """What a signal agent is asked to produce. `kind` is set by the agent itself."""

    demand_impact_pct: float = Field(
        description="Percent change in demand versus baseline attributable to THIS signal "
        "domain only. Negative for suppressed demand. Range -100 to 300.",
        ge=-100,
        le=300,
    )
    confidence: float = Field(description="How sure you are, 0.0 to 1.0", ge=0.0, le=1.0)
    horizon_days: int = Field(description="Days over which the impact plays out", ge=1, le=365)
    rationale: str = Field(description="One or two sentences naming the specific driver.")
    drivers: list[str] = Field(description="Short names of the causes, e.g. ['Diwali'].")


class SignalAgent(ABC):
    """Observes one domain and converts it into a demand impact estimate."""

    kind: SignalKind
    name: str
    cadence: Cadence
    system: str

    def __init__(self, reasoner: Reasoner, source: SignalSource):
        self.reasoner = reasoner
        self.source = source

    @abstractmethod
    def heuristic(self, raw: dict[str, Any], target: SKUMarket) -> SignalEstimate:
        """Deterministic estimate used offline and whenever the API call fails."""

    async def run(self, target: SKUMarket) -> AttributedSignal:
        raw = await self.source.observe(target)
        estimate = await self.reasoner.think(
            system=self.system,
            payload=raw,
            instruction=(
                f"Estimate the demand impact on {target.sku.name} "
                f"({target.sku.category}) in {target.market.name} from these "
                f"{self.kind.value} observations. Judge only your own domain; other "
                f"agents cover the rest."
            ),
            schema=SignalEstimate,
            fallback=self.heuristic(raw, target),
        )
        reading = SignalReading(kind=self.kind, **estimate.model_dump())
        return AttributedSignal(
            reading=reading,
            agent=self.name,
            cadence=self.cadence,
            weight=SETTINGS.signal_weights[self.kind],
        )
