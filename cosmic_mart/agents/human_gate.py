"""Human-in-the-loop gate: the final decision layer."""

from __future__ import annotations

from ..models import BlockRecord, EvaluatedAction, GateItem, Verdict

# CFO Rowan Ortega takes financial escalations; CSO Finley Martin takes strategic
# and sustainability-contested ones.
OWNERS = {"CFO": "Rowan Ortega", "CSO": "Finley Martin"}


class HumanGate:
    """Builds decision packages for humans and records what they decide.

    Approved actions carry a recommendation; flagged ones carry both raw scores
    and full context so the reviewer can see the tension rather than a verdict.
    """

    def __init__(self) -> None:
        self.queue: list[GateItem] = []
        self.blocked: list[BlockRecord] = []

    def submit(self, evaluated: EvaluatedAction) -> GateItem | BlockRecord:
        action = evaluated.action
        decision = evaluated.decision

        if decision.verdict is Verdict.BLOCK:
            record = BlockRecord(
                action_id=action.id,
                target_key=action.target.key,
                action=action.action,
                reason=decision.reasoning,
            )
            self.blocked.append(record)
            return record

        if decision.verdict is Verdict.APPROVE:
            context = (
                f"Recommendation. Net ${decision.net_score:,.0f} after a "
                f"${decision.carbon_penalty_usd:,.0f} carbon penalty. {decision.reasoning}"
            )
        else:
            context = (
                f"Scores in tension - both shown rather than reconciled. "
                f"Financial net ${evaluated.financial.net_benefit_usd:,.0f} "
                f"(payback {evaluated.financial.payback_days:.0f} days) versus a carbon score "
                f"of {evaluated.carbon.score:.0f} "
                f"({evaluated.carbon.emissions_kg_co2e:,.0f} kg CO2e). "
                f"{decision.reasoning}"
            )

        item = GateItem(
            action_id=action.id,
            summary=action.description,
            verdict=decision.verdict,
            owner=decision.escalation_owner,
            net_benefit_usd=evaluated.financial.net_benefit_usd,
            carbon_score=evaluated.carbon.score,
            context=context,
        )
        self.queue.append(item)
        return item

    def for_owner(self, owner: str) -> list[GateItem]:
        return [i for i in self.queue if i.owner == owner]

    def briefing(self) -> str:
        approvals = [i for i in self.queue if i.verdict is Verdict.APPROVE]
        flags = [i for i in self.queue if i.verdict is Verdict.FLAG]
        value = sum(i.net_benefit_usd for i in approvals)
        return (
            f"{len(approvals)} recommendation(s) worth ${value:,.0f} net, "
            f"{len(flags)} contested case(s) needing a call, "
            f"{len(self.blocked)} rejected and fed back to the overstock agent."
        )
