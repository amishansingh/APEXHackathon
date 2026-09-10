"""Human in the Loop — final reviewer for all order recommendations (§6).

Every recommendation passes through human review before execution. The system
assists but does not execute autonomously. This offline gate simulates a reviewer:
clean recommendations are approved, escalation-flagged ones are routed to modify /
escalate, and it surfaces the full synthesizer context including any conflict.
"""

from __future__ import annotations

from ..models import HumanReviewDecision, OrderRecommendation
from .base import Agent


class HumanGate(Agent):
    name = "human_gate"

    def review(self, recommendations: list[OrderRecommendation]) -> list[HumanReviewDecision]:
        """Review every recommendation. There is no autonomous path around this.

        The gate is total by construction: one decision per recommendation, in
        order, with no branch that lets a recommendation reach execution
        unreviewed. The post-condition below is deliberate — if a future change
        ever filters this loop, the run fails loudly rather than quietly
        executing something no human saw.
        """
        decisions: list[HumanReviewDecision] = []
        for rec in recommendations:
            decisions.append(self._decide(rec))

        if len(decisions) != len(recommendations):  # pragma: no cover - invariant
            raise RuntimeError(
                f"Human review is mandatory: {len(recommendations)} recommendation(s) "
                f"produced only {len(decisions)} decision(s)."
            )

        approved = sum(1 for d in decisions if d.action == "approve")
        escalated = sum(1 for d in decisions if d.action == "escalate")
        self._log(
            reviewed=len(decisions),
            approved=approved,
            escalated=escalated,
            coverage="all_recommendations",
        )
        return decisions

    def _decide(self, rec: OrderRecommendation) -> HumanReviewDecision:
        flag_types = {f.flag_type for f in rec.escalation_flags}

        if not rec.escalation_flags:
            action, notes = "approve", "Within thresholds — approved for execution."
        elif "high_divergence" in flag_types and len(rec.escalation_flags) >= 2:
            # Conflicting signals with high divergence go up for further review.
            action, notes = "escalate", "High divergence with additional flags; escalated for review."
        elif "high_value" in flag_types:
            action, notes = "escalate", "High-value order requires sign-off."
        elif "low_confidence" in flag_types:
            action, notes = "modify", "Low confidence; trim quantity pending firmer signal."
        else:
            action, notes = "modify", "Flagged for reviewer adjustment."

        # A hold with no upside is simply approved as a no-op.
        if rec.action == "hold" and not rec.escalation_flags:
            notes = "Hold — no order this cycle."

        return HumanReviewDecision(
            recommendation_id=rec.id,
            sku_id=rec.sku.id,
            action=action,  # type: ignore[arg-type]
            modifier_notes=notes,
            reviewer="ops-reviewer",
        )

    def briefing(self, decisions: list[HumanReviewDecision]) -> str:
        approved = sum(1 for d in decisions if d.action == "approve")
        modified = sum(1 for d in decisions if d.action == "modify")
        escalated = sum(1 for d in decisions if d.action == "escalate")
        rejected = sum(1 for d in decisions if d.action == "reject")
        return (
            f"{approved} approved, {modified} modified, "
            f"{escalated} escalated, {rejected} rejected across {len(decisions)} recommendation(s)."
        )
