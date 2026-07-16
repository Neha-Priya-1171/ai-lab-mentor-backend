# Circuit Diagnostic AI — Phase 7 Build Log

**Phase:** 7 — Quick-Win Text-Only Tools (Power Budget Calculator, Multimeter Assistant, Symptom → Root Cause Mapping)
**Date:** 2026-07-15
**Stack:** Unchanged from Phase 6 — FastAPI, Groq (llama-3.3-70b-versatile) / Google Gemini (gemini-3.5-flash), user's own key, Cohere + Pinecone shared retrieval
**Status:** ✅ All three tools built, unit-tested, live-tested | ✅ `generate_diagnostic_report` (open item carried from Phase 6) now live-tested | ⚠️ Groq TPM ceiling hit — real, currently open | ⚠️ Possible phantom-hypothesis issue in Report Generator flagged, not yet confirmed | 🔜 Multimeter Assistant not yet live-tested

---

## 1. Objective

Per `V2_ROADMAP.md`, Phase 7 is the "lowest technical risk" set — three tools extending the Phase 6 tool-calling architecture without touching its core mechanics:

1. **Power Budget Calculator** — mostly deterministic math (Ohm's Law, current summation), implemented as a real function tool rather than LLM-guessed arithmetic.
2. **Multimeter Assistant** — guided prompts for taking and interpreting a measurement.
3. **Symptom → Root Cause Mapping** — a browsable, queryable version of the existing `common-failures.md` knowledge base.

Also folded in: closing Phase 6's one carried-over open item, live-testing `generate_diagnostic_report`, which had structural test coverage but no real-model confirmation.

---

## 2. Architecture

No changes to `agent.py` or the provider abstraction — all three tools slot into the existing `dispatch()` table and `ALL_TOOLS` list from Phase 6. Each follows the established split: universal/deterministic facts live in a self-contained, independently-testable module; anything board-specific reuses `ground_truth.py`; anything datasheet-specific goes through the existing `_retrieve()` hook. No new Cohere/Pinecone wiring was needed for any of the three.

```
tools/
├── power_budget.py         — pure Ohm's-Law/current-summation math + dispatcher-facing string formatter
├── multimeter_reference.py — universal meter-usage facts + digital-logic HIGH/LOW rule of thumb
├── symptom_map.py          — 5-category browsable index, built only from signatures already
│                              validated in this project's own Phase 1–6 logs
├── schemas.py               — extended with 3 new tool schemas (bare-dict format, matching
│                              the project's existing convention, not OpenAI's nested wrapper)
└── dispatcher.py            — extended with calculate_power_budget, guide_multimeter_measurement,
                               map_symptom_to_root_cause, each combining the above sources
```

---

## 3. Build Steps

| Tool | Design | Key source split |
|---|---|---|
| **Power Budget Calculator** | Pure Python function (`calculate_power_budget`) doing Ohm's Law + current summation, wrapped by `format_power_budget_result` for the dispatcher's `str`-return contract. Flags a component as missing data rather than guessing a current draw. Separately tracks steady-state vs. peak/stall current (servo scenario) and the 80% continuous-derating convention as a distinct threshold from the rated max. | No ground truth / no RAG needed — self-contained arithmetic only. |
| **Multimeter Assistant** | `multimeter_reference.py` holds universal, verifiable facts (DC voltage/resistance/continuity/current setup, probe placement, safety notes) plus a digital-logic HIGH/LOW/INDETERMINATE interpreter using a 70%/30%-of-VCC rule of thumb — explicitly labeled a convention, never presented as a specific chip's real VIH/VIL spec. `dispatcher.py`'s `guide_multimeter_measurement()` combines this with `gt.normalize_gpio`/`gt.lookup_pin` for GPIO-specific notes (input-only pins, strapping-pin warnings) and falls back to `_retrieve()` for named components — same combined-source shape as `check_component_compatibility`. Also the structured hook for the project's Rule 4 ("measurement before speculation," established Phase 1). | Ground truth (GPIO board profile) + RAG fallback, same split as Phase 4/6. |
| **Symptom → Root Cause Mapping** | `symptom_map.py` holds a 5-category browsable index (I2C communication, power/brownout, firmware crash, output driver mismatch, sensor erratic) built only from failure signatures this project's own phase logs already validated — nothing invented. `dispatcher.py`'s `map_symptom_to_root_cause()` supports three modes: pure browse (no args), category lookup, and free-text query against the existing shared retriever (which already indexes `common-failures.md` since Phase 3). Explicitly reminds the model never to cite `common-failures.md` unless something was actually retrieved that turn. | Static category index + existing shared RAG corpus, no new indexing. |

All three were built against the real `agent.py`/`dispatcher.py`/`schemas.py` files (uploaded mid-phase) rather than guessed interfaces, after an initial draft incorrectly assumed OpenAI's nested `{"type": "function", "function": {...}}` schema wrapper — corrected once the real `schemas.py` showed the project's actual bare-dict convention.

---

## 4. Issues Found and Fixed

| Issue | Root Cause | Fix |
|---|---|---|
| Test file `sys.path` assumed a `tests/` subfolder | Guessed at project layout instead of checking it | Corrected to match the project's actual flat layout — test files live at project root, confirmed via a Finder screenshot |
| Initial tool schema draft used OpenAI's nested function-wrapper format | Built before seeing the real `schemas.py`; assumed the generic convention rather than this project's actual bare-dict shape | Rebuilt against the real uploaded `schemas.py`/`dispatcher.py`/`agent.py` |
| Groq `413`: `Request too large... tokens per minute (TPM): Limit 12000, Requested 13180` | 6 tool schemas now sent on every turn (~2,793 tokens) on top of `system_prompt.md` (~21KB) and a growing YAML state block repeated in conversation history — confirmed `llama-3.3-70b-versatile`'s real free-tier ceiling is 12,000 TPM (verified via web search, not assumed) | Trimmed the three new tool schemas' description text (structure/types/enums untouched) — cut combined schema size from ~2,793 to ~1,932 tokens (~31%). **Did not fully resolve it** — a fresh-session first message still hit `Requested 12088` against the same 12,000 limit. Per the project's bounded-patching rule, stopped further micro-trimming after this second attempt and reclassified as a structural issue rather than a wording one. |
| (Investigated, not a fix) Whether switching Groq models would help | Checked via web search — most free-tier Groq models share the same or worse TPM ceiling; the one meaningfully higher-TPM model (Gemma 2 9B) has an 8K context window, too small for this project's system prompt + tool schemas | Not viable. Two real remaining levers identified, neither implemented yet: (1) Groq prompt caching — cached tokens reportedly don't count toward TPM, worth investigating docs directly; (2) trimming `system_prompt.md` itself, already flagged as a contingent next step in `PHASE6_LOG.md` and now genuinely triggered by a recurring blocker. |

---

## 5. Verification Testing

### Structural / unit tests (no real API calls, no quota spent)

| Test file | What it covers | Result |
|---|---|---|
| `test_power_budget.py` | Pure math, Ohm's Law derivation, quantity multiplication, peak-vs-steady separation, 80%-derating flag, missing-data handling, invalid-input errors, dispatcher-facing formatter contract | ✅ 15/15 pass |
| `test_multimeter_reference.py` | Meter setup facts (all 4 measurement types), series-vs-parallel current placement, power-off safety notes, digital logic HIGH/LOW/INDETERMINATE thresholds, continuity interpretation (beep and raw-ohms paths) | ✅ 14/14 pass |
| `test_symptom_map.py` | Category presence/fields, browsing, case/label-tolerant lookup, formatted output with/without a documented signature or related tool | ✅ 12/12 pass |
| Full project suite (incl. pre-existing Phase 6 files) | `test_agent_loop.py`, `test_tools.py`, `test_integration.py`, `test_gemini_thought_signature.py` + all Phase 7 additions | ✅ 59/59 pass |

### Live testing (real Groq and Gemini keys, real Cohere/Pinecone retrieval)

| Test | Provider | Result |
|---|---|---|
| `I've got a 5V/500mA USB port powering an ESP32, an SSD1306 OLED, and 3 SG90 servos. Will it hold up?` (fresh session) | Groq | ✅ Pass — `calculate_power_budget` self-triggered with no hardcoded routing; correctly asked for missing SG90 stall current rather than guessing it |
| `My OLED screen is blank. What's usually the cause of that?` (fresh session) | Gemini, then Groq on a later turn | ✅ Pass, strong positive signal — `map_symptom_to_root_cause` self-triggered on the very first message. By Q2, the ranked hypothesis list already included "Missing I2C pull-up resistors — 15%" alongside three other leads. This is meaningfully ahead of the Phase 2 (pre-RAG) baseline, which took until Q2–3 to form any hypothesis at all and never reached pull-up-specificity without RAG — real evidence the tool's retrieved content is feeding the hypothesis, not just decorating the response. |
| Full completed T7-style transcript (I2C address-mismatch scenario, 8 questions) → `Can you generate a full diagnostic report for this session?` (fresh session, per-tool test) | Gemini | ✅ Pass — full 10-section report + Learning Resources appendix produced. Verified individually against every specific Phase 4/5 bug fix: **Hypotheses Considered** shows elimination status + evidence per item, not bare labels; **confidence score** correctly carried into Root Cause Identified; **Documentation References** correctly stated no citations were made rather than inventing a plausible one; **Engineering Rationale** gives real mechanism (I2C ACK-bit / charge-pump behavior), not a label. |

**Closes the one Phase 6 open item** — `generate_diagnostic_report` now has real-model confirmation, not just structural test coverage.

### Not yet tested

- **Multimeter Assistant** has structural test coverage only — no live session has actually exercised `guide_multimeter_measurement` against a real model yet.
- **Possible phantom-hypothesis issue in the Report Generator run above:** the output's `eliminated_hypotheses` state block included *"Software configuration issue (missing display.display() or initialization)"* — a hypothesis never actually raised or eliminated anywhere in the real 8-question transcript it was given. This may be the same invented-plausible-content failure mode Phase 4/5 caught in the Documentation References field (few-shot-fixed there), just surfacing in a different field here. **Not yet confirmed as reproducible** — flagged for a regression rerun on the same or a similar transcript before treating it as a real, fixable bug, per the project's own "document what didn't work, not just what did" principle.

---

## 6. Known Limitations Carried Into Next Steps (Updated — Post Live Testing)

**Resolved this phase, after the sections above were first drafted:**

- **Real bug found via live testing, fixed:** `guide_multimeter_measurement` was fabricating measurements and results in the user's voice when called with `measured_value` omitted — a direct violation of Rule 4 (measurement before speculation) and Hard Rule 1 (no unsourced numbers), just expressed as invented dialogue instead of a stated fact. Root cause: the three Phase 7 tools were wired into `dispatcher.py`/`schemas.py` but never described in `system_prompt.md` — no output-format spec existed for any of them, unlike the original three tools' `Verdict:`/`Signature:`/report structures. Fixed with a new "Never Fabricate the User's Real-World Actions or Results" Shared Rule (WRONG/RIGHT example, same technique as every prior successful fix on this stack) plus output-format specs added for all three Phase 7 tools. **Confirmed fixed on a full live retest** — a real relay/brownout session correctly requested a measurement, genuinely waited, and used the user's actual reported reading (5.01V idle → 4.15V active) to drive the conclusion.
- **UI quick-action buttons added:** Power Budget Check, Multimeter Assistant, Browse Known Issues, Generate Report — wired into `static/index.html`, reusing the existing `send()`/history flow. Generate Report starts disabled until the first real exchange.

**Open, lower-priority finding — not yet confirmed as a bug:** unhedged specific numbers (e.g. "240mA Wi-Fi burst," "70-100mA relay coil," a precise "ESP32 Series Datasheet v5.2" citation) appeared in both a generated report and, separately, in a live Conclude-stage Evidence field — suggesting this may be a general conclusion-stage sourcing-discipline gap, not confined to the Report Generator. A debug print was added to `generate_diagnostic_report` to check whether these numbers are genuinely retrieved or fabricated, but the check was never completed (blocked by the Groq/Gemini rate-limit investigation below eating the rest of the session). **First item for Phase 8.**

**Groq TPM ceiling — fully diagnosed, root cause pinned down exactly, will not be fully solved without a different provider or a paid tier:**

Three real, verified interventions were made, in order:
1. Trimmed the 3 new tool schemas' description text: ~2,793 → ~1,932 tokens (rough estimate).
2. Lowered Groq's default `max_tokens` from 4096 → 2560 in `providers/groq_provider.py`, after confirming (via an exact-match arithmetic check: `16083 - 14547 = 1536 = 4096 - 2560`) that Groq's TPM limiter reserves the full `max_tokens` against the budget, not just the actual prompt content.
3. Trimmed `system_prompt.md` prose (~461 tokens, conservative — no WRONG/RIGHT examples or Core Rules touched) and added `get_relevant_tools()` — a per-turn tool filter that always sends the 4-tool "live troubleshooting" cluster (compatibility, error log, power budget, multimeter — confirmed via live testing to genuinely chain together in one session) and conditionally excludes only Report Generator or Symptom Mapping, biased toward inclusion on any ambiguity.

**Final, confirmed number:** after all three fixes, a fresh-session first message request measured `13,970` tokens — down from the original `16,083`, a real `~2,113` token reduction. Subtracting the reserved `max_tokens` (2,560) leaves `~11,410` tokens of actual prompt+tools+message content — genuinely under the 12,000 limit on its own. **The entire remaining overage is the `max_tokens` reservation itself** — only ~590 tokens of real response headroom remain, nowhere near enough for a real diagnostic response, hypothesis list, or report.

**Conclusion, not further pursued this phase (bounded-patching stop point):** this is the real ceiling. Further trimming would require either gutting `max_tokens` to a point that guarantees response truncation, or cutting into `system_prompt.md`'s tested WRONG/RIGHT examples and Core Rules — both explicitly ruled out as not worth it. **Gemini is the practical primary provider going forward; Groq remains usable for light/short turns and will predictably 413 on anything substantial** until Groq's own limits change or a higher-headroom provider is added (two more providers are planned).

---

## 7. Next Steps

1. Confirm or rule out the unhedged-citation finding (Conclude-stage and Report Generator both showed it) — the debug print is already in place in `generate_diagnostic_report`, just needs a completed test run.
2. Rerun the phantom-hypothesis regression check from the earlier Report Generator test (an eliminated hypothesis appeared that was never actually raised in the transcript).
3. Proceed to Phase 8 (AI Lab Viva Mode, Component Replacement Suggestion, Sensor Calibration Assistant, AI Lab Notebook) per `V2_ROADMAP.md`.
4. If Groq's constrained headroom becomes a recurring problem for real users (not just testing), revisit once the 2 additional planned providers are added — one of them may have more comfortable free-tier limits.
