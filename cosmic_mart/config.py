"""Runtime configuration and the tunable weights the tradeoff agent depends on."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

from .models import SignalKind

load_dotenv()

DEFAULT_MODEL = "claude-opus-5"


@dataclass(frozen=True)
class Settings:
    model: str = os.getenv("COSMIC_MART_MODEL", DEFAULT_MODEL)
    seed: int = int(os.getenv("COSMIC_MART_SEED", "42"))
    offline: bool = os.getenv("COSMIC_MART_OFFLINE", "0") == "1"

    # Dollars of financial benefit Cosmic Mart is willing to give up per point of
    # carbon score. Raising this makes the tradeoff agent greener. Calibrated so a
    # full 100-point burden outweighs a typical action's benefit several times over;
    # set it too low and carbon can never change a verdict.
    carbon_price_usd_per_point: float = 300.0

    # Net score bands that separate approve / flag / block.
    approve_threshold_usd: float = 25_000.0
    block_threshold_usd: float = 0.0

    # A forecast this uncertain goes to a human regardless of the numbers. Set it
    # near the typical confidence and every forecast escalates, which defeats the
    # gate; it should catch the genuinely shaky tail only.
    escalation_confidence_floor: float = 0.40

    # A forecast below this cannot carry a straight approval, only a flag.
    approve_confidence_floor: float = 0.45

    # Warehousing cost per unit per day, and the discount rate on tied-up capital.
    storage_cost_per_unit_day: float = 0.06
    capital_cost_annual_rate: float = 0.09

    # Starting trust in each signal agent. The synthesizer re-weights from here.
    signal_weights: dict[SignalKind, float] = field(
        default_factory=lambda: {
            SignalKind.CULTURAL: 1.0,
            SignalKind.WEATHER: 0.9,
            SignalKind.SOCIAL: 0.7,
            SignalKind.MACRO: 1.1,
            SignalKind.LOCAL_EVENTS: 0.8,
            SignalKind.SEASONALITY: 1.3,
        }
    )


SETTINGS = Settings()
