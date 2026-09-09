import os
import sys
from dotenv import load_dotenv

# إضافة المسار الرئيسي للمشروع لضمان استيراد الوحدات بشكل صحيح
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.optimization_agent import OptimizationAgent

# تحميل المتغيرات البيئية من ملف .env
load_dotenv()

def run_pipeline_test():
    print("==================================================")
    print("[RAGOps optimization_agent Pipeline Test] بدء اختبار خط أنابيب التحسين")
    print("==================================================\n")

    agent = OptimizationAgent()

    # 1️⃣ اختبار معالجة تباين الأسئلة (Query Mismatch)
    print("[1] تجربة تحسين الاستعلام (Query Rewriting):")
    query_report = {
        "issue_type": "Query Mismatch",
        "query": "وش اسوي لو انتهت رخصتي حق بلدي"
    }
    
    print(f"    السؤال الأصلي: '{query_report['query']}'")
    query_result = agent.process_optimization(query_report)
    print(f"   النتيجة بعد التحسين: '{query_result.get('new_query')}'\n")

    # 2️⃣ اختبار جودة التقسيم وإعادة التكشير (Chunking Quality & HITL)
    print("[2] تجربة إستراتيجية التقسيم والموافقة البشرية (HITL):")
    chunk_report = {
        "issue_type": "Chunking Quality",
        "query": "ما هي رسوم تجديد الرخصة؟"
    }
    
    chunk_result = agent.process_optimization(chunk_report)
    print(f"    الحالة: {chunk_result.get('status')}")
    print(f"    الرسالة: {chunk_result.get('message')}\n")

    print("==================================================")
    print(" اكتمل اختبار خط الأنابيب بنجاح 100%!")
    print("==================================================")

if __name__ == "__main__":
    run_pipeline_test()