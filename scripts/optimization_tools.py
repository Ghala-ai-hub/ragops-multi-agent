import os
from pathlib import Path
from dotenv import load_dotenv

# 1. تحديد المسار الرئيسي للوصول لملف .env والمجلدات
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_text_splitters import (
    MarkdownHeaderTextSplitter,
    RecursiveCharacterTextSplitter,
)
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

KNOWLEDGE_BASE_DIR = PROJECT_ROOT / "knowledge_base"
VECTOR_STORE_PATH = PROJECT_ROOT / "vector_store" / "balady_najiz_index"

# 1. أداة تعديل Top-K
def change_top_k(vector_store: FAISS, new_k: int = 6):
    print(f"[Optimization Tool] تعديل Top-K إلى: {new_k}")
    retriever = vector_store.as_retriever(search_kwargs={"k": new_k})
    return retriever

# 2. أداة إعادة صياغة السؤال (Query Rewriting)
def rewrite_query(original_query: str) -> str:
    print(f" [Optimization Tool] إعادة صياغة السؤال الأصلي: '{original_query}'")
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    prompt = ChatPromptTemplate.from_messages([
        ("system", 
         "أنت خبير في البحث المستندي للخدمات الحكومية السعودية (ناجز وبلدي).\n"
         "قم بإعادة صياغة سؤال المستخدم ليكون أكثر دقة واستخداماً للمصطلحات الرسمية المفتاحية ليعطي نتائج أفضل عند البحث في المتجهات."),
        ("human", "السؤال الأصلي: {query}\n\nالسؤال المطور للبحث:")
    ])
    chain = prompt | llm | StrOutputParser()
    rewritten = chain.invoke({"query": original_query})
    print(f" [Optimization Tool] السؤال بعد التعديل: '{rewritten}'")
    return rewritten

# 3. أداة إعادة التقسيم وبناء الفهرس (Re-chunking & Re-indexing)
def rechunk_and_reindex(chunk_size: int = 500, chunk_overlap: int = 100):
    print(f" [Optimization Tool] إعادة تقسيم المستندات بحجم Chunk Size: {chunk_size}, Overlap: {chunk_overlap}...")
    target_folders = ["balady", "najiz"]
    files = []
    for folder in target_folders:
        folder_path = KNOWLEDGE_BASE_DIR / folder
        if folder_path.exists():
            for root, _, filenames in os.walk(folder_path):
                for f in filenames:
                    if f.endswith(".md"):
                        files.append(os.path.join(root, f))

    if not files:
        raise FileNotFoundError("لم يتم العثور على ملفات .md في المجلدات المحددة.")

    headers_to_split_on = [
        ("#", "Header 1"),
        ("##", "Header 2"),
        ("###", "Header 3"),
    ]
    markdown_splitter = MarkdownHeaderTextSplitter(headers_to_split_on=headers_to_split_on)
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size, 
        chunk_overlap=chunk_overlap
    )

    all_splits = []
    for file_path in files:
        with open(file_path, "r", encoding="utf-8") as f:
            markdown_text = f.read()
        md_header_splits = markdown_splitter.split_text(markdown_text)
        splits = text_splitter.split_documents(md_header_splits)
        all_splits.extend(splits)

    embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
    vectorstore = FAISS.from_documents(all_splits, embeddings)
    os.makedirs(VECTOR_STORE_PATH, exist_ok=True)
    vectorstore.save_local(VECTOR_STORE_PATH)
    print(f"✅ [Optimization Tool] تم حفظ الفهرس الجديد بنجاح في: {VECTOR_STORE_PATH}")
    return vectorstore