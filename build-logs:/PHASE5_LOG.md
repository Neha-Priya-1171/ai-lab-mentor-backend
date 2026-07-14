# Phase 5 Log — Supporting Features (A, B, C)

**Status:** Complete
**Scope:** Supporting Feature A (Engineering Reasoning), Supporting Feature B (Confidence Score), Supporting Feature C (Learning Resources)
**Prompts touched:** `combined-system-prompt-v2.md` (Compatibility Checker + Error Log Analyzer + Report Generator chain), `diagnostic-engine-prompt.md` (core Observe→Ask→Measure→Eliminate→Conclude diagnostic engine)

---

## Summary

All three Supporting Features from the PRD are implemented and validated. Feature C turned out to already exist from Phase 4's Report Generator work and didn't need new functionality — only test coverage and one hardening patch. Features A and B required new prompt rules, each of which had at least one real bug caught during proxy testing before any Groq quota was spent.

Testing methodology for this phase: a Claude-powered proxy test harness (Claude Sonnet standing in for Llama-3.3-70B) was built for each feature, calling the Anthropic API directly from an HTML artifact with the actual candidate system prompt embedded. This validates prompt logic and structure cheaply and quickly. **It does not replace real Llama-3.3-70B validation on Flowise** — Claude and Llama can diverge in behavior, particularly on the kind of turn-to-turn formatting consistency this stack has previously shown variance on. A real Flowise/Groq confirmation pass for all three features is still outstanding and is the top item in Next Steps.

---

## Feature A — Engineering Reasoning

**Goal:** Every cause, fix, or recommendation must explain the underlying mechanism (Ohm's Law, current budgets, physical cause-and-effect) rather than stating a bare label or instruction.

**Implementation:** Added a new Shared Rule to `combined-system-prompt-v2.md` (applies across Compatibility Checker, Error Log Analyzer, and Report Generator modes), plus a dedicated worked example for Guru Meditation panics inside Error Log Analyzer mode, and tightened the `Likely Cause` field spec to explicitly require mechanism, not just cause name.

**Bug caught — sourcing/reasoning rule conflict:**
The first draft's Shared Rule example modeled good reasoning depth (USB current limits, Wi-Fi TX current draw) but stated those numbers as plain fact, violating an existing, older Hard Rule requiring unsourced numbers to be flagged as general engineering knowledge. Proxy testing on a brownout scenario reproduced this exactly — the model invented several current/voltage figures with no "(unverified — general knowledge)" style flag, essentially copying the pattern demonstrated in our own flawed example.

*Root cause:* the new example was written to demonstrate one rule (mechanism depth) without checking it against a second, older rule (sourcing discipline) already active in the same prompt. Two correct rules, incompatible example.

*Fix:* rewrote the Shared Rule example to satisfy both rules simultaneously — mechanism explained, and every unsourced number explicitly labeled as general engineering knowledge — with an explicit line tying the two rules together so future edits don't re-diverge them.

*Verification:* re-ran the same brownout scenario after the fix. Model correctly flagged SG90 stall current and brownout trip voltage as general knowledge with a "verify against your specific part's datasheet" caveat. Confirmed pass.

**Test results (Claude proxy, T13 + brownout + control + regression):**

| Test | Result |
|---|---|
| T13 — Guru Meditation / LoadProhibited | PASS (2 runs, consistent reasoning both times) |
| Brownout reset (rule generalization check) | FAIL → PASS after 1 patch |
| DEEPSLEEP_RESET (over-explanation control) | PASS — no bloat on trivial/expected reset codes |
| Compatibility Checker missing-info (regression) | PASS — Asking vs. Concluding mutual exclusivity intact |

---

## Feature B — Confidence Score

**Goal:** Display a ranked, percentage-based hypothesis list during the live diagnostic session, updating each turn, as a clean field the Flowise output parser can extract separately from the full session state.

**Implementation:** Added a `HYPOTHESIS DISPLAY` block to `diagnostic-engine-prompt.md`, placed between `QUESTION COUNTER` and `PROJECT MEMORY`. This is a display-only rule — hypothesis tracking with confidence values already existed in `diagnostic_state.hypotheses`; this feature only adds a clean, separately-parseable rendering (`Current hypotheses: ● [label] — [confidence]%`) that must stay in sync with the state block's decimal values in the same response.

Testing used an interactive multi-turn harness (not a scripted transcript) — since the model's exact question order can't be predicted in advance, the harness lets the tester answer live like a real T7 (OLED blank / I2C) session, auto-parsing each turn for counter presence, list presence/absence at the correct stage, and list-to-state percentage sync.

**Bug 1 — fabricated confidence on eliminated hypotheses:**
When a hypothesis was eliminated mid-session, the model kept it in the visible ranked list with an invented `0% (eliminated)` annotation. `eliminated_hypotheses` in state has no confidence field, so that 0% was fabricated, not sourced from state — a violation of the "list is a rendering of state, not a second source of truth" rule.

*Fix:* explicit instruction that the ranked list renders `diagnostic_state.hypotheses` only, never `eliminated_hypotheses`; eliminations belong in prose and the eliminated_hypotheses field, not the ranked list. Added WRONG/RIGHT example.

**Bug 2 — ranked list and final diagnosis co-displayed:**
When confidence crossed the 85% threshold and conclusion triggered in the *same* turn as the last hypothesis update, the model showed both the updated ranked list and the full four-field diagnosis (Root Cause/Evidence/Confidence/Recommended Confirming Test) in one response. The original rule said "suppress the list once concluded" but didn't account for same-turn transitions with no prior "already concluded" turn to anchor the suppression to.

*Fix:* reframed as a mutual-exclusivity rule (explicitly parallel to the existing Asking-vs-Concluding pattern in the combined prompt) — a response containing "Root Cause:" must never also contain "Current hypotheses:", regardless of which turn triggers conclusion. Added WRONG/RIGHT example showing the same-turn case specifically.

**Verification:** ran two independent full T7 sessions after both fixes, with different hypothesis sets and different question orderings. Both sessions showed clean eliminations (no fabricated confidence) and correct list suppression at CONCLUDE. Confirmed pass on both.

---

## Feature C — Learning Resources

**Finding:** This feature already existed. The Report Generator mode's unnumbered "Learning Resources" section (built during Phase 4 / Feature 6 work) already matched the PRD's three required categories — datasheet sections, ESP-IDF/Arduino-ESP32 docs, example projects/code — nearly word for word. No new prompt content was needed.

**Lesson for future phases:** check existing prompts against the full feature list before writing new patches. Work can already be done without having been explicitly labeled against the PRD item it satisfies.

**What Phase 5 did add:** test coverage (this section had never been tested) and one hardening patch.

**Bug — unhedged specific document locators:**
A proxy test using a real completed T7 transcript produced a Learning Resources item citing "Section 8" of the SSD1306 datasheet as fact. No datasheet chunk was actually retrieved during that session — the section number was invented. A second test on the same feature, run on a compressed/no-citation session summary, handled the equivalent case correctly (hedged, no invented locator) — inconsistent behavior across otherwise-similar inputs.

*Fix:* added an explicit rule that specific section/page/chapter locators may only be stated if they came from retrieved context; general topic pointers are fine, invented specific locators are not. Added WRONG/RIGHT example using the actual SSD1306 case that surfaced the bug.

**Verification:** re-ran the same full T7 transcript test post-fix. The SSD1306 entry changed from an unhedged "Section 8" claim to a hedged general pointer, matching the already-correct compressed-summary run. Confirmed pass on both test cases.

**Test results (Claude proxy):**

| Test | Result |
|---|---|
| Learning Resources — full real T7 transcript | FAIL (unhedged section number) → PASS after 1 patch |
| Learning Resources — compressed/no-citation summary | PASS (both before and after patch) |

---

## Known Limitations / Carried Forward

- Question-bundling remains an accepted v0.1 limitation (unchanged from prior phases).
- Llama-3.3-70B turn-to-turn behavioral variance remains a known constraint — all Phase 5 proxy tests used Claude Sonnet as a stand-in, which validates prompt logic but not final model behavior.
- All three features are validated via proxy testing only. **Real Flowise/Llama-3.3-70B confirmation has not yet been run for Features A, B, or C.**

## Next Steps

1. Run the real Flowise/Llama-3.3-70B confirmation pass for Features A, B, and C — reuse the exact test inputs already validated via proxy (T13, brownout, DEEPSLEEP_RESET, Compatibility missing-info, full T7 session, compressed-summary session) rather than spending quota on new exploratory cases.
2. Proceed to Workflow Enhancement Features (WF1–WF6) or the 50-scenario evaluation suite, per PRD roadmap — decision pending.

## Files Delivered This Phase

- `combined-system-prompt-v2.md` — patched with Feature A Shared Rule + Guru Meditation example, Feature C locator-hedging rule
- `diagnostic-engine-prompt.md` — patched with Feature B Hypothesis Display rule
- `feature_a_test_harness.html` — proxy test harness (T13, brownout, control, compatibility regression)
- `feature_b_hypothesis_sync_test.html` — interactive multi-turn proxy test harness (T7 sync checks)
- `feature_c_test_harness.html` — proxy test harness (full transcript + compressed summary)
