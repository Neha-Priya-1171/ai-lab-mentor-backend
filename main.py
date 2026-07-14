import os
from pathlib import Path

import cohere
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pinecone import Pinecone
from pydantic import BaseModel

import agent
from providers.base import ProviderError
from providers.registry import available_providers
from tools.dispatcher import set_retriever

load_dotenv()

COHERE_API_KEY = os.environ["COHERE_API_KEY"]          # yours, shared across all users
PINECONE_API_KEY = os.environ["PINECONE_API_KEY"]      # yours, shared across all users
PINECONE_INDEX_NAME = os.environ["PINECONE_INDEX_NAME"]

# The full validated diagnostic prompt (guided diagnostic loop + Shared
# Rules), Phase-6 edition — Step 0 hardcoded mode routing removed, replaced
# by real tool-calling. See system_prompt.md for the "why" on each change.
SYSTEM_PROMPT = Path(__file__).parent.joinpath("system_prompt.md").read_text()

co = cohere.Client(COHERE_API_KEY)
pc = Pinecone(api_key=PINECONE_API_KEY)
index = pc.Index(PINECONE_INDEX_NAME)

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten to your actual frontend domain once deployed
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str


class ChatRequest(BaseModel):
    provider: str = "groq"          # "groq" or "gemini" — Phase 6 multi-provider BYOK
    api_key: str                    # the user's own key for whichever provider they picked
    message: str
    history: list[ChatMessage] = []


def retrieve_context(query: str, top_k: int = 4) -> list[str]:
    """Embed the query with Cohere, retrieve matching datasheet chunks from Pinecone.
    Shared across all users (unchanged from Phase 6.0) — only LLM generation is BYOK.
    Returns a list of raw chunk strings; callers format as needed.
    """
    embedding = co.embed(
        texts=[query],
        model="embed-english-v3.0",
        input_type="search_query",
    ).embeddings[0]

    results = index.query(vector=embedding, top_k=top_k, include_metadata=True)
    return [m["metadata"].get("text", "") for m in results.get("matches", [])]


# Wire the shared retriever into the tool dispatcher once at startup, so
# check_component_compatibility / analyze_error_log / generate_diagnostic_report
# can pull real datasheet context without importing Cohere/Pinecone themselves.
set_retriever(retrieve_context)


@app.get("/providers")
def list_providers():
    """Lets the frontend populate the provider dropdown without hardcoding it twice."""
    return {"providers": available_providers()}


@app.post("/chat")
def chat(req: ChatRequest):
    # Retrieval for the plain diagnostic conversation loop (separate from
    # whatever a tool call might retrieve mid-turn — see system_prompt.md's
    # "Context" section vs. tool-result context).
    chunks = retrieve_context(req.message)
    context_text = "\n\n---\n\n".join(chunks) if chunks else "(no matching datasheet content retrieved)"
    system_with_context = SYSTEM_PROMPT.replace("{context}", context_text)

    history_messages = [{"role": m.role, "content": m.content} for m in req.history]
    history_messages.append({"role": "user", "content": req.message})

    try:
        result = agent.run_agent_turn(
            provider_name=req.provider,
            api_key=req.api_key,
            messages=history_messages,
            system_prompt=system_with_context,
        )
    except ProviderError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))

    return {"reply": result["reply"], "tool_calls_made": result["tool_calls_made"]}


# Serve the frontend. Must be registered AFTER the /chat route above,
# otherwise this mount would swallow every request including /chat.
app.mount("/", StaticFiles(directory="static", html=True), name="static")
