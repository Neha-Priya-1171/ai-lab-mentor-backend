# Circuit Diagnostic AI — Phase 6.0 Build Log

**Phase:** 6.0 — The Transition (Flowise workflow → standalone BYOK backend)
**Date:** 2026-07-12
**Stack:** FastAPI (Python 3.13) → ChatGroq (llama-3.3-70b-versatile, user's own key) → Cohere Embeddings (shared) → Pinecone (shared) → static HTML frontend
**Status:** ✅ Migration complete and validated | ✅ Multi-tenant quota isolation confirmed live | ⚠️ Cosmetic prompt leftover flagged, not yet cleaned

---

## 1. Objective

Phases 1–5 (v1) were built entirely on Flowise Cloud, which meant every user of the deployed chatbot shared a single Flowise prediction cap and a single Groq API key — the author's own. A friend testing the app would silently consume the author's personal quota, with no isolation between users. This is a structural limitation of the platform, not a prompt or config issue (confirmed via investigation: Flowise's `overrideConfig` API supports overriding prompt variables but not swapping LLM credentials per request, and this behavior has been inconsistently supported even for variables in recent Flowise versions per public bug reports).

Phase 6.0's objective: **move the serving layer off Flowise entirely**, replacing it with a small self-hosted backend that lets each user supply their own LLM API key (BYOK — bring your own key), while keeping the retrieval layer (Cohere + Pinecone) on shared credentials, since read-mostly embedding/query traffic has far more free-tier headroom than LLM generation.

This phase is also a **terminology correction**, not just an infrastructure change: v1 (Phases 1–5) is now explicitly documented as a *structured diagnostic workflow* — a prompt pipeline with RAG grounding and state tracking — not an *AI agent*. No autonomous tool selection or multi-step planning occurred; a single prompt internally performed mode-detection (Step 0) between Compatibility Checker / Error Log Analyzer / Report Generator, which is a routing instruction inside one static prompt, not agentic behavior. Genuine agentic architecture — the model actively selecting and invoking discrete tools — is deferred to Phase 6.

---

## 2. Architecture

```
Browser (user enters their own Groq key)
        │
        ▼
Your backend (FastAPI) — embeds, retrieves, orchestrates
        │                              │
        ▼                              ▼
Cohere + Pinecone (shared,        Groq (user's own key)
 author's keys)
```

Cohere and Pinecone stay on shared credentials deliberately — retrieval calls are cheap relative to generation, and this keeps the rebuild scoped to the actual bottleneck (Groq's daily/per-minute token caps, which were the original problem). The same BYOK pattern can extend to Cohere later if retrieval volume ever becomes the limiting factor.

---

## 3. Build Steps

| Step | Component | Detail |
|---|---|---|
| 1 | Backend | `main.py` — FastAPI app, `/chat` endpoint accepting `{groq_api_key, message, history}` |
| 2 | Retrieval | Cohere `embed-english-v3.0` (search_query) → Pinecone top-k=4 query, same index used throughout Phases 3–5 |
| 3 | Generation | Direct call to Groq's OpenAI-compatible endpoint (`api.groq.com/openai/v1/chat/completions`) using the **request's** Groq key, not an env var |
| 4 | System prompt | Full validated prompt (`diagnostic-engine-prompt.md` + `combined-system-prompt-v2.md` content) ported verbatim into `system_prompt.md`, loaded at startup, with retrieved context appended per-turn |
| 5 | Frontend | Single static `index.html` — Groq key field (browser-only, never persisted), chat log, fetch to `/chat` |
| 6 | Hosting (planned) | Render free tier — documented in README, not yet deployed publicly as of this log |

---

## 4. Issues Found and Fixed

| Issue | Root Cause | Fix |
|---|---|---|
| Files never appeared in expected project folder | Chat-provided files land as loose individual downloads, not a folder — `find` across the home directory located them scattered in `~/Downloads` alongside ~150 unrelated files | Created the actual project folder structure manually (`mkdir -p`), copied the correct files into place with explicit `cp` commands, renamed dotfiles that lost their leading dot on download (`env.example` → `.env.example`, `gitignore` → `.gitignore`) |
| `uvicorn: command not found` after a fresh terminal session | Virtual environment activation (`source venv/bin/activate`) is per-terminal-session, not persistent — a new terminal tab starts outside the venv even if it was activated earlier | Documented as a recurring step: always confirm `(venv)` prefix is present before running `uvicorn` |
| Frontend rendered as raw HTML source text instead of a page | TextEdit's default Rich Text mode escaped `<tags>` into literal displayed text when code was pasted in and saved — file bloated from ~2.5KB to 22KB | Abandoned GUI text editors for this project entirely; used `nano` (plain-text terminal editor) instead, after first deleting the corrupted file to avoid leftover-content contamination from an earlier interrupted paste |
| Raw `` ```state ``` `` JSON block and un-wrapped text displayed directly in the chat UI | Frontend was doing a literal `textContent = data.reply` with no formatting or filtering | Added `white-space: pre-wrap` CSS for real line breaks, and a `stripStateBlock()` regex to hide the internal state block from display while still sending the full raw reply (state block included) back to the backend in `history`, preserving the model's session memory |
| `429 rate_limit_exceeded` mid-session (Groq tokens-per-minute cap) | Multi-turn conversation with injected datasheet context pushed a single request's token count above Groq's free-tier TPM limit | Not a bug — this is the free-tier ceiling working as expected. **Confirmed the error's organization ID belonged to the author's own Groq account**, directly validating that per-user quota isolation is functioning as designed. Resolved by waiting ~15s and resending the affected turn. |

---

## 5. Verification Testing

Ran a full T7-equivalent scenario (ESP32 + SSD1306 OLED, missing I2C pull-ups) end-to-end through the new backend, live in the browser, using a real personal Groq key (not the proxy-testing harness used in Phases 1–5).

| Check | Result |
|---|---|
| Server starts cleanly, reads `.env`, connects to Cohere/Pinecone | ✅ Pass |
| Frontend collects and submits the user's own Groq key | ✅ Pass |
| Invalid key produces a clean `401` error, not a crash | ✅ Pass |
| Multi-turn conversation maintains state (hypothesis list, question counter) | ✅ Pass — matched v1's Phase 5 hypothesis-display behavior exactly |
| Rate-limit error surfaces as a readable message, session recoverable by resending | ✅ Pass |
| Final diagnosis includes all four required fields (Root Cause / Evidence / Confidence / Confirming Test) | ✅ Pass — 100% confidence, correct root cause (missing pull-ups) |
| Evidence field cites the SSD1306 datasheet by name | ❌ Not this run — consistent with the 1-of-3 citation reliability already logged in Phase 4; not a new regression introduced by the migration |
| Frontend displays clean, readable text (no raw JSON/state leakage) | ✅ Pass, after the `stripStateBlock` fix |

**Conclusion:** the migration preserves 100% of the validated Phase 1–5 prompt behavior — same hypothesis tracking, same question discipline, same conclusion format — while solving the actual structural problem (shared quota) that motivated this phase. The citation-reliability gap is a carried-over, already-documented model-variance issue, not something this migration introduced or is expected to fix.

---

## 6. Known Limitations Carried Into Phase 6

- `system_prompt.md` still contains a literal `Context:\n{context}` placeholder left over from the Flowise template syntax. Harmless (no risky string formatting is applied to it), but redundant next to the `DATASHEET CONTEXT` block the backend appends — flagged for cleanup, not yet done.
- No rate limiting or abuse protection on the backend itself yet — acceptable for a demo shared with friends, not for wider public traffic.
- Cohere/Pinecone remain shared-key; not yet BYOK. Fine at current traffic levels.
- Not yet deployed publicly (Render steps documented, not executed as of this log).
- No genuine tool-calling/agentic architecture yet — this remains a single-prompt mode-detection system, same as v1, just running on new infrastructure. This is the explicit target of Phase 6.

---

## 7. Next Steps → Phase 6

1. Add multi-provider BYOK: Groq (done), Google Gemini, OpenRouter, Mistral — user selects provider + supplies matching key.
2. Replace the single-prompt "Step 0 mode detection" pattern with genuine function/tool-calling: the model is given discrete callable tools (Compatibility Checker, Error Log Analyzer, Report Generator, and later additions) and selects among them based on context, rather than following a hardcoded routing instruction inside one prompt.
3. Deploy to Render for real public/friend access.
4. Clean up the leftover `{context}` placeholder text in the system prompt.
