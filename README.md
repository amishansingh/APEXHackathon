# Cosmic Mart — Demand Forecasting Pipeline

A multi-agent agentic system that generates per-item inventory order recommendations for the
North American market. A daily historical-analysis branch and a continuously running signals
branch are merged in a weighted demand synthesizer; every recommendation is reviewed by a
human before execution. When historical baselines and live signals disagree, the forecast
range widens and both views are surfaced to the reviewer — conflict is preserved, not
averaged away.

Initial deployment covers North America only (US, Canada, Mexico, and Other North America).
Other regions follow in later rollout phases once North American operation is validated.

Built on the Anthropic Python SDK with `claude-opus-5`.

## The pipeline

```
Trigger (daily schedule)
       │  fires both branches in parallel
  ─────┴───────────────────────────────┐
  Historical Branch (weight 0.7)        Signals Branch (weight 0.3)
  ┌──────────────────────────────┐      ┌───────────────────────────┐
  │ Inputs:                       │      │ Inputs:                    │
  │  · 4 yr Earth Sales (0.9)     │      │  · New Drops + Promos       │
  │  · 25 yr Regional Data (0.1)  │      │  · Large Events             │
  │  · YoY Annotated Sales        │      │  · News Agent               │
  │                               │      │                             │
  │ Historical Manager            │      │ Signal Processing Agent     │
  │   → Worker 1..n (parallel)    │      │   → Signal Report Agent     │
  │   → Merge and Weight          │      └───────────────────────────┘
  └──────────────────────────────┘
                 │                                  │
                 └───────────────┬──────────────────┘
                                 ▼
                        Demand Synthesizer
                   (conflict → range widens, not averaged)
                                 │
                        Order Recommendation
                   (reorder · rebalance · hold)
                                 │
                        Human in the Loop
                   (approve · modify · reject · escalate)
```

The historical branch is a map-reduce: the manager shards the SKU catalogue across parallel
workers, each producing a per-item demand context, and Merge and Weight reduces them into one
weighted baseline (Earth 0.9, analogues 0.1). The signals branch runs continuously, pulling
the last 24 hours across three live feeds and mapping detected signals to specific items. The
synthesizer waits for both branches, then blends them 0.7 / 0.3 per item.

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
exercises the complete graph — both branches, the map-reduce, conflict widening, the human
gate — for free. It is also what the tests run against.

To use Claude, set a key and drop the flag:

```bash
cp .env.example .env      # then fill in ANTHROPIC_API_KEY
python -m cosmic_mart.cli run
```

Behind a proxy or course-issued gateway, also set `ANTHROPIC_BASE_URL` in `.env` — the SDK
picks it up automatically, no code change needed.

Other commands:

```bash
python -m cosmic_mart.cli markets              # sub-markets and the SKU catalogue
python -m cosmic_mart.cli run --sku GAD-1001   # restrict to one SKU
python -m cosmic_mart.cli run --limit 4        # process fewer SKUs
python -m cosmic_mart.cli run --verbose        # stream every agent event
python -m cosmic_mart.cli run --save run.json  # persist the full typed run
python -m cosmic_mart.cli serve                # dashboard on http://127.0.0.1:8000
```

The dashboard streams every pipeline stage live over server-sent events. Each stage in the
workflow is clickable and opens a drawer showing that agent's full output. When the run
completes, the page scrolls to the recommended orders, grouped by the reviewer's decision.

## The agents

**Trigger.** Fires on a fixed daily schedule, dispatching both branches in parallel against
the full North American SKU catalogue. The synthesizer waits for both to complete.

**Historical Manager.** Receives the trigger and shards the catalogue into `n` parallel work
units (configurable via `COSMIC_MART_WORKERS`). In a real deployment it tracks worker
completion, retries failed shards, and assembles the merge when all workers report back.

**Workers (parallel).** Each processes one shard: loads Earth and regional sales history,
applies the YoY annotation layer, and produces a per-item demand context. Independent — no
inter-worker communication. Total time is bounded by the slowest shard, not the full
catalogue.

**Merge and Weight.** Reduces all worker outputs into one weighted demand baseline per item:
`earth × 0.9 + regional × 0.1`. Flags items with sparse Earth data so the analogue weight
carries more of the forecast. This is the historical branch's final output.

**Signal Processing Agent.** Always-on. Pulls the last 24 hours across three feeds (new drops
+ promos, large events, news), deduplicates across streams, and scores signal strength per
SKU using the catalogue as the reference frame.

**Signal Report Agent.** Maps processed signals to specific items. When a signal contradicts
the net pull it records both views and flags the divergence rather than resolving it — the
synthesizer receives the full tension.

**Demand Synthesizer.** The core decision agent. Blends the historical baseline (0.7) with
the signal report (0.3) per item. When the two disagree it does *not* average: it anchors on
the historical baseline and widens the forecast range to cover both scenarios, flagging the
divergence for review.

**Order Recommendation.** Packages the synthesizer output into an executable order —
reorder, rebalance, or hold — with quantity, supplier, warehouse routing, confidence, and
forecast range.

**Human in the Loop.** Final reviewer for every recommendation. Sees the full synthesizer
context including any conflict summary and widened range, and chooses approve, modify, reject,
or escalate. The system assists but never executes autonomously.

## Calibration

Settings in `config.py`, tuned so the pipeline behaves sensibly:

| Setting | Value | Why it matters |
|---|---|---|
| `hist_branch_weight` / `sig_branch_weight` | `0.7` / `0.3` | The blend between the daily anchor and live signals. |
| `earth_data_weight` / `regional_data_weight` | `0.9` / `0.1` | Within the merge step. New expansions with thin Earth history may raise the analogue weight. |
| `escalation_value_threshold_usd` | `50_000` | Reorder value past this escalates to a human. |
| `escalation_confidence_floor` | `0.45` | A forecast less certain than this cannot proceed autonomously. |
| `divergence_std_threshold` | `2.0` | Divergence past this many standard deviations flags a conflict for review. |
| `worker_count` | `3` | Historical Manager shard count; scale to catalogue size and SLA. |

## Swapping in real data

The three feeds sit behind the `EarthSalesSource`, `RegionalDataSource`, and
`SignalsFeedSource` protocols in `adapters/base.py`. The default providers supply
deterministic synthetic data seeded from `COSMIC_MART_SEED`. To go live, implement `observe()`
against a real API and inject it into the worker or signal-processing agent:

```python
from cosmic_mart.models import SKU

class RealEarthSales:
    async def observe(self, sku: SKU) -> dict:
        return await my_sales_api.history(sku.id)
```

No agent code changes — agents consume the payload, not the source.

## Tests

```bash
python -m pytest
```

Ten tests covering manager sharding coverage, worker per-item context, merge weighting math,
sparse-data flagging, signal conflict detection, forecast-range widening under conflict, clean
blends without widening, the human gate approving clean recommendations, an end-to-end offline
pass, and offline determinism.

## Layout

```
cosmic_mart/
  models.py             typed contracts between every agent (§7.2 data contracts)
  config.py             settings and calibration (branch + data weights)
  data.py               North American sub-markets, SKU catalogue
  llm.py                Claude access; every agent asks for a Pydantic type
  orchestrator.py       the two-branch pipeline graph
  cli.py                terminal interface (run, markets, serve)
  adapters/
    base.py             EarthSales / RegionalData / SignalsFeed protocols
    earth_sales.py      4 yr Earth sales provider (mock)
    regional_data.py    25 yr regional analogue provider (mock)
    signals_feed.py     live signal feed provider (mock)
  agents/
    historical_manager.py   shards the catalogue (map)
    historical_worker.py    per-item demand context per shard
    merge_and_weight.py     weighted baseline (reduce)
    signal_processing.py    always-on 24h signal pull
    signal_report.py        maps signals to items, preserves conflict
    demand_synthesizer.py   blends 0.7 / 0.3, widens on conflict
    order_recommendation.py packages executable orders
    human_gate.py           approve / modify / reject / escalate
  web/
    app.py              FastAPI + SSE endpoint
    static/index.html   single-file dashboard (no build step)
```
