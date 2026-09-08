from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI
import os


PROJECT_ROOT = Path(__file__).resolve().parent.parent

SERVICE_FOLDER = (
    PROJECT_ROOT
    / "knowledge_base"
    / "sakani"
    / "real_estate_transaction_tax_support"
)

INPUT_PATH = SERVICE_FOLDER / "content.md"
OUTPUT_PATH = SERVICE_FOLDER / "content_final_pilot.md"

MODEL = "gpt-4.1-mini"


load_dotenv(PROJECT_ROOT / ".env")

api_key = os.getenv("OPENAI_API_KEY")

if not api_key:
    raise ValueError("OPENAI_API_KEY was not found in .env")

client = OpenAI(api_key=api_key)


SYSTEM_PROMPT = """
You are performing final cleaning of text extracted from an official
Saudi government service guide.

Your task is ONLY to clean and reconstruct the extracted document text.

Rules:
1. Preserve ALL factual information from the input.
2. Do NOT add any information.
3. Do NOT summarize.
4. Do NOT translate.
5. Do NOT change the meaning.
6. Fix broken Arabic words and sentences caused by PDF extraction.
7. Merge lines that belong to the same sentence.
8. Remove repeated document titles, repeated section headers,
   table-of-contents noise, standalone page numbers, and visual noise.
9. Preserve numbered steps exactly as factual procedural information.
   Do not swap, reorder, merge, or renumber steps unless their correct
   number-to-text mapping is unambiguous from the input.
10. If the extracted text makes the correct order or number-to-text
    mapping uncertain, preserve the extracted wording rather than guessing.
    Never infer a procedural order based only on what seems logically likely.
11. Preserve requirements, conditions, contact information,
    working hours, warnings, notes, and other factual service details.
12. Remove closing decorative text such as standalone thank-you text
    only when it carries no service information.
13. Return only the cleaned document content.
14. Remove cover-page text and table-of-contents sections when they only
    repeat titles or section names already present in the document.

15. Do NOT paraphrase or stylistically rewrite valid sentences.
    Preserve the original wording as closely as possible.
    Only modify wording when necessary to repair clear PDF extraction errors.

16. Do NOT normalize a word into a different expression unless the original
    extracted form is clearly broken. When uncertain, preserve the original wording.

 17. Preserve valid original Arabic wording exactly whenever possible.
    For example, do not replace a valid word or phrase with a synonym.
"""


def final_clean(text):
    response = client.responses.create(
        model=MODEL,
        input=[
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": text,
            },
        ],
    )

    return response.output_text


def run_pilot():
    if not INPUT_PATH.exists():
        raise FileNotFoundError(
            f"Input file was not found: {INPUT_PATH}"
        )

    text = INPUT_PATH.read_text(encoding="utf-8")

    print("[PILOT] sakani/online_financing")
    print(f"[INPUT]  {INPUT_PATH.name}")

    cleaned = final_clean(text)

    OUTPUT_PATH.write_text(
        cleaned,
        encoding="utf-8",
    )

    print(f"[OUTPUT] {OUTPUT_PATH.name}")
    print("[OK] Sakani pilot final cleaning completed.")


if __name__ == "__main__":
    run_pilot()