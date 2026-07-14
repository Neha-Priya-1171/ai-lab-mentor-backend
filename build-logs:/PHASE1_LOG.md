# Circuit Diagnostic AI — Phase 1 Build Log

**Phase:** 1 — Core Diagnostic Engine (Bare-bones chatflow, no RAG, no structured memory)
**Date:** 2026-07-01
**Stack:** Flowise Cloud → ChatGroq (llama-3.3-70b-versatile) → Buffer Memory → Conversation Chain
**Status:** ✅ Core behavior validated | ⚠️ Known limitations documented → carried into Phase 2/3

---

## 1. Objective

Per the PRD (Section 7), the guided diagnostic state machine — *Observe → Ask → Measure → Eliminate → Conclude → Explain → Document* — was to be implemented first, before any RAG, memory schema, or board-specific logic. Phase 1's goal was to validate this reasoning loop using only a system prompt, with no external knowledge sources.

---

## 2. Build Steps

| Step | Component | Configuration |
|---|---|---|
| 1 | Chatflow created | `Circuit Diagnostic AI - Core Engine` |
| 2 | Chat Model | Initially **Google Gemini** (`gemini-2.0-flash`, temp 0.2) |
| 3 | Memory | **Buffer Memory** (default session/memory key) |
| 4 | Orchestration | **Conversation Chain** node, wired to Chat Model + Memory |
| 5 | System Prompt | Custom state-machine prompt encoding 9 core rules (see §5) |

---

## 3. Issue #1 — Gemini Free Tier Quota (`limit: 0`)

- **Symptom:** `429 Too Many Requests` on first message. Error showed `limit: 0` for `generate_content_free_tier_requests`.
- **Diagnosis:** Not a usage cap — the Google Cloud project tied to the AI Studio key was never assigned a free-tier quota bucket (a known, fairly common AI Studio issue, unrelated to Flowise config).
- **Attempted fix:** New API key in a fresh Google Cloud project — did not resolve it.
- **Resolution:** Swapped provider entirely, from **Google Gemini → Groq** (`llama-3.3-70b-versatile`), keeping temperature (0.2), Buffer Memory, Conversation Chain, and system prompt unchanged. Groq's free tier worked immediately.
- **Takeaway:** The PRD's "$0 budget" constraint doesn't mandate a specific provider — Groq is a valid Gemini substitute for this project.

---

## 4. Iterative Prompt Debugging

Testing was done manually, turn-by-turn, using a single repeated scenario: **"My OLED screen is blank"** (ESP32 DevKit V1 + SSD1306 via I2C). This maps to PRD test case **T7** (expected root cause: missing I2C pull-up resistors).

### Round 1 — Baseline prompt
- ✅ Flagged unverified specs correctly (`unverified — general knowledge, not yet from datasheet`)
- ✅ Produced all 4 required diagnosis fields (Root Cause / Evidence / Confidence / Confirming Test)
- ❌ Bundled multiple questions into single turns using "and" / "such as"
- ❌ Concluded a diagnosis at 40% confidence, after only 4 questions — violated the "85% confidence or 8–10 questions" rule

**Fix applied:** Added explicit `STRICT ENFORCEMENT` rule (plain-language instruction: one question mark per turn, no early conclusions).

### Round 2 — After plain-language fix
- ❌ Still bundled questions — satisfied "one question mark" *literally* while asking 2–3 things per turn via "and"/commas
- **Root cause of fix failure:** abstract rules are weakly followed by LLMs; concrete examples are far more reliable.

**Fix applied:** Replaced the rule with explicit few-shot **WRONG vs. RIGHT** examples of bundled vs. single-fact questions.

### Round 3 — After few-shot fix
- ✅ Clean single-fact questions, no bundling
- ✅ Logical progression (board → connection type → library → I2C detection → power → init)
- ❌ Ran to **11 questions** without stopping, despite the root cause (missing pull-ups) being directly confirmed twice
- **Root cause of fix failure:** "8–10 questions" as a soft/implied limit gave the model nothing concrete to track — it cannot reliably self-count turns from an unstructured chat transcript.

**Fix applied:** Added a **mandatory numeric counter** — model required to prefix every question with `[Question N of 10]`, with a hard rule to stop and conclude at N=10 or 85% confidence, whichever comes first.

### Round 4 — After hard counter fix
- ✅ Counter displayed correctly every turn, tracked accurately
- ✅ Hard stop worked — model self-announced *"This is the final question"* at Q10 and delivered a conclusion
- ❌ **Redundant questioning** — re-asked about I2C address and dimensions after they were already confirmed (turns 3, 7 vs. re-asked at turn 8)
- ❌ **Evidence reversal at conclusion** — correctly identified missing pull-up resistors as the likely cause at Q7 (matches PRD test case T7), but at the final diagnosis (Q10) walked it back to *"not the primary cause,"* concluding a vaguer, less-supported "software/configuration issue" instead

---

## 5. Final Phase 1 System Prompt Structure

1. Role framing (lab mentor, not chatbot) + 7-stage sequence
2. 9 core rules (one question/turn, 3-question minimum before conclusion, power-before-hardware, software-before-hardware, measurement-over-guessing, no invented specs, 4-field mandatory diagnosis format, explain-the-why, confidence-based stopping)
3. `STRICT ENFORCEMENT` block with few-shot WRONG/RIGHT question examples
4. `QUESTION COUNTER` block — mandatory `[Question N of 10]` tagging + hard stop at N=10
5. `EVIDENCE INTEGRITY` block (added at close of Phase 1, untested in a full run) — instructs the model not to contradict previously confirmed facts, and to check confirmed-fact list before writing a final Root Cause

---

## 6. Phase 1 Evaluation Summary

| Check (per PRD Design Principles / T7 pass criteria) | Result |
|---|---|
| One diagnostic question per turn | ✅ Pass (after few-shot fix) |
| Minimum 3 questions before any conclusion | ✅ Pass |
| All 4 required diagnosis fields present | ✅ Pass |
| Unverified specs explicitly flagged | ✅ Pass |
| Hard question ceiling respected | ✅ Pass (mechanical counter) |
| Correct root cause reached and **retained** (T7: missing pull-ups) | ❌ **Fail** — found, then reversed |
| No redundant re-asking of confirmed facts | ❌ **Fail** |

**Baseline metrics for tracking (Section 15 format):**

```
Version | Date       | Pass Rate | Avg Questions | Hallucination Count | Notes
v0.1    | 2026-07-01 | 0/1 (T7)  | 10             | 0                    | No RAG, no structured memory. Correct hypothesis (missing pull-ups) reached at Q7, reversed by Q10. Redundant questions from relying on raw chat-history memory only.
```

---

## 7. Root Cause of Remaining Failures (Diagnosis, Not Just Symptoms)

Both remaining failures — redundant questions and evidence reversal — trace back to the **same structural gap**: Buffer Memory only stores raw conversational text. The model re-reads the full transcript every turn and must *re-infer* what's already confirmed, what's eliminated, and what the leading hypothesis is. At scale (8–10+ turns), this re-inference becomes unreliable — confirmed facts get diluted or contradicted by newer, less-supported reasoning.

This is not a prompt-wording problem. It's the exact problem the PRD's **Section 8 Project Memory schema** (explicit `hypotheses[]`, `eliminated_hypotheses[]`, `confirmed_facts[]` fields) is designed to solve, and the exact reason RAG (Phase 3, Common Failure Library) is required rather than optional — grounding the model in documented failure patterns instead of letting it reason from scratch every session.

---

## 8. Decision: Scope of Further Prompt Patching

One additional patch (`EVIDENCE INTEGRITY` block) was added to directly target the reversal bug, but further prompt-only iteration was intentionally stopped here. Rationale: the remaining issues are architectural (unstructured memory), not linguistic — additional prompt tuning would cost disproportionate time for diminishing, scenario-specific returns. Per the PRD's own build guidance, this was flagged as a "defer to the correct phase" decision rather than over-engineering Phase 1.

---

## 9. Next Steps → Phase 2

Replace raw Buffer Memory with a structured **Project Memory** object (Section 8 schema): board profile, hypotheses with confidence scores, eliminated causes, and confirmed measurements tracked as explicit fields rather than implied within conversation text. This directly targets both open Phase 1 failures before Phase 3 (RAG) is layered on top.
