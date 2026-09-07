import os
from dotenv import load_dotenv
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_community.vectorstores import FAISS
from langchain_classic.chains import create_retrieval_chain
from langchain_classic.chains.combine_documents import create_stuff_documents_chain
from langchain_core.prompts import ChatPromptTemplate

load_dotenv()

# 1. تحميل Vector Store
embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
vector_store = FAISS.load_local(
    "vector_store/balady_najiz_index", 
    embeddings, 
    allow_dangerous_deserialization=True  # مطلوب في الإصدارات الحديثة لـ FAISS
)

# ضبط الـ Retriever لاسترجاع أفضل 4 قطع (Top-K = 4)
retriever = vector_store.as_retriever(search_kwargs={"k": 4})

# 2. إعداد LLM والـ Prompt
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

system_prompt = (
    "أنت مساعد ذكي متخصص في الخدمات الحكومية السعودية (ناجز وبلدي).\n"
    "استخدم السياق التالي للإجابة على سؤال المستخدم بدقة واختصار.\n"
    "إذا لم تجد الإجابة في السياق، قل بوضوح 'لا أملك معلومات كافية للإجابة بناءً على الأدلة الحالية'.\n\n"
    "السياق:\n{context}"
)

prompt = ChatPromptTemplate.from_messages([
    ("system", system_prompt),
    ("human", "{input}"),
])

# 3. ربط الـ Chain
question_answer_chain = create_stuff_documents_chain(llm, prompt)
rag_chain = create_retrieval_chain(retriever, question_answer_chain)

# 4. تشغيل أسئلة اختبارية
test_queries = [
    "ما هي خطوات إصدار رخصة بناء من منصة بلدي؟",
    "كيف يمكنني رفع صحيفة دعوى عبر ناجز؟",
    "هل يمكنني تجديد رخصة تجارية منتهية؟"
]

print("جاري اختبار Baseline RAG...\n")
for query in test_queries:
    print(f"السؤال: {query}")
    response = rag_chain.invoke({"input": query})
    print(f"الإجابة:\n{response['answer']}")
    print("-" * 50)