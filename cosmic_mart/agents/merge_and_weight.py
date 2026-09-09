"""Merge and Weight — reduce step of the historical branch.

Collects all worker shard outputs and produces a single weighted demand baseline
per item: earth * 0.9 + regional * 0.1. This is the historical branch's final
output, fed to the synthesizer at branch weight 0.7.
"""

from __future__ import annotations

from ..models import MergedBaseline, WorkerOutput
from .base import Agent


class MergeAndWeight(Agent):
    name = "merge_and_weight"

    def __init__(
        self,
        earth_weight: float = 0.9,
        regional_weight: float = 0.1,
        sparse_earth_threshold: float = 50.0,
    ):
        self.earth_weight = earth_weight
        self.regional_weight = regional_weight
        self.sparse_earth_threshold = sparse_earth_threshold

    def run(self, worker_outputs: list[WorkerOutput]) -> list[MergedBaseline]:
        baselines: list[MergedBaseline] = []
        for output in worker_outputs:
            for item in output.items:
                # Apply the YoY correction layer to the raw Earth figure first.
                yoy_factor = 1.0
                for adj in item.yoy_adjustments:
                    yoy_factor *= adj.impact_multiplier
                earth_adj = item.earth_baseline * yoy_factor

                weighted = earth_adj * self.earth_weight + item.regional_baseline * self.regional_weight

                flags = list(item.data_quality_flags)
                if item.earth_baseline < self.sparse_earth_threshold and "sparse_earth_data" not in flags:
                    flags.append("sparse_earth_data")

                baselines.append(
                    MergedBaseline(
                        sku=item.sku,
                        weighted_baseline=round(weighted, 1),
                        earth_baseline=round(earth_adj, 1),
                        regional_baseline=item.regional_baseline,
                        earth_weight=self.earth_weight,
                        regional_weight=self.regional_weight,
                        yoy_adjustments=item.yoy_adjustments,
                        data_quality_flags=flags,
                    )
                )
        self._log(items=len(baselines))
        return baselines
