"""Terminal interface for the agent network."""

from __future__ import annotations

import asyncio

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .config import SETTINGS
from .data import MARKETS, SKUS
from .llm import Reasoner
from .models import SKU, PipelineRun
from .orchestrator import Orchestrator

app = typer.Typer(help="Cosmic Mart demand forecasting pipeline.", no_args_is_help=True)
console = Console()

_ACTION_STYLE = {"reorder": "green", "rebalance": "cyan", "hold": "dim"}
_DECISION_STYLE = {
    "approve": "green",
    "modify": "yellow",
    "escalate": "magenta",
    "reject": "red",
}


async def _select(orchestrator: Orchestrator, limit: int, sku: str | None) -> list[SKU]:
    """The catalogue comes from the current-inventory database, then is filtered."""
    catalogue = await orchestrator.inventory.catalogue()
    if sku:
        catalogue = [s for s in catalogue if s.id == sku.upper()]
    if not catalogue:
        raise typer.BadParameter("No SKUs match those filters.")
    return catalogue[:limit]


@app.command("markets")
def list_markets() -> None:
    """List the North American sub-markets and the SKU catalogue."""
    table = Table(title="North American Markets", header_style="bold cyan")
    table.add_column("Code")
    table.add_column("Name")
    table.add_column("Region")
    for m in MARKETS:
        table.add_row(m.code, m.name, m.region)
    console.print(table)

    catalogue = Table(title="SKUs", header_style="bold cyan")
    catalogue.add_column("ID")
    catalogue.add_column("Name")
    catalogue.add_column("Category")
    catalogue.add_column("Cost", justify="right")
    catalogue.add_column("Price", justify="right")
    for s in SKUS:
        catalogue.add_row(
            s.id, s.name, s.category, f"${s.unit_cost_usd:,.0f}", f"${s.unit_price_usd:,.0f}"
        )
    console.print(catalogue)


@app.command("run")
def run(
    limit: int = typer.Option(6, help="How many SKUs to process."),
    sku: str = typer.Option(None, help="Restrict to one SKU id, e.g. GAD-1001."),
    offline: bool = typer.Option(
        False, "--offline", help="Run deterministically with no API calls."
    ),
    verbose: bool = typer.Option(False, "--verbose", help="Stream every agent event."),
    save: str = typer.Option(None, help="Write the full run to this JSON path."),
) -> None:
    """Run one full pass of the demand forecasting pipeline."""
    reasoner = Reasoner(offline=offline or SETTINGS.offline)

    async def progress(event: str, data: dict) -> None:
        if verbose:
            console.print(f"[dim]{event}[/dim] {data}")

    orchestrator = Orchestrator(reasoner=reasoner, on_progress=progress if verbose else None)

    async def drive() -> tuple[list[SKU], PipelineRun]:
        catalogue = await _select(orchestrator, limit, sku)
        console.print(
            Panel(
                f"Processing {len(catalogue)} item(s) from the current-inventory "
                f"database across a historical branch ({SETTINGS.worker_count} "
                f"workers) and a signals branch.\n"
                f"Trigger: [bold]daily schedule[/bold]   Mode: [bold]"
                f"{'offline' if reasoner.offline else reasoner.model}[/bold]",
                title="Cosmic Mart",
                border_style="blue",
            )
        )
        return catalogue, await orchestrator.run(catalogue)

    with console.status("Agents working..."):
        _catalogue, result = asyncio.run(drive())

    _render(result, orchestrator)

    if save:
        with open(save, "w", encoding="utf-8") as handle:
            handle.write(result.model_dump_json(indent=2))
        console.print(f"[dim]Full run written to {save}[/dim]")


def _render(result: PipelineRun, orchestrator: Orchestrator) -> None:
    baseline_table = Table(title="Merged baselines (Earth 0.9 · analogues 0.1)", header_style="bold cyan")
    baseline_table.add_column("SKU")
    baseline_table.add_column("Earth", justify="right")
    baseline_table.add_column("Regional", justify="right")
    baseline_table.add_column("Weighted", justify="right")
    baseline_table.add_column("Flags")
    for b in result.merged_baselines:
        flags = ", ".join(b.data_quality_flags) or "-"
        baseline_table.add_row(
            b.sku.id,
            f"{b.earth_baseline:,.0f}",
            f"{b.regional_baseline:,.0f}",
            f"{b.weighted_baseline:,.0f}",
            flags,
        )
    console.print(baseline_table)

    rec_table = Table(title="Order recommendations", header_style="bold cyan")
    rec_table.add_column("SKU")
    rec_table.add_column("Action")
    rec_table.add_column("Qty", justify="right")
    rec_table.add_column("Range", justify="right")
    rec_table.add_column("Conf", justify="right")
    rec_table.add_column("Escalation")
    for r in result.order_recommendations:
        style = _ACTION_STYLE.get(r.action, "white")
        fr = r.forecast_range
        widen = " [yellow]±[/yellow]" if fr.widened else ""
        flags = ", ".join(f.flag_type for f in r.escalation_flags) or "-"
        rec_table.add_row(
            r.sku.id,
            f"[{style}]{r.action}[/{style}]",
            f"{r.quantity:,}",
            f"{fr.units_low:,}-{fr.units_high:,}{widen}",
            f"{r.confidence:.0%}",
            flags,
        )
    console.print(rec_table)

    decision_table = Table(title="Human in the loop", header_style="bold cyan")
    decision_table.add_column("SKU")
    decision_table.add_column("Decision")
    decision_table.add_column("Notes")
    for d in result.human_decisions:
        style = _DECISION_STYLE.get(d.action, "white")
        decision_table.add_row(
            d.sku_id, f"[{style}]{d.action}[/{style}]", (d.modifier_notes or "")[:70]
        )
    console.print(decision_table)

    console.print(
        Panel(
            f"{orchestrator.gate.briefing(result.human_decisions)}\n"
            f"Every recommendation reviewed — no autonomous execution.\n"
            f"LLM calls: {orchestrator.reasoner.call_count}   "
            f"deterministic fallbacks: {orchestrator.reasoner.fallback_count}",
            title="Summary",
            border_style="magenta",
        )
    )


@app.command("serve")
def serve(
    host: str = typer.Option("127.0.0.1"),
    port: int = typer.Option(8000),
) -> None:
    """Start the web dashboard."""
    import uvicorn

    uvicorn.run("cosmic_mart.web.app:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    app()
