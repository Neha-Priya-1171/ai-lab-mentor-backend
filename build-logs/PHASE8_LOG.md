# AI Lab Mentor — Phase 8 Build Log

**Phase:** 8 — Final Scope Cut, Grounding Backstop, Cleanup & Release
**Date:** 2026-07-18 to 2026-07-23
**Stack:** Unchanged from Phase 7 — FastAPI, Groq (`llama-3.3-70b-versatile`) / Google Gemini (`gemini-3.5-flash`), user's own key, Cohere + Pinecone shared retrieval
**Status:** ✅ Scope finalized at 5 tools + Viva Mode | ✅ Real live-caught fabrication bug closed with a code-level backstop | ✅ Dead code and orphaned tests removed | ✅ Docs, `.gitignore`, and license finalized for release | ✅ 60/60 structural tests passing

---

## 1. Objective

Phase 7 closed with four candidate tools prototyped (Symptom → Root Cause Mapping, Component Replacement Suggestion, Sensor Calibration Assistant, AI Lab Notebook) on top of the five already-validated Phase 6/7 tools, plus AI Lab Viva Mode. Phase 8's job was not to add another capability — it was to decide, honestly, which of those nine were actually worth shipping, close out a real bug the expanded surface area exposed, and bring the repo itself up to the same standard the code had already been held to.

This phase also marks a deliberate change in what "done" means for this project: every prior phase asked "what should we build next." This one asked "what should we remove," which is a different, harder discipline — the value of catching a scope creep problem and having the record to prove it was noticed and corrected, not just accumulated forever.

---

## 2. The Scope Decision — 9 Capabilities Down to 6

At its widest point, the app's frontend looked like this (`build-logs/assets/phase8-before-bloated-ui-and-fabricated-locator-bug.png`):

```
LIVE TROUBLESHOOTING     Power Budget · Multimeter · Browse Issues
PARTS & SENSORS          Replacement Ideas · Calibration Help
THIS SESSION             Generate Report · Quiz Me · Save to Notebook
```

Eight buttons across three groups, for a project whose own stated design principle (`CLAUDE_CODE_PREREQUISITES.md`) is "minimal and useful over feature-broad." Two concrete problems drove the cut, not just a preference for tidiness:

1. **Groq's free-tier TPM ceiling is real and load-bearing** (fully diagnosed in `PHASE7_LOG.md`) — every additional tool schema is a measured, recurring cost on every single turn, not a one-time build cost. Nine tool schemas would have made the already-tight 12,000 TPM budget worse, not better.
2. **Not every tool met the project's own grounding bar.** `component_replacement.py` and `sensor_calibration.py` both carry an explicit `VERIFICATION STATUS` docstring stating their reference data was written from training knowledge and never checked against a real datasheet, unlike `ground_truth.py`'s board profile (traced to Espressif's own docs) or the AMS1117 dropout figures (checked against the real manufacturer PDF in Phase 4). Shipping those two meant shipping a lower grounding guarantee under the same "never invent a number" banner the rest of the app enforces.

**Decision:** keep the guided diagnostic loop, `check_component_compatibility`, `analyze_error_log`, `guide_multimeter_measurement`, `calculate_power_budget`, `generate_diagnostic_report`, and AI Lab Viva Mode (prompt-only, no schema cost). Cut `map_symptom_to_root_cause`, `suggest_component_replacement`, `guide_sensor_calibration`, and `generate_notebook_entry` from the running app entirely, rather than leaving them wired but de-prioritized.

The frontend was simplified back down to the original four-button "Live Troubleshooting" set (`Power Budget Check`, `Multimeter Assistant`, `Generate Report`), matching `build-logs/assets/phase7-demo-multimeter-session.png` — the last known-good UI state before the Phase 8 expansion.

---

## 3. The Bug That Made the Cut Non-Optional

The same wide-scope screenshot that documents the UI bloat also happens to be live-caught evidence of exactly the fabrication failure mode `grounding_guard.py` was built to catch. In that session, asking whether an LD1117V33 could substitute for an AMS1117 produced:

> "The ESP32 requires a power supply capable of delivering 500 mA or more (per the **ESP32 Series Datasheet v5.2**)."

No such retrieval happened that turn — "ESP32 Series Datasheet v5.2" is an invented document name and version tag, attributed with full confidence to a source that was never actually pulled. This is the identical failure pattern already documented twice in `system_prompt.md`'s Viva Mode section (the GPIO current-limit and relay pull-in-voltage incidents) — a prompt-only Hard Rule failing live, on a third distinct topic, after two prior prompt patches.

Per this project's own bounded-patching principle (two failed attempts → stop patching prompts, drop to code), this was the trigger for `grounding_guard.py`: a deterministic, regex-based post-generation check that strips any `<Document Name> <Datasheet/Spec/Reference Manual> <version/section/page locator>` pattern unless that exact locator string appears verbatim in what was actually retrieved that turn. 8 structural tests (`test_grounding_guard.py`) cover the fabricated-vs-genuine locator distinction, case-insensitivity, and multi-locator replies. A debug `print()` left in from initial verification was removed once the guard was confirmed live.

**Scope note, documented rather than silently left implicit:** `grounding_guard.py`'s `build_grounded_text()` only pulls from the current turn's tool-role messages and the system prompt's Context block — not earlier assistant turns. A locator legitimately established several turns ago (which Viva Mode's own prompt rule permits reusing) could still get stripped if referenced again later. The failure direction is safe — over-cautious, not under-cautious — so this was flagged in the module's docstring for a future pass rather than blocking release on it.

---

## 4. Cleanup — Dead Code, Orphaned Tests, Repo Hygiene

With `tools/dispatcher.py` and `tools/schemas.py` already trimmed to the final 5-tool table (done earlier in this phase), the following were confirmed orphaned and removed:

| Removed | Why |
|---|---|
| `tools/component_replacement.py`, `tools/sensor_calibration.py`, `tools/lab_notebook.py`, `tools/symptom_map.py` | No longer imported by `dispatcher.py` or `schemas.py` — dead code |
| `test_component_replacement.py`, `test_sensor_calibration.py`, `test_lab_notebook.py`, `test_symptom_map.py` | Imported dispatcher functions that no longer existed — these were failing `pytest` collection with `ImportError` before removal, not just sitting unused |
| Stale `__pycache__/` directories | Held compiled bytecode for already-deleted source files, confirmed via `find` before deletion |

Additional fixes applied this phase:

- **`grounding_guard.py`** — removed the leftover `TEMP` debug `print()`.
- **`agent.py`** — `provider_extra` (Gemini's `thought_signature`) is now only attached to a tool-call entry when a provider actually populated it, instead of unconditionally sending `"provider_extra": null` on every Groq request. This was flagged specifically because it mirrors the exact failure category (an unexpected key in the tool-call wire shape) that caused Phase 6's documented Groq 400 error — an untested assumption riding on the same sensitivity, closed before it could become a second incident.
- **`.gitignore`** — added `.pytest_cache/` and `.DS_Store`, neither of which were covered before (confirmed via `git check-ignore -v` that `.env` and `venv/` were already correctly ignored; no key exposure at any point this phase).
- **`README.md`** — architecture diagram, tool count, and test count brought back in sync with the actual codebase (was documenting `map_symptom_to_root_cause` as shipped after it had already been cut in code — the single most reviewer-visible inconsistency found this phase). Added a "Descoped Features" section stating what was cut and why, rather than leaving four tools' worth of real work invisible.

---

## 5. Verification

```
===================================== 60 passed in 1.10s ======================================
```

Full suite, zero failures, run after every change in this phase (orphan removal, `agent.py` edit, `grounding_guard.py` edit) — not just once at the end. `git status` / `git check-ignore -v .env venv` confirmed clean before push: no secrets, no cache artifacts, no orphaned files left staged.

---

## 6. License

Project released under the MIT License — permissive, standard for a public portfolio repo, no obligation created for anyone who forks or reuses it beyond preserving the copyright notice.

---

## Phase 8 Evaluation Summary

| Check | Result |
|---|---|
| Final tool scope decided and documented (not just implemented) | ✅ Pass — 4 tools cut, reasons stated in README's "Descoped Features" |
| Live-caught fabrication bug (fabricated datasheet version) closed | ✅ Pass — `grounding_guard.py`, 8/8 tests passing |
| Orphaned modules and tests removed | ✅ Pass — 4 modules + 4 test files, confirmed via `find`/`grep` before deletion |
| Known wire-format risk in `agent.py` closed pre-emptively | ✅ Pass — `provider_extra` no longer sent as `null` |
| `.gitignore` hardened | ✅ Pass — `.pytest_cache/`, `.DS_Store` added |
| README synced to actual shipped scope | ✅ Pass — tool count, architecture diagram, test count all corrected |
| Full test suite passing after every change | ✅ Pass — 60/60, verified repeatedly, not just once |
| License added | ✅ Pass — MIT |
| No secrets staged before push | ✅ Pass — confirmed via `git check-ignore -v` |

---

## Next Steps

None planned — this phase closes the project's active development. The `V2_ROADMAP.md` items beyond this point (Phase 9 multimodal circuit-image analysis, Phase 10 schematic/waveform/logic-analyzer reading) remain a documented possibility, not a commitment, and would start as their own phase with the same build-test-document rhythm as everything before it, if picked up again.
