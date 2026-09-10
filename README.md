# Cosmic Mart — Demand Forecasting Pipeline

A multi-agent agentic system that generates per-item inventory order recommendations for the
North American market. A historical-analysis branch and a live-signals branch run in parallel
on a daily schedule and are merged in a weighted demand synthesizer; **every** recommendation
is reviewed by a human before execution. When historical baselines and live signals disagree,
the forecast range widens and both views are surfaced to the reviewer — conflict is preserved,
not averaged away.

Initial deployment covers North America only (US, Canada, Mexico, and Other North America).
Other regions follow in later rollout phases once North American operation is validated.

Built on the Anthropic Python SDK with `claude-opus-5`.

## The pipeline

```
Current-inventory database ──► SKU catalogue (item id + item name)
       │
Trigger (daily schedule — the only trigger)
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
weighted baseline (Earth 0.9, analogues 0.1). The signals branch pulls the last 24 hours
across three live feeds and maps detected signals to specific items. Both branches run
concurrently under `asyncio.gather`; the synthesizer waits for both, then blends them
0.7 / 0.3 per item.

> **Cadence note.** The architecture spec describes the signals branch as an always-on process
> refreshing every 15–60 minutes, decoupled from the daily trigger. As built, it runs **once
> per triggered run** — it pulls a fresh 24-hour window at synthesis time rather than
> maintaining a standing report between runs. Since the synthesizer only runs daily, the two
> designs see the same news; what a standing report would add is resilience if a feed is down
> at trigger time, and the ability to react off-schedule. That second half would also need a
> trigger that fires on something other than the clock, which this system deliberately does
> not have.

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

Every agent that reasons with Claude carries a deterministic fallback, so `--offline`
exercises the complete graph — both branches, the map-reduce, conflict widening, the human
gate — for free. It is also what the tests run against.

To use Claude, set a key and drop the flag:

```bash
cp .env.example .env      # then fill in ANTHROPIC_API_KEY
python -m cosmic_mart.cli run
```

See [Turning it on](#turning-it-on) for what changes and what happens without a key.

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
the full North American SKU catalogue. The synthesizer waits for both to complete. **All runs
are schedule-driven — there is no anomaly-event trigger.** `TriggerContext.reason` is a
single-member `Literal`, so adding one would be a deliberate type change rather than a new
string appearing at a call site.

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

**Signal Processing Agent.** Pulls the last 24 hours across three feeds (new drops + promos,
large events, news), deduplicates across streams, and scores signal strength per item.

It takes the **SKU catalogue as an input, retrieved from the current-inventory database**
(`adapters/inventory_db.py`). Each inventory row carries an `item_id` (item identification
number) and an `item_name`, and those are the fields the agent matches signals against — so
signals are scored against inventory actually carried, not in the abstract. Call
`run()` with no argument and the agent reads the catalogue itself; the orchestrator passes
one in only to avoid reading the same rows twice.

**Signal Report Agent.** Maps processed signals to specific items, producing a net direction,
a conflict flag, and a one-sentence rationale naming the drivers on each side. It records both
views rather than resolving them — the synthesizer receives the full tension.

Two conflict fields exist on `SignalItem` and they mean different things:

| Field | Set by | Meaning |
|---|---|---|
| `opposes_net_pull` | Signal Report | This signal pulls against the item's *net signal direction* — tension among the signals |
| `conflict_with_baseline` | Demand Synthesizer | This signal contradicts the *historical baseline* — the §7.2 contract field |

They were previously one field carrying both meanings. Only the synthesizer holds the
baseline, so only the synthesizer can honestly set the second.

**Demand Synthesizer.** The core decision agent. Blends the historical baseline (0.7) with
the signal report (0.3) per item. When the two disagree it does *not* average: it anchors on
the historical baseline and widens the forecast range to cover both scenarios, flagging the
divergence for review.

An item is in conflict when **any** of these hold:

1. The signals disagree among themselves (`has_conflict` from the report agent).
2. The net signal direction and the implied move are incoherent — signals say "up" but the
   implied forecast lands below baseline, or vice versa.
3. Divergence exceeds `divergence_std_threshold` (2σ by default, per §7.4).

**Signal strength alone is not conflict.** A strong signal that agrees with the baseline is a
confident forecast, not a contested one. An earlier version treated any move >25% off baseline
as divergence, which made almost every item conflict once the feeds produced coherent
directions — every recommendation came back `hold` with a divergence flag.

**Order Recommendation.** Packages the synthesizer output into an executable order —
reorder, rebalance, or hold — with quantity, supplier, warehouse routing, confidence, and
forecast range.

**Human in the Loop.** Final reviewer for **every** recommendation, without exception. Sees
the full synthesizer context including any conflict summary and widened range, and chooses
approve, modify, reject, or escalate. The system assists but never executes autonomously.

There is no autonomous path around the gate. `HumanGate.review()` produces exactly one
decision per recommendation and raises if it ever produces fewer, so a future change that
filtered the loop would fail the run rather than quietly execute something no human saw.
Approval is a review *outcome*, not a bypass — a clean recommendation is still reviewed.

## Where Claude is used

Four agents reason with Claude. The rest are arithmetic and stay that way on purpose — a
weighted mean or a threshold check should not vary run to run.

| Agent | Claude? | What it decides |
|---|---|---|
| Historical Manager | no | Sharding — round-robin split |
| Historical Worker | **yes** | The YoY annotation layer over the raw sales figures |
| Merge and Weight | no | `earth × 0.9 + regional × 0.1` |
| Signal Processing | **yes** | Each headline's direction and strength *for this item* |
| Signal Report | **yes** | Net direction, whether signals genuinely conflict, the rationale |
| Demand Synthesizer | **yes** | The reviewer-facing reasoning and conflict summary |
| Order Recommendation | no | Action, quantity, supplier, warehouse routing |
| Human in the Loop | no | Threshold routing — modelling a human's decision would defeat the point |

**The synthesizer's arithmetic is never modelled.** The blend, the widening and the divergence
score are computed in code and handed to Claude as facts to explain, not values to choose. No
model output is ever multiplied into the forecast at that stage.

**But a live run is not numerically identical to `--offline`.** Claude supplies *inputs* to
that arithmetic upstream — the YoY multipliers from the worker, and signal direction and
strength from the signals branch — and those legitimately move the result. On seed 42,
GAD-1001 comes out at a 258-unit reorder offline and 287 live, because Claude read the YoY
annotation layer differently from the deterministic heuristic.

What *is* guaranteed: `--offline` is reproducible run to run, so tests and demos are stable,
and a live run degrades to exactly those offline values if the API is unreachable.

Every call goes through `Reasoner.think`, which requires the caller to supply a deterministic
fallback of the same Pydantic type. So there are exactly two outcomes: Claude answers, or the
fallback is used. There is no third path where an agent has no answer.

### Turning it on

Drop a key into `.env` and remove `--offline`:

```bash
ANTHROPIC_API_KEY=sk-ant-...
```

Nothing else changes. Until then — no key, no network, a bad key, a rate limit, a refusal, or
a connection error — every agent uses its fallback and the pipeline completes normally, with
one warning logged. Credential resolution is the SDK's own (`ANTHROPIC_API_KEY`,
`ANTHROPIC_AUTH_TOKEN`, an `ant auth login` profile), so an unset key does not necessarily
mean no credentials. The CLI prints `LLM calls` and `deterministic fallbacks` after each run,
which is the quickest way to confirm the key is live.

Behind a proxy or course-issued gateway, set `ANTHROPIC_BASE_URL` in `.env` too — the SDK
picks it up, no code change needed. Reasoning effort is `COSMIC_MART_EFFORT` (default
`medium`).

## Calibration

Settings in `config.py`, tuned so the pipeline behaves sensibly:

| Setting | Value | Why it matters |
|---|---|---|
| `hist_branch_weight` / `sig_branch_weight` | `0.7` / `0.3` | The blend between the daily anchor and live signals. |
| `earth_data_weight` / `regional_data_weight` | `0.9` / `0.1` | Within the merge step. New expansions with thin Earth history may raise the analogue weight. |
| `escalation_value_threshold_usd` | `50_000` | Reorder value past this is flagged high-value. |
| `escalation_confidence_floor` | `0.45` | A forecast less certain than this is flagged low-confidence. |
| `divergence_std_threshold` | `2.0` | Divergence past this many standard deviations counts as conflict and flags for review. |
| `sparse_earth_threshold` | `50.0` | Below this Earth baseline an item is flagged data-sparse, costing confidence. |
| `worker_count` | `3` | Historical Manager shard count; scale to catalogue size and SLA. Env: `COSMIC_MART_WORKERS`. |
| `llm_effort` | `medium` | Reasoning effort per Claude call. Env: `COSMIC_MART_EFFORT`. |

Escalation flags route the reviewer's decision — they do **not** gate whether a human sees the
recommendation. Every recommendation is reviewed regardless; the flags decide whether the
outcome is approve, modify, or escalate.

Two constants in `demand_synthesizer.py` set how readily conflict is declared, and they are
calibrated against each other:

| Constant | Value | Why |
|---|---|---|
| `_SIGNAL_SWING` | `0.38` | Fraction of baseline a saturated net signal moves the implied forecast. |
| `_HIST_VARIABILITY` | `0.20` | Assumed historical variability, the denominator of the divergence score. |

At these values a fully saturated signal lands just under the 2σ threshold, so agreement —
however strong — reads as agreement. Raising `_SIGNAL_SWING` above roughly `0.40` makes every
strong signal a conflict; the pipeline then returns `hold` for nearly everything.

## Swapping in real data

The data sources sit behind the `InventorySource`, `EarthSalesSource`, `RegionalDataSource`,
and `SignalsFeedSource` protocols in `adapters/base.py`. The default providers supply
deterministic synthetic data seeded from `COSMIC_MART_SEED`. To go live, implement `observe()`
against a real API and inject it into the worker or signal-processing agent:

```python
from cosmic_mart.models import SKU

class RealEarthSales:
    async def observe(self, sku: SKU) -> dict:
        return await my_sales_api.history(sku.id)
```

The inventory database is the one source with a wider surface, because it supplies the
catalogue rather than a per-item payload — three methods instead of one:

```python
from cosmic_mart.models import SKU, InventoryRecord

class RealInventoryDB:
    async def records(self) -> list[InventoryRecord]:
        rows = await my_warehouse_db.fetch("select * from current_inventory")
        return [
            InventoryRecord(
                item_id=r["sku_id"],        # item identification number
                item_name=r["description"],  # item name
                category=r["category"],
                sub_market=r["market"],
                warehouse=r["dc"],
                on_hand_units=r["on_hand"],
                inbound_units=r["inbound"],
            )
            for r in rows
        ]

    async def catalogue(self) -> list[SKU]: ...    # distinct items carried
    async def item_index(self) -> dict[str, str]:  # {item_id: item_name}
        return {r.item_id: r.item_name for r in await self.records()}
```

Inject it with `Orchestrator(...).inventory = RealInventoryDB()`, or pass it to
`SignalProcessingAgent(feed, inventory=...)` directly.

No agent code changes — agents consume the payload, not the source.

## Tests

```bash
python -m pytest
```

Twenty tests. The originals cover manager sharding coverage, worker per-item context, merge
weighting math, sparse-data flagging, signal conflict detection, forecast-range widening under
conflict, clean blends without widening, the human gate approving clean recommendations, an
end-to-end offline pass, and offline determinism.

The rest pin the behaviour this repo is specified on:

- **Trigger** — `reason` is `daily_schedule`, and constructing an anomaly trigger raises.
- **Human review** — one decision per recommendation, ids matching, every run.
- **Inventory database** — every row exposes `item_id` and `item_name`; the Signal Processing
  Agent retrieves the catalogue from it when called with no argument.
- **Signal coherence** — a headline's direction follows from what it says, so a supply
  disruption lowers demand and a flash sale raises it.
- **LLM wiring** — all four reasoning agents hold the shared reasoner; missing credentials and
  a mid-run API failure both degrade to fallbacks and still complete the run.

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
    base.py             Inventory / EarthSales / RegionalData / SignalsFeed protocols
    inventory_db.py     current-inventory database — source of the SKU catalogue (mock)
    earth_sales.py      4 yr Earth sales provider (mock)
    regional_data.py    25 yr regional analogue provider (mock)
    signals_feed.py     live signal feed provider (mock)
  agents/
    historical_manager.py   shards the catalogue (map)
    historical_worker.py    per-item demand context per shard
    merge_and_weight.py     weighted baseline (reduce)
    signal_processing.py    24h signal pull, scoped by the inventory catalogue
    signal_report.py        maps signals to items, preserves conflict
    demand_synthesizer.py   blends 0.7 / 0.3, widens on conflict
    order_recommendation.py packages executable orders
    human_gate.py           approve / modify / reject / escalate
  web/
    app.py              FastAPI + SSE endpoint
    static/index.html   single-file dashboard (no build step)
tests/
  test_pipeline.py      the twenty tests above
```
