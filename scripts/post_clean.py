from pathlib import Path
import re


PROJECT_ROOT = Path(__file__).resolve().parent.parent
KNOWLEDGE_BASE = PROJECT_ROOT / "knowledge_base"

TARGET_PLATFORMS = {"najiz", "balady"}

NOISE_PATTERNS = [
    r"User Manual",
    r"Via Najiz Portal",
    r"najiz\.sa",
    r"الدليل الإرشادي",
    r"دليل المستخدم",
    r"^\s*---\s*$"
]


def normalize_line(line):
    line = line.strip()

    if not line:
        return ""

    for pattern in NOISE_PATTERNS:
        line = re.sub(pattern, "", line, flags=re.IGNORECASE)

    line = re.sub(r"\s+", " ", line)

    line = re.sub(r"\s+([،؛:.؟])", r"\1", line)

    return line.strip()


def remove_duplicate_lines(lines):
    result = []

    for line in lines:
        if not line:
            continue

        if result and line == result[-1]:
            continue

        result.append(line)

    return result


def post_clean_text(text):
    lines = []

    for raw_line in text.splitlines():
        cleaned = normalize_line(raw_line)

        if cleaned:
            lines.append(cleaned)

    lines = remove_duplicate_lines(lines)

    return "\n".join(lines)


def process_documents():
    processed = 0

    for platform in TARGET_PLATFORMS:
        platform_folder = KNOWLEDGE_BASE / platform

        if not platform_folder.exists():
            continue

        for service_folder in platform_folder.iterdir():

            if not service_folder.is_dir():
                continue

            content_path = service_folder / "content.md"

            if not content_path.exists():
                continue

            text = content_path.read_text(
                encoding="utf-8"
            )

            cleaned = post_clean_text(text)

            content_path.write_text(
                cleaned,
                encoding="utf-8"
            )

            print(
                f"[OK] {platform}/{service_folder.name}"
            )

            processed += 1

    print("\n" + "=" * 50)
    print(f"Post-cleaned documents: {processed}")
    print("=" * 50)


if __name__ == "__main__":
    process_documents()