# Circuit Diagnostic AI — Phase 4 Build Log

**Phase:** 4 — Compatibility Checker, Error Log Analyzer, Diagnostic Report Generator (Features 4, 5, 6)
**Date:** 2026-07-05
**Stack:** Flowise Cloud → ChatGroq (llama-3.3-70b-versatile) → Buffer Memory → Conversational Retrieval QA Chain → Cohere Embeddings (embed-english-v3.0) → Pinecone (serverless, free tier)
**Status:** ✅ Phase 3 T7 retest closed out | ✅ Feature 4 validated (T17-T19 pass) | ✅ Feature 5 validated (initial scenario) | ✅ Feature 6 validated (2 full tests) | ⚠️ Real Flowise platform bug found and routed around | 🔜 Integration phase (wiring all features into diagnostic-agent) deferred to a future phase

---

## Part 1 — Closing Out Phase 3: T7 Retest

Phase 3 had ended with the RAG pipeline built and unit-verified, but with two open items: (1) the flagship T7 scenario (OLED blank / missing I2C pull-ups) had not been re-run end-to-end with RAG active, and (2) citation language was confirmed inconsistent during natural diagnostic dialogue. Both were closed out today before starting Phase 4 feature work, per the project's standing rule against advancing before validating the current phase's core claims.

### T7 Run 1 (baseline, before any prompt changes)

Ran the full T7 scenario fresh. **Result: PASS on root cause** — correctly reached "insufficient I2C pull-up resistors" via 7 questions, with the diagnostic path fully respecting Rule 4 (measurement before speculation — requested multimeter SDA/SCL readings before recommending a fix). All four required conclusion fields (Root Cause / Evidence / Confidence / Confirming Test) were present.

**Failure found:** zero citation/grounding language at the conclusion — the single highest-stakes claim in the session. This reproduced the exact gap flagged in the Phase 3 log's Test 2, now confirmed on the flagship test case rather than just in exploratory dialogue.

Also observed: question-bundling recurred at Q4 (contrast + sleep mode combined into one question), consistent with the Phase 2 finding that this is a persistent, only-partially-mitigated limitation.

### Prompt Patch: Conclusion-Stage Grounding

Added a targeted `CONCLUSION-STAGE GROUNDING` block to the diagnostic-agent Response Prompt, using the WRONG/RIGHT few-shot pattern (the one technique with an actual track record on this stack, per Phase 2/3 learnings). Scoped narrowly to STATE 6 (Root Cause Identification) rather than rewriting the general grounding rule, since the general rule already worked on direct questions and mid-dialogue reasoning.

### T7 Run 2 (after patch)

**Result: root cause still correct, but citation still absent at conclusion.** Also regressed in two other ways not related to the citation fix: skipped the Rule 4 measurement-request step entirely (jumped straight to "try adding resistors and see"), and the confidence-score field disappeared from the JSON state entirely for this run. This is a new, useful data point: significant turn-to-turn behavioral variance on this stack, independent of prompt quality — the same prompt produced a materially different quality of session on back-to-back runs.

### T7 Run 3 (after confirming the prompt was genuinely live)

**Result: PASS, including citation.** The Evidence field explicitly stated: *"Per the SSD1306 datasheet, the I2C interface requires external pull-up resistors on SDA and SCL for reliable communication."* Notably, the citation also appeared unprompted one turn earlier, during the pre-conclusion question itself — suggesting the model had genuinely picked up the retrieved context that turn, not just produced a lucky token sequence at the finish line.

Mid-run, hit a **Groq daily token cap (TPD) 429 error** — `Limit 100000, Used 95886, service tier on_demand`. Three full multi-turn T7 runs in one day exhausted the free-tier daily budget. Waited ~5 minutes per the error's own retry guidance, then resent the in-flight message. **Session recovery behavior was inconsistent**: the resend initially appeared to roll the session back to the last successfully completed turn (re-asking a question that had already been answered) rather than resuming from the failed turn — but the very next turn showed the state had actually recovered correctly (the previously-given answer was reflected in state). This looks like a one-off recovery glitch rather than a systemic state-loss bug, but it's an open question rather than a resolved one.

### Phase 3 T7 Retest — Final Evaluation

| Check | Run 1 | Run 2 | Run 3 |
|---|---|---|---|
| Correct root cause | ✅ | ✅ | ✅ |
| Reached via requesting pull-up measurement (not skipped) | ✅ | ❌ | ✅ |
| Citation at conclusion | ❌ | ❌ | ✅ |
| Confidence score present in state | ✅ | ❌ | ✅ (only at conclusion) |
| Question-bundling at Q4 | Present | Present | Present |

**Conclusion:** citation gap treated as **resolved enough to stop patching** — 1-for-3 is real evidence the fix works when the model attends to it, not proof of 100% reliability. Given the project's own bounded-attempts principle and Llama-3.3-70B's demonstrated turn-to-turn variance independent of prompt quality, further prompt engineering against inherent model variance has a poor cost/benefit ratio here, matching the earlier experience with question-bundling.

**New findings logged, not fully resolved:**
- Question-bundling: confirmed still present, accepted as a documented v0.1 limitation (unchanged from Phase 2).
- Sources UI: showed up consistently across all three T7 runs (chips visible every turn) — tentatively resolved from Phase 3's "Fail — no UI element" status, though not exhaustively re-tested.
- **Groq TPD ceiling is a validation-pacing constraint**, not just a build-time annoyance: heavy same-day iterative testing is viable but bounded by the free tier's daily budget. Future full-suite validation runs (e.g. the eventual 50-scenario PRD test suite) should be paced across multiple days rather than attempted in one sitting.
- **Mid-session 429 recovery is not fully reliable** — open question, not blocking, worth another look if it recurs.

---

## Part 2 — Feature 4: Component Compatibility Checker

### Design

Built with two knowledge sources, following the same "structured ground truth + RAG for depth" pattern established in Phase 3:

1. **`esp32.json` / plaintext board profile** — a static, hardcoded lookup table for GPIO capabilities (input-only pins, output-capable pins, flash-reserved pins), current limits (12mA source / 20mA sink), ADC1/ADC2 mapping, strapping pins, bus defaults, and logic level. Deliberately *not* RAG-based — these are small, fixed, safety-critical facts where a lossy PDF-extraction chunk would be the wrong tool.
2. **Existing Pinecone/Cohere RAG pipeline** (from Phase 3) — reused as-is for component-side specs (e.g. AMS1117 dropout voltage) that genuinely require retrieval from long-form datasheet prose.

Built as a standalone chatflow initially (`Compatibility Checker`), per the PRD's own file structure (`compatibility-checker.json`), with the explicit design intent that it can later be invoked as a tool by the main diagnostic-agent flow once an integration phase begins.

### Build Issues Found and Fixed

| Issue | Root Cause | Fix |
|---|---|---|
| `model 'embed-english-v2.0' was removed` | New Cohere Embeddings node defaults to a deprecated model, doesn't inherit config from other chatflows | Manually set Model Name to `embed-english-v3.0` on every new node |
| `non-empty string for 'name'... index` | New Pinecone node's Index Name field is blank by default, doesn't inherit from other chatflows | Manually enter the existing index name on every new node |
| Fix recommended "add a transistor" for an input-only pin (GPIO34) | Prompt conflated two distinct failure modes: "pin cannot output at all" (input-only) vs. "pin can output but insufficient current" (current-limited) | Added explicit distinction + rule to identify which failure mode applies before writing the Fix field |
| Verbose "Step 1... Step 5" visible reasoning trace in output | No instruction suppressing visible chain-of-thought | Added explicit output instruction to suppress step-by-step trace, show only final fields |
| AMS1117/Li-ion question answered with vague hedging, no real number | AMS1117 datasheet was never in the Phase 3 corpus (only ESP32, SSD1306, DHT22, relay were loaded) | Sourced and loaded the official AMS1117 datasheet (`advanced-monolithic.com/pdf/ds1117.pdf`) into the existing Pinecone index |
| Citation exposed raw internal doc IDs (`doc id='1'`) | No formatting rule for citations | Added explicit rule: plain document names only, never internal IDs/chunk numbers |
| Conclusion understated severity ("fails when discharged" when the numbers showed it fails even fully charged) | No instruction to follow a calculated threshold through to its actual implication against the *full* range of the other value | Added rule requiring the model to check its own calculated threshold against the full range, not just the cited worst case |
| **Safety-relevant bug:** GPIO-to-GND buzzer wiring evaluated against the wrong current limit (20mA sink instead of 12mA source), producing a false "Compatible" verdict on a genuinely unsafe connection | Prompt never specified which limit (source vs. sink) applies to which wiring topology | Added source-vs-sink topology rule directly to the board profile (ground truth), not just the prompt — GPIO-to-GND = sourcing/12mA limit; GPIO-to-VCC = sinking/20mA limit |
| Verdict produced simultaneously with a request for missing information (contradictory — "Incompatible" + "I need more info to conclude") | Plain-prose instruction insufficient; took **3 attempts** to resolve | Attempt 1 (prose): failed. Attempt 2 (prose, more forceful): failed, and regressed further (dropped the explicit question). Attempt 3 (WRONG/RIGHT few-shot examples): passed cleanly. Reinforces the project's established finding that few-shot examples reliably outperform prose for behavioral constraints on this stack. |

### Test Results (Tier 4: T17-T19)

| Test | Scenario | Result |
|---|---|---|
| T17 | 12V relay coil direct from GPIO | ✅ PASS — correct voltage-mismatch reasoning, correct fix (driver stage on separate 12V rail) |
| T18 | AMS1117 3.3V LDO + Li-ion battery direct | ✅ PASS — correct dropout voltage (1.1-1.3V) verified word-for-word against the real datasheet after the corpus gap was fixed; one logged reasoning-severity nuance (see table above), since resolved |
| T19 | Buzzer on GPIO, current draw not initially given | ✅ PASS (3rd attempt) — correctly withholds verdict until spec provided, then correctly identifies GPIO-to-GND as a sourcing topology and applies the 12mA limit correctly |

**Verified against the actual manufacturer PDF** (`advanced-monolithic.com`) rather than trusting a search snippet — confirmed the model's cited 15V absolute max input and 1.1-1.3V dropout figures were both accurate, not hallucinated.

---

## Part 3 — Platform Constraint: Flowise 2-Flow Limit and Chain Tool Bug

### The 2-Flow Limit

Flowise Cloud's free tier caps chatflows at 2 total. With `diagnostic-agent` and `Compatibility Checker` already occupying both slots, adding Feature 5 as a third standalone chatflow was blocked outright (`Failed to retrieve Chatflow: Limit exceeded: flows`).

**Decision:** rather than deleting a validated flow or upgrading, combine Compatibility Checker and Error Log Analyzer into a single chatflow using an agent/router layer — chosen specifically because it also previews the eventual integration-phase architecture (the PRD's own design calls for exactly this kind of tool-based composition later).

### The Chain Tool + Conversational Retrieval QA Chain Bug

Built a `Tool Agent` with two `Chain Tool` nodes wrapping the two feature chains. Hit two issues in sequence:

1. **Agent silently rewrote the sub-chain's grounded answer into a generic, ungrounded one** — the Tool Agent's own top-level model was rewriting tool output into a "final answer" rather than returning it directly, discarding all the board-profile grounding. Fixed by enabling **Return Direct** on both Chain Tool nodes.
2. **After enabling Return Direct: `TypeError: chain.run is not a function`.** Confirmed via web search to be a known, unresolved Flowise platform bug (GitHub Discussion #3156, first reported ~a year prior, multiple independent users hitting the identical error, no fix or workaround ever posted by the Flowise team). This is a genuine structural incompatibility between the `ChainTool` node (which calls `.run()`) and `Conversational Retrieval QA Chain` (which doesn't expose that method) — not fixable from the prompt or config side.

**Resolution:** per the project's established principle (structural fix over endless patching for provider/platform-side issues — same category as the Gemini Embeddings and HuggingFace Inference failures in Phase 3), abandoned the Tool Agent / Chain Tool architecture entirely. Replaced with a **single Conversational Retrieval QA Chain** whose one Response Prompt internally performs its own mode detection ("Step 0") between Compatibility Checker, Error Log Analyzer, and (later) Report Generator modes, based on the shape of the input. This also had the side benefit of reverting to a simpler, already-proven-reliable chain pattern rather than an unproven agent layer.

**Takeaway for future phases:** avoid `Chain Tool` + `Conversational Retrieval QA Chain` combinations in Flowise entirely. If multiple retrieval-backed behaviors need to share a flow under the 2-flow limit, a single merged prompt with internal mode detection is the more reliable pattern on this platform, at the cost of a more complex prompt to maintain.

---

## Part 4 — Feature 5: Error Log Analyzer

### Design

Same dual-source pattern as Feature 4:

1. **`error-signatures-plaintext.txt`** — structured ground truth for ESP32 reset reason codes (`rst:0x...`), Guru Meditation / panic exception types, stack canary, backtrace handling guidance, and Wi-Fi error prefixes. Verified against ESP-IDF's own reset reason enum before writing, rather than relying on unverified memory.
2. **`common-failures.md`** — a curated, manually-authored RAG document (matching the PRD's own planned `failure-library/common-failures.md`, WF4) added to the existing Pinecone index, covering deeper engineering explanations (e.g. why brownouts correlate with Wi-Fi activation) with citations. Chosen deliberately over indexing the full 600+ page ESP32 Technical Reference Manual, which would have been slow, expensive on the Cohere trial quota, and mostly irrelevant (register maps, peripheral addressing) to error diagnosis.

### Test Result

Ran the brownout scenario (`rst:0x0f (RTCWDT_BROWN_OUT_RESET)`) after merging into the combined chain. **PASS** — correctly identified the signature, correctly classified as a hardware/power-delivery cause (not firmware), and the Likely Cause field was a genuine paraphrase of `common-failures.md`'s actual reasoning (inadequate current delivery, not voltage regulation) rather than a generic guess.

**Minor open items, not blocking:** the model didn't ask about Wi-Fi-timing correlation (the strongest diagnostic signal per the failure library) even though it was available in the retrieved chunk; and two irrelevant "Solomon Systech" (SSD1306-manufacturer) source chips appeared alongside the correct ones, suggesting some retrieval-precision noise. Both logged as watch items for future testing rather than fixed now — only one scenario has been run against this feature so far (Guru Meditation and stack canary scenarios remain untested).

---

## Part 5 — Feature 6: Professional Diagnostic Report Generator

### Design

Added as a third mode to the same combined chain (avoiding the 2-flow limit again, consistent with Part 3's resolution). Takes a pasted diagnostic session (transcript, JSON state dump, or both) and synthesizes it into the PRD's required 10-section Markdown report, plus an 11th unnumbered "Learning Resources" appendix (Supporting Feature C).

### Build Issues Found and Fixed

| Issue | Fix |
|---|---|
| Hypotheses Considered rendered as a flat list with no elimination status or evidence, despite an explicit prose instruction requiring both | Replaced prose instruction with a WRONG/RIGHT few-shot example — fixed on first retry |
| Documentation References listed plausible-sounding but never-actually-cited sources (e.g. "ESP32 board profile for I2C pin specifications") when the input session contained no real citations | Added an explicit honesty requirement with a WRONG/RIGHT example: state "no citations recorded" rather than inventing sources, and route plausible follow-up reading into Learning Resources instead | 
| Root Cause Identified section dropped the confidence score entirely, even though it was present in the source session data | Added an explicit standalone reminder that the confidence percentage must always be carried into this section if present anywhere in the input — fixed on first retry |

### Test Results

Two tests run, both passing after fixes:
1. **Compressed session summary** (single-message, cleaned-up version of the T7 conclusion) — passed after the Hypotheses/Documentation fixes.
2. **Full raw T7 transcript** (all 7 turns, exactly as originally produced by diagnostic-agent, including question counters and JSON state blocks) — the more realistic and harder test. **All chat scaffolding was correctly stripped** (`[Question N of 10]` tags, raw JSON braces) — the report read as a genuine standalone document. Confidence score fix also confirmed working on this run.

**Observed variance (not a defect):** across the two Report Generator runs, hypothesis granularity differed slightly — one run kept "I2C communication issue" and "I2C pull-up resistor issue" as two separate hypotheses, the other merged them into one. Consistent with the turn-to-turn stochastic variance observed throughout this project on Llama-3.3-70B; not something a report-formatting prompt can or should try to eliminate.

---

## Phase 4 Evaluation Summary

| Check | Result |
|---|---|
| Phase 3 T7 scenario, end-to-end with RAG | ✅ Pass (3 runs; citation fix confirmed working, not 100% reliable) |
| Feature 4 (Compatibility Checker) built and validated | ✅ Pass (T17-T19, including one real safety-relevant bug caught and fixed) |
| Feature 5 (Error Log Analyzer) built and validated | ✅ Pass (1 of several planned scenarios tested) |
| Feature 6 (Report Generator) built and validated | ✅ Pass (2 tests, 3 prompt fixes all held) |
| 2-flow platform limit handled | ✅ Resolved via merged multi-mode prompt architecture |
| Chain Tool + Retrieval QA Chain bug | ⚠️ Confirmed unfixable platform bug, routed around structurally |
| Board profile / error signature ground-truth files | ✅ Built, verified against real sources before use |
| AMS1117 corpus gap | ✅ Found via testing, fixed by sourcing and loading the official datasheet |

---

## Next Steps

1. Run additional Error Log Analyzer scenarios (Guru Meditation panic, stack canary) to bring Feature 5's validation rigor in line with Feature 4's.
2. Investigate the minor retrieval-precision noise in Feature 5 (irrelevant source chips, incomplete diagnostic-approach retrieval) if it recurs.
3. Consider whether `common-failures.md`'s chunking is too coarse (one retrieved chunk spanned the document intro plus two unrelated failure sections) — revisit if future queries show cross-topic contamination.
4. Fill out remaining Tier 4 scenarios if fuller PRD test-suite coverage is wanted before integration.
5. **Integration phase** (wiring Compatibility Checker, Error Log Analyzer, and Report Generator into the main diagnostic-agent flow as callable tools) is deferred to its own future phase, to be scoped and tested separately rather than bolted on mid-build — consistent with the project's standing build-test-document-proceed rhythm applied one level up.
6. Given today's Groq TPD ceiling finding, pace future full-suite validation sessions across multiple days rather than attempting them in one sitting.
