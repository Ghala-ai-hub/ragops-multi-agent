# RAGOps Agent – Multi-Agent Retrieval QA Optimizer

> **Observe. Diagnose. Optimize. Validate.**

![Python](https://img.shields.io/badge/Python-3.11+-blue)
![LangGraph](https://img.shields.io/badge/LangGraph-Multi--Agent-black)
![FAISS](https://img.shields.io/badge/FAISS-Vector%20Search-blueviolet)
![Streamlit](https://img.shields.io/badge/Streamlit-Live%20App-FF4B4B)
![OpenAI](https://img.shields.io/badge/OpenAI-RAG-412991)

A multi-agent RAGOps system that monitors retrieval quality, diagnoses retrieval failures, proposes targeted optimizations, applies risk-based Human-in-the-loop (HITL), and validates retrieval performance before and after optimization.

### 🚀 Live Demo

**[Launch RAGOps Agent](https://ragops-agent.streamlit.app)**

The government-services corpus is a controlled testbed. The project itself is an optimization layer around a RAG pipeline, not a government chatbot.

---

## What RAGOps Does

Traditional RAG systems can fail silently even when the correct knowledge exists in the knowledge base.

RAGOps adds an optimization layer around the retrieval pipeline to:

- **Observe** retrieval behavior and collect evidence.
- **Diagnose** the likely cause of retrieval failure.
- **Optimize** using targeted actions instead of blind tuning.
- **Control** high-impact changes through risk-based HITL.
- **Validate** whether the proposed optimization actually improved retrieval.

---

## Architecture

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
Accept Optimized Run
        OR
Retain Baseline