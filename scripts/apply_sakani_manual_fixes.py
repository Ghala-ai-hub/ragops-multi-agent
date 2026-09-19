import json
import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent

FIXES_PATH = (
    PROJECT_ROOT
    / "evaluation"
    / "sakani_manual_fixes.json"
)

KNOWLEDGE_BASE = (
    PROJECT_ROOT
    / "knowledge_base"
    / "sakani"
)


STEP_PATTERN = re.compile(
    r"^\s*(0?[1-9]|[1-9][0-9])[\.\)]?\s*(.*)\s*$"
)


SECTION_MARKERS = (
    "ملاحظات",
    "تواصل معنا",
    "إجراءات",
    "شروط",
)


def load_fixes():
    if not FIXES_PATH.exists():
        raise FileNotFoundError(
            f"Fixes file was not found: {FIXES_PATH}"
        )

    with FIXES_PATH.open(
        "r",
        encoding="utf-8",
    ) as file:
        return json.load(file)


def apply_step_fixes(text, fixes):
    fixes_by_step = {
        int(item["step"]): item["correct_text"].strip()
        for item in fixes
    }

    applied_steps = set()
    lines = text.splitlines()
    output_lines = []

    i = 0

    while i < len(lines):
        current_line = lines[i]
        match = STEP_PATTERN.match(current_line)

        if match:
            step_number = int(match.group(1))

            if step_number in fixes_by_step:
                output_lines.append(
                    f"{step_number:02d}"
                )
                output_lines.append(
                    fixes_by_step[step_number]
                )

                applied_steps.add(step_number)
                i += 1

                while i < len(lines):
                    next_line = lines[i]
                    stripped = next_line.strip()
                    next_step = STEP_PATTERN.match(
                        next_line
                    )

                    if next_step:
                        break

                    if stripped == "تواصل معنا":
                        break

                    i += 1

                continue

        output_lines.append(current_line)
        i += 1

    missing_steps = (
        set(fixes_by_step.keys())
        - applied_steps
    )

    if missing_steps:
        raise ValueError(
            "Could not apply fixes for steps: "
            f"{sorted(missing_steps)}"
        )

    return (
        "\n".join(output_lines).strip()
        + "\n"
    )


def rebuild_step_block(
    text,
    replacement_steps,
):
    lines = text.splitlines()

    first_step_index = None

    for index, line in enumerate(lines):
        if STEP_PATTERN.match(line):
            first_step_index = index
            break

    if first_step_index is None:
        raise ValueError(
            "Could not find the first numbered step."
        )

    end_index = len(lines)

    for index in range(
        first_step_index + 1,
        len(lines),
    ):
        stripped = lines[index].strip()

        if any(
            stripped.startswith(marker)
            for marker in SECTION_MARKERS
        ):
            end_index = index
            break

    rebuilt_steps = []

    for item in replacement_steps:
        step_number = int(item["step"])
        correct_text = (
            item["correct_text"].strip()
        )

        rebuilt_steps.append(
            f"{step_number:02d}"
        )
        rebuilt_steps.append(
            correct_text
        )

    new_lines = (
        lines[:first_step_index]
        + rebuilt_steps
        + [""]
        + lines[end_index:]
    )

    return (
        "\n".join(new_lines).strip()
        + "\n"
    )


def rebuild_multi_section_document(entry):
    output_lines = []

    document_title = entry.get(
        "document_title",
        "",
    ).strip()

    if document_title:
        output_lines.append(document_title)
        output_lines.append("")

    replacement_sections = entry.get(
        "replacement_sections",
        [],
    )

    if not replacement_sections:
        raise ValueError(
            "replacement_sections is empty."
        )

    for section in replacement_sections:
        output_lines.append(
            section["title"].strip()
        )
        output_lines.append("")

        for item in section["steps"]:
            step_number = int(item["step"])
            correct_text = (
                item["correct_text"].strip()
            )

            output_lines.append(
                f"{step_number:02d}"
            )
            output_lines.append(
                correct_text
            )

        output_lines.append("")

    append_validated_tail(
        output_lines,
        entry.get("validated_tail", {}),
    )

    return (
        "\n".join(output_lines).strip()
        + "\n"
    )


def rebuild_intro_step_document(entry):
    output_lines = []

    document_title = entry.get(
        "document_title",
        "",
    ).strip()

    if document_title:
        output_lines.append(document_title)
        output_lines.append("")

    for intro_line in entry.get(
        "intro_lines",
        [],
    ):
        output_lines.append(
            intro_line.strip()
        )

    if entry.get("intro_lines"):
        output_lines.append("")

    replacement_steps = entry.get(
        "replacement_steps",
        [],
    )

    if not replacement_steps:
        raise ValueError(
            "replacement_steps is empty."
        )

    for item in replacement_steps:
        step_number = int(item["step"])
        correct_text = (
            item["correct_text"].strip()
        )

        output_lines.append(
            f"{step_number:02d}"
        )
        output_lines.append(
            correct_text
        )

    output_lines.append("")

    append_validated_tail(
        output_lines,
        entry.get("validated_tail", {}),
    )

    return (
        "\n".join(output_lines).strip()
        + "\n"
    )


def append_validated_tail(
    output_lines,
    validated_tail,
):
    for section in validated_tail.get(
        "sections",
        [],
    ):
        output_lines.append(section)

    conditions = validated_tail.get(
        "conditions",
        [],
    )

    if conditions:
        output_lines.append("")

        for condition in conditions:
            output_lines.append(
                f"- {condition}"
            )

    contact = validated_tail.get(
        "contact",
        [],
    )

    if contact:
        output_lines.append("")
        output_lines.append("تواصل معنا")

        for contact_item in contact:
            output_lines.append(
                f"- {contact_item}"
            )


def apply_text_replacements(
    text,
    replacements,
):
    updated_text = text

    for item in replacements:
        updated_text = updated_text.replace(
            item["wrong_text"],
            item["correct_text"],
        )

    return updated_text


def apply_validated_tail(
    text,
    validated_tail,
):
    lines = text.splitlines()

    tail_start_index = None

    for index, line in enumerate(lines):
        stripped = line.strip()

        if any(
            stripped.startswith(marker)
            for marker in SECTION_MARKERS
        ):
            tail_start_index = index
            break

    if tail_start_index is None:
        raise ValueError(
            "Could not find the start "
            "of the document tail."
        )

    output_lines = lines[:tail_start_index]
    output_lines.append("")

    append_validated_tail(
        output_lines,
        validated_tail,
    )

    return (
        "\n".join(output_lines).strip()
        + "\n"
    )


def process_service(entry):
    service = entry["service"]

    service_folder = (
        KNOWLEDGE_BASE
        / service
    )

    input_path = (
        service_folder
        / "content_final_pilot.md"
    )

    output_path = (
        service_folder
        / "content_validated_pilot.md"
    )

    if not input_path.exists():
        raise FileNotFoundError(
            f"Pilot file was not found: "
            f"{input_path}"
        )

    text = input_path.read_text(
        encoding="utf-8"
    )

    if "replacement_sections" in entry:
        validated_text = (
            rebuild_multi_section_document(
                entry
            )
        )

    elif (
        "intro_lines" in entry
        and "replacement_steps" in entry
    ):
        validated_text = (
            rebuild_intro_step_document(
                entry
            )
        )

    elif "replacement_steps" in entry:
        validated_text = rebuild_step_block(
            text,
            entry["replacement_steps"],
        )

    elif "fixes" in entry:
        validated_text = apply_step_fixes(
            text,
            entry["fixes"],
        )

    else:
        validated_text = text

    full_rebuild = (
        "replacement_sections" in entry
        or (
            "intro_lines" in entry
            and "replacement_steps" in entry
        )
    )

    if (
        not full_rebuild
        and "text_replacements" in entry
    ):
        validated_text = (
            apply_text_replacements(
                validated_text,
                entry["text_replacements"],
            )
        )

    if (
        not full_rebuild
        and "validated_tail" in entry
    ):
        validated_text = (
            apply_validated_tail(
                validated_text,
                entry["validated_tail"],
            )
        )

    output_path.write_text(
        validated_text,
        encoding="utf-8",
    )

    print(f"[SERVICE] {service}")
    print(f"[INPUT]   {input_path.name}")
    print(f"[OUTPUT]  {output_path.name}")
    print("[OK] Documented fixes applied.")


def main():
    entries = load_fixes()

    for entry in entries:
        process_service(entry)

    print(
        "[DONE] All documented Sakani fixes "
        "were applied successfully."
    )


if __name__ == "__main__":
    main()