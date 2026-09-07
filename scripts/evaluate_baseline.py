import json
import os
from dotenv import load_dotenv
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_community.vectorstores import FAISS
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser

load_dotenv()

# 1. تحميل Vector Store
embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
vector_store = FAISS.load_local(
    "vector_store/balady_najiz_index", 
    embeddings, 
    allow_dangerous_deserialization=True
)
retriever = vector_store.as_retriever(search_kwargs={"k": 4})

# 2. إعداد LLM والـ Prompt
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

rag_prompt = ChatPromptTemplate.from_messages([
    ("system", "أنت مساعد ذكي للخدمات الحكومية السعودية.\nاستخدم السياق التالي للإجابة على سؤال المستخدم بدقة:\n\nالسياق:\n{context}"),
    ("human", "{question}")
])

# دالة لتنسيق النصوص المسترجعة
def format_docs(docs):
    return "\n\n".join(doc.page_content for doc in docs)

# بناء RAG Chain الحديث بنمط LCEL
rag_chain = (
    {"context": retriever | format_docs, "question": RunnablePassthrough()}
    | rag_prompt
    | llm
    | StrOutputParser()
)

# 3. إعداد مقيّم الأداء (LLM-as-a-Judge)
judge_prompt = ChatPromptTemplate.from_messages([
    ("system", 
     "أنت مقيّم لأنظمة استرجاع المعلومات (RAG). مهمتك مقارنة 'الإجابة المولدة' بـ 'الإجابة النموذجية'.\n"
     "أعطِ تقييماً من 1 إلى 5 بناءً على الدقة، واكتب سبباً مختصراً جداً.\n"
     "التنسيق المطلوب:\nالتقييم: [رقم]/5\nالسبب: [نص]"),
    ("human", "السؤال: {query}\n\nالإجابة النموذجية: {expected}\n\nالإجابة المولدة: {generated}")
])

judge_chain = judge_prompt | llm | StrOutputParser()

# 4. قراءة البيانات وبدء التقييم
with open("evaluation/dataset.json", "r", encoding="utf-8") as f:
    dataset = json.load(f)

print("بدء تقييم Baseline RAG...\n" + "="*50)

for item in dataset:
    query = item["query"]
    expected = item["expected_answer"]
    
    print(f"السؤال: {query}")
    
    # توليد الإجابة
    generated = rag_chain.invoke(query)
    
    # تحكيم الإجابة
    eval_result = judge_chain.invoke({
        "query": query, 
        "expected": expected, 
        "generated": generated
    })
    
    print(f"الإجابة المولدة:\n{generated}\n")
    print(eval_result)
    print("-" * 50)