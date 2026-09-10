"""Signal Report Agent — maps processed signals to per-item signal context.

Records both views when signals pull against each other and flags the
divergence. It does not resolve or average — the synthesizer receives the full
tension, weighted 0.3 at synthesis time.

Note on the two conflict fields (they are not the same thing):
* `opposes_net_pull` — set here. This signal pulls against the item's net signal
  direction. Tension *among the signals*.
* `conflict_with_baseline` — the §7.2 contract field, set by the synthesizer,
  which is the only stage holding the historical baseline to compare against.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from ..llm import Reasoner
from ..models import PerItemSignalContext, SignalItem
from .base import Agent
from .signal_processing import ProcessedSignals

_SYSTEM = """You are the Signal Report Agent in Cosmic Mart's demand forecasting \
pipeline.

You receive the scored signals for one inventory item. Produce the per-item \
signal report:
- net_direction: the overall pull across all signals ("up", "down", or \
"neutral" when they cancel out or there are none).
- has_conflict: true when signals genuinely pull against each other, so the \
item's outlook is contested rather than clear.
- rationale: one short sentence naming the drivers on each side.

Do not resolve the conflict and do not average it away. If two credible signals \
disagree, say so — the synthesizer widens its forecast range on the strength of \
this flag, and a reviewer reads your rationale. Weigh signal strength, not just \
how many point each way: one strong signal can outweigh two weak ones."""


class SignalReportAssessment(BaseModel):
    """What Claude returns for one item's report."""

    net_direction: Literal["up", "down", "neutral"] = "neutral"
    has_conflict: bool = False
    rationale: str = Field(default="", description="One sentence naming both sides")


class SignalReportAgent(Agent):
    name = "signal_report"

    def __init__(self, reasoner: Reasoner | None = None):
        self.reasoner = reasoner or Reasoner()

    async def run(self, processed: list[ProcessedSignals]) -> list[PerItemSignalContext]:
        reports: list[PerItemSignalContext] = []

        for item in processed:
            fallback = SignalReportAssessment(
                net_direction=self._net_direction(item.signals),
                has_conflict=self._has_conflict(item.signals),
                rationale=self._rationale(item.signals),
            )

            assessed = await self.reasoner.think(
                system=_SYSTEM,
                payload={
                    "item_id": item.sku.id,
                    "item_name": item.sku.name,
                    "category": item.sku.category,
                    "signals": [s.model_dump() for s in item.signals],
                },
                instruction=(
                    "Produce the per-item signal report. Preserve conflict; do "
                    "not average opposing signals into a single view."
                ),
                schema=SignalReportAssessment,
                fallback=fallback,
            )

            net = assessed.net_direction
            for s in item.signals:
                # Mark each signal that pulls against the net direction.
                s.opposes_net_pull = net != "neutral" and s.direction not in (net, "neutral")

            reports.append(
                PerItemSignalContext(
                    sku=item.sku,
                    signals=item.signals,
                    has_conflict=assessed.has_conflict,
                    net_direction=net,
                    rationale=assessed.rationale,
                )
            )

        conflicts = sum(1 for r in reports if r.has_conflict)
        self._log(items=len(reports), conflicts=conflicts)
        return reports

    # --- deterministic fallbacks --------------------------------------------

    def _net_direction(self, signals: list[SignalItem]) -> Literal["up", "down", "neutral"]:
        score = 0.0
        for s in signals:
            if s.direction == "up":
                score += s.strength
            elif s.direction == "down":
                score -= s.strength
        if score > 0.05:
            return "up"
        if score < -0.05:
            return "down"
        return "neutral"

    def _has_conflict(self, signals: list[SignalItem]) -> bool:
        ups = sum(1 for s in signals if s.direction == "up")
        downs = sum(1 for s in signals if s.direction == "down")
        return ups > 0 and downs > 0

    def _rationale(self, signals: list[SignalItem]) -> str:
        up = [s.description for s in signals if s.direction == "up" and s.description]
        down = [s.description for s in signals if s.direction == "down" and s.description]
        if up and down:
            return f"Raising: {', '.join(up)}. Lowering: {', '.join(down)}."
        if up:
            return f"Raising: {', '.join(up)}."
        if down:
            return f"Lowering: {', '.join(down)}."
        return "No live signals for this item in the window."
