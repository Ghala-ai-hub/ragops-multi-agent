import os
from pathlib import Path

from dotenv import load_dotenv
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import (
    MarkdownHeaderTextSplitter,
    RecursiveCharacterTextSplitter,
)

load_dotenv()


def build_evaluation_vectorstore():
    knowledge_base_dir = Path("knowledge_base")
    target_platforms = ["absher", "balady", "najiz", "sakani"]

    files = []

    for platform in target_platforms:
        platform_dir = knowledge_base_dir / platform

        if not platform_dir.exists():
            print(f"WARNING: Platform folder not found: {platform_dir}")
            continue

        for service_dir in platform_dir.iterdir():
            if not service_dir.is_dir():
                continue

            final_file = service_dir / "content_final.md"

            if final_file.exists():
                files.append(final_file)

    files = sorted(files)

    if not files:
        print("ERROR: No content_final.md files found.")
        return

    print(f"FINAL FILES FOUND: {len(files)}")

    headers_to_split_on = [
        ("#", "Header 1"),
        ("##", "Header 2"),
        ("###", "Header 3"),
    ]

    markdown_splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=headers_to_split_on
    )

    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
    )

    all_splits = []

    for file_path in files:
        relative_path = file_path.relative_to(knowledge_base_dir)

        platform = relative_path.parts[0]
        service = relative_path.parts[1]

        with open(file_path, "r", encoding="utf-8") as f:
            markdown_text = f.read()

        md_header_splits = markdown_splitter.split_text(markdown_text)
        splits = text_splitter.split_documents(md_header_splits)

        source = file_path.as_posix()

        for chunk_index, split in enumerate(splits):
            split.metadata.update(
                {
                    "platform": platform,
                    "service": service,
                    "source": source,
                    "chunk_index": chunk_index,
                }
            )

        all_splits.extend(splits)

        print(f"{platform}/{service}: {len(splits)} chunks")

    print(f"TOTAL CHUNKS: {len(all_splits)}")

    embeddings = OpenAIEmbeddings(model="text-embedding-3-small")

    print("Building evaluation FAISS index...")

    vectorstore = FAISS.from_documents(all_splits, embeddings)

    output_path = "vector_store/evaluation_index"
    os.makedirs(output_path, exist_ok=True)

    vectorstore.save_local(output_path)

    print(f"Saved evaluation index to: {output_path}")


if __name__ == "__main__":
    build_evaluation_vectorstore()
