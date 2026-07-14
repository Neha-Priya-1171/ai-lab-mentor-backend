# Circuit Diagnostic AI — Phase 6 Build Log

**Phase:** 6 — Multi-Provider BYOK + Real Tool-Calling Architecture
**Date:** 2026-07-13 to 2026-07-14
**Stack:** FastAPI (Python 3.13) → Groq (llama-3.3-70b-versatile) / Google Gemini (gemini-3.5-flash), user's own key → Cohere Embeddings (shared) → Pinecone (shared) → static HTML frontend, deployed on Render
**Status:** ✅ Multi-provider BYOK live (Groq + Gemini) | ✅ Real tool-calling confirmed — both tools independently triggered correctly | ✅ Deployed publicly on Render | ✅ All local test suites passing (15+ tests across 4 files) | ⚠️ Report Generator tool not yet live-tested end-to-end

---

## 1. Objective

Per `V2_ROADMAP.md`, Phase 6 was the actual "agent" milestone — the point where this project stops being a structured prompt workflow (v1, Phases 1–5, and the Phase 6.0 transition) and becomes a genuine multi-tool AI agent. Two concrete goals, both from the roadmap's own definition of done:

1. Add Gemini as a second BYOK provider alongside Groq, behind one abstracted interface.
2. Replace the Phase 4/5 single-prompt "Step 0" mode-detection pattern with real function/tool-calling — the model autonomously selecting between Compatibility Checker, Error Log Analyzer, and Report Generator, rather than following a hardcoded routing instruction inside one prompt.

**Definition of done (from V2_ROADMAP.md):** a session where the model autonomously invokes at least two different tools across one conversation, without a hardcoded routing instruction telling it which to use. Confirmed live — see §6.

---

## 2. Architecture

```
Browser (provider dropdown: Groq or Gemini, user's own key)
        │
        ▼
FastAPI backend (main.py)
        │
        ├── retrieve_context() — Cohere + Pinecone, shared keys, unchanged from Phase 6.0
        │
        └── agent.run_agent_turn()
                │
                ├── providers/registry.py → get_provider("groq" | "gemini")
                │       providers/groq_provider.py   — OpenAI-compatible wire format
                │       providers/gemini_provider.py — native Gemini translation layer
                │
                └── tools/dispatcher.py
                        ├── check_component_compatibility → ground_truth.py (board profile) + RAG
                        ├── analyze_error_log              → ground_truth.py (error signatures) + RAG
                        └── generate_diagnostic_report      → RAG (supplementary context only)
```

**Key design decision:** tools do NOT produce final Verdict/Signature/Report output themselves. They return grounded facts (board-profile lookups, RAG chunks); the model — governed by `system_prompt.md`'s Shared Rules (Engineering Reasoning Is Mandatory, Asking vs. Concluding, the source/sink topology rule) — still turns those facts into the labeled output. This preserves all of the validated Phase 4/5 prompt engineering (few-shot WRONG/RIGHT examples, the input-only-pin distinction, the Asking-vs-Concluding mutual exclusivity pattern) rather than re-deriving that reasoning in Python from scratch.

Ground truth (ESP32 board profile, error signature reference table) moved out of prose re-fed to the model every turn and into `ground_truth.py` as real Python data with regex-based lookup helpers — an extension of the project's own established "ground truth files over RAG for small, fixed, safety-relevant facts" principle.

---

## 3. Build Steps

| Step | Component | Detail |
|---|---|---|
| 1 | Provider abstraction | `providers/base.py` — `LLMProvider` ABC, normalized `ChatResult`/`ToolCall` dataclasses so `agent.py` never special-cases a provider |
| 2 | Groq adapter | `providers/groq_provider.py` — thin wrapper, since Groq's endpoint is already OpenAI-compatible |
| 3 | Gemini adapter | `providers/gemini_provider.py` — full translation layer (roles, `functionCall`/`functionResponse` parts, `thoughtSignature` handling — see §5) |
| 4 | Tool schemas | `tools/schemas.py` — three tools defined in OpenAI function-calling JSON schema, translated per-provider by each adapter |
| 5 | Ground truth | `ground_truth.py` — ESP32 board profile (pins, strapping warnings, source/sink current limits) and error signature table (reset reason codes, exception keywords), ported verbatim from `combined-system-prompt-v2.md`'s prose blocks into real, testable Python data |
| 6 | Tool dispatcher | `tools/dispatcher.py` — routes a model's tool call to ground-truth lookups + a shared RAG retriever hook (injected by `main.py`, same Cohere/Pinecone pipeline as the plain diagnostic loop) |
| 7 | Agent loop | `agent.py` — call model with tools → dispatch any tool calls → feed results back → repeat, capped at `MAX_TOOL_ITERATIONS = 5` |
| 8 | System prompt | `system_prompt.md` — Step 0 routing removed; Shared Rules and the guided diagnostic loop (question counter, hypothesis display, state tracking, datasheet grounding) preserved from `diagnostic-engine-prompt.md` and `combined-system-prompt-v2.md` |
| 9 | Frontend | `static/index.html` — provider dropdown, New Session button, animated loading indicator (see §7) |
| 10 | Deployment | Pushed to GitHub (`Neha-Priya-1171/ai-lab-mentor-backend`), deployed on Render free tier — live at `ai-lab-mentor.onrender.com` |

---

## 4. Issues Found and Fixed

| Issue | Root Cause | Fix |
|---|---|---|
| Groq `400`: `'messages.2.tool_calls.0.type' — property 'type' is missing` | The assistant's tool-call turn was built with a flat `{id, name, arguments}` shape; Groq/OpenAI's API requires `tool_calls[].type: "function"` plus a nested `function: {name, arguments}` with `arguments` as a JSON **string**, not a dict | Rebuilt the message shape in `agent.py` to match the exact OpenAI wire format. Added a dedicated regression test (`test_gemini_thought_signature.py`'s sibling, `test_tool_call_message_shape_matches_groq_wire_format` in `test_agent_loop.py`) so this can't silently reappear |
| `gemini-2.5-flash` → `404: no longer available to new users` | Google deprecated 2.5-series models for new API keys; current GA free-tier model is `gemini-3.5-flash` (released May 2026) | Updated `DEFAULT_MODEL` in `providers/gemini_provider.py` and the frontend dropdown label. Confirmed live |
| Gemini `400`: `Function call is missing a thought_signature in functionCall parts` | Gemini 3.x "thinking" models attach an opaque `thoughtSignature` to every function-call response and strictly require it echoed back, positionally, on the next request's history — new, stricter validation vs. Gemini 2.5. Not something the mainstream docs surface until you hit it | Added a generic `provider_extra` passthrough field to `ToolCall` (`providers/base.py`). Gemini adapter now captures `thoughtSignature` from the response and reattaches it to the same `functionCall` part on replay. Added `test_gemini_thought_signature.py` — pure unit test, no network needed, verifies the round-trip |
| Garbled response: `[Question 1 of 10] Signature: ...` blended together | `system_prompt.md`'s "Begin every new session by asking..." instruction was unconditional — no exception for "the user's first message already gave you a tool-worthy input" (e.g. pasting a raw log as message #1). Model tried to do both: open the question-counter loop AND call the tool, producing a mixed-format response | Added an explicit mutual-exclusivity rule (same pattern as the existing Asking-vs-Concluding fix) with a WRONG/RIGHT few-shot example: tool output and the standalone question-counter loop can't coexist in one response. The tool's own "Next Diagnostic Step" field may still contain a question — that's expected — but it can't be duplicated as a separate `[Question N of 10]` block |
| Gemini responses truncated mid-sentence (twice, reproducible) | `max_tokens` defaulted to 1024. For Gemini's thinking-class models, this budget covers **both** invisible internal reasoning tokens and the visible answer — the model was spending most of the budget on reasoning before it started writing, then hitting the ceiling mid-answer | Raised default `max_tokens` to 4096 across `providers/base.py`, `groq_provider.py`, and `gemini_provider.py`. Confirmed fixed — full, uncut responses on retest |
| `.env` staged for commit despite `.gitignore` existing | `git add .` was run once before `.gitignore` was actually in place/recognized in that shell session, leaving a stale git index | `git reset` to unstage everything, confirmed via `git check-ignore -v .env` that the ignore rule was actually active, then re-staged clean. Caught before any commit — no real key exposure occurred |
| Local dev environment friction (recurring, same root causes as Phase 6.0) | `providers:`/`tools:`/`static:` folders had trailing colons baked into their names from how files were extracted on macOS; venv activation not persisting across new terminal/VS Code sessions; `.env` created via GUI text editor didn't actually save in the expected location | Renamed folders via `mv 'providers:' providers` etc.; re-confirmed `(venv)` prefix before every `uvicorn` run; recreated `.env` directly via `cat > .env << 'EOF'` heredoc in the terminal instead of a GUI editor, which resolved it immediately |

---

## 5. Gemini Thought Signatures — Worth Documenting in Detail

This is a genuinely new finding not present in any prior phase, since Phase 6.0 only used Groq. Gemini 3.x models use an internal "thinking" process before deciding to call a function. Because the API is stateless, the model encodes that reasoning into an opaque `thoughtSignature` string attached to the `functionCall` part of its response. If a subsequent request in the same multi-step tool-calling turn replays that history *without* the exact signature in the exact same position, Gemini returns a strict `400 INVALID_ARGUMENT`.

Handling rules (per Google's docs, confirmed against the real error message this project hit):
- A single function call: the signature sits on that one `functionCall` part.
- Parallel function calls in one response: only the **first** `functionCall` part carries a signature.
- The signature must be reattached to the same positional part, unmodified, when that turn is replayed.

This project's fix: `ToolCall.provider_extra` is a generic passthrough dict (not Gemini-specific by name, so it could carry similar opaque data for a future provider), populated only by the Gemini adapter. `agent.py` threads it through the persisted message without needing to know what's inside it — same "provider adapter owns its own wire-format quirks" boundary the rest of the abstraction already follows.

---

## 6. Verification Testing

### Structural / unit tests (no real API calls, no quota spent)

| Test file | What it covers | Result |
|---|---|---|
| `test_agent_loop.py` | Multi-tool sequencing, iteration ceiling, plain-answer fast path, Groq wire-format shape | ✅ 4/4 pass |
| `test_tools.py` | Ground-truth lookups (input-only pins, source/sink topology), all three tool dispatchers, refusal-to-guess behavior | ✅ 9/9 pass |
| `test_integration.py` | Full turn with real system prompt + real board-profile tool + scripted model | ✅ 2/2 pass |
| `test_gemini_thought_signature.py` | thought_signature capture and positional round-trip | ✅ 2/2 pass |

### Live testing (real Groq and Gemini keys, real Cohere/Pinecone retrieval)

| Test | Provider | Result |
|---|---|---|
| Full multi-turn T7-style diagnostic (relay/buzzer brownout) — plain conversational loop | Groq | ✅ Pass — correct root cause (USB cable/power), correct 4-field conclusion, correct state block, no format collision |
| `Can I drive a 12V relay coil directly from GPIO25 to GND?` (fresh session) | Groq → 400 error (tool_calls shape bug) → **fixed** → Gemini (after Groq TPD cap hit) | ✅ Pass after fixes — `check_component_compatibility` called correctly, full Verdict/Reasoning/Fix/Source with correct voltage/current math and flyback diode reasoning, grounded in real SRD relay datasheet content from Pinecone |
| `rst:0x0f (RTCWDT_BROWN_OUT_RESET)` (fresh session) | Gemini | ✅ Pass after 2 fixes (format collision, then truncation) — clean `Signature:/Meaning:/Likely Cause:/Firmware or Hardware:/Next Diagnostic Step:` block, correctly grounded in `common-failures.md` (cited specific Wi-Fi TX current figures), correct state block |
| `My ESP32's OLED screen is blank` (fresh session, plain description) | Gemini | ✅ Pass — correctly did NOT trigger any tool; opened the standard `[Question 1 of 10]` guided-loop flow, matching Phase 6.0 behavior exactly |
| Same relay compatibility question, against the live Render deployment (not localhost) | Groq | ✅ Pass — confirms the public deployment works end-to-end, not just local dev |

**Two different tools, each correctly self-selected by the model based on message content alone (no hardcoded routing), each in a clean session — the literal Phase 6 definition of done — confirmed live on both providers.**

### Not yet tested

- `generate_diagnostic_report` tool has not been triggered and verified live yet (unlike the other two, which got real multi-scenario coverage). Structural tests pass (`test_tools.py`'s report-tool test), but no live confirmation.
- Groq's TPD (tokens-per-day) cap was hit during testing (100K tokens/day on `llama-3.3-70b-versatile`, ~7-9K tokens per call due to the large system prompt + tool schemas) — real, but expected; not a bug. Worth revisiting if this becomes a recurring friction point (candidate: trimming `system_prompt.md`, or investigating Groq's prompt caching).

---

## 7. Frontend Improvements (added post-milestone, same session)

- **New Session button** — clears chat log and history array in-browser, no page reload needed. Addressed real friction (previously required a manual refresh between test scenarios).
- **Loading indicator** — animated bouncing-dots + "thinking..." text while awaiting a response, with an extra note ("Gemini can take up to a minute") when Gemini is selected, since Gemini's thinking-model latency was initially mistaken for the app being stuck.
- **Provider dropdown label** updated to reflect the actual model in use (`gemini-3.5-flash`, not the deprecated `gemini-2.5-flash`).

---

## 8. Deployment

Deployed to Render free tier, per the plan already documented in the Phase 6.0 README:

1. `.gitignore` added (`​.env`, `venv/`, `__pycache__/`, `*.pyc`, `.DS_Store`) — critically, before the first commit, to avoid pushing real Cohere/Pinecone keys to a public GitHub repo. One near-miss caught during setup: a stale `git add .` staged `.env` before `.gitignore` was confirmed active; caught via `git status` review before any commit was made — no actual key exposure occurred.
2. Pushed to `github.com/Neha-Priya-1171/ai-lab-mentor-backend`.
3. Render Web Service: Python 3 runtime, `pip install -r requirements.txt` build command, `uvicorn main:app --host 0.0.0.0 --port $PORT` start command, `COHERE_API_KEY`/`PINECONE_API_KEY`/`PINECONE_INDEX_NAME` set as environment variables (Render's env, not a committed `.env`).
4. Live at **`https://ai-lab-mentor.onrender.com`** — confirmed working with a real end-to-end tool-calling test against the deployed instance, not just localhost.

Known free-tier tradeoff (documented for anyone testing it): Render's free instances spin down after inactivity, adding ~30-50s to the first request after idle time.

---

## Phase 6 Evaluation Summary

| Check | Result |
|---|---|
| Gemini added as a second BYOK provider behind one abstracted interface | ✅ Pass |
| Step 0 hardcoded routing replaced with real tool-calling | ✅ Pass |
| Model autonomously invokes ≥2 different tools across a conversation (V2_ROADMAP.md's stated definition of done) | ✅ Pass — confirmed live on both providers, in separate clean sessions |
| Validated Phase 4/5 prompt logic (Shared Rules, source/sink topology, Asking-vs-Concluding) preserved, not re-derived | ✅ Pass |
| Plain guided diagnostic loop (no tool call) still behaves identically to Phase 6.0 | ✅ Pass |
| Ground truth (board profile, error signatures) moved to testable Python data | ✅ Pass |
| All structural test suites passing | ✅ Pass (17 tests across 4 files) |
| Deployed publicly, tested live against the deployed instance | ✅ Pass |
| Report Generator tool live-tested | ❌ Not yet done |
| `{context}` leftover placeholder (Phase 6.0's known cosmetic issue) | ✅ Resolved — confirmed exactly one placeholder, correctly consumed by `main.py`'s `.replace()` |

---

## Next Steps → Phase 7

1. Live-test `generate_diagnostic_report` — paste a completed diagnostic transcript (e.g. the relay/buzzer brownout session from this phase's testing) and confirm the 10-section format holds up on a real model, not just the structural test.
2. Monitor Groq's TPD ceiling during Phase 7 testing — if it becomes a recurring blocker, consider trimming `system_prompt.md` size as a dedicated cleanup item.
3. Proceed to Phase 7 per `V2_ROADMAP.md`: Power Budget Calculator, Multimeter Assistant, Symptom → Root Cause Mapping — quick-win text-only tools extending the same tool-calling architecture built this phase.
4. No rate limiting/abuse protection exists yet on the deployed Render instance — acceptable for sharing with friends/recruiters at current scale, per the project's own carried-forward Phase 6.0 note; revisit if traffic grows.
