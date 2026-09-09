# Cosmic Mart — Multi-Agent Supply Chain Architecture

Cosmic Mart operates across 10 Earth markets and carries a pre-tax loss of $7.84B, a
significant share of it from inventory misalignment: overstocking low-demand markets while
understocking high-demand ones. This repository implements the agent network that watches
the world for demand-shifting events, scopes which products they touch, forecasts demand per
SKU per market, prices the daily bleed on overstocked inventory, and weighs every proposed
correction against both financial benefit and carbon cost before putting a recommendation in
front of a human.

Built on the Anthropic Python SDK with `claude-opus-5`.

## The pipeline

```
5 world monitors (parallel)
  holiday calendar · weather watch · social media · economy tracker · local news
                    │  TriggerSignal per market
                    ▼
          Item Scope Agent
          (maps each trigger to affected SKU categories)
                    │  ItemSynthesizerOutput per trigger
          ┌─────────┴─────────┐
          ▼                   ▼
  3 history agents      3 stock agents        (parallel within each group)
  Year-over-Year Sales  Real-time Stock
  Seasonal Peaks        Inbound Shipments
  Supplier Lead Times   Sell-through Velocity
          └─────────┬─────────┘
                    ▼
          Demand Synthesizer
          (probabilistic range; conflicts named, not averaged)
                    │
          ┌─────────┴─────────┐
          ▼                   ▼
  Financial Agent      Sustainability Agent   (parallel)
  (net dollar benefit) (carbon score 0–100)
          └─────────┬─────────┘
                    ▼
          Tradeoff Agent
          net = financial benefit − carbon penalty
          ┌─────────┼─────────┐
       approve     flag     block ──┐
          └─────────┴──┐            │ feedback loop
                       ▼            ▼
              Human-in-the-loop   Overstock agent
              CFO / CSO           (suppresses re-proposal)
```

Every stage shown side by side runs concurrently. Block verdicts never reach a human — they
are logged back to the overstock agent, which suppresses the same proposal on later runs.

## Quick start

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows;  source .venv/bin/activate on Unix
pip install -r requirements.txt
pip install -e .
```

Run the whole network with no API key and no network access:

```bash
python -m cosmic_mart.cli run --offline
```

Every agent has a deterministic heuristic that stands in for its Claude call, so `--offline`
exercises the complete graph — routing, the feedback loop, the credit bank — for free. It is
also what the tests run against.

To use Claude, set a key and drop the flag:

```bash
cp .env.example .env      # then fill in ANTHROPIC_API_KEY
python -m cosmic_mart.cli run
```

Behind a proxy or course-issued gateway, also set `ANTHROPIC_BASE_URL` in `.env` — the SDK
picks it up automatically, no code change needed.

Other commands:

```bash
python -m cosmic_mart.cli markets              # the 10 markets and the SKU catalogue
python -m cosmic_mart.cli run --market IN      # restrict to one market
python -m cosmic_mart.cli run --sku GAD-1001   # restrict to one SKU
python -m cosmic_mart.cli run --limit 4        # process fewer SKU/market pairs
python -m cosmic_mart.cli run --verbose        # stream every agent event
python -m cosmic_mart.cli run --save run.json  # persist the full typed run
python -m cosmic_mart.cli serve                # dashboard on http://127.0.0.1:8000
```

The dashboard streams every pipeline stage live over server-sent events. Each step in the
workflow is clickable and opens a drawer showing that agent's full output. When the run
completes, the page scrolls to the recommended maneuvers and explains which items were
filtered at each transition and why.

## The agents

**World monitors.** Five specialists in `agents/signals.py`, each scoped to one domain.
Cadences differ — social media is real-time, weather hourly, holiday calendar and economy
tracker daily, local news event-driven. Each fires a `TriggerSignal` carrying the event
type, estimated demand impact, and affected SKU categories.

**Item Scope Agent.** Maps each trigger's affected categories to the actual SKU catalogue,
producing one `ItemSynthesizerOutput` per trigger listing the specific (SKU, market) pairs
that flow into the rest of the pipeline.

**History agents (P1).** Three specialists run in parallel per scoped target: Year-over-Year
Sales (trend, sell-through rate), Seasonal Peaks (uplift multiplier, onset days), and
Supplier Lead Times (order trigger days, variability). Their outputs feed the demand
synthesizer.

**Stock agents (P2).** Three specialists run in parallel per scoped target: Real-time Stock
(days of supply, hard override flag), Inbound Shipments (on-time status, adjusted days of
supply), and Sell-through Velocity (divergence ratio, projected stockout). P2 can hard-
override the demand forecast when current stock conditions dominate.

**Demand Synthesizer.** Reconciles history and stock signals into one probabilistic range,
never a point estimate. Conflicts are not averaged away: when two signals pull in opposite
directions the range widens and both agents are named. `SignalAccuracyLedger` re-weights
each signal from its realized accuracy over time.

**Overstock loss agent.** A continuous cost clock computing three loss components per unit
per day — capital tied up, storage fees, and depreciation. Depreciation dominates for
gadgets, which are 77% of revenue and go stale as new models release. Excess is measured
against the *high* end of the forecast, so stock is only called overstock when even good
demand leaves it unsold.

**Financial agent.** Nets holding-loss savings against execution cost, and keeps a rolling
impact log that auto-assembles the CFO's weekly report.

**Sustainability agent.** Scores each action 0–100 on carbon burden from a tonne-km freight
model, and runs a `CarbonCreditBank` that logs wins as credits to offset later quarters.

**Tradeoff agent.** The convergence point. `net = financial benefit − (carbon score ×
carbon price)`, routed to approve, flag, or block. Flags surface both raw scores rather than
a reconciled verdict, so the reviewer sees the tension.

**Human gate.** CFO Rowan Ortega takes financial escalations, CSO Finley Martin takes
sustainability-contested ones.

## Calibration

Four settings in `config.py` decide whether the system behaves sensibly, and all four were
tuned against real runs:

| Setting | Value | Why it matters |
|---|---|---|
| `carbon_price_usd_per_point` | `300.0` | Too low and carbon can never change a verdict, making the sustainability agent decorative. Too high and everything blocks. |
| `escalation_confidence_floor` | `0.40` | Set near the typical forecast confidence and every forecast escalates, defeating the gate. |
| `approve_confidence_floor` | `0.45` | Gates straight approvals on the forecast actually being solid. |
| `approve_threshold_usd` | `15_000.0` | Calibrated against the conservative benefits the financial agent returns; set higher and nothing clears a straight approval. |

`carbon_price_usd_per_point` is the main policy lever: raise it to make Cosmic Mart
greener, lower it to prioritise cash recovery.

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

Ten tests covering signal validity, an end-to-end offline pass, offline determinism, the
three-component cost clock, gadgets depreciating faster than home goods, block routing on a
negative net score, the block feedback loop, credit bank overdraft protection, ledger
re-weighting, and escalation on conflicting signals.

## Layout

```
cosmic_mart/
  models.py             typed contracts between every agent
  config.py             settings and calibration
  data.py               10 markets, SKU catalogue
  llm.py                Claude access; every agent asks for a Pydantic type
  orchestrator.py       the six-step pipeline graph
  cli.py                terminal interface (run, markets, serve)
  adapters/             SignalSource / InventorySource protocols + mocks
  agents/
    signals.py          5 world monitors (P3 triggers)
    item_synthesizer.py maps triggers → affected SKUs
    p1/                 3 history agents (YoY, seasonal peaks, lead times)
    p2/                 3 stock agents (realtime, inbound, sell-through)
    synthesizer.py      demand synthesizer
    overstock.py        loss clock + block-feedback memory
    financial.py        net benefit + CFO report
    sustainability.py   carbon score + credit bank
    tradeoff.py         verdict routing
    human_gate.py       CFO / CSO gate queue
    proposals.py        overstock → proposed actions
  web/
    app.py              FastAPI + SSE endpoint
    static/index.html   single-file dashboard (no build step)
```
