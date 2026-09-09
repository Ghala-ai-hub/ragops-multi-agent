from typing import Dict, Any, Optional
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings
from optimization_tools import change_top_k, rewrite_query, rechunk_and_reindex

class OptimizationAgent:
    def __init__(self, vector_store_path: str = "vector_store/balady_najiz_index"):
        self.embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
        self.vector_store_path = vector_store_path
        self.vector_store = FAISS.load_local(
            vector_store_path, 
            self.embeddings, 
            allow_dangerous_deserialization=True
        )

    def process_optimization(self, diagnosis_report: Dict[str, Any], user_approval: Optional[bool] = None) -> Dict[str, Any]:
        """
        استلام تقرير التشخيص واتخاذ إجراء التحسين المناسب
        diagnosis_report يحتوي على:
        - issue_type: ("Top-K", "Query Mismatch", "Chunking Quality")
        - original_query: نص السؤال
        """
        issue_type = diagnosis_report.get("issue_type")
        query = diagnosis_report.get("original_query", "")
        
        print(f"\n [Optimization Agent] بدء معالجة المشكلة: {issue_type}")
        
        # Scenario 1: مشكلة Top-K
        if issue_type == "Top-K":
            new_k = diagnosis_report.get("recommended_k", 6)
            retriever = change_top_k(self.vector_store, new_k=new_k)
            return {
                "action_taken": "change_top_k",
                "status": "applied",
                "retriever": retriever,
                "applied_k": new_k
            }
            
        # Scenario 2: مشكلة عدم تطابق الاستعلام Query Mismatch
        elif issue_type == "Query Mismatch":
            new_query = rewrite_query(query)
            return {
                "action_taken": "rewrite_query",
                "status": "applied",
                "new_query": new_query
            }
            
        # Scenario 3: مشكلة جودة التقسيم Chunking Quality (تتطلب Human Approval HITL)
        elif issue_type == "Chunking Quality":
            if user_approval is None:
                print("[Optimization Agent] الإجراء يحتاج موافقة بشرية (HITL) لإعادة تقسيم القاعدة.")
                return {
                    "action_taken": "rechunk_and_reindex",
                    "status": "pending_approval",
                    "message": "هل توافق على إعادة بناء الفهرس بأحجام Chunks أصغر؟ (Approve/Reject)"
                }
            elif user_approval is True:
                new_chunk_size = diagnosis_report.get("new_chunk_size", 500)
                new_overlap = diagnosis_report.get("new_chunk_overlap", 100)
                new_vectorstore = rechunk_and_reindex(chunk_size=new_chunk_size, chunk_overlap=new_overlap)
                self.vector_store = new_vectorstore
                return {
                    "action_taken": "rechunk_and_reindex",
                    "status": "completed",
                    "vector_store": new_vectorstore
                }
            else:
                return {
                    "action_taken": "rechunk_and_reindex",
                    "status": "rejected_by_user",
                    "message": "تم إلغاء عملية إعادة التقسيم بطلب من المستخدم."
                }
        else:
            return {"status": "unknown_issue", "message": "لم يتم التعرف على نوع المشكلة."}

# تجربة تشغيلية سريعة لوكيل التحسين
if __name__ == "__main__":
    agent = OptimizationAgent()
    
    # تجربة 1: حل مشكلة Query Mismatch
    report_1 = {
        "issue_type": "Query Mismatch",
        "original_query": "وش اسوي لو انتهت رخصتي حق بلدي"
    }
    res_1 = agent.process_optimization(report_1)
    print("النتيجة:", res_1)
    
    # تجربة 2: طلب موافقة بشرية لإعادة الـ Chunking
    report_2 = {
        "issue_type": "Chunking Quality",
        "original_query": "خطوات التقديم على خدمة ناجز"
    }
    res_2_pending = agent.process_optimization(report_2)
    print("\nطلب الموافقة:", res_2_pending)
    
    # موافقة المستخدم
    res_2_approved = agent.process_optimization(report_2, user_approval=True)
    print("\nبعد الموافقة:", res_2_approved["status"])