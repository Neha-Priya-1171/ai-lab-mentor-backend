"""
Agent loop — this is the actual Phase 6 "Definition of done" mechanism
from V2_ROADMAP.md: a session where the model autonomously invokes at
least two different tools across one conversation, without a hardcoded
routing instruction telling it which to use.

Flow per turn:
  1. Send full message history + tool schemas to the chosen provider.
  2. If the model returns tool_calls, dispatch each one, append the
     results as "tool" messages, and call the model again.
  3. Repeat until the model returns plain text with no tool_calls, or
     MAX_TOOL_ITERATIONS is hit (bounded, same "don't patch forever"
     philosophy as the rest of this project — an agent that can't
     converge in N tool calls has a prompt/tool-design problem, not
     something to paper over with a higher ceiling).

This module is provider-agnostic — it only talks to ChatResult/ToolCall
from providers/base.py, never to Groq or Gemini specifics directly.
"""

from __future__ import annotations

import json
from typing import Any

from providers.base import ChatResult, ProviderError
from providers.registry import get_provider
from tools.dispatcher import dispatch
from tools.schemas import get_relevant_tools
from grounding_guard import strip_unverified_locators, build_grounded_text

MAX_TOOL_ITERATIONS = 5


def run_agent_turn(
    provider_name: str,
    api_key: str,
    messages: list[dict[str, Any]],
    system_prompt: str,
    temperature: float = 0.2,
) -> dict[str, Any]:
    """
    messages: prior conversation, OpenAI-style, NOT including the system
              prompt (that's passed separately and prepended here).
    Returns: {"reply": str, "messages": <updated full history to persist>,
              "tool_calls_made": [tool names actually invoked, in order]}
    """
    provider = get_provider(provider_name)
    full_messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}] + messages
    relevant_tools = get_relevant_tools(messages)

    tool_calls_made: list[str] = []

    for _ in range(MAX_TOOL_ITERATIONS):
        result: ChatResult = provider.chat(
            api_key=api_key,
            messages=full_messages,
            tools=relevant_tools,
            temperature=temperature,
        )

        if not result.tool_calls:
            # Plain answer — done. Deterministic backstop: strip any
            # document version/section/page locator that isn't actually
            # backed by anything retrieved this turn (see grounding_guard.py
            # for why this is code, not another prompt patch — the
            # corresponding Hard Rule has failed live testing twice on this
            # exact sub-pattern).
            grounded_text = build_grounded_text(full_messages, system_prompt)
            reply_text = strip_unverified_locators(result.text or "", grounded_text)
            full_messages.append({"role": "assistant", "content": reply_text})
            return {
                "reply": reply_text,
                "messages": full_messages[1:],  # drop the system message before persisting/returning
                "tool_calls_made": tool_calls_made,
            }

        # Model wants to call one or more tools. Record the assistant's
        # tool-call turn in OpenAI/Groq's exact wire shape — each entry needs
        # "type": "function" and a nested "function": {name, arguments} where
        # arguments is a JSON *string*, not a dict. Getting this shape wrong
        # is what produces Groq's "'messages.N.tool_calls.0.type': property
        # 'type' is missing" 400 error.
        full_messages.append({
            "role": "assistant",
            "content": result.text,  # None is valid here; Groq/OpenAI accept a null content on a tool-call turn
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": json.dumps(tc.arguments),
                    },
                    "provider_extra": tc.provider_extra,  # e.g. Gemini's thought_signature; None for Groq
                }
                for tc in result.tool_calls
            ],
        })

        for tc in result.tool_calls:
            tool_output = dispatch(tc.name, tc.arguments)
            tool_calls_made.append(tc.name)
            full_messages.append({
                "role": "tool",
                "name": tc.name,
                "tool_call_id": tc.id,
                "content": tool_output,
            })

    # Hit the iteration ceiling without converging — surface this clearly
    # rather than silently truncating, so it shows up in testing instead
    # of looking like a normal answer.
    return {
        "reply": (
            "The assistant made too many tool calls in a row without reaching a final "
            "answer (agent loop safety limit hit). This usually means a tool description "
            "is ambiguous enough that the model keeps re-invoking it — check tool "
            "descriptions in tools/schemas.py first."
        ),
        "messages": full_messages[1:],
        "tool_calls_made": tool_calls_made,
    }
