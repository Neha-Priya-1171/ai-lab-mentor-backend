"""
Groq adapter. Groq's chat completions endpoint is OpenAI-compatible,
including tool-calling shape, so this is the simplest adapter — mostly
pass-through with normalization into ChatResult.

Carried over from Phase 6.0: the key always comes from the caller
(per-request BYOK), never from an env var.
"""

from __future__ import annotations

import json
from typing import Any

import requests

from .base import ChatResult, LLMProvider, ProviderError, ToolCall

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_MODEL = "llama-3.3-70b-versatile"


class GroqProvider(LLMProvider):
    name = "groq"

    def chat(
        self,
        api_key: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        model: str = DEFAULT_MODEL,
    ) -> ChatResult:
        if not api_key:
            raise ProviderError("Missing Groq API key", status_code=401, provider=self.name)

        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            payload["tools"] = [{"type": "function", "function": t} for t in tools]
            payload["tool_choice"] = "auto"

        try:
            resp = requests.post(
                GROQ_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=60.0,
            )
        except requests.RequestException as e:
            raise ProviderError(f"Network error calling Groq: {e}", status_code=502, provider=self.name)

        if resp.status_code == 401:
            raise ProviderError("Invalid Groq API key", status_code=401, provider=self.name)
        if resp.status_code == 429:
            raise ProviderError(
                "Groq rate limit hit (per-minute or daily token cap). Wait and retry.",
                status_code=429,
                provider=self.name,
            )
        if resp.status_code >= 400:
            raise ProviderError(f"Groq error {resp.status_code}: {resp.text}", status_code=resp.status_code, provider=self.name)

        data = resp.json()
        choice = data["choices"][0]
        msg = choice["message"]

        tool_calls: list[ToolCall] = []
        for tc in msg.get("tool_calls") or []:
            try:
                args = json.loads(tc["function"]["arguments"])
            except (json.JSONDecodeError, KeyError):
                args = {}
            tool_calls.append(ToolCall(id=tc["id"], name=tc["function"]["name"], arguments=args))

        return ChatResult(
            text=msg.get("content"),
            tool_calls=tool_calls,
            raw=data,
            finish_reason=choice.get("finish_reason"),
        )
