# Circuit Diagnostic AI — Phase 2 Build Log

**Phase:** 2 — Structured Project Memory (JSON state tracking, no RAG yet)
**Date:** 2026-07-01
**Stack:** Flowise Cloud → ChatGroq (llama-3.3-70b-versatile) → Buffer Memory → Conversation Chain
**Status:** ✅ Structured memory objective achieved | ⚠️ Question-bundling remains unresolved | ⚠️ Root cause not reached without RAG (expected — confirms Phase 3 necessity)

---

## 1. Objective

Per the PRD (Section 8), replace reliance on raw chat-history memory with an explicit structured state object — the Project Memory schema (`project`, `diagnostic_state.hypotheses`, `measurements`, `tests_completed`, `session_timeline`) — read and updated by the model on every turn, instead of inferred from unstructured conversation text.

This phase directly targets the two unresolved Phase 1 failures:
- Redundant re-asking of already-confirmed facts
- Reversal of a correctly-identified hypothesis at final conclusion

---

## 2. Implementation Approach

No new Flowise nodes were added this phase. Structured memory was implemented entirely through system-prompt engineering:

- The AI is instructed to maintain a JSON object matching the Section 8 schema and reprint the **full updated state** at the end of every response, inside a fenced ` ```state ` block.
- Because Buffer Memory (from Phase 1) already carries the full conversation forward, this state block becomes part of what the model reads back next turn — structured data to check against, rather than prose to reinterpret.
- Rationale: this validates the memory-schema concept cheaply before investing in real persistence (external DB / custom tool), which remains a valid Phase 2b stretch goal if cross-session persistence is needed later.

---

## 3. Issue #1 — Flowise Template Parsing Error (`Single '}' in template`)

- **Symptom:** Chat failed immediately with a template parsing error after adding the JSON schema directly into the System Message field.
- **Root cause:** Flowise/LangChain's prompt templating treats single curly braces (`{ }`) as variable placeholders (Handlebars/Mustache-style), not literal text. Any raw `{` or `}` in the system prompt — including ones inside an example JSON block — breaks the template parser.
- **Compounding issue:** a first patch attempt was pasted into the field without removing the original broken block, leaving two conflicting "PROJECT MEMORY" sections stacked in the same field.
- **Resolution:** Rewrote the schema description entirely in prose (field names and types as plain English, e.g. "measurements (array of objects: point, value, timestamp) — APPEND ONLY"), removing all literal braces from the instruction text. The model's actual JSON *output* to the user is unaffected — this escaping issue only applies to text sitting inside the Flowise input field itself.
- **Takeaway for documentation:** any future prompt content containing raw JSON syntax must avoid literal `{ }` in the System Message field, or double them (`{{ }}`) if Flowise's templating requires literal-brace escaping.

---

## 4. Test Methodology

Same repeated scenario as Phase 1 for direct comparability: **"My OLED screen is blank"** (ESP32 DevKit V1 + SSD1306 via I2C), matching PRD test case **T7** (expected root cause: missing I2C pull-up resistors). Two full runs were conducted as the prompt was iterated.

### Run 1 — Initial structured-memory prompt
- ✅ `state` block rendered correctly, no template errors after the fix
- ✅ `project` fields (board, symptom) populated accurately from the first message
- ❌ `hypotheses` remained empty until question 6 — no theory-forming until very late
- ❌ `tests_completed` remained empty for most of the run — confirmed findings were logged only as vague `session_timeline` narrative entries instead of structured fields
- ❌ `power_source` field populated with a voltage reading ("3.3V") instead of a supply description — schema ambiguity
- ❌ Question bundling reappeared (e.g., "is display() called repeatedly... and are there other functions interfering")

**Fixes applied:**
- Added `STATE DISCIPLINE` block — explicit instructions to classify every answer into the correct field (measurements vs. tests_completed vs. project) rather than defaulting to the timeline narrative
- Instructed the model to form an initial hypothesis by question 2, even at low confidence
- Clarified `power_source` as "origin of supply, not a voltage reading"
- Reordered the prompt — question-format rules moved near the top (after Core Rules), on the theory that instructions near the start/end of a long prompt are followed more reliably than ones buried in the middle
- Added an explicit "self-check before output" instruction for question bundling: draft, count facts, rewrite down to one before sending

### Run 2 — After consolidated fixes (full 10-question run)
- ✅ `project.components.pins` correctly captured full wiring detail (SDA/SCL/VCC) as soon as mentioned
- ✅ `hypotheses` began forming by question 2-3 and evolved sensibly as evidence came in (e.g., "Display initialization issue" rose to 0.5 after a clean voltage reading reduced power-fault likelihood)
- ✅ `measurements` and `tests_completed` correctly captured real findings in their proper fields, not just the timeline
- ✅ **Zero redundant questions** across all 10 turns — every question addressed a genuinely new fact
- ✅ **Final Root Cause matched the highest-confidence, non-eliminated hypothesis exactly** (0.5, "I2C communication issue") — no reversal
- ✅ Confidence reported honestly (50%), matching internal state, not inflated
- ❌ Question bundling persisted on **every single turn (10/10)** despite four independent mitigation attempts
- ❌ Never formed a hypothesis specific to pull-up resistors — landed on the correct *category* (I2C communication) but not the documented *specific cause*

---

## 5. Bundling — Root Cause Investigation (Unresolved)

Four separate mitigation attempts were made across this phase, all unsuccessful:
1. Explicit rule statement ("ask exactly one question")
2. Few-shot WRONG/RIGHT examples
3. Reordering the prompt to place the rule near the top
4. Explicit self-check instruction ("draft, count facts, rewrite before output")

**Conclusion:** this is not a wording problem. Further prompt-only iteration is not expected to resolve it and has been intentionally stopped, per the same "know when to stop patching" decision made in Phase 1. This is logged as a known v0.2 limitation rather than a blocker.

**Recommended real fix (deferred, not urgent):** a structural validation step — checking the AI's drafted question for multiple `?`/facts before it reaches the user and forcing a retry if found — rather than continued prompt engineering. Candidate for Phase 7 (polish).

---

## 6. Phase 2 Evaluation Summary

| Check (carried over from Phase 1 + new for Phase 2) | Result |
|---|---|
| One diagnostic question per turn | ❌ Fail (unresolved, 4 fixes attempted) |
| Minimum 3 questions before conclusion | ✅ Pass |
| All 4 required diagnosis fields present | ✅ Pass |
| Hard question ceiling respected | ✅ Pass |
| No redundant re-asking of confirmed facts | ✅ **Fixed this phase** |
| Root Cause matches highest-confidence hypothesis (no reversal) | ✅ **Fixed this phase** |
| Structured fields (measurements/tests_completed/hypotheses) populated correctly | ✅ Pass (after STATE DISCIPLINE fix) |
| Correct root cause reached (T7: missing pull-ups) | ❌ Fail — reached correct category, not the specific documented cause |

**Metrics for tracking (Section 15 format):**

```
Version | Date       | Pass Rate | Avg Questions | Hallucination Count | Notes
v0.2    | 2026-07-01 | 0/1 (T7)  | 10             | 0                    | Structured memory added. Redundancy and evidence-reversal bugs from v0.1 both fixed. Question bundling persists (10/10 turns) despite 4 mitigation attempts — logged as known limitation. Never reached pull-up hypothesis; landed on correct category ("I2C communication issue") without RAG-grounded specificity.
```

---

## 7. Why the Root Cause Still Wasn't Found — And Why That's Expected

This is the key finding of Phase 2, and it's a positive result for the project's design, not a failure of this phase's work: structured memory fixed exactly the two things it was meant to fix (redundancy, evidence reversal), and it did **not** fix — nor was it meant to fix — the model's lack of domain-specific grounding. The AI correctly narrowed to "I2C communication issue" as its top hypothesis (0.5 confidence) using a thorough, honestly-tracked evidence trail (I2C detection, pin wiring, VCC voltage, begin()/display() calls, solid-fill test, serial log check) — a real engineer would have earned the right to suspect pull-ups from that same evidence. The model doesn't have that specific documented pattern connected yet.

This directly validates the PRD's Feature 2 requirement (Datasheet-Aware RAG): grounding claims in real documentation is not optional polish, it's the mechanism that turns "correct category of hypothesis" into "correct, specific, documented root cause."

---

## 8. Next Steps → Phase 3

Connect the ESP32/SSD1306/DHT22/relay datasheets and the Common Failure Library (per PRD Feature 2, v1 scope) via RAG, so retrieval — not model guesswork — supplies the specific documented failure pattern ("blank OLED + I2C address detected + no pull-ups = common failure signature") that structured memory alone cannot provide.
