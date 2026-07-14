"""
Regression test for the Gemini thought_signature bug: a functionCall part
returned by Gemini must have its exact thoughtSignature echoed back,
positionally, when that turn is replayed in the next request's history.

Run: python3 test_gemini_thought_signature.py
"""

import json

from providers.gemini_provider import _to_gemini_contents
from providers.base import ToolCall


def test_thought_signature_round_trips_through_agent_message_shape():
    # Simulates what agent.py builds after receiving a Gemini ToolCall with
    # a captured thought_signature, then feeding that message back into
    # _to_gemini_contents on the next loop iteration.
    tc = ToolCall(
        id="gemini-call-0",
        name="check_component_compatibility",
        arguments={"component_a": "GPIO25", "component_b": "12V relay"},
        provider_extra={"thought_signature": "opaque-signature-abc123"},
    )

    # This mirrors agent.py's exact message-building code.
    assistant_msg = {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": tc.id,
                "type": "function",
                "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)},
                "provider_extra": tc.provider_extra,
            }
        ],
    }

    messages = [
        {"role": "user", "content": "Can I drive a 12V relay from GPIO25 to GND?"},
        assistant_msg,
        {"role": "tool", "name": tc.name, "tool_call_id": tc.id, "content": "tool result text"},
    ]

    _, contents = _to_gemini_contents(messages)

    model_turn = contents[1]
    assert model_turn["role"] == "model"
    part = model_turn["parts"][0]
    assert "functionCall" in part
    assert part["thoughtSignature"] == "opaque-signature-abc123", (
        "thought_signature was not reattached to the functionCall part — "
        "this is exactly what caused the real 400 error."
    )
    print("PASS: thought_signature is correctly reattached to its functionCall part on replay.")


def test_missing_thought_signature_does_not_crash():
    """Groq-originated tool calls (or any without a signature) must not
    inject a thoughtSignature key at all -- Gemini should just not see one."""
    assistant_msg = {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "call_1",
                "type": "function",
                "function": {"name": "analyze_error_log", "arguments": "{}"},
                "provider_extra": None,
            }
        ],
    }
    _, contents = _to_gemini_contents([assistant_msg])
    part = contents[0]["parts"][0]
    assert "thoughtSignature" not in part
    print("PASS: no thoughtSignature key injected when none was ever captured (no crash on None).")


if __name__ == "__main__":
    test_thought_signature_round_trips_through_agent_message_shape()
    test_missing_thought_signature_does_not_crash()
    print("\nAll thought_signature regression tests passed.")
