"""Typed access to Claude. Every reasoning agent goes through `Reasoner.think`.

Agents never ask for free text — they ask for a Pydantic type and supply a
deterministic fallback of that same type. That keeps three properties at once:

* with a key in `.env`, the agent's judgement comes from Claude;
* with no key, no network, or an API failure, the pipeline still completes;
* `--offline` is byte-identical to a failed call, so the tests exercise the same
  code path the production fallback uses.

Credential resolution is the SDK's own (ANTHROPIC_API_KEY, ANTHROPIC_AUTH_TOKEN,
an `ant auth login` profile, workload identity). We do not read the key
ourselves — we construct the client and let the SDK resolve it, then degrade to
fallbacks if that fails. So dropping a key into `.env` is the only step needed to
turn the network on.
"""

from __future__ import annotations

import json
import logging
from typing import Any, TypeVar

import anthropic
from pydantic import BaseModel

from .config import SETTINGS

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class Reasoner:
    """Wraps the Anthropic client so agents ask for a Pydantic type, not text."""

    def __init__(
        self,
        model: str | None = None,
        offline: bool | None = None,
        effort: str | None = None,
    ):
        self.model = model or SETTINGS.model
        self.offline = SETTINGS.offline if offline is None else offline
        self.effort = effort or SETTINGS.llm_effort
        self._client: anthropic.AsyncAnthropic | None = None
        # Set once we learn no credentials resolve, so we try exactly once and
        # then stay quiet for the rest of the run.
        self._unavailable = False
        self.call_count = 0
        self.fallback_count = 0

    @property
    def available(self) -> bool:
        """True when a call would be attempted (not offline, creds resolved)."""
        return not self.offline and not self._unavailable

    def _get_client(self) -> anthropic.AsyncAnthropic | None:
        """Build the client lazily. Returns None when no credentials resolve."""
        if self._client is not None:
            return self._client
        try:
            self._client = anthropic.AsyncAnthropic()
        except Exception as exc:  # no API key, no auth profile, bad config
            log.warning(
                "No Anthropic credentials resolved (%s). Running on deterministic "
                "fallbacks — add ANTHROPIC_API_KEY to .env to enable Claude.",
                exc.__class__.__name__,
            )
            self._unavailable = True
            return None
        return self._client

    async def think(
        self,
        *,
        system: str,
        payload: dict[str, Any],
        instruction: str,
        schema: type[T],
        fallback: T,
        max_tokens: int = 8192,
    ) -> T:
        """Ask Claude for one `schema` instance, or return `fallback` unchanged."""
        if not self.available:
            self.fallback_count += 1
            return fallback

        client = self._get_client()
        if client is None:
            self.fallback_count += 1
            return fallback

        # sort_keys keeps the serialized payload stable so the cached system
        # prefix in front of it is not invalidated by dict ordering.
        content = (
            f"{instruction}\n\n<observations>\n"
            f"{json.dumps(payload, indent=2, sort_keys=True, default=str)}\n"
            f"</observations>"
        )

        try:
            response = await client.messages.parse(
                model=self.model,
                max_tokens=max_tokens,
                system=[
                    {
                        "type": "text",
                        "text": system,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[{"role": "user", "content": content}],
                output_config={"effort": self.effort},
                output_format=schema,
            )
        except anthropic.AuthenticationError:
            # A bad or expired key: stop retrying for the rest of the run.
            log.warning("Anthropic authentication failed; using fallbacks for this run.")
            self._unavailable = True
            self.fallback_count += 1
            return fallback
        except anthropic.RateLimitError:
            log.warning("Rate limited; using deterministic fallback for %s", schema.__name__)
            self.fallback_count += 1
            return fallback
        except anthropic.APIStatusError as exc:
            log.warning("API error %s; using fallback for %s", exc.status_code, schema.__name__)
            self.fallback_count += 1
            return fallback
        except anthropic.APIConnectionError:
            log.warning("Connection error; using fallback for %s", schema.__name__)
            self.fallback_count += 1
            return fallback

        self.call_count += 1

        if response.stop_reason == "refusal":
            log.warning("Refusal on %s; using fallback", schema.__name__)
            self.fallback_count += 1
            return fallback

        parsed = response.parsed_output
        if parsed is None:
            self.fallback_count += 1
            return fallback
        return parsed
