from pathlib import Path
import pymupdf
import json
import unicodedata
from datetime import date


# Project paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
KNOWLEDGE_BASE = PROJECT_ROOT / "knowledge_base"

def normalize_text(text):
    """
    Normalize Arabic presentation forms and Unicode characters.
    """
    text = unicodedata.normalize("NFKC", text)

    # Remove extra spaces
    lines = []

    for line in text.splitlines():
        line = " ".join(line.split())

        if line:
            lines.append(line)

    return "\n".join(lines)


def extract_pdf_text(pdf_path):
    """
    Extract text page-by-page from a PDF file.
    """
    document = pymupdf.open(pdf_path)

    pages = []

    for page_number, page in enumerate(document, start=1):
        text = page.get_text("text").strip()
        text = normalize_text(text)
        
        pages.append({
            "page": page_number,
            "text": text
        })

    document.close()

    return pages


def save_extracted_text(service_folder, pages):
    """
    Save extracted PDF text as Markdown.
    """
    output_path = service_folder / "extracted_text.md"

    with open(output_path, "w", encoding="utf-8") as file:
        for page in pages:
            file.write(f"# Page {page['page']}\n\n")

            if page["text"]:
                file.write(page["text"])
            else:
                file.write("[No extractable text found on this page]")

            file.write("\n\n---\n\n")


def create_metadata(platform, service_folder, pdf_path, pages):
    """
    Create basic metadata for each knowledge unit.
    """
    metadata = {
        "platform": platform,
        "service_folder": service_folder.name,
        "domain": "Government Digital Services",
        "country": "Saudi Arabia",
        "language": "Arabic",
        "source_type": "Official PDF Guide",
        "source_file": str(pdf_path.relative_to(service_folder)),
        "document_id": f"{platform}_{service_folder.name}_001",
        "page_count": len(pages),
        "extraction_date": str(date.today())
    }

    metadata_path = service_folder / "metadata.json"

    with open(metadata_path, "w", encoding="utf-8") as file:
        json.dump(
            metadata,
            file,
            ensure_ascii=False,
            indent=4
        )


def process_knowledge_base():
    total_files = 0
    successful = 0
    failed = 0

    for platform_folder in KNOWLEDGE_BASE.iterdir():

        if not platform_folder.is_dir():
            continue

        platform = platform_folder.name

        print(f"\nPlatform: {platform}")
        print("-" * 50)

        for service_folder in platform_folder.iterdir():

            if not service_folder.is_dir():
                continue

            pdf_path = (
                service_folder
                / "source"
                / "official_guide.pdf"
            )

            if not pdf_path.exists():
                print(
                    f"[SKIPPED] {service_folder.name} "
                    f"- official_guide.pdf not found"
                )
                continue

            total_files += 1

            try:
                pages = extract_pdf_text(pdf_path)

                save_extracted_text(
                    service_folder,
                    pages
                )

                create_metadata(
                    platform,
                    service_folder,
                    pdf_path,
                    pages
                )

                extracted_characters = sum(
                    len(page["text"])
                    for page in pages
                )

                print(
                    f"[OK] {service_folder.name}"
                    f" | Pages: {len(pages)}"
                    f" | Characters: {extracted_characters}"
                )

                successful += 1

            except Exception as error:
                print(
                    f"[ERROR] {service_folder.name}"
                    f" | {error}"
                )

                failed += 1

    print("\n" + "=" * 50)
    print("Extraction completed")
    print(f"PDF files found: {total_files}")
    print(f"Successful: {successful}")
    print(f"Failed: {failed}")
    print("=" * 50)


if __name__ == "__main__":
    process_knowledge_base()