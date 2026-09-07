from pathlib import Path
import re


PROJECT_ROOT = Path(__file__).resolve().parent.parent
KNOWLEDGE_BASE = PROJECT_ROOT / "knowledge_base"


NOISE_PATTERNS = [
    r"najiz\.sa",
    r"Via Najiz Portal",
    r"User Manual",
]


def clean_line(line):
    line = line.strip()

    # Remove Markdown page separators and headers
    if not line:
        return ""

    if line.startswith("# Page"):
        return ""

    if line == "---":
        return ""

    # Remove known repeated noise
    for pattern in NOISE_PATTERNS:
        line = re.sub(pattern, "", line, flags=re.IGNORECASE)

    # Normalize spaces
    line = re.sub(r"\s+", " ", line)

    # Fix spaces before punctuation
    line = re.sub(r"\s+([،.:؛؟])", r"\1", line)

    # Remove escaped markdown numbers such as 1\.
    line = re.sub(r"(\d+)\\\.", r"\1.", line)

    return line.strip()


def clean_document(text):
    cleaned_lines = []

    for line in text.splitlines():
        cleaned = clean_line(line)

        if cleaned:
            cleaned_lines.append(cleaned)

    # Remove consecutive duplicate lines
    final_lines = []

    for line in cleaned_lines:
        if not final_lines or line != final_lines[-1]:
            final_lines.append(line)

    return "\n".join(final_lines)


def process_all_documents():
    processed = 0

    for platform_folder in KNOWLEDGE_BASE.iterdir():
        if not platform_folder.is_dir():
            continue

        for service_folder in platform_folder.iterdir():
            if not service_folder.is_dir():
                continue

            extracted_path = service_folder / "extracted_text.md"

            if not extracted_path.exists():
                continue

            raw_text = extracted_path.read_text(
                encoding="utf-8"
            )

            cleaned_text = clean_document(raw_text)

            output_path = service_folder / "content.md"

            output_path.write_text(
                cleaned_text,
                encoding="utf-8"
            )

            print(
                f"[OK] {platform_folder.name}/"
                f"{service_folder.name}"
            )

            processed += 1

    print("\n" + "=" * 50)
    print(f"Cleaned documents: {processed}")
    print("=" * 50)


if __name__ == "__main__":
    process_all_documents()