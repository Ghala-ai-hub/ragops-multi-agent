# RAGOps Premium Streamlit Frontend

This frontend is built directly on the `ghala-integration-review` backend.

## What is included

- Sticky top navigation: Overview / RAGOps in Action / Dashboard / Architecture / Team
- Animated RAGOps control-loop hero
- Verified Demo Mode backed by stored evaluation artifacts
- Live Mode hook for local FAISS + OpenAI + LangGraph
- Live Trace visualization
- High-impact HITL approval / reject interaction
- Before vs After validation metrics
- Dashboard charts using stored evaluation data
- Architecture view that distinguishes 4 agents from control/system components
- Team cards with configurable LinkedIn URLs

## Install

```powershell
python -m pip install -r requirements.txt
```

## Run

```powershell
python -m streamlit run app.py
```

## Runtime modes

### VERIFIED DEMO MODE
Works without OpenAI quota or a local FAISS index. It uses only verified stored artifacts under `evaluation/`.

### LIVE MODE
Enabled automatically when both exist:

- `OPENAI_API_KEY` in local `.env`
- `vector_store/evaluation_index/index.faiss`
- `vector_store/evaluation_index/index.pkl`

If live execution fails, the UI does not invent an answer. A matching verified case may be used instead.

## LinkedIn URLs

Edit:

```text
frontend/config.py
```

and fill `TEAM_LINKEDIN`.

## Safety

- Do not commit `.env`.
- Candidate re-chunking remains non-destructive.
- Human Approval is shown only for high-impact structural changes.
- The current backend is retrieval-first; the UI does not fabricate chatbot answers when answer generation is unavailable.
