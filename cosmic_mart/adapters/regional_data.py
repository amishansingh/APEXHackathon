"""Mock 25 yr regional analogue feed — the 15 most similar interplanetary regions."""

from __future__ import annotations

import random
from typing import Any

from ..models import SKU

ANALOGUE_REGIONS = [
    "Kepler-Belt", "Titan-Ring", "Ceres-Hub", "Europa-Shelf", "Vesta-Cluster",
    "Io-Terminus", "Ganymede-Reach", "Callisto-Verge", "Enceladus-Bay", "Mimas-Fold",
    "Rhea-Corridor", "Dione-Passage", "Tethys-Haven", "Oberon-Flats", "Ariel-Drift",
]

# Per-region consumption affinity multiplier per category.
# A factor > 1.0 means this region over-indexes on that category relative to Earth.
_REGION_AFFINITY: dict[str, dict[str, float]] = {
    "Kepler-Belt":    {"gadgets": 1.25, "appliances": 0.85, "home": 0.80},
    "Titan-Ring":     {"gadgets": 0.90, "appliances": 1.30, "home": 1.10},
    "Ceres-Hub":      {"gadgets": 1.10, "appliances": 1.00, "home": 0.95},
    "Europa-Shelf":   {"gadgets": 0.75, "appliances": 1.20, "home": 1.35},
    "Vesta-Cluster":  {"gadgets": 1.15, "appliances": 0.90, "home": 1.05},
    "Io-Terminus":    {"gadgets": 1.30, "appliances": 0.75, "home": 0.70},
    "Ganymede-Reach": {"gadgets": 0.85, "appliances": 1.15, "home": 1.20},
    "Callisto-Verge": {"gadgets": 1.00, "appliances": 1.10, "home": 0.90},
    "Enceladus-Bay":  {"gadgets": 0.80, "appliances": 0.95, "home": 1.40},
    "Mimas-Fold":     {"gadgets": 1.20, "appliances": 1.05, "home": 0.85},
    "Rhea-Corridor":  {"gadgets": 0.70, "appliances": 1.25, "home": 1.15},
    "Dione-Passage":  {"gadgets": 1.10, "appliances": 0.80, "home": 1.00},
    "Tethys-Haven":   {"gadgets": 0.95, "appliances": 1.00, "home": 1.30},
    "Oberon-Flats":   {"gadgets": 1.05, "appliances": 0.90, "home": 0.95},
    "Ariel-Drift":    {"gadgets": 0.90, "appliances": 1.10, "home": 1.05},
}

_CATEGORY_BASE: dict[str, float] = {"gadgets": 300, "appliances": 140, "home": 80}

_SKU_BASE: dict[str, float] = {
    "GAD-1001": 340.0,
    "GAD-1002": 430.0,
    "GAD-1003": 370.0,
    "GAD-1004": 240.0,
    "GAD-1005": 200.0,
    "GAD-1006": 150.0,
    "GAD-1007": 110.0,
    "APP-2001": 140.0,
    "APP-2002": 155.0,
    "APP-2003": 85.0,
    "APP-2004": 115.0,
    "HOM-3001": 75.0,
    "HOM-3002": 165.0,
    "HOM-3003": 65.0,
    "HOM-3004": 100.0,
}


class RegionalDataProvider:
    """Seeded random analogue history, used to fill gaps when Earth data is sparse."""

    def __init__(self, seed: int = 42):
        self.seed = seed

    def _rng(self, sku: SKU) -> random.Random:
        return random.Random(f"{self.seed}:regional:{sku.id}")

    async def observe(self, sku: SKU) -> dict[str, Any]:
        rng = self._rng(sku)
        base = _SKU_BASE.get(sku.id) or _CATEGORY_BASE.get(sku.category, 100)
        # Analogue markets run structurally similar but noisier than Earth.
        monthly = base * rng.uniform(0.5, 1.5)
        cat = sku.category
        by_region = {
            r: round(monthly * _REGION_AFFINITY[r].get(cat, 1.0) * rng.uniform(0.05, 0.25), 1)
            for r in ANALOGUE_REGIONS
        }
        return {
            "sku_id": sku.id,
            "years_of_history": 25,
            "monthly_units": round(monthly, 1),
            "by_region": by_region,
            "structural_similarity": round(rng.uniform(0.45, 0.95), 2),
        }
