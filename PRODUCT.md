# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

The primary user is a **hackathon judge or demo-audience member** seeing Cosmic Mart for the
first time, in a short live demo, with no supply-chain background and no knowledge of the
agent architecture underneath. They are deciding whether the system does something real and
worthwhile, in minutes, while someone talks over the screen.

This audience sets the bar for the interface: every label must be legible cold. Someone who
has never heard the words "SKU", "sell-through", or "overstock" must still be able to follow
what the system spotted, what it concluded, and what it wants a human to do about it.

The human reviewer at the end of the pipeline is a role *inside* the product's decision flow,
not the person the dashboard is designed for.

## Product Purpose

Cosmic Mart operates across 10 Earth markets and carries a **$7.84B pre-tax loss**, a
significant share of it from inventory misalignment: overstocking low-demand markets while
understocking high-demand ones. This product is the agent network that closes that gap for
North America first. Each day it reads what is currently in stock, works out what four years
of sales history says demand should be, watches the outside world for events that change what
customers will buy, works out which products those events touch, and blends the two into a
per-item order recommendation — which a human reviews before anything is executed.

Success is a viewer who has never worked in supply chain watching one run and being able to
say, unprompted, what the system found and what it recommends.

## Positioning

The system does not produce a point forecast, and it does not hand a number to a human without
showing how it was reached. Two things a neighbouring inventory tool could not truthfully copy:

- **Conflict is preserved, not averaged.** When one signal says demand is rising and another
  says buying power is falling, the forecast range widens and both sources are named. The
  tension is surfaced to the reviewer rather than reconciled away into a single confident
  number. Strength is not treated as conflict: a strong signal that *agrees* with the
  historical baseline is a confident forecast, not a contested one.
- **The human gate is total, not a threshold.** Every recommendation is reviewed before
  execution — not just the expensive or uncertain ones. Approval is a review outcome, not a
  bypass, and the code raises rather than letting a recommendation reach execution unreviewed.

## Operating Context

The system runs as a pipeline on a **fixed daily schedule**. All runs are schedule-driven;
there is no anomaly-event trigger:

1. The daily trigger reads the SKU catalogue from the current-inventory database and fires
   both branches in parallel.
2. The historical branch shards the catalogue across parallel workers, each contributing what
   four years of North American sales and the YoY annotation layer say, then reduces them to
   one weighted baseline (Earth 0.9, analogues 0.1).
3. The signals branch pulls the last 24 hours across three live feeds and maps detected
   signals to specific items, scoped by item identification number and item name.
4. The Demand Synthesizer blends the two (0.7 / 0.3). Where they disagree it widens the
   forecast range rather than averaging, and names both sides.
5. Every recommendation is packaged as an executable order and passed to a human reviewer,
   who approves, modifies, rejects, or escalates. Nothing executes autonomously.

It is exercised two ways: a terminal CLI, and a browser dashboard that streams every stage
live over server-sent events. The demo is the browser dashboard. An **offline mode** runs the
entire graph on deterministic heuristics with no API key and no network, and is what both the
tests and most demos run against.

## Capabilities and Constraints

- Python 3.11+, FastAPI, Pydantic v2 typed contracts between every agent, Anthropic Python
  SDK targeting `claude-opus-5`.
- **The dashboard is a single hand-written static HTML file** served by FastAPI. This is a
  confirmed constraint: no build step, no framework, no `node_modules`, no CDN dependencies.
  Future UI work must stay inside one self-contained file that runs with nothing but the
  Python server. Everything the interface does — layout, state, live streaming, rendering —
  is plain HTML, CSS, and vanilla JavaScript.
- All data sources sit behind the `InventorySource` / `EarthSalesSource` /
  `RegionalDataSource` / `SignalsFeedSource` protocols in `adapters/base.py`, so real APIs can
  replace mocks without touching agent code. The SKU catalogue comes from the
  current-inventory database, which exposes an item identification number and item name per
  row.
- Four agents reason with Claude (historical worker, signal processing, signal report,
  synthesizer narrative); the rest are deterministic arithmetic by design. Every Claude call
  carries a deterministic fallback of the same type, so a missing key, a rate limit, or a
  connection error degrades rather than fails.
- Mock data is deterministic, seeded from `COSMIC_MART_SEED`, so a demo run is reproducible.
  The forecast numbers are computed, never modelled — `--offline` and a live run are
  numerically identical on the same seed.
- Secrets (`ANTHROPIC_API_KEY`, `ANTHROPIC_BASE_URL`) live only in a gitignored `.env` and
  must never appear in a tracked file.
- The v1 scope is North America — four sub-markets (US, Canada, Mexico, Other North America)
  and 6 products; the agent pipeline is as described above. These were **not** declared
  binding, so future work may extend them — but it should not do so casually, and never merely
  to fill out a layout.

## Evidence on Hand

- **Binding, confirmed figures — never restate loosely, embellish, or invent around these:**
  the **$7.84B pre-tax loss**, and gadgets being **77% of revenue**.
- Real, inspectable artefacts in the repository: the market and product catalogue
  (`data.py`), the current-inventory database (`adapters/inventory_db.py`), calibration
  settings with recorded reasoning (`config.py`), and a twenty-test suite. A full run can be
  captured to JSON at any time with `cli run --save run.json`.
- **Absent — must not be fabricated:** there are no customers, testimonials, case studies,
  press mentions, benchmarks, pricing, adoption numbers, or deployment claims. Cosmic Mart is
  a scenario. No surface may imply the system is running in production anywhere.

## Product Principles

1. **A stranger must be able to follow it.** The interface is judged by someone with no
   domain knowledge, watching once. Internal component vocabulary never reaches the screen.
2. **Show the reasoning, not just the answer.** The value is in watching a world event become
   a scoped product set, then a forecast, then a recommendation. A bare verdict wastes what
   the system actually does.
3. **Surface tension rather than resolving it.** Conflicting signals and a widened forecast
   range are features to display, not noise to smooth over.
4. **A recommendation always names its basis.** Every suggested action carries its forecast
   range, its confidence, the signals that moved it, and any conflict between them, so no one
   has to take it on trust.
5. **Constraints are the craft.** One static file, no build step, deterministic data. The
   work is making that feel considered, not apologising for it.

## Accessibility & Inclusion

No product-specific standard has been established. The demo context — a projected or shared
screen, viewed briefly, from a distance, possibly while someone is talking — makes legible
type sizes, strong contrast, and meaning that never rests on colour alone practical
requirements rather than compliance items.
