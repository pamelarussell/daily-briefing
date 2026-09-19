"""Thin wrapper around the Claude API for JSON-structured calls."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

import anthropic

from .util import log


@dataclass
class Usage:
    calls: list = field(default_factory=list)   # (label, model, input_tokens, output_tokens)

    def add(self, label: str, model: str, usage) -> None:
        self.calls.append((label, model, int(getattr(usage, "input_tokens", 0) or 0),
                           int(getattr(usage, "output_tokens", 0) or 0)))

    def cost(self, pricing: dict) -> float:
        total = 0.0
        for _, model, i, o in self.calls:
            p = pricing.get(model) or {}
            total += i / 1e6 * float(p.get("input_per_mtok", 0)) + o / 1e6 * float(p.get("output_per_mtok", 0))
        return total


class LLMError(RuntimeError):
    pass


class Claude:
    def __init__(self, usage: Usage, client: anthropic.Anthropic | None = None):
        key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
        if client is None and not key:
            raise LLMError("ANTHROPIC_API_KEY is not set (add it under Settings → Secrets and variables → Actions).")
        self.client = client or anthropic.Anthropic(api_key=key, max_retries=4, timeout=900)
        self.usage = usage

    def json_call(self, *, label: str, model: str, system: str, user: str, schema: dict,
                  max_tokens: int, effort: str | None = None) -> dict:
        """One request whose final text is guaranteed (by structured outputs) to match `schema`."""
        output_config: dict = {"format": {"type": "json_schema", "schema": schema}}
        if effort:
            output_config["effort"] = effort
        params = dict(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
            output_config=output_config,
        )
        log.info("Claude call: %s (%s)", label, model)
        with self.client.messages.stream(**params) as stream:
            msg = stream.get_final_message()
        self.usage.add(label, model, msg.usage)
        if msg.stop_reason == "max_tokens":
            raise LLMError(f"{label}: response hit max_tokens ({max_tokens}); raise it or lower effort.")
        if msg.stop_reason == "refusal":
            raise LLMError(f"{label}: the model declined this request.")
        # Thinking blocks may come first; the JSON is in the text block(s).
        text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text").strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            raise LLMError(f"{label}: could not parse JSON ({e}): {text[:300]}") from e
