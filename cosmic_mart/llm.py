"""Typed access to Claude. Every agent goes through `Reasoner.think`."""

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
    """Wraps the Anthropic client so agents ask for a Pydantic type, not text.

    In offline mode no API call is made and each agent's own deterministic
    fallback is used instead, so the full workflow still runs end to end.
    """

    def __init__(self, model: str | None = None, offline: bool | None = None):
        self.model = model or SETTINGS.model
        self.offline = SETTINGS.offline if offline is None else offline
        self._client: anthropic.AsyncAnthropic | None = None
        self.call_count = 0

    @property
    def client(self) -> anthropic.AsyncAnthropic:
        if self._client is None:
            self._client = anthropic.AsyncAnthropic()
        return self._client

    async def think(
        self,
        *,
        system: str,
        payload: dict[str, Any],
        instruction: str,
        schema: type[T],
        fallback: T,
        max_tokens: int = 4096,
    ) -> T:
        if self.offline:
            return fallback

        # sort_keys keeps the serialized payload stable so the cached system
        # prefix in front of it is not invalidated by dict ordering.
        content = f"{instruction}\n\n<observations>\n{json.dumps(payload, indent=2, sort_keys=True, default=str)}\n</observations>"

        try:
            response = await self.client.messages.parse(
                model=self.model,
                max_tokens=max_tokens,
                system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": content}],
                output_format=schema,
            )
        except anthropic.RateLimitError:
            log.warning("Rate limited; using deterministic fallback for %s", schema.__name__)
            return fallback
        except anthropic.APIStatusError as exc:
            log.warning("API error %s; using fallback for %s", exc.status_code, schema.__name__)
            return fallback
        except anthropic.APIConnectionError:
            log.warning("Connection error; using fallback for %s", schema.__name__)
            return fallback

        self.call_count += 1

        if response.stop_reason == "refusal":
            log.warning("Refusal on %s; using fallback", schema.__name__)
            return fallback

        parsed = response.parsed_output
        return parsed if parsed is not None else fallback
