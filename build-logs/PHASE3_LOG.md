# Circuit Diagnostic AI — Phase 3 Build Log

**Phase:** 3 — Datasheet-Aware RAG (Retrieval-Augmented Generation)
**Date:** 2026-07-02
**Stack:** Flowise Cloud → ChatGroq (llama-3.3-70b-versatile) → Buffer Memory → Conversational Retrieval QA Chain → Cohere Embeddings (embed-english-v3.0) → Pinecone (serverless, free tier)
**Status:** ✅ Core RAG pipeline functional and verified | ⚠️ Sources UI not displaying (cosmetic) | ⚠️ Citation language inconsistent | 🔜 Full re-test of T7 (pull-up scenario) deferred to next session

---

## 1. Objective

Per the PRD (Feature 2 — Datasheet-Aware RAG), ground the AI's hardware claims in real component datasheets instead of general training knowledge, closing the gap identified at the end of Phase 2: the model correctly narrowed to the right *category* of fault (I2C communication) but never connected it to the specific documented failure pattern (missing pull-up resistors) because it had no real reference material to retrieve from.

---

## 2. Datasheet Sources (v1 scope, matches PRD's board-specific component list)

| Component | Source |
|---|---|
| ESP32 (main chip) | `espressif.com/sites/default/files/documentation/esp32_datasheet_en.pdf` (official Espressif) |
| SSD1306 (OLED driver) | `cdn-shop.adafruit.com/datasheets/SSD1306.pdf` (Adafruit-hosted, standard reference copy) |
| DHT22 (temp/humidity sensor) | `cdn-shop.adafruit.com/datasheets/Digital+humidity+and+temperature+sensor+AM2302.pdf` |
| SRD-05VDC-SL-C (5V relay module) | `circuitbasics.com/wp-content/uploads/2015/11/SRD-05VDC-SL-C-Datasheet.pdf` |

All 4 loaded via Flowise's Document Store → PDF File loader ("One document per page" chunking). Final combined corpus: **228 chunks** across all 4 datasheets, stored in a dedicated `ESP32 Circuit Datasheets` Document Store, kept separate from the Core Engine chatflow logic (per the PRD's instruction to preserve separation between board-specific knowledge and board-agnostic diagnostic engine reasoning).

---

## 3. The Embedding Provider Saga

Getting a working embeddings + vector store pipeline required **four separate provider attempts** before finding a stable pairing. Documented in full since each failure mode is a legitimate, reusable troubleshooting lesson.

### Attempt 1 — Google Gemini Embeddings (`gemini-embedding-001`)
- **Symptom:** `PineconeBadRequestError: Vector dimension 0 does not match the dimension of the index`
- **Investigation:** Confirmed the model name itself was current and correct (Google's Feb 2026 docs). Confirmed the model's real default output is 3072 dimensions (not 768, which was our initial — incorrect — assumption). Recreated the Pinecone index at 3072 dimensions; error persisted identically.
- **Root cause (best available conclusion):** Dimension 0 means the embedding call returned nothing at all — this points to the call failing before a vector was even generated, not a size mismatch. Tried both the original Gemini API key (same project that hit the Phase 1 free-tier `limit: 0` bug) and a freshly generated key in a new project. **Both failed identically.** This suggests an issue with Flowise Cloud's Gemini Embedding node/integration itself, not the Google account.
- **Resolution:** Abandoned, moved to a different provider rather than continue debugging a black-box integration issue.

### Attempt 2 — HuggingFace Inference Embeddings (`sentence-transformers/all-MiniLM-L6-v2`)
- **Symptom:** `HubApiError: ... Invalid username or password.`
- **Investigation:** Verified token permissions (Read token, inference access enabled). Web search confirmed this is a **known, actively-reported HuggingFace infrastructure bug** affecting this exact model — multiple independent developers hitting the identical error around the same period, tied to HF's migration to a new "Inference Providers" routing system.
- **Resolution:** Not a fixable issue on our end. Abandoned.

### Attempt 3 — Cohere Embeddings (`embed-english-v3.0`) ✅ SUCCESS
- **Setup:** Free Cohere trial API key, Pinecone index recreated at 1024 dimensions (Cohere's correct output size for this model).
- **Result:** Upsert succeeded immediately — 78/78 chunks added on first attempt (ESP32 datasheet), later 150 additional chunks added cleanly for the remaining 3 datasheets (228 total, verified via Pinecone's dashboard record count — no duplication, since Upsert only reprocessed new/changed loaders).
- **Verified via Flowise's "Test Retrieval" tool:** query *"What is the operating voltage of the ESP32?"* correctly returned semantically relevant chunks (power/reset section, product overview) despite no literal keyword match to "operating voltage" — confirming genuine semantic search, not keyword matching.

**Takeaway for future phases:** Cohere + Pinecone is the confirmed stable pairing for this project. If adding the Common Failure Library (Phase 3b/4) or any further embedding work, default to this pairing rather than re-attempting Gemini or HuggingFace embeddings.

---

## 4. Wiring Retrieval Into the Core Engine Chatflow

- Replaced the Phase 1/2 **Conversation Chain** node with a **Conversational Retrieval QA Chain**, which requires: Chat Model (Groq, unchanged), Memory (Buffer Memory, unchanged), and a new **Vector Store Retriever** input.
- **Issue:** The chatflow-level "Document Store" node's store-selector dropdown showed "No options," failing to list the already-working `ESP32 Circuit Datasheets` store, even after a hard refresh and node re-add.
- **Resolution:** Bypassed the Document Store node entirely. Wired a direct **Pinecone node** (same index, same credential) plus a matching **Cohere Embeddings node** (Type: `search_query`, to correctly encode live user questions rather than stored documents) straight into the chain's retriever input. This is functionally equivalent and considered the more standard Flowise pattern regardless.
- **Prompt structure change:** Conversational Retrieval QA Chain uses two separate prompts (Rephrase Prompt, left as Flowise default; Response Prompt, replaced with the full accumulated system prompt from Phases 1–2) rather than a single System Message field. A new `DATASHEET GROUNDING` instruction block was added to the Response Prompt, along with the required `{context}` placeholder where retrieved chunks are injected at runtime.

---

## 5. Verification Testing

### Test 1 — Sources panel visibility
Ran the OLED test scenario through several turns with "Return Source Documents" enabled. **No visible Sources UI element appeared** below any AI response, despite the toggle being confirmed on. Concluded as a likely Flowise UI/version quirk rather than a functional failure — deferred as a cosmetic issue.

### Test 2 — Grounding language consistency
During natural diagnostic dialogue, the AI stated several specific hardware facts (I2C pin defaults, VCC voltage expectations) with **no grounding language at all** — neither the "(unverified — general knowledge)" tag nor a "per the datasheet" citation. Inconsistent application of the DATASHEET GROUNDING rule.

### Test 3 — Direct retrieval verification (decisive test)
Asked directly: *"According to the ESP32 datasheet, what voltage does the internal LDO output when VDD_SDIO is configured to source internally?"*

**Result:** Correctly answered *"a voltage in the range of 1.65 V to 2.0 V, with a maximum current of 40 mA"* — an exact match to the real datasheet chunk (verified word-for-word against the source PDF: *"the maximum current this LDO can offer is 40 mA, and the output voltage range is 1.65 V ~ 2.0 V"*). This is a specific, obscure figure with negligible chance of being produced correctly from general training knowledge alone.

**Conclusion: retrieval is genuinely functioning correctly.** The remaining issues (no visible Sources UI, inconsistent citation phrasing) are display/prompt-adherence problems layered on top of a working retrieval pipeline — not a broken pipeline.

---

## 6. Phase 3 Evaluation Summary

| Check | Result |
|---|---|
| Datasheets sourced and chunked | ✅ Pass (228 chunks, 4 components) |
| Working embeddings + vector store pipeline | ✅ Pass (Cohere + Pinecone, after 2 failed provider attempts) |
| Retrieval returns semantically relevant results | ✅ Pass (verified via Test Retrieval tool and direct decisive test) |
| Retrieval wired into live chatflow | ✅ Pass (via direct Pinecone node, bypassing broken Document Store dropdown) |
| Sources visibly displayed to user | ❌ Fail (toggle on, no UI element appears — cosmetic) |
| Consistent "per the datasheet" / "unverified" citation tagging | ❌ Fail (inconsistent — correct on direct/explicit datasheet questions, absent during natural diagnostic dialogue) |
| Full T7 scenario re-test (does it now find missing pull-ups?) | 🔜 Deferred to next session |

---

## 7. Next Steps

1. **Re-run the full OLED/T7 diagnostic scenario end-to-end** with RAG now active — the real test of whether Phase 3 closes the gap identified at the end of Phase 2 (model reaching the correct *category* but not the specific documented pull-up resistor cause).
2. Investigate the missing Sources UI panel (low priority — cosmetic, does not affect actual grounding).
3. Consider tightening the DATASHEET GROUNDING prompt instruction if citation inconsistency persists across further testing — likely candidate for the same "few-shot example" technique that partially helped with question-bundling in Phase 2, though that technique's mixed track record so far is worth keeping in mind.
4. Optional stretch: build the **Common Failure Library** (documented failure signatures like "blank OLED + I2C detected + no pull-ups") as an additional Document Store source, using the now-confirmed-stable Cohere + Pinecone pairing.
