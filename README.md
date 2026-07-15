## Build History

This project was built in phases, each documented with real bugs found, root causes, fixes applied, and test evidence — not just a feature list. Full logs: [`build-logs/`](./build-logs).

| Phase | What it added |
|---|---|
| [1](./build-logs/PHASE1_LOG.md) | Core diagnostic engine (no RAG, no structured memory) |
| [2](./build-logs/PHASE2_LOG.md) | Structured Project Memory (JSON state tracking) |
| [3](./build-logs/PHASE3_LOG.md) | Datasheet-aware RAG (Cohere + Pinecone) |
| [4](./build-logs/PHASE4_LOG.md) | Compatibility Checker, Error Log Analyzer, Report Generator |
| [5](./build-logs/PHASE5_LOG.md) | Engineering reasoning depth, confidence display, learning resources |
| [6.0](./build-logs/PHASE6_0_LOG.md) | Migration off Flowise to a self-hosted FastAPI backend (BYOK, Groq) |
| [6](./build-logs/PHASE6_LOG.md) | Multi-provider BYOK (Groq + Gemini) + real tool-calling agent architecture |
