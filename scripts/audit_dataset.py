import json
import re
from collections import Counter


DATASET = r"F:\vertex-gemma-agent\data\processed\sft_main_lora.jsonl"


def get_message(row, role):
    for message in row["messages"]:
        if message.get("role") == role:
            return message.get("content", "")
    return ""


def get_repository(user_content):
    match = re.search(
        r"^Repository:\s*(.+)$",
        user_content,
        re.MULTILINE,
    )
    return match.group(1).strip() if match else "<unknown>"


def get_base_commit(user_content):
    match = re.search(
        r"^Base commit:\s*(.+)$",
        user_content,
        re.MULTILINE,
    )
    return match.group(1).strip() if match else "<unknown>"


def get_patch_files(patch):
    files = []

    for match in re.finditer(
        r"^--- a/(.+)$",
        patch,
        re.MULTILINE,
    ):
        files.append(match.group(1))

    return files


def main():
    print("=" * 70)
    print("VERTEX CORE - DATASET AUDIT")
    print("=" * 70)
    print(f"Dataset: {DATASET}")
    print()

    with open(DATASET, "r", encoding="utf-8") as f:
        rows = [
            json.loads(line)
            for line in f
            if line.strip()
        ]

    print(f"REGISTROS: {len(rows)}")
    print()

    repositories = Counter()
    files = Counter()

    missing_repository = 0
    missing_commit = 0
    missing_issue = 0
    invalid_patch = 0

    total_issue_chars = 0
    total_patch_chars = 0

    # -------------------------------------------------------------------------
    # Inspect every record
    # -------------------------------------------------------------------------

    for index, row in enumerate(rows, start=1):

        user_content = get_message(row, "user")
        assistant_content = get_message(row, "assistant")

        repository = get_repository(user_content)
        base_commit = get_base_commit(user_content)

        repositories[repository] += 1

        if repository == "<unknown>":
            missing_repository += 1

        if base_commit == "<unknown>":
            missing_commit += 1

        if not user_content.strip():
            missing_issue += 1

        total_issue_chars += len(user_content)
        total_patch_chars += len(assistant_content)

        patch_files = get_patch_files(assistant_content)

        for file_path in patch_files:
            files[file_path] += 1

        # Basic Git diff validation
        has_old_file = bool(
            re.search(
                r"^--- ",
                assistant_content,
                re.MULTILINE,
            )
        )

        has_new_file = bool(
            re.search(
                r"^\+\+\+ ",
                assistant_content,
                re.MULTILINE,
            )
        )

        if not has_old_file or not has_new_file:
            invalid_patch += 1

    # -------------------------------------------------------------------------
    # First examples
    # -------------------------------------------------------------------------

    print("-" * 70)
    print("PRIMEROS 10 EJEMPLOS")
    print("-" * 70)

    for index, row in enumerate(rows[:10], start=1):

        user_content = get_message(row, "user")
        assistant_content = get_message(row, "assistant")

        repository = get_repository(user_content)
        base_commit = get_base_commit(user_content)

        issue_match = re.search(
            r"^Issue:\s*(.*?)(?:\n\n|\Z)",
            user_content,
            re.DOTALL,
        )

        issue = (
            issue_match.group(1).strip()
            if issue_match
            else "<not found>"
        )

        patch_files = get_patch_files(assistant_content)

        print(
            f"[{index:03d}] "
            f"repo={repository} | "
            f"commit={base_commit} | "
            f"issue_chars={len(user_content)} | "
            f"patch_chars={len(assistant_content)}"
        )

        print(f"       issue: {issue[:150]}")

        if patch_files:
            print(
                f"       files: {', '.join(patch_files[:5])}"
            )

        print()

    # -------------------------------------------------------------------------
    # Repository statistics
    # -------------------------------------------------------------------------

    print("-" * 70)
    print("REPOSITORIES")
    print("-" * 70)

    for repository, count in repositories.most_common():
        print(f"  {repository}: {count}")

    # -------------------------------------------------------------------------
    # File statistics
    # -------------------------------------------------------------------------

    print()
    print("-" * 70)
    print("ARCHIVOS MÁS MODIFICADOS")
    print("-" * 70)

    for file_path, count in files.most_common(20):
        print(f"  {count:3d}  {file_path}")

    # -------------------------------------------------------------------------
    # Quality statistics
    # -------------------------------------------------------------------------

    average_issue_chars = (
        total_issue_chars / len(rows)
        if rows
        else 0
    )

    average_patch_chars = (
        total_patch_chars / len(rows)
        if rows
        else 0
    )

    print()
    print("-" * 70)
    print("CALIDAD DEL DATASET")
    print("-" * 70)

    print(f"Registros totales       : {len(rows)}")
    print(f"Repository faltante     : {missing_repository}")
    print(f"Base commit faltante    : {missing_commit}")
    print(f"Issue vacío             : {missing_issue}")
    print(f"Patches inválidos       : {invalid_patch}")

    print()
    print(f"Issue promedio chars    : {average_issue_chars:.0f}")
    print(f"Patch promedio chars    : {average_patch_chars:.0f}")
    print(f"Patch total chars       : {total_patch_chars}")

    # -------------------------------------------------------------------------
    # Final verdict
    # -------------------------------------------------------------------------

    print()
    print("=" * 70)

    if (
        missing_repository == 0
        and missing_commit == 0
        and missing_issue == 0
        and invalid_patch == 0
    ):
        print("AUDITORÍA BÁSICA: PASS")
    else:
        print("AUDITORÍA BÁSICA: REVISAR")

    print("=" * 70)


if __name__ == "__main__":
    main()