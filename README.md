# Cosmic Mart — Multi-Agent Supply Chain Architecture

Cosmic Mart operates across 10 Earth markets and carries a pre-tax loss of $7.84B, a
significant share of it from inventory misalignment: overstocking low-demand markets while
understocking high-demand ones. This repository implements the agent network that forecasts
demand per SKU per market, prices the daily bleed on overstocked inventory, and weighs every
proposed correction against both financial benefit and carbon cost before putting a
recommendation in front of a human.

Built on the Anthropic Python SDK with `claude-opus-5`.

## The workflow

```
Signal layer (6 specialists, parallel)
  cultural · weather · social · macro · local events · seasonality
                    │
        ┌───────────┴───────────┐
        ▼                       ▼
  Demand synthesizer      Overstock loss agent
  (probabilistic range)   (three-component cost clock)
        └───────────┬───────────┘
        ┌───────────┴───────────┐
        ▼                       ▼
  Sustainability agent    Financial report agent
  (carbon score 0–100)    (net dollar benefit)
        └───────────┬───────────┘
                    ▼
          Tradeoff decision agent
     net = financial benefit − carbon penalty
        ┌───────────┼───────────┐
     approve       flag       block ──┐
        └───────────┴──┐              │ feedback loop
                       ▼              ▼
              Human-in-the-loop   Overstock agent
              CFO / CSO           (suppresses re-proposal)
```

Every stage that the architecture shows side by side runs concurrently: the six signal
agents observe a target together, and sustainability and financial evaluate each action
together.

## Quick start

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows;  source .venv/bin/activate on Unix
pip install -e ".[dev]"
```

Run the whole network with no API key and no network access:

```bash
python -m cosmic_mart.cli run --limit 12 --offline
```

Every agent has a deterministic heuristic that stands in for its Claude call, so `--offline`
exercises the complete graph — routing, the feedback loop, the credit bank — for free. It is
also what the tests run against.

To use Claude, set a key and drop the flag:

```bash
cp .env.example .env      # then fill in ANTHROPIC_API_KEY
python -m cosmic_mart.cli run --limit 6
```

Other commands:

```bash
python -m cosmic_mart.cli markets              # the 10 markets and the SKU catalogue
python -m cosmic_mart.cli run --market IN      # one market
python -m cosmic_mart.cli run --sku GAD-1001   # one SKU
python -m cosmic_mart.cli run --verbose        # stream every agent event
python -m cosmic_mart.cli run --save run.json  # persist the full typed run
python -m cosmic_mart.cli serve                # dashboard on http://127.0.0.1:8000
```

The dashboard lights up each agent as it reports, streams milestones over server-sent
events, and renders the bleed list, the tradeoff table, and the human gate queue.

## The agents

**Signal layer.** Six specialists in `agents/signals.py`, each scoped to one domain and each
asked to judge only that domain. Cadences differ as the architecture specifies — social is
real-time, weather hourly, cultural daily, macro and seasonality weekly, local events
event-driven. The seasonality agent is the long memory that stops the social agent
mistaking a predictable seasonal peak for a viral moment.

**Demand synthesizer.** Reconciles all six into one probabilistic range, never a point
estimate. Conflicts are not averaged away: when weather says demand is rising while macro
says confidence is falling, the range widens and both agents are named. `SignalAccuracyLedger`
re-weights each signal from its realized accuracy, so the weights become a proprietary
Earth-market model over time.

**Overstock loss agent.** A continuous cost clock computing three loss components per unit
per day — capital tied up, storage fees, and depreciation. Depreciation dominates for
gadgets, which are 77% of revenue and go stale as new models release. Excess is measured
against the *high* end of the forecast, so stock is only called overstock when even good
demand leaves it unsold.

**Sustainability agent.** Scores each action 0–100 on carbon burden from a tonne-km freight
model, and runs a `CarbonCreditBank` that logs wins as credits to offset later quarters.

**Financial report agent.** Nets holding-loss savings against execution cost, and keeps a
rolling impact log that auto-assembles the CFO's weekly report.

**Tradeoff decision agent.** The convergence point. `net = financial benefit − (carbon score
× carbon price)`, routed to approve, flag, or block. Flags carry both raw scores rather than
a reconciled verdict, so the reviewer sees the tension.

**Human gate.** CFO Rowan Ortega takes financial escalations, CSO Finley Martin takes
sustainability-contested ones. Blocks never reach a human — they are logged straight back to
the overstock agent, which suppresses the same proposal on later runs.

## Calibration

Three settings in `config.py` decide whether the system behaves sensibly, and all three were
wrong in an obvious direction before being tuned against real runs:

| Setting | Value | Why it matters |
|---|---|---|
| `carbon_price_usd_per_point` | `300.0` | Too low and carbon can never change a verdict, making the sustainability agent decorative. Too high and everything blocks. |
| `escalation_confidence_floor` | `0.40` | Set near the typical forecast confidence and *every* forecast escalates, which defeats the point of a gate for edge cases. |
| `approve_confidence_floor` | `0.45` | Gates straight approvals on the forecast underneath actually being solid. |

`carbon_price_usd_per_point` is the main policy lever: raise it to make Cosmic Mart greener,
lower it to prioritise cash recovery.

## Swapping in real data

Everything behind the agents sits behind the `SignalSource` and `InventorySource` protocols
in `adapters/base.py`. `adapters/mock.py` supplies deterministic synthetic data seeded from
`COSMIC_MART_SEED`. To go live, implement `observe()` against a real API and register it:

```python
from cosmic_mart.adapters.base import SourceRegistry
from cosmic_mart.models import SignalKind

class RealWeatherSource:
    kind = SignalKind.WEATHER
    async def observe(self, target):
        return await my_weather_api.forecast(target.market.code)

registry.signals[SignalKind.WEATHER] = RealWeatherSource()
```

No agent code changes — agents consume the payload, not the source.

## Tests

```bash
python -m pytest
```

Ten tests covering signal validity, an end-to-end pass, offline determinism, the
three-component cost clock, gadgets depreciating faster than home goods, block routing on a
negative net score, the block feedback loop, credit bank overdraft protection, ledger
re-weighting, and escalation on conflicting signals.

## Layout

```
cosmic_mart/
  models.py         typed contracts between agents
  config.py         settings and calibration
  data.py           10 markets, SKU catalogue
  llm.py            Claude access; every agent asks for a Pydantic type
  orchestrator.py   the workflow graph
  cli.py            terminal interface
  adapters/         data-source protocols + mocks
  agents/           the nine agents and the human gate
  web/              FastAPI dashboard with SSE
```
