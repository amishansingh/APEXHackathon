"""Turns the ranked bleed list into concrete actions for parallel evaluation."""

from __future__ import annotations

from ..models import (
    ActionType,
    OverstockAssessment,
    ProposedAction,
    SynthesizedDemand,
)


def build_proposals(
    overstock: list[OverstockAssessment],
    demand: list[SynthesizedDemand],
    max_proposals: int = 12,
) -> list[ProposedAction]:
    """Pair the worst overstock positions with the hungriest markets for the same SKU.

    A transfer needs somewhere to send the units. Where no market is short of the
    same SKU, the only lever left is a discount in place.
    """
    shortfall_by_sku: dict[str, list[tuple[str, int]]] = {}
    for d in demand:
        gap = d.forecast.units_expected - d.baseline_units
        if gap > 0:
            shortfall_by_sku.setdefault(d.target.sku.id, []).append((d.target.market.code, gap))
    for entries in shortfall_by_sku.values():
        entries.sort(key=lambda e: e[1], reverse=True)

    ranked = sorted(overstock, key=lambda a: a.daily_loss.total_usd, reverse=True)

    proposals: list[ProposedAction] = []
    for assessment in ranked:
        if assessment.units_excess <= 0 or assessment.severity == "none":
            continue

        target = assessment.target
        destinations = [
            (code, gap)
            for code, gap in shortfall_by_sku.get(target.sku.id, [])
            if code != target.market.code
        ]

        if destinations:
            dest_code, gap = destinations[0]
            units = min(assessment.units_excess, gap)
            proposals.append(
                ProposedAction(
                    id=f"ACT-{len(proposals) + 1:03d}",
                    action=ActionType.TRANSFER,
                    target=target,
                    units=units,
                    destination_market=dest_code,
                    description=(
                        f"Transfer {units:,} units of {target.sku.name} from "
                        f"{target.market.code} to {dest_code}, where demand runs "
                        f"{gap:,} units above baseline."
                    ),
                )
            )
        else:
            discount = 15.0 if assessment.severity == "severe" else 8.0
            proposals.append(
                ProposedAction(
                    id=f"ACT-{len(proposals) + 1:03d}",
                    action=ActionType.DISCOUNT,
                    target=target,
                    units=assessment.units_excess,
                    discount_pct=discount,
                    description=(
                        f"Discount {assessment.units_excess:,} excess units of "
                        f"{target.sku.name} in {target.market.code} by {discount:.0f}% "
                        f"to clear a ${assessment.daily_loss.total_usd:,.0f}/day bleed."
                    ),
                )
            )

        if len(proposals) >= max_proposals:
            break

    return proposals
