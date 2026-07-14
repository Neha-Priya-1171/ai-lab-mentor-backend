"""
Gemini adapter.

Gemini's wire format is meaningfully different from OpenAI/Groq's:
- roles are "user" / "model" (not "assistant"), and there is no "system"
  role in `contents` — system instructions go in a separate top-level field.
- tool definitions live under `tools: [{"functionDeclarations": [...]}]`.
- a model tool call arrives as a `functionCall` part, not a `tool_calls` list.
- returning a tool's result back to the model uses a `functionResponse`
  part in a "user"-role turn (actually role "function" is accepted too,
  but "user" with a functionResponse part is the documented pattern).

This adapter's whole job is absorbing that difference so agent.py never
has to special-case Gemini vs Groq.

Note (Phase 1 history): a prior Gemini *free-tier quota* issue
(`limit: 0` on generate_content) was an AI-Studio project misconfiguration
specific to the author's own key, not a code bug — see PHASE1_LOG.md.
This adapter has no opinion on that; if a user's own Gemini key hits it,
it'll surface as a normal 4xx from Google and get wrapped as ProviderError.
"""

from __future__ import annotations

import json
from typing import Any

import requests

from .base import ChatResult, LLMProvider, ProviderError, ToolCall

GEMINI_URL_TMPL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
# gemini-2.5-flash was deprecated for new API keys (confirmed July 2026 — new
# keys got a 404 "no longer available to new users"). gemini-3.5-flash is the
# current GA replacement with an active free tier (~15 req/min, ~1,500 req/day
# as of its May 2026 release — check https://ai.google.dev/gemini-api/docs/models
# for the current numbers if this ever needs updating again).
DEFAULT_MODEL = "gemini-3.5-flash"


def _to_gemini_contents(messages: list[dict[str, Any]]) -> tuple[str | None, list[dict[str, Any]]]:
    """Split OpenAI-style messages into (system_instruction, contents[])."""
    system_instruction = None
    contents: list[dict[str, Any]] = []

    for m in messages:
        role = m["role"]
        if role == "system":
            # Gemini takes exactly one system_instruction; concatenate if multiple.
            system_instruction = (system_instruction + "\n\n" + m["content"]) if system_instruction else m["content"]
            continue
        if role == "tool":
            contents.append({
                "role": "user",
                "parts": [{
                    "functionResponse": {
                        "name": m.get("name", "unknown_tool"),
                        "response": {"result": m["content"]},
                    }
                }],
            })
            continue

        if role == "assistant" and m.get("tool_calls"):
            # This turn is the model calling one or more tools — represent
            # each as a functionCall part, matching what Gemini itself would
            # have sent if it had made this call directly (needed so a
            # Gemini session that calls a tool, then continues, has a
            # coherent history on the next request).
            #
            # Gemini 3.x thinking models additionally REQUIRE the exact
            # thoughtSignature they returned with the original functionCall
            # to be echoed back here — omitting it produces a 400
            # ("missing a thought_signature in functionCall parts"), even
            # though the docs don't surface this until you hit it. We
            # captured it into ToolCall.provider_extra when the response
            # first came in (see below); reattach it here, verbatim, to the
            # exact part it came from.
            parts = []
            for tc in m["tool_calls"]:
                fn = tc["function"]
                try:
                    args = json.loads(fn["arguments"])
                except (json.JSONDecodeError, TypeError):
                    args = {}
                part: dict[str, Any] = {"functionCall": {"name": fn["name"], "args": args}}
                extra = tc.get("provider_extra") or {}
                if extra.get("thought_signature"):
                    part["thoughtSignature"] = extra["thought_signature"]
                parts.append(part)
            contents.append({"role": "model", "parts": parts})
            continue

        gemini_role = "model" if role == "assistant" else "user"
        text = m.get("content") or ""
        contents.append({"role": gemini_role, "parts": [{"text": text}]})

    return system_instruction, contents


def _to_gemini_tools(tools: list[dict[str, Any]] | None) -> list[dict[str, Any]] | None:
    if not tools:
        return None
    # Gemini's functionDeclarations schema is a near-subset of OpenAI's
    # JSON-schema function format; passed through directly here. If a
    # schema ever uses a JSON-schema keyword Gemini rejects, strip it in
    # tools/schemas.py rather than special-casing it here.
    return [{"functionDeclarations": tools}]


class GeminiProvider(LLMProvider):
    name = "gemini"

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
            raise ProviderError("Missing Gemini API key", status_code=401, provider=self.name)

        system_instruction, contents = _to_gemini_contents(messages)

        payload: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            },
        }
        if system_instruction:
            payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}
        gemini_tools = _to_gemini_tools(tools)
        if gemini_tools:
            payload["tools"] = gemini_tools

        url = GEMINI_URL_TMPL.format(model=model, api_key=api_key)

        try:
            resp = requests.post(url, json=payload, timeout=60.0)
        except requests.RequestException as e:
            raise ProviderError(f"Network error calling Gemini: {e}", status_code=502, provider=self.name)

        if resp.status_code in (401, 403):
            raise ProviderError("Invalid or unauthorized Gemini API key", status_code=401, provider=self.name)
        if resp.status_code == 429:
            raise ProviderError("Gemini rate limit hit. Wait and retry.", status_code=429, provider=self.name)
        if resp.status_code >= 400:
            raise ProviderError(f"Gemini error {resp.status_code}: {resp.text}", status_code=resp.status_code, provider=self.name)

        data = resp.json()
        try:
            candidate = data["candidates"][0]
        except (KeyError, IndexError):
            raise ProviderError(f"Gemini returned no candidates: {data}", status_code=502, provider=self.name)

        parts = candidate.get("content", {}).get("parts", [])
        text_chunks: list[str] = []
        tool_calls: list[ToolCall] = []
        for i, part in enumerate(parts):
            if "text" in part:
                text_chunks.append(part["text"])
            elif "functionCall" in part:
                fc = part["functionCall"]
                # Per Gemini's thought-signature rules: on a single function
                # call, the signature sits on that part. On parallel function
                # calls, only the FIRST functionCall part carries it. Either
                # way, capture whatever's on this specific part — we reattach
                # it to this same part's position next turn, not just "any"
                # signature, since Gemini validates positionally.
                thought_sig = part.get("thoughtSignature")
                tool_calls.append(ToolCall(
                    id=f"gemini-call-{i}",  # Gemini doesn't issue call ids; synthesize one
                    name=fc["name"],
                    arguments=fc.get("args", {}),
                    provider_extra={"thought_signature": thought_sig} if thought_sig else None,
                ))

        return ChatResult(
            text="\n".join(text_chunks) if text_chunks else None,
            tool_calls=tool_calls,
            raw=data,
            finish_reason=candidate.get("finishReason"),
        )
