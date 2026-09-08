"""Terminal interface for the agent network."""

from __future__ import annotations

import asyncio
import json

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .config import SETTINGS
from .data import MARKETS, SKUS, all_pairs
from .llm import Reasoner
from .models import PipelineRun, SKUMarket, Verdict
from .orchestrator import Orchestrator

app = typer.Typer(help="Cosmic Mart multi-agent supply chain.", no_args_is_help=True)
console = Console()

_VERDICT_STYLE = {
    Verdict.APPROVE: "green",
    Verdict.FLAG: "yellow",
    Verdict.BLOCK: "red",
}


def _select(limit: int, market: str | None, sku: str | None) -> list[SKUMarket]:
    pairs = all_pairs()
    if market:
        pairs = [p for p in pairs if p.market.code == market.upper()]
    if sku:
        pairs = [p for p in pairs if p.sku.id == sku.upper()]
    if not pairs:
        raise typer.BadParameter("No SKU/market pairs match those filters.")
    return pairs[:limit]


@app.command("markets")
def list_markets() -> None:
    """List the 10 Earth markets and the SKU catalogue."""
    table = Table(title="Markets", header_style="bold cyan")
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
    limit: int = typer.Option(8, help="How many SKU/market pairs to process."),
    market: str = typer.Option(None, help="Restrict to one market code, e.g. IN."),
    sku: str = typer.Option(None, help="Restrict to one SKU id, e.g. GAD-1001."),
    offline: bool = typer.Option(
        False, "--offline", help="Run deterministically with no API calls."
    ),
    verbose: bool = typer.Option(False, "--verbose", help="Stream every agent event."),
    save: str = typer.Option(None, help="Write the full run to this JSON path."),
) -> None:
    """Run one full pass of the agent network."""
    targets = _select(limit, market, sku)
    reasoner = Reasoner(offline=offline or SETTINGS.offline)

    async def progress(event: str, data: dict) -> None:
        if verbose:
            console.print(f"[dim]{event}[/dim] {data}")

    orchestrator = Orchestrator(reasoner=reasoner, on_progress=progress if verbose else None)

    mode = "offline" if reasoner.offline else reasoner.model
    console.print(
        Panel(
            f"Processing {len(targets)} SKU/market pairs with {len(orchestrator.signal_agents)} "
            f"signal agents.\nMode: [bold]{mode}[/bold]",
            title="Cosmic Mart",
            border_style="blue",
        )
    )

    with console.status("Agents working..."):
        result = asyncio.run(orchestrator.run(targets))

    _render(result, orchestrator)

    if save:
        with open(save, "w", encoding="utf-8") as handle:
            handle.write(result.model_dump_json(indent=2))
        console.print(f"[dim]Full run written to {save}[/dim]")


def _render(result: PipelineRun, orchestrator: Orchestrator) -> None:
    demand_table = Table(title="Demand forecasts", header_style="bold cyan")
    demand_table.add_column("SKU @ Market")
    demand_table.add_column("Baseline", justify="right")
    demand_table.add_column("Range", justify="right")
    demand_table.add_column("Conf", justify="right")
    demand_table.add_column("Conflicts")
    for d in result.demand:
        conflicts = ", ".join(d.forecast.conflicting_signals) or "-"
        flag = " [yellow]escalate[/yellow]" if d.escalate_to_human else ""
        demand_table.add_row(
            d.target.key,
            f"{d.baseline_units:,}",
            f"{d.forecast.units_low:,}-{d.forecast.units_high:,}",
            f"{d.forecast.confidence:.0%}{flag}",
            conflicts,
        )
    console.print(demand_table)

    bleed = Table(title="Overstock bleed list", header_style="bold cyan")
    bleed.add_column("SKU @ Market")
    bleed.add_column("Excess", justify="right")
    bleed.add_column("Cover", justify="right")
    bleed.add_column("$/day", justify="right")
    bleed.add_column("Severity")
    for a in sorted(result.overstock, key=lambda x: x.daily_loss.total_usd, reverse=True):
        if a.units_excess == 0:
            continue
        bleed.add_row(
            a.target.key,
            f"{a.units_excess:,}",
            f"{a.days_of_cover:.0f}d",
            f"${a.daily_loss.total_usd:,.0f}",
            a.severity,
        )
    console.print(bleed)

    decisions = Table(title="Tradeoff decisions", header_style="bold cyan")
    decisions.add_column("Action")
    decisions.add_column("Description")
    decisions.add_column("Net $", justify="right")
    decisions.add_column("Carbon", justify="right")
    decisions.add_column("Verdict")
    decisions.add_column("Owner")
    for e in result.evaluated:
        style = _VERDICT_STYLE[e.decision.verdict]
        decisions.add_row(
            e.action.id,
            e.action.description[:70],
            f"${e.decision.net_score:,.0f}",
            f"{e.carbon.score:.0f}",
            f"[{style}]{e.decision.verdict.value}[/{style}]",
            e.decision.escalation_owner,
        )
    console.print(decisions)

    console.print(
        Panel(
            f"{orchestrator.gate.briefing()}\n"
            f"Carbon credit bank: {result.carbon_credits_kg:,.0f} kg CO2e\n"
            f"Signal trust weights: {json.dumps(orchestrator.ledger.snapshot())}\n"
            f"LLM calls: {orchestrator.reasoner.call_count}",
            title="Human-in-the-loop gate",
            border_style="magenta",
        )
    )

    report = orchestrator.financial.weekly_report()
    console.print(
        Panel(json.dumps(report, indent=2), title="Weekly financial report", border_style="green")
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
