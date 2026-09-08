from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent

SAKANI_ROOT = (
    PROJECT_ROOT
    / "knowledge_base"
    / "sakani"
)


SERVICES = [
    "housing_support_eligibility",
    "housing_unit_rental",
    "online_financing",
    "real_estate_advisor",
    "real_estate_transaction_tax_support",
    "residential_lands",
]


SOURCE_FILENAME = "content_validated_pilot.md"
TARGET_FILENAME = "content_final.md"


def validate_all_services():
    validated_files = []

    for service in SERVICES:
        service_folder = SAKANI_ROOT / service

        source_path = (
            service_folder
            / SOURCE_FILENAME
        )

        target_path = (
            service_folder
            / TARGET_FILENAME
        )

        if not service_folder.exists():
            raise FileNotFoundError(
                f"Service folder was not found: "
                f"{service_folder}"
            )

        if not source_path.exists():
            raise FileNotFoundError(
                f"Validated file was not found: "
                f"{source_path}"
            )

        content = source_path.read_text(
            encoding="utf-8"
        ).strip()

        if not content:
            raise ValueError(
                f"Validated file is empty: "
                f"{source_path}"
            )

        if target_path.exists():
            raise FileExistsError(
                f"Final file already exists: "
                f"{target_path}"
            )

        validated_files.append(
            (
                service,
                source_path,
                target_path,
                content,
            )
        )

    return validated_files


def promote_files(validated_files):
    for (
        service,
        source_path,
        target_path,
        content,
    ) in validated_files:

        target_path.write_text(
            content + "\n",
            encoding="utf-8",
        )

        print(f"[SERVICE] {service}")
        print(
            f"[SOURCE]  {source_path.name}"
        )
        print(
            f"[FINAL]   {target_path.name}"
        )
        print("[OK] Promoted to final corpus.")


def main():
    print(
        "[CHECK] Validating all Sakani "
        "services before promotion..."
    )

    validated_files = (
        validate_all_services()
    )

    print(
        f"[PASS] {len(validated_files)} "
        "services are ready."
    )

    promote_files(validated_files)

    print(
        "[DONE] Sakani validated corpus "
        "promotion completed successfully."
    )


if __name__ == "__main__":
    main()