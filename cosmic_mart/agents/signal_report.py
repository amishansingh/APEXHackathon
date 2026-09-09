"""Signal Report Agent — maps processed signals to per-item signal context.

When a signal contradicts the historical baseline direction, it records BOTH
views and flags the divergence. It does not resolve or average — the synthesizer
receives the full tension. Weighted 0.3 at synthesis time.
"""

from __future__ import annotations

from ..models import PerItemSignalContext
from .base import Agent
from .signal_processing import ProcessedSignals


class SignalReportAgent(Agent):
    name = "signal_report"

    def run(self, processed: list[ProcessedSignals]) -> list[PerItemSignalContext]:
        reports: list[PerItemSignalContext] = []
        for item in processed:
            net = self._net_direction(item)
            # A conflict exists when signals pull in opposing directions among
            # themselves — the synthesizer resolves signal-vs-baseline conflict later.
            ups = sum(1 for s in item.signals if s.direction == "up")
            downs = sum(1 for s in item.signals if s.direction == "down")
            has_conflict = ups > 0 and downs > 0

            for s in item.signals:
                # Mark each signal that opposes the net pull as conflicting.
                if net != "neutral" and s.direction not in (net, "neutral"):
                    s.conflict_with_baseline = True

            reports.append(
                PerItemSignalContext(
                    sku=item.sku,
                    signals=item.signals,
                    has_conflict=has_conflict,
                    net_direction=net,
                )
            )
        conflicts = sum(1 for r in reports if r.has_conflict)
        self._log(items=len(reports), conflicts=conflicts)
        return reports

    def _net_direction(self, item: ProcessedSignals):
        score = 0.0
        for s in item.signals:
            if s.direction == "up":
                score += s.strength
            elif s.direction == "down":
                score -= s.strength
        if score > 0.05:
            return "up"
        if score < -0.05:
            return "down"
        return "neutral"
