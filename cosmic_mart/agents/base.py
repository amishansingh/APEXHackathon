"""Shared scaffolding for pipeline agents.

Each agent is a discrete, stateless unit (§7.1). Inputs and outputs are typed
Pydantic documents. Agents emit a structured log line per run so a full pass is
auditable: inputs received, outputs produced, and any flags raised.
"""

from __future__ import annotations

import logging

log = logging.getLogger("cosmic_mart.agents")


class Agent:
    """Base for every agent. Provides a uniform structured-log helper."""

    name: str = "agent"

    def _log(self, **fields: object) -> None:
        parts = " ".join(f"{k}={v}" for k, v in fields.items())
        log.info("%s %s", self.name, parts)
