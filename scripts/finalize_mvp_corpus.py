from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI
import os


PROJECT_ROOT = Path(__file__).resolve().parent.parent
KNOWLEDGE_BASE = PROJECT_ROOT / "knowledge_base"

TARGET_PLATFORMS = {"najiz", "balady"}

load_dotenv(PROJECT_ROOT / ".env")

api_key = os.getenv("OPENAI_API_KEY")

if not api_key:
    raise ValueError("OPENAI_API_KEY was not found in .env")

client = OpenAI(api_key=api_key)


SYSTEM_PROMPT = """
You are performing the final cleaning of text extracted from official Saudi government service guides.

Rules:
1. Preserve ALL factual information.
2. Do NOT add any information.
3. Do NOT summarize.
4. Do NOT translate.
5. Do NOT change the meaning.
6. Fix broken Arabic words and sentences caused by PDF extraction.
7. Remove repeated headers, repeated document titles, website names used only as headers, and visual separators.
8. Remove table-of-contents noise and standalone page numbers when they are clearly not part of the service instructions.
9. Preserve actual numbered service steps in their correct order.
10. Preserve requirements, conditions, fees, warnings, notes, and service details.
11. Merge lines that belong to the same sentence.
12. Return only the cleaned content.
"""


def clean_final(text):
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


def process_documents():
    processed = 0
    failed = 0

    for platform in TARGET_PLATFORMS:

        platform_folder = KNOWLEDGE_BASE / platform

        for service_folder in platform_folder.iterdir():

            if not service_folder.is_dir():
                continue

            input_path = service_folder / "content.md"
            output_path = service_folder / "content_final.md"

            if not input_path.exists():
                continue

            try:
                text = input_path.read_text(encoding="utf-8")

                print(f"[FINAL CLEAN] {platform}/{service_folder.name}")

                cleaned = clean_final(text)

                output_path.write_text(
                    cleaned,
                    encoding="utf-8"
                )

                print(f"[OK] {platform}/{service_folder.name}")

                processed += 1

            except Exception as error:
                print(
                    f"[ERROR] {platform}/{service_folder.name} | {error}"
                )
                failed += 1

    print("\n" + "=" * 60)
    print("FINAL MVP CLEANING COMPLETED")
    print(f"Processed: {processed}")
    print(f"Failed: {failed}")
    print("=" * 60)


if __name__ == "__main__":
    process_documents()