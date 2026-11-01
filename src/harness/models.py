"""Anthropic model wrapper with exact token accounting and cost estimation.

Uses the official Anthropic SDK (Messages API). Outputs on math problems are short,
so calls are non-streaming. Sampling parameters (`temperature` etc.) are not sent:
API version 2026-10-21 rejects them. Adaptive thinking is on by default for the
Claude 5.5 models (and cannot be disabled on Opus 5.5); `thinking=True` only sends it
explicitly.

NOTE: model ids and prices live in config/models.yaml. Verify prices against the
official pricing page — token counts here are exact (from response.usage).
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

import yaml

CONFIG = Path(__file__).resolve().parents[2] / "config" / "models.yaml"

SYSTEM_PROMPT = (
    "You are a careful mathematician. Solve the problem step by step, then give the "
    "final answer on its own line in the form \\boxed{ANSWER}. Put only the final "
    "answer inside \\boxed{}."
)


@dataclass
class ModelSpec:
    alias: str
    id: str
    label: str
    price_in: float    # USD per 1M input tokens
    price_out: float   # USD per 1M output tokens
    max_tokens: int


@dataclass
class Completion:
    text: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_s: float
    model_id: str
    stop_reason: str = ""  # "max_tokens" = truncated, "refusal" = declined


def load_model_specs() -> Dict[str, ModelSpec]:
    with open(CONFIG, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    specs: Dict[str, ModelSpec] = {}
    for alias, d in raw.items():
        specs[alias] = ModelSpec(
            alias=alias,
            id=d["id"],
            label=d.get("label", d["id"]),
            price_in=float(d["price_in_per_mtok"]),
            price_out=float(d["price_out_per_mtok"]),
            max_tokens=int(d.get("max_tokens", 4096)),
        )
    return specs


class ClaudeRunner:
    """Thin wrapper around the Anthropic client for one completion at a time."""

    def __init__(self, thinking: bool = False):
        from anthropic import Anthropic  # imported lazily so tests don't need a key

        self.client = Anthropic()  # reads ANTHROPIC_API_KEY from env
        self.thinking = thinking

    def complete(self, spec: ModelSpec, problem: str) -> Completion:
        kwargs = dict(
            model=spec.id,
            max_tokens=spec.max_tokens,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": problem}],
        )
        if self.thinking:
            # adaptive thinking (Claude 4.6+); already the default on the 5.5 models
            kwargs["thinking"] = {"type": "adaptive"}

        t0 = time.time()
        msg = self.client.messages.create(**kwargs)
        latency = time.time() - t0

        text = "".join(
            block.text for block in msg.content if getattr(block, "type", "") == "text"
        )
        in_tok = msg.usage.input_tokens
        out_tok = msg.usage.output_tokens
        cost = in_tok / 1e6 * spec.price_in + out_tok / 1e6 * spec.price_out
        return Completion(
            text=text,
            input_tokens=in_tok,
            output_tokens=out_tok,
            cost_usd=cost,
            latency_s=latency,
            model_id=spec.id,
            stop_reason=msg.stop_reason or "",
        )
