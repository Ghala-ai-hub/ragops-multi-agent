"""Frontend adapter for the verified RAGOps backend.

The UI consumes backend/shared-state shaped objects and never re-implements
agent logic. Two modes are supported:

- LIVE MODE: requires a local evaluation FAISS index + OpenAI API access.
- VERIFIED DEMO MODE: uses stored, previously validated backend evidence.

No synthetic production metrics are generated here.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
EVAL_DIR = PROJECT_ROOT / "evaluation"
INDEX_DIR = PROJECT_ROOT / "vector_store" / "evaluation_index"

DATASET_PATH = EVAL_DIR / "dataset_v2.json"
RETRIEVAL_PATH = EVAL_DIR / "retrieval_results_v2.json"
WORKFLOW_PATH = EVAL_DIR / "real_failure_workflow_results.json"
REWRITE_PATH = EVAL_DIR / "rewrite_probe_results.json"
CHUNK_SWEEP_PATH = EVAL_DIR / "chunking_sweep_results.json"
RECHUNK_DETAIL_PATH = EVAL_DIR / "rechunk_750_150_detailed.json"

BASELINE_K = 4
EXPANDED_K = 10
EMBEDDING_MODEL = "text-embedding-3-small"
STRUCTURAL_CASE_ID = "verified_chunking_750_150"


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _norm_query(value: str) -> str:
    return " ".join(str(value or "").strip().split())


@dataclass
class RuntimeStatus:
    live_configured: bool
    index_ready: bool
    api_key_present: bool
    langsmith_configured: bool

    @property
    def default_mode(self) -> str:
        # Live is the primary product experience. Saved runs are only a fallback.
        return "LIVE MODE"

    @property
    def reason(self) -> str:
        if self.live_configured:
            return "Local FAISS index and OpenAI credentials detected."
        missing=[]
        if not self.index_ready:
            missing.append("evaluation FAISS index")
        if not self.api_key_present:
            missing.append("OpenAI API key")
        return "Live execution unavailable: missing " + " + ".join(missing) + "."


class FrontendAdapter:
    def __init__(self) -> None:
        self.dataset: List[Dict[str, Any]] = _load(DATASET_PATH)
        self.retrieval: Dict[str, Any] = _load(RETRIEVAL_PATH)
        self.workflow: Dict[str, Any] = _load(WORKFLOW_PATH)
        self.rewrites: Dict[str, Any] = _load(REWRITE_PATH)
        self.chunk_sweep: Dict[str, Any] = _load(CHUNK_SWEEP_PATH)
        self.rechunk_detail: Dict[str, Any] = _load(RECHUNK_DETAIL_PATH)
        self.dataset_by_id={x["id"]:x for x in self.dataset}
        self.dataset_by_query={_norm_query(x["query"]):x for x in self.dataset}
        self.retrieval_by_id={x["id"]:x for x in self.retrieval["results"]}
        self.rewrite_by_id={x["id"]:x for x in self.rewrites["results"]}
        self.workflow_by_id={x["id"]:x for x in self.workflow["results"]}
        self._live_bundle=None

    def runtime_status(self) -> RuntimeStatus:
        index_ready=(INDEX_DIR / "index.faiss").exists() and (INDEX_DIR / "index.pkl").exists()
        api_key_present=bool(os.getenv("OPENAI_API_KEY"))
        langsmith_configured=(str(os.getenv("LANGSMITH_TRACING","")).lower()=="true" and bool(os.getenv("LANGSMITH_API_KEY")))
        return RuntimeStatus(index_ready and api_key_present,index_ready,api_key_present,langsmith_configured)


    def set_session_api_key(self, api_key: str) -> None:
        """Use an OpenAI key for the current process only. Never writes it to disk."""
        api_key = str(api_key or "").strip()
        if not api_key:
            raise ValueError("Enter an OpenAI API key first.")
        os.environ["OPENAI_API_KEY"] = api_key
        self._live_bundle = None

    def build_evaluation_index(self) -> None:
        """Build the missing FAISS evaluation index using the configured API key."""
        if not os.getenv("OPENAI_API_KEY"):
            raise RuntimeError("OpenAI API key is required before building the index.")
        from scripts.build_evaluation_vectorstore import build_evaluation_vectorstore
        cwd = os.getcwd()
        try:
            os.chdir(PROJECT_ROOT)
            build_evaluation_vectorstore()
        finally:
            os.chdir(cwd)
        if not ((INDEX_DIR / "index.faiss").exists() and (INDEX_DIR / "index.pkl").exists()):
            raise RuntimeError("Index build finished but FAISS files were not found.")
        self._live_bundle = None

    def dashboard(self) -> Dict[str, Any]:
        summary=self.retrieval["summary"]
        failures=self.workflow["results"]
        validations=[x["validation"] for x in failures]
        avg_before={k:sum(float(v["before"].get(k) or 0) for v in validations)/len(validations) for k in ["recall_at_k","precision_at_k","reciprocal_rank","latency_seconds"]}
        avg_after={k:sum(float(v["after"].get(k) or 0) for v in validations)/len(validations) for k in ["recall_at_k","precision_at_k","reciprocal_rank","latency_seconds"]}
        issue_counts={"Query Mismatch":0,"Top-K":0,"Chunking Quality":0}
        for x in failures:
            issue_counts[x["diagnosis"]["issue_type"]]=issue_counts.get(x["diagnosis"]["issue_type"],0)+1
        outcomes={"IMPROVED":0,"SAME":0,"WORSE":0}
        for x in failures:
            outcomes[x["validation"]["verdict"]]=outcomes.get(x["validation"]["verdict"],0)+1
        return {
            "summary":summary,
            "failures":failures,
            "avg_before":avg_before,
            "avg_after":avg_after,
            "issue_counts":issue_counts,
            "outcomes":outcomes,
            "chunking_candidates":self.chunk_sweep["candidates"],
            "chunking_baseline":self.chunk_sweep["baseline"],
            "run_rows":[
                {
                    "Run":x["id"],"Query":x["original_query"],"Platform":x["platform"].title(),
                    "Issue":x["diagnosis"]["issue_type"],"Proposed Action":x["proposal"]["action"],
                    "Human Decision":x["approval"].get("human_decision") or x["approval"].get("approval_status","auto"),
                    "Verdict":x["validation"]["verdict"],
                }
                for x in failures
            ],
        }

    def verified_cases(self) -> List[Dict[str, Any]]:
        cases=[]
        for x in self.workflow["results"]:
            cases.append({
                "id":x["id"],"label":f"{x['platform'].title()} · {x['diagnosis']['issue_type']}",
                "query":x["original_query"],"platform":x["platform"],"service":x["service"],
                "issue":x["diagnosis"]["issue_type"],
            })
        cases.append({
            "id":STRUCTURAL_CASE_ID,"label":"Structural · Chunking Quality","query":"Evaluate the validated 750/150 chunking candidate before promotion.",
            "platform":"all","service":"unified_corpus","issue":"Chunking Quality",
        })
        return cases

    def match_dataset_query(self, query: str) -> Optional[Dict[str, Any]]:
        return self.dataset_by_query.get(_norm_query(query))

    def _baseline_run_from_retrieval(self, query_id: str) -> Dict[str, Any]:
        row=self.retrieval_by_id[query_id]
        return {
            "query":row["query"],"top_k":row.get("k",4),
            "retrieved_results":[dict(x) for x in row.get("retrieved",[])],
            "answer":"","judge_score":None,"latency_seconds":0.0,
        }

    def _trace_for_verified(self, item: Dict[str, Any]) -> List[Dict[str, Any]]:
        approval=item["approval"]
        return [
            {"stage":"baseline","name":"Baseline RAG","status":"completed","detail":"Top-K retrieval evidence loaded from the verified evaluation run."},
            {"stage":"monitoring","name":"Monitoring Agent","status":"completed","detail":"Retrieval evidence observed; no optimization selected here."},
            {"stage":"diagnosis","name":"Diagnosis Agent","status":"completed","detail":f"{item['diagnosis']['issue_type']} · {int(float(item['diagnosis'].get('confidence') or 0)*100)}% confidence"},
            {"stage":"optimization","name":"Optimization Agent","status":"proposal_ready","detail":f"Proposed {item['proposal']['action']}."},
            {"stage":"approval","name":"Human Approval Gate","status":approval.get("approval_status","auto_approved"),"detail":"Low-impact action auto-applied by backend policy.","human":True},
            {"stage":"execution","name":"Action Executor","status":"completed","detail":"Allowed optimization executed against a candidate run."},
            {"stage":"validation","name":"Validation Agent","status":item['validation']['verdict'].lower(),"detail":f"{item['validation']['verdict']} · {item['validation']['recommendation']}"},
        ]

    def verified_case(self, case_id: str, human_decision: Optional[str] = None) -> Dict[str, Any]:
        if case_id == STRUCTURAL_CASE_ID:
            return self.structural_case(human_decision)
        item=self.workflow_by_id[case_id]
        baseline=self._baseline_run_from_retrieval(case_id)
        after=dict(item["execution"]["after_run"])
        return {
            "mode":"VERIFIED DEMO MODE","case_id":case_id,"query":item["original_query"],
            "platform":item["platform"],"service":item["service"],"query_type":item["query_type"],
            "before_run":baseline,"diagnosis_report":item["diagnosis"],"optimization_proposal":item["proposal"],
            "approval_result":item["approval"],"execution_result":item["execution"],"after_run":after,
            "validation_result":item["validation"],"final_status":item["final_status"],
            "trace":self._trace_for_verified(item),"verified":True,"requires_human":False,
        }

    def structural_case(self, human_decision: Optional[str] = None) -> Dict[str, Any]:
        best=next(x for x in self.chunk_sweep["candidates"] if x["chunk_size"]==750 and x["chunk_overlap"]==150)
        baseline=self.chunk_sweep["baseline"]
        proposal={
            "issue_type":"Chunking Quality","action":"rechunk_and_reindex","status":"proposed","confidence":0.90,
            "reason":"A non-destructive chunking sweep found a candidate with higher Recall@4 and MRR.",
            "parameters":{"baseline_k":4,"chunk_size":750,"chunk_overlap":150},
        }
        pending={"approval_mode":"human","approval_status":"pending_human_approval","execution_allowed":False,"next_step":"await_human_decision",**proposal}
        trace=[
            {"stage":"baseline","name":"Baseline RAG","status":"completed","detail":"Official baseline 1000 / 200 retained."},
            {"stage":"monitoring","name":"Monitoring Agent","status":"completed","detail":"Structural evaluation evidence available from the chunking sweep."},
            {"stage":"diagnosis","name":"Diagnosis Agent","status":"completed","detail":"Chunking Quality candidate identified for controlled review."},
            {"stage":"optimization","name":"Optimization Agent","status":"proposal_ready","detail":"Proposed non-destructive 750 / 150 candidate index."},
            {"stage":"approval","name":"Human Approval Gate","status":"pending_human_approval","detail":"Structural change paused before promotion.","human":True},
        ]
        if human_decision is None:
            return {"mode":"VERIFIED DEMO MODE","case_id":STRUCTURAL_CASE_ID,"query":"Validated structural optimization candidate","platform":"all","service":"unified_corpus","before_run":{"answer":"","judge_score":None,"latency_seconds":0.0,"retrieved_results":[]},"diagnosis_report":{"issue_type":"Chunking Quality","confidence":0.90,"reason":proposal["reason"],"recommended_action":"rechunk_and_reindex"},"optimization_proposal":proposal,"approval_result":pending,"final_status":"PENDING_HUMAN_APPROVAL","trace":trace,"verified":True,"requires_human":True}
        decision=str(human_decision).strip().lower()
        if decision=="reject":
            approval={**pending,"human_decision":"reject","approval_status":"rejected","next_step":"retain_baseline"}
            trace[-1]={"stage":"approval","name":"Human Approval Gate","status":"rejected","detail":"Rejected · baseline configuration retained.","human":True}
            return {"mode":"VERIFIED DEMO MODE","case_id":STRUCTURAL_CASE_ID,"query":"Validated structural optimization candidate","platform":"all","service":"unified_corpus","diagnosis_report":{"issue_type":"Chunking Quality","confidence":0.90,"reason":proposal["reason"],"recommended_action":"rechunk_and_reindex"},"optimization_proposal":proposal,"approval_result":approval,"final_status":"REJECTED","trace":trace,"verified":True,"requires_human":True}
        approval={**pending,"human_decision":"approve","approval_status":"approved","execution_allowed":True,"next_step":"execute_approved_action"}
        trace[-1]={"stage":"approval","name":"Human Approval Gate","status":"approved","detail":"Approved · candidate evidence released to Validation.","human":True}
        trace += [
            {"stage":"execution","name":"Action Executor","status":"completed","detail":"Verified 750 / 150 candidate index evaluated non-destructively."},
            {"stage":"validation","name":"Validation Agent","status":"improved","detail":"IMPROVED · official baseline is still not auto-promoted."},
        ]
        before={"recall_at_k":baseline["recall_at_k"],"precision_at_k":baseline["precision_at_k"],"reciprocal_rank":baseline["mrr"],"judge_score":None,"latency_seconds":0.0}
        after={"recall_at_k":best["recall_at_k"],"precision_at_k":best["precision_at_k"],"reciprocal_rank":best["mrr"],"judge_score":None,"latency_seconds":0.0}
        validation={"verdict":"IMPROVED","recommendation":"ACCEPT_OPTIMIZED","before":before,"after":after,"delta":{"recall_at_k":after["recall_at_k"]-before["recall_at_k"],"precision_at_k":after["precision_at_k"]-before["precision_at_k"],"reciprocal_rank":after["reciprocal_rank"]-before["reciprocal_rank"],"judge_score":None,"latency_seconds":0.0},"answer_comparison":{"before":"","after":""}}
        return {"mode":"VERIFIED DEMO MODE","case_id":STRUCTURAL_CASE_ID,"query":"Validated structural optimization candidate","platform":"all","service":"unified_corpus","diagnosis_report":{"issue_type":"Chunking Quality","confidence":0.90,"reason":proposal["reason"],"recommended_action":"rechunk_and_reindex"},"optimization_proposal":proposal,"approval_result":approval,"validation_result":validation,"final_status":"IMPROVED","trace":trace,"verified":True,"requires_human":True}

    def verified_case_for_query(self, query: str) -> Optional[Dict[str, Any]]:
        q=_norm_query(query)
        for case in self.workflow["results"]:
            if _norm_query(case["original_query"])==q:
                return self.verified_case(case["id"])
        return None

    def _build_live_bundle(self):
        if self._live_bundle is not None:
            return self._live_bundle
        from dotenv import load_dotenv
        load_dotenv(PROJECT_ROOT / ".env")
        from langchain_community.vectorstores import FAISS
        from langchain_openai import OpenAIEmbeddings
        from scripts.action_executor import ApprovedActionExecutor
        from scripts.diagnosis_agent import DiagnosisAgent
        from scripts.langgraph_workflow import LangGraphRAGOps
        from scripts.monitoring_agent import MonitoringAgent
        from scripts.optimization_agent import OptimizationAgent
        from scripts.rechunk_candidate_adapter import RechunkCandidateAdapter
        from scripts.retrieval_run import build_retrieval_run
        embeddings=OpenAIEmbeddings(model=EMBEDDING_MODEL)
        cwd=os.getcwd()
        try:
            os.chdir(PROJECT_ROOT)
            vector_store=FAISS.load_local(str(Path("vector_store")/"evaluation_index"),embeddings,allow_dangerous_deserialization=True)
        finally:
            os.chdir(cwd)
        current={"platform":None,"service":None}
        def run_candidate(query:str,top_k:int):
            return build_retrieval_run(vector_store,query,top_k,expected_platform=current["platform"],expected_service=current["service"])
        def run_rechunk_candidate(parameters: Dict[str, Any]):
            # The existing adapter builds an isolated candidate only after the
            # native approval gate allows execution. Keep this run's labels.
            candidate = RechunkCandidateAdapter(
                expected_platform=current["platform"],
                expected_service=current["service"],
            )
            return candidate(parameters)
        executor=ApprovedActionExecutor(run_candidate=run_candidate,default_k=BASELINE_K,rechunk_candidate=run_rechunk_candidate)
        workflow=LangGraphRAGOps(monitoring_agent=MonitoringAgent(vector_store),diagnosis_agent=DiagnosisAgent(),optimization_agent=OptimizationAgent(),action_executor=executor)
        self._live_bundle=(vector_store,workflow,current,build_retrieval_run)
        return self._live_bundle

    def run_live(self, query: str) -> Dict[str, Any]:
        query=_norm_query(query)
        if not query:
            raise ValueError("Enter a query first.")
        if not self.runtime_status().live_configured:
            raise RuntimeError(self.runtime_status().reason)
        vector_store,workflow,current,build_run=self._build_live_bundle()
        item=self.match_dataset_query(query)
        expected_platform=item.get("platform") if item else None
        expected_service=item.get("service") if item else None
        current["platform"],current["service"]=expected_platform,expected_service
        before=build_run(vector_store,query,BASELINE_K,expected_platform=expected_platform,expected_service=expected_service)
        kwargs={"baseline_k":BASELINE_K,"expanded_k":EXPANDED_K,"expected_platform":expected_platform,"expected_service":expected_service}
        if item:
            probe=self.rewrite_by_id.get(item["id"]) or {}
            rewritten=str(probe.get("rewritten_query") or "").strip()
            if rewritten:
                kwargs["rewritten_query"]=rewritten
        thread_id=f"streamlit-{item['id'] if item else abs(hash(query))}"
        state=workflow.invoke({"query":query,"before_run":before,"expected_platform":expected_platform,"expected_service":expected_service,"monitoring_kwargs":kwargs,"trace":[]},thread_id=thread_id)
        return {"state":state,"thread_id":thread_id,"workflow":workflow,"dataset_item":item}

    @staticmethod
    def resume_live(workflow: Any, thread_id: str, decision: str) -> Dict[str, Any]:
        return workflow.resume(decision,thread_id=thread_id)
