from pathlib import Path
import json


PROJECT_ROOT = Path(__file__).resolve().parent.parent
KNOWLEDGE_BASE = PROJECT_ROOT / "knowledge_base"


def classify_quality(avg_chars_per_page):
    if avg_chars_per_page >= 250:
        return "GOOD"
    elif avg_chars_per_page >= 100:
        return "MEDIUM"
    else:
        return "LOW"


def check_quality():
    results = []

    for platform_folder in KNOWLEDGE_BASE.iterdir():
        if not platform_folder.is_dir():
            continue

        platform = platform_folder.name

        for service_folder in platform_folder.iterdir():
            if not service_folder.is_dir():
                continue

            metadata_path = service_folder / "metadata.json"
            extracted_path = service_folder / "extracted_text.md"

            if not metadata_path.exists() or not extracted_path.exists():
                continue

            with open(metadata_path, "r", encoding="utf-8") as file:
                metadata = json.load(file)

            text = extracted_path.read_text(encoding="utf-8")

            page_count = metadata.get("page_count", 0)
            char_count = len(text)

            if page_count > 0:
                avg_chars_per_page = round(char_count / page_count, 2)
            else:
                avg_chars_per_page = 0

            quality = classify_quality(avg_chars_per_page)

            results.append({
                "platform": platform,
                "service": service_folder.name,
                "pages": page_count,
                "characters": char_count,
                "avg_chars_per_page": avg_chars_per_page,
                "quality": quality
            })

    results.sort(
        key=lambda item: (
            item["quality"],
            item["avg_chars_per_page"]
        )
    )

    print("\nDATA QUALITY REPORT")
    print("=" * 90)

    for item in results:
        print(
            f"{item['platform']:10}"
            f" | {item['service']:35}"
            f" | Pages: {item['pages']:3}"
            f" | Chars: {item['characters']:6}"
            f" | Avg/Page: {item['avg_chars_per_page']:7}"
            f" | {item['quality']}"
        )

    print("=" * 90)

    good = sum(1 for item in results if item["quality"] == "GOOD")
    medium = sum(1 for item in results if item["quality"] == "MEDIUM")
    low = sum(1 for item in results if item["quality"] == "LOW")

    print(f"GOOD:   {good}")
    print(f"MEDIUM: {medium}")
    print(f"LOW:    {low}")
    print(f"TOTAL:  {len(results)}")


if __name__ == "__main__":
    check_quality()