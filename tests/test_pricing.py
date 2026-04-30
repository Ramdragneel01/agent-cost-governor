from agent_cost_governor.pricing import (
    ModelPrice,
    approx_token_count,
    estimate_cost_usd,
    extract_request_tokens,
    extract_response_usage,
)


PRICES = {
    "gpt-4o": ModelPrice(input_per_1k=0.005, output_per_1k=0.015),
    "gpt-4o-mini": ModelPrice(input_per_1k=0.00015, output_per_1k=0.0006),
}


def test_estimate_cost_basic():
    cost = estimate_cost_usd("gpt-4o", 1000, 1000, PRICES)
    assert round(cost, 4) == round(0.005 + 0.015, 4)


def test_estimate_cost_unknown_model_is_zero():
    assert estimate_cost_usd("mystery-model", 1000, 1000, PRICES) == 0.0


def test_approx_token_count_is_monotonic():
    assert approx_token_count("") == 0
    assert approx_token_count("hello world") >= 1
    assert approx_token_count("x" * 400) > approx_token_count("x" * 40)


def test_extract_request_tokens_messages():
    payload = {
        "model": "gpt-4o",
        "messages": [
            {"role": "system", "content": "you are helpful"},
            {"role": "user", "content": "hello there"},
        ],
    }
    n = extract_request_tokens(payload)
    assert n > 0


def test_extract_response_usage():
    body = {"usage": {"prompt_tokens": 12, "completion_tokens": 34}}
    assert extract_response_usage(body) == (12, 34)
    assert extract_response_usage({}) == (0, 0)
    assert extract_response_usage({"usage": "broken"}) == (0, 0)
