# RAGOps Agent – Multi-Agent Retrieval QA Optimizer

A multi-agent RAGOps system that monitors retrieval quality, diagnoses retrieval failures, proposes targeted optimizations, applies risk-based Human-in-the-loop (HITL), and validates Before vs After retrieval performance.

The government-services corpus is a controlled testbed. The project itself is an optimization layer around a RAG pipeline, not a government chatbot.

## Current architecture

```text
User Query
   ↓
Baseline Retrieval
   ↓
Monitoring Agent
   ↓
Diagnosis Agent
   ↓
Optimization Agent
   ↓
Risk Gate / HITL
   ↓
Action Executor
   ↓
Validation Agent
   ↓
Accept optimized run or keep baseline
```

LangGraph orchestrates the workflow. LangSmith tracing is supported through environment variables.

## Supported retrieval issues

The current system focuses on exactly three retrieval problems:

1. **Top-K Retrieval** → `change_top_k`
2. **Query Mismatch / Query Rewriting** → `rewrite_query`
3. **Chunking Quality** → `rechunk_and_reindex`

Low-impact changes can auto-apply. Structural re-chunking/re-indexing requires human approval and is executed against a non-destructive candidate index.

## Corpus

The current evaluation corpus contains **24 services** across four Saudi government platforms:

- Absher: 6 services
- Balady: 6 services
- Najiz: 6 services
- Sakani: 6 services

Only `content_final.md` files are indexed.

The evaluation dataset contains **48 queries**: one standard and one query-mismatch query per service.

## Baseline configuration

- Embeddings: `text-embedding-3-small`
- Generation model used by baseline components: `gpt-4o-mini`
- Baseline Top-K: `4`
- Baseline chunk size: `1000`
- Baseline chunk overlap: `200`
- Vector store: FAISS

Current retrieval baseline over 48 queries:

| Metric | Value |
|---|---:|
| Recall@4 | 0.8958 |
| Precision@4 | 0.4896 |
| MRR | 0.7986 |

## Verified optimization results

Five real Recall@4 failures were passed through the integrated workflow.

- 4 were diagnosed as **Query Mismatch** and optimized with query rewriting.
- 1 was diagnosed as **Top-K** and optimized by changing K.
- Validation result: **5/5 IMPROVED**.
- The active FAISS index remained unchanged.

A chunking sweep also tested structural candidates non-destructively:

| Chunking | Recall@4 | Precision@4 | MRR | Validation |
|---|---:|---:|---:|---|
| Baseline 1000/200 | 0.8958 | 0.4896 | 0.7986 | baseline |
| 750/150 | 0.9167 | 0.4896 | 0.8212 | improved |
| 1250/250 | 0.8750 | 0.4583 | 0.8177 | worse |
| 1500/300 | 0.8750 | 0.4531 | 0.8229 | worse |

The 750/150 candidate recovered one baseline Recall@4 failure and introduced no new Recall@4 failures in detailed validation. It has **not** replaced the official 1000/200 baseline; promotion remains a separate human-approved structural decision.

## Setup

Create a local `.env` file from `.env.example`.

Required for real retrieval runs:

```env
OPENAI_API_KEY=your_openai_api_key_here
```

Optional LangSmith tracing:

```env
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=your_private_langsmith_key
LANGSMITH_PROJECT=ragops-multi-agent
```

Never commit `.env` or API keys.

Install dependencies:

```powershell
py -m pip install -r requirements.txt
```

## Build the current evaluation index

The FAISS index is intentionally gitignored and must be built locally when absent.

```powershell
py scripts\build_evaluation_vectorstore.py
```

Expected corpus build: 24 final files. The current baseline configuration produces 168 chunks.

## Main commands

Run the offline regression suite:

```powershell
py scripts\run_regression_suite.py
```

Expected current result:

```text
Passed: 8/8
Failed: 0/8
All current offline RAGOps regression tests passed.
```

Run one real-data unified LangGraph demo:

```powershell
py scripts\run_ragops_demo.py
```

Run all current real baseline failures:

```powershell
py scripts\run_ragops_demo.py --all-failures
```

Run the optional LangSmith smoke trace:

```powershell
py scripts\run_langsmith_smoke_trace.py
```

Run release/readiness checks:

```powershell
py scripts\check_release_readiness.py
```

## LangGraph + HITL

The orchestration graph is implemented in:

```text
scripts/langgraph_workflow.py
```

The graph uses native interrupt/resume behavior for high-impact structural actions. Re-chunking does not auto-promote a candidate or overwrite the active index.

Validated graph path:

```text
monitoring
→ diagnosis
→ optimization
→ approval
→ execution
→ validation
```

## LangSmith

When tracing is enabled locally, LangSmith captures the graph run with workflow tags and metadata such as:

- workflow name
- baseline K
- expected platform
- expected service

The LangSmith smoke trace has been successfully verified with a real trace visible in the LangSmith project.

## Evaluation evidence

Key result files:

```text
evaluation/retrieval_results_v2.json
evaluation/rewrite_probe_results.json
evaluation/real_failure_workflow_results.json
evaluation/rechunk_candidate_results.json
evaluation/chunking_sweep_results.json
evaluation/rechunk_750_150_detailed.json
```

Candidate FAISS indexes are intentionally excluded from Git.

## Safety and reproducibility notes

- `.env` is ignored.
- Active and candidate FAISS indexes are ignored.
- Monitoring logs are ignored.
- Structural optimization requires HITL.
- Candidate re-indexing is non-destructive.
- The current baseline remains 1000/200 until a separate promotion decision is approved.
- `test_baseline_rag.py` is a legacy two-platform Balady/Najiz script and is intentionally excluded from the current regression suite.
- A `langchain-community` sunset warning may appear during FAISS usage. It is currently non-blocking. As of the current dependency review, LangChain still documents local FAISS through `langchain-community`, so the project keeps the dependency pinned rather than forcing an unsupported migration; revisit this when an official dedicated FAISS integration is available.

## Current verified status

As of 2026-09-20:

- Real four-platform retrieval evaluation: complete
- Monitoring → Diagnosis contract: passed
- Optimization proposal logic: passed
- HITL + Action Executor: passed
- Integration workflow: passed
- Non-destructive re-chunk adapter: passed
- LangGraph orchestration: passed
- LangGraph native HITL interrupt/resume: passed
- LangSmith observability configuration: passed
- LangSmith trace delivery: verified
- Offline regression suite: **8/8 passed**
- Unified real-data failure demo: **5/5 improved**
