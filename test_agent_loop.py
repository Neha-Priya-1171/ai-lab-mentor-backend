"""
Proxy/structural test for the agent loop — no network calls, no real API
keys, no quota spent. This follows the project's own established
convention (PHASE5_LOG.md: "test before spending real API quota... a
Claude-powered proxy test harness... validates prompt logic and structure
cheaply"). Here the thing under test is the *loop mechanics themselves*
(does multi-tool-call sequencing, message threading, and the iteration
ceiling work correctly) — a layer below prompt/model behavior, and one
that's fully testable with a scripted fake provider instead of a real LLM.

Run: python3 test_agent_loop.py

This does NOT validate tool-selection quality (does Llama actually choose
the right tool for a given user message) — that requires a real provider
call and belongs in a later, real-Groq/Gemini test pass, same as Phase 5's
"proxy passed, real Flowise/Llama confirmation still outstanding" pattern.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from providers.base import ChatResult, LLMProvider, ToolCall
import providers.registry as registry
import agent


class ScriptedProvider(LLMProvider):
    """Returns a pre-scripted sequence of ChatResults, one per call.
    Lets us simulate 'model calls tool A, then tool B, then answers'
    without touching a real API.
    """
    name = "scripted"

    def __init__(self, script: list[ChatResult]):
        self.script = script
        self.calls = 0

    def chat(self, api_key, messages, tools=None, temperature=0.2, max_tokens=1024):
        result = self.script[self.calls]
        self.calls += 1
        return result


def test_two_different_tools_invoked_in_one_conversation():
    """This is literally the Phase 6 'Definition of done' from V2_ROADMAP.md."""
    scripted = ScriptedProvider([
        ChatResult(text=None, tool_calls=[ToolCall(id="1", name="check_component_compatibility",
                                                     arguments={"component_a": "GPIO34", "component_b": "relay", "connection_topology": "GND"})]),
        ChatResult(text=None, tool_calls=[ToolCall(id="2", name="analyze_error_log",
                                                     arguments={"log_text": "rst:0x0f (RTCWDT_BROWN_OUT_RESET)"})]),
        ChatResult(text="Based on both checks, here is my combined answer.", tool_calls=[]),
    ])
    registry._PROVIDERS["scripted"] = scripted  # inject fake provider

    result = agent.run_agent_turn(
        provider_name="scripted",
        api_key="fake-key-not-sent-anywhere",
        messages=[{"role": "user", "content": "Is GPIO34 to a relay safe, and what does this brownout log mean?"}],
        system_prompt="You are a test system prompt.",
    )

    assert result["tool_calls_made"] == ["check_component_compatibility", "analyze_error_log"], result["tool_calls_made"]
    assert "combined answer" in result["reply"]
    assert scripted.calls == 3
    print("PASS: two different tools invoked across one conversation, then a final answer.")


def test_iteration_ceiling_does_not_hang():
    """If the model never stops calling tools, the loop must bail out cleanly,
    not loop forever or crash."""
    loop_call = ChatResult(text=None, tool_calls=[ToolCall(id="x", name="check_component_compatibility",
                                                              arguments={"component_a": "A", "component_b": "B"})])
    scripted = ScriptedProvider([loop_call] * (agent.MAX_TOOL_ITERATIONS + 2))
    registry._PROVIDERS["scripted"] = scripted

    result = agent.run_agent_turn(
        provider_name="scripted",
        api_key="fake",
        messages=[{"role": "user", "content": "loop forever"}],
        system_prompt="test",
    )

    assert scripted.calls == agent.MAX_TOOL_ITERATIONS, scripted.calls
    assert "safety limit" in result["reply"]
    print("PASS: iteration ceiling triggers cleanly instead of hanging.")


def test_single_text_reply_no_tools_needed():
    scripted = ScriptedProvider([
        ChatResult(text="Just a plain answer, no tools needed.", tool_calls=[]),
    ])
    registry._PROVIDERS["scripted"] = scripted

    result = agent.run_agent_turn(
        provider_name="scripted",
        api_key="fake",
        messages=[{"role": "user", "content": "hello"}],
        system_prompt="test",
    )
    assert result["tool_calls_made"] == []
    assert result["reply"] == "Just a plain answer, no tools needed."
    print("PASS: plain conversational turn doesn't force a tool call.")


def test_tool_call_message_shape_matches_groq_wire_format():
    """This is the exact regression that broke on real Groq: the assistant's
    tool-call turn must have tool_calls[].type == "function" and a nested
    function.{name,arguments} with arguments as a JSON STRING, not a dict.
    Groq returns a 400 ('tool_calls.0.type is missing') if this is wrong."""
    scripted = ScriptedProvider([
        ChatResult(text=None, tool_calls=[ToolCall(id="call_abc", name="analyze_error_log",
                                                     arguments={"log_text": "rst:0x0f (RTCWDT_BROWN_OUT_RESET)"})]),
        ChatResult(text="Signature: brownout reset...", tool_calls=[]),
    ])
    registry._PROVIDERS["scripted"] = scripted

    result = agent.run_agent_turn(
        provider_name="scripted",
        api_key="fake",
        messages=[{"role": "user", "content": "rst:0x0f (RTCWDT_BROWN_OUT_RESET)"}],
        system_prompt="test",
    )

    assistant_tool_call_msg = result["messages"][1]  # [0]=user, [1]=assistant tool-call turn
    assert assistant_tool_call_msg["role"] == "assistant"
    tc = assistant_tool_call_msg["tool_calls"][0]
    assert tc["type"] == "function", "missing type:'function' -- this is exactly the Groq 400 bug"
    assert tc["function"]["name"] == "analyze_error_log"
    assert isinstance(tc["function"]["arguments"], str), "arguments must be a JSON string, not a dict"
    import json as _json
    assert _json.loads(tc["function"]["arguments"]) == {"log_text": "rst:0x0f (RTCWDT_BROWN_OUT_RESET)"}
    print("PASS: tool_calls message shape matches Groq/OpenAI's required wire format (type + stringified arguments).")


if __name__ == "__main__":
    test_two_different_tools_invoked_in_one_conversation()
    test_iteration_ceiling_does_not_hang()
    test_single_text_reply_no_tools_needed()
    test_tool_call_message_shape_matches_groq_wire_format()
    print("\nAll structural agent-loop tests passed.")
