"""
Provider abstraction layer — Phase 6.

Every LLM provider (Groq, Gemini, OpenRouter, Mistral, ...) gets wrapped
behind this one interface so the rest of the backend (agent loop, /chat
route) never has to know which provider is in use. This is the "one
abstracted interface" called for in V2_ROADMAP.md Section 3/4.

Design notes carried over from the project's established conventions:
- BYOK only. Every function here takes api_key as an explicit argument.
  Nothing in this module reads from an environment variable for LLM
  credentials — that's reserved for the shared Cohere/Pinecone retrieval
  layer only (unchanged from Phase 6.0).
- Normalized response shape (ChatResult) so the agent loop written once
  in agent.py works identically regardless of provider, even though Groq
  (OpenAI-style tool_calls) and Gemini (functionCall parts) return wildly
  different raw JSON shapes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolCall:
    """A single tool invocation the model wants to make."""
    id: str                 # provider-issued call id (Groq) or synthesized (Gemini has none)
    name: str
    arguments: dict[str, Any]
    provider_extra: dict[str, Any] | None = None
    # Opaque, provider-specific data that must be echoed back verbatim on the
    # next request for multi-turn tool calling to work. Currently used by
    # Gemini's "thought_signature" requirement (Gemini 3.x thinking models
    # reject a tool-call turn in history if this isn't preserved exactly as
    # received — see providers/gemini_provider.py). Groq doesn't need this
    # and leaves it None.


@dataclass
class ChatResult:
    """Normalized result of one provider chat-completion call."""
    text: str | None                 # plain text content, if any
    tool_calls: list[ToolCall] = field(default_factory=list)
    raw: dict[str, Any] | None = None  # untouched provider response, kept for debugging/logs
    finish_reason: str | None = None


class ProviderError(Exception):
    """Raised for any provider-side failure (auth, rate limit, network).

    Carries a `status_code` so the /chat route can map it to a clean HTTP
    response instead of a 500 — Phase 6.0 already established the pattern
    of "invalid key -> clean 401, not a crash"; this generalizes it.
    """
    def __init__(self, message: str, status_code: int = 502, provider: str = ""):
        super().__init__(message)
        self.status_code = status_code
        self.provider = provider


class LLMProvider(ABC):
    """Base class every provider adapter implements."""

    name: str = "base"

    @abstractmethod
    def chat(
        self,
        api_key: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        # NOTE: for Gemini's thinking-class models (gemini-3.x), this budget
        # covers internal reasoning tokens AND the visible answer combined.
        # 1024 was too tight — it truncated real answers mid-sentence because
        # the model's invisible "thinking" ate most of the budget before it
        # started writing the answer. 4096 gives real headroom; bump further
        # if generate_diagnostic_report's 10-section output ever gets cut off.
    ) -> ChatResult:
        """
        messages: list of {"role": "user"|"assistant"|"system"|"tool", "content": ...}
                  using the OpenAI-style shape as the canonical internal format —
                  each adapter is responsible for translating to/from its own
                  provider's wire format.
        tools:    list of tool schemas in OpenAI function-calling JSON-schema
                  shape (see tools/schemas.py). Adapter translates to whatever
                  the provider natively expects (Gemini needs a different
                  envelope than Groq/OpenAI-compatible).
        """
        raise NotImplementedError
