"""Runtime configuration and the tunable weights the tradeoff agent depends on."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

DEFAULT_MODEL = "claude-opus-5"


@dataclass(frozen=True)
class Settings:
    model: str = os.getenv("COSMIC_MART_MODEL", DEFAULT_MODEL)
    seed: int = int(os.getenv("COSMIC_MART_SEED", "42"))
    offline: bool = os.getenv("COSMIC_MART_OFFLINE", "0") == "1"

    # Branch weights into the demand synthesizer (§7.3). Historical branch is the
    # anchor; signals nudge it. Configurable per market — new expansions with thin
    # Earth history may raise the regional analogue weight below.
    hist_branch_weight: float = 0.7
    sig_branch_weight: float = 0.3

    # Within the historical branch's merge step: Earth data dominates, regional
    # analogues fill the gaps when Earth history is sparse.
    earth_data_weight: float = 0.9
    regional_data_weight: float = 0.1

    # Number of parallel worker agents the Historical Manager shards work across.
    worker_count: int = int(os.getenv("COSMIC_MART_WORKERS", "3"))

    # Below this Earth baseline, the merge step flags an item as data-sparse so the
    # regional analogue weight carries more of the forecast.
    sparse_earth_threshold: float = 50.0

    # Escalation triggers for the synthesizer (§5). A recommendation past any of
    # these goes to a human rather than the autonomous path.
    escalation_value_threshold_usd: float = 50_000.0
    escalation_confidence_floor: float = 0.45
    # Divergence past this many standard deviations flags a conflict for review.
    divergence_std_threshold: float = 2.0


SETTINGS = Settings()
