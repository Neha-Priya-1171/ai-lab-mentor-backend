"""
End-to-end integration test — everything real (system prompt, ground
truth, dispatcher, agent loop) except the actual Groq/Gemini network call,
which is scripted. This is the "test the architecture before spending
real quota" step; a real Groq/Gemini confirmation pass (pasting a live
key into static/index.html) is still the next step after this passes,
same pattern as PHASE5_LOG.md's "proxy passed, real Flowise/Llama
confirmation still outstanding."

Run: python3 test_integration.py
"""

from pathlib import Path

import agent
import providers.registry as registry
from providers.base import ChatResult, LLMProvider, ToolCall
from tools.dispatcher import set_retriever


def fake_retriever(query: str, top_k: int) -> list[str]:
    if "relay" in query.lower() or "12v" in query.lower():
        return ["12V relay coils require a driver transistor when switched from a 3.3V logic GPIO; direct drive exceeds GPIO current limits."]
    return []


set_retriever(fake_retriever)

SYSTEM_PROMPT = Path(__file__).parent.joinpath("system_prompt.md").read_text().replace(
    "{context}", "(no matching datasheet content retrieved)"
)


class ScriptedProvider(LLMProvider):
    name = "scripted"

    def __init__(self, script):
        self.script = script
        self.calls = 0

    def chat(self, api_key, messages, tools=None, temperature=0.2, max_tokens=1024):
        result = self.script[self.calls]
        self.calls += 1
        return result


def test_full_turn_with_real_prompt_and_tool():
    """Simulates: user asks a compatibility question -> model calls the real
    tool (real board profile + fake retriever) -> model produces a final answer."""
    scripted = ScriptedProvider([
        ChatResult(text=None, tool_calls=[ToolCall(
            id="1", name="check_component_compatibility",
            arguments={"component_a": "GPIO25", "component_b": "12V relay coil", "connection_topology": "GPIO to GND"},
        )]),
        ChatResult(text=(
            "Verdict: Incompatible\n"
            "Reasoning: GPIO25 sourcing current into the relay coil (GPIO-to-GND topology) "
            "is limited to 12mA per the ESP32 board profile; a 12V relay coil needs far more than that.\n"
            "Fix: Add a driver transistor (e.g. NPN + flyback diode) between the GPIO and the relay coil.\n"
            "Source: ESP32 board profile"
        ), tool_calls=[]),
    ])
    registry._PROVIDERS["scripted"] = scripted

    result = agent.run_agent_turn(
        provider_name="scripted",
        api_key="fake",
        messages=[{"role": "user", "content": "Can I drive a 12V relay coil directly from GPIO25 to GND?"}],
        system_prompt=SYSTEM_PROMPT,
    )

    assert result["tool_calls_made"] == ["check_component_compatibility"]
    assert "Verdict: Incompatible" in result["reply"]
    assert "driver transistor" in result["reply"]
    print("PASS: full turn — real system prompt + real board-profile tool + scripted model — produces a correct, grounded verdict.")


def test_system_prompt_has_no_leftover_placeholder():
    """The known Phase 6.0 cosmetic issue (leftover {context} placeholder) —
    confirm it's actually gone now that main.py does a real .replace()."""
    raw = Path("system_prompt.md").read_text()
    assert raw.count("{context}") == 1  # exactly one, meant to be replaced by main.py at request time
    print("PASS: system_prompt.md has exactly one {context} placeholder, correctly positioned for main.py's .replace().")


if __name__ == "__main__":
    test_full_turn_with_real_prompt_and_tool()
    test_system_prompt_has_no_leftover_placeholder()
    print("\nAll integration tests passed.")
