import os
from dotenv import load_dotenv

load_dotenv()

from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import (
    MarkdownHeaderTextSplitter,
    RecursiveCharacterTextSplitter,
)



def build_specific_vectorstore():
  # تحديد المجلدات المطلوبة فقط
  target_folders = ["balady", "najiz"]
  knowledge_base_dir = "knowledge_base"

  files = []
  for folder in target_folders:
    folder_path = os.path.join(knowledge_base_dir, folder)
    if os.path.exists(folder_path):
      for root, dirs, filenames in os.walk(folder_path):
        for f in filenames:
          if f.endswith(".md"):
            files.append(os.path.join(root, f))
    else:
      print(f"تنبيه: المجلد غير موجود: {folder_path}")

  if not files:
    print("خطأ: لم يتم العثور على أي ملفات .md في المجلدات المحددة.")
    return

  print(f"تم العثور على {len(files)} ملفات تخص (بلدي وناجز) فقط.")

  headers_to_split_on = [
      ("#", "Header 1"),
      ("##", "Header 2"),
      ("###", "Header 3"),
  ]
  markdown_splitter = MarkdownHeaderTextSplitter(
      headers_to_split_on=headers_to_split_on
  )
  text_splitter = RecursiveCharacterTextSplitter(
      chunk_size=1000, chunk_overlap=200
  )

  all_splits = []

  for file_path in files:
    print(f"جاري معالجة الملف: {file_path}")
    with open(file_path, "r", encoding="utf-8") as f:
      markdown_text = f.read()

    md_header_splits = markdown_splitter.split_text(markdown_text)
    splits = text_splitter.split_documents(md_header_splits)
    all_splits.extend(splits)

  print(f"إجمالي عدد الـ Chunks الخاصة ببلدي وناجز: {len(all_splits)}")

  embeddings = OpenAIEmbeddings(model="text-embedding-3-small")

  print("جاري إنشاء وحفظ الـ Vector Store الخاص ببلدي وناجز...")
  vectorstore = FAISS.from_documents(all_splits, embeddings)

  # يمكنك حفظها في مسار مختلف لكي لا تحذفي النسخة الشاملة القديمة
  output_path = "vector_store/balady_najiz_index"
  os.makedirs(output_path, exist_ok=True)
  vectorstore.save_local(output_path)
  print(f"تم بنجاح حفظ فهرس بلدي وناجز في المسار: {output_path}")


if __name__ == "__main__":
  build_specific_vectorstore()