from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI
import os
import json


PROJECT_ROOT = Path(__file__).resolve().parent.parent
KNOWLEDGE_BASE = PROJECT_ROOT / "knowledge_base"

load_dotenv(PROJECT_ROOT / ".env")

api_key = os.getenv("OPENAI_API_KEY")

if not api_key:
    raise ValueError("OPENAI_API_KEY was not found in .env")

client = OpenAI(api_key=api_key)


SYSTEM_PROMPT = """
You are cleaning text extracted from official Saudi government PDF documents.

Your task is ONLY to repair PDF extraction errors.

Rules:
1. Preserve every factual detail from the source.
2. Do NOT add new information.
3. Do NOT remove factual information.
4. Do NOT summarize.
5. Do NOT answer questions about the content.
6. Repair broken Arabic words caused by PDF extraction.
7. Join lines that were incorrectly split.
8. Remove repeated page headers and obvious extraction noise.
9. Remove repeated website names such as najiz.sa when they are only page headers.
10. Remove visual separators such as --- when they do not carry meaning.
11. Preserve numbered steps and their original order.
12. Preserve English terms when they are meaningful.
13. Do not translate the content.
14. Return only the cleaned document text.
"""


def classify_quality(avg_chars_per_page):
    if avg_chars_per_page >= 250:
        return "GOOD"
    elif avg_chars_per_page >= 100:
        return "MEDIUM"
    else:
        return "LOW"


def clean_with_llm(text):
    response = client.responses.create(
        model="gpt-4.1-mini",
        input=[
            {
                "role": "system",
                "content": SYSTEM_PROMPT
            },
            {
                "role": "user",
                "content": text
            }
        ]
    )

    return response.output_text


def get_quality(service_folder):
    metadata_path = service_folder / "metadata.json"
    extracted_path = service_folder / "extracted_text.md"

    if not metadata_path.exists() or not extracted_path.exists():
        return None

    with open(metadata_path, "r", encoding="utf-8") as file:
        metadata = json.load(file)

    text = extracted_path.read_text(encoding="utf-8")

    page_count = metadata.get("page_count", 0)

    if page_count == 0:
        return None

    avg_chars_per_page = len(text) / page_count

    return classify_quality(avg_chars_per_page)


def process_all():
    processed = 0
    skipped = 0
    failed = 0

    for platform_folder in KNOWLEDGE_BASE.iterdir():

        if not platform_folder.is_dir():
            continue

        for service_folder in platform_folder.iterdir():

            if not service_folder.is_dir():
                continue

            quality = get_quality(service_folder)

            if quality is None:
                continue

            if quality == "LOW":
                print(
                    f"[SKIPPED LOW] "
                    f"{platform_folder.name}/{service_folder.name}"
                )
                skipped += 1
                continue

            input_path = service_folder / "extracted_text.md"
            output_path = service_folder / "content.md"

            try:
                raw_text = input_path.read_text(
                    encoding="utf-8"
                )

                print(
                    f"[CLEANING] "
                    f"{platform_folder.name}/{service_folder.name}"
                    f" | {quality}"
                )

                cleaned_text = clean_with_llm(raw_text)

                output_path.write_text(
                    cleaned_text,
                    encoding="utf-8"
                )

                print(
                    f"[OK] "
                    f"{platform_folder.name}/{service_folder.name}"
                )

                processed += 1

            except Exception as error:

                print(
                    f"[ERROR] "
                    f"{platform_folder.name}/{service_folder.name}"
                    f" | {error}"
                )

                failed += 1

    print("\n" + "=" * 60)
    print("LLM CLEANING COMPLETED")
    print(f"Processed GOOD/MEDIUM: {processed}")
    print(f"Skipped LOW: {skipped}")
    print(f"Failed: {failed}")
    print("=" * 60)


if __name__ == "__main__":
    process_all()