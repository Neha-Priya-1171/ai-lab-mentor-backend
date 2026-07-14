# AI Lab Mentor — Circuit Diagnostic AI

An ESP32 electronics diagnostic assistant that runs a guided, adaptive
diagnostic loop grounded in real datasheets, with a genuine multi-tool AI
agent architecture (BYOK — bring your own key, Groq or Gemini) rather than
a single hardcoded prompt.

**Live demo:** https://ai-lab-mentor.onrender.com

## Build History

This project was built in phases, each documented with real bugs found,
root causes, fixes applied, and test evidence — not just a feature list.
Full logs: [`build-logs/`](./build-logs).

| Phase | What it added |
|---|---|
| [1](./build-logs/PHASE1_LOG.md) | Core diagnostic engine (no RAG, no structured memory) |
| [2](./build-logs/PHASE2_LOG.md) | Structured Project Memory (JSON state tracking) |
| [3](./build-logs/PHASE3_LOG.md) | Datasheet-aware RAG (Cohere + Pinecone) |
| [4](./build-logs/PHASE4_LOG.md) | Compatibility Checker, Error Log Analyzer, Report Generator |
| [5](./build-logs/PHASE5_LOG.md) | Engineering reasoning depth, confidence display, learning resources |
| [6.0](./build-logs/PHASE6_0_LOG.md) | Migration off Flowise to a self-hosted FastAPI backend (BYOK, Groq) |
| [6](./build-logs/PHASE6_LOG.md) | Multi-provider BYOK (Groq + Gemini) + real tool-calling agent architecture |

## 1. Local setup

```bash
cd ai-lab-mentor-backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and fill in your real Cohere and Pinecone values, then run:

```bash
uvicorn main:app --reload
```

Open `http://localhost:8000`, pick a provider (Groq or Gemini), paste your own free API key, and start a diagnostic session.

## 2. What to test before deploying

- A short T7-style exchange ("My OLED screen is blank...") to confirm the plain guided diagnostic loop works end to end.
- A compatibility question ("Can I drive a 12V relay from GPIO25 to GND?") to confirm real tool-calling fires correctly.
- A pasted error log (e.g. `rst:0x0f (RTCWDT_BROWN_OUT_RESET)`) to confirm the Error Log Analyzer tool fires correctly.

## 3. Deploy to Render (free tier)

1. Push this repo to GitHub.
2. On [render.com](https://render.com), New → Web Service → connect the repo.
3. Build command: `pip install -r requirements.txt`
4. Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
5. Add environment variables in Render's dashboard: `COHERE_API_KEY`, `PINECONE_API_KEY`, `PINECONE_INDEX_NAME`.
6. Deploy. Render gives you a public URL to share.

Free tier note: Render's free web services spin down after inactivity and take ~30-50 seconds to wake on the next request.

## 4. Architecture

- **Backend:** FastAPI, real multi-tool agent loop (`agent.py`) — the model autonomously decides when to call `check_component_compatibility`, `analyze_error_log`, or `generate_diagnostic_report`, rather than following a hardcoded routing prompt.
- **LLM providers:** Groq and Google Gemini, both BYOK, behind one abstracted interface (`providers/`).
- **Retrieval:** Cohere embeddings + Pinecone vector search (shared keys) for real datasheet grounding.
- **Ground truth:** ESP32 board profile and error-signature reference live as real, tested Python data (`ground_truth.py`), not re-fed prose.
