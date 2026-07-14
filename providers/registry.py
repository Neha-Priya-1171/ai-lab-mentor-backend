"""
Provider registry — single place that maps a provider name (string the
frontend sends, e.g. "groq" or "gemini") to its adapter instance.

Adding OpenRouter or Mistral later (per V2_ROADMAP.md Phase 6 scope) is a
two-line change: write the adapter file, register it here. Nothing else
in the codebase needs to change — that's the point of the abstraction.
"""

from __future__ import annotations

from .base import LLMProvider, ProviderError
from .gemini_provider import GeminiProvider
from .groq_provider import GroqProvider

_PROVIDERS: dict[str, LLMProvider] = {
    "groq": GroqProvider(),
    "gemini": GeminiProvider(),
    # "openrouter": OpenRouterProvider(),  # TODO Phase 6 remainder
    # "mistral": MistralProvider(),         # TODO Phase 6 remainder
}


def get_provider(name: str) -> LLMProvider:
    provider = _PROVIDERS.get(name.lower().strip())
    if provider is None:
        raise ProviderError(
            f"Unknown provider '{name}'. Available: {', '.join(_PROVIDERS)}",
            status_code=400,
            provider=name,
        )
    return provider


def available_providers() -> list[str]:
    return list(_PROVIDERS.keys())
