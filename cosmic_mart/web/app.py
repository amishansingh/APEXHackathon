"""Dashboard over the agent network, streaming each agent's contribution live."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, StreamingResponse

from ..config import SETTINGS
from ..data import MARKETS, SKUS, all_skus
from ..llm import Reasoner
from ..orchestrator import Orchestrator

app = FastAPI(title="Cosmic Mart Demand Forecasting")
STATIC = Path(__file__).parent / "static"


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/api/catalogue")
async def catalogue() -> dict:
    return {
        "markets": [m.model_dump() for m in MARKETS],
        "skus": [s.model_dump() for s in SKUS],
        "model": SETTINGS.model,
        "offline": SETTINGS.offline,
        "weights": {
            "hist_branch": SETTINGS.hist_branch_weight,
            "sig_branch": SETTINGS.sig_branch_weight,
            "earth_data": SETTINGS.earth_data_weight,
            "regional_data": SETTINGS.regional_data_weight,
        },
        "worker_count": SETTINGS.worker_count,
    }


@app.get("/api/run")
async def run_stream(limit: int = 6, offline: bool = False) -> StreamingResponse:
    """Server-sent events: one message per agent milestone, then the full run."""
    queue: asyncio.Queue[str | None] = asyncio.Queue()

    async def on_progress(event: str, data: dict) -> None:
        await queue.put(json.dumps({"event": event, "data": data}))

    orchestrator = Orchestrator(
        reasoner=Reasoner(offline=offline or SETTINGS.offline), on_progress=on_progress
    )
    catalogue_slice = all_skus()[:limit]

    async def drive() -> None:
        try:
            result = await orchestrator.run(catalogue_slice)
            payload = {
                "event": "result",
                "data": {
                    "run": json.loads(result.model_dump_json()),
                    "briefing": orchestrator.gate.briefing(result.human_decisions),
                    "llm_calls": orchestrator.reasoner.call_count,
                },
            }
            await queue.put(json.dumps(payload))
        except Exception as exc:  # surface failures to the browser rather than hanging
            await queue.put(json.dumps({"event": "error", "data": {"message": str(exc)}}))
        finally:
            await queue.put(None)

    async def stream():
        task = asyncio.create_task(drive())
        try:
            while True:
                message = await queue.get()
                if message is None:
                    break
                yield f"data: {message}\n\n"
        finally:
            task.cancel()

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
