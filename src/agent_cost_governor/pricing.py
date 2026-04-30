"""Cost model: token counts → USD.

Pricing is loaded from the policy YAML. We deliberately do NOT hardcode
provider prices because they change. The policy is the single source of
truth and is hot-reloadable.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional


@dataclass(frozen=True)
class ModelPrice:
    """Per-1k-token prices in USD for a given model."""

    input_per_1k: float
    output_per_1k: float


def estimate_cost_usd(
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    prices: Dict[str, ModelPrice],
) -> float:
    """Compute USD cost for a request given its token counts.

    Unknown models are treated as zero-cost so the proxy never crashes on a
    pricing miss; the audit log still records the model name for back-filling.
    """
    p = prices.get(model)
    if p is None:
        return 0.0
    return (
        (prompt_tokens / 1000.0) * p.input_per_1k
        + (completion_tokens / 1000.0) * p.output_per_1k
    )


def approx_token_count(text: str) -> int:
    """Cheap heuristic: ~4 characters per token. Good enough for budget guards.

    For exact accounting use the provider's reported token usage from the
    response (``usage`` block); this helper is only used for *pre-flight*
    estimation when blocking a request before it hits the upstream.
    """
    if not text:
        return 0
    return max(1, len(text) // 4)


def extract_request_tokens(payload: dict) -> int:
    """Estimate prompt tokens from a chat-completion payload."""
    total = 0
    prompt = payload.get("prompt")
    if isinstance(prompt, str):
        total += approx_token_count(prompt)
    msgs = payload.get("messages")
    if isinstance(msgs, list):
        for msg in msgs:
            if not isinstance(msg, dict):
                continue
            content = msg.get("content")
            if isinstance(content, str):
                total += approx_token_count(content)
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        text = block.get("text")
                        if isinstance(text, str):
                            total += approx_token_count(text)
    return total


def extract_response_usage(response_json: dict) -> tuple[int, int]:
    """Pull ``(prompt_tokens, completion_tokens)`` from a provider response.

    Falls back to ``(0, 0)`` if the response shape is unexpected.
    """
    usage = response_json.get("usage") if isinstance(response_json, dict) else None
    if not isinstance(usage, dict):
        return (0, 0)
    return (int(usage.get("prompt_tokens", 0)), int(usage.get("completion_tokens", 0)))
