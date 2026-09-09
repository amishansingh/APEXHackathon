"""Mock 25 yr regional analogue feed — the 10 most similar interplanetary regions."""

from __future__ import annotations

import random
from typing import Any

from ..models import SKU

ANALOGUE_REGIONS = [
    "Kepler-Belt", "Titan-Ring", "Ceres-Hub", "Europa-Shelf", "Vesta-Cluster",
    "Io-Terminus", "Ganymede-Reach", "Callisto-Verge", "Enceladus-Bay", "Mimas-Fold",
]


class RegionalDataProvider:
    """Seeded random analogue history, used to fill gaps when Earth data is sparse."""

    def __init__(self, seed: int = 42):
        self.seed = seed

    def _rng(self, sku: SKU) -> random.Random:
        return random.Random(f"{self.seed}:regional:{sku.id}")

    async def observe(self, sku: SKU) -> dict[str, Any]:
        rng = self._rng(sku)
        base = {"gadgets": 300, "appliances": 140, "home": 80}.get(sku.category, 100)
        # Analogue markets run structurally similar but noisier than Earth.
        monthly = base * rng.uniform(0.5, 1.5)
        by_region = {r: round(monthly * rng.uniform(0.05, 0.25), 1) for r in ANALOGUE_REGIONS}
        return {
            "sku_id": sku.id,
            "years_of_history": 25,
            "monthly_units": round(monthly, 1),
            "by_region": by_region,
            "structural_similarity": round(rng.uniform(0.55, 0.92), 2),
        }
