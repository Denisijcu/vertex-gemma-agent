import json
import os


# =============================================================================
# CONFIGURATION
# =============================================================================

BASE_DIR = r"F:\vertex-gemma-agent"

INPUT_TASKS = os.path.join(
    BASE_DIR,
    "data",
    "raw",
    "tasks.jsonl",
)

OUTPUT_DATASET = os.path.join(
    BASE_DIR,
    "data",
    "processed",
    "sft_main_lora.jsonl",
)

REPORT_FILE = os.path.join(
    BASE_DIR,
    "data",
    "processed",
    "dataset_validation_report.json",
)


# =============================================================================
# VALIDATION
# =============================================================================

def validate_record(data):
    """
    Validate one SWE-bench/Kaggle-style task.

    Returns:
        (True, None) if valid.
        (False, reason) if invalid.
    """

    if not isinstance(data, dict):
        return False, "record_is_not_object"

    # -------------------------------------------------------------------------
    # Required fields
    # -------------------------------------------------------------------------

    problem_statement = data.get("problem_statement")
    patch = data.get("patch")

    if problem_statement is None:
        return False, "missing_problem_statement"

    if not isinstance(problem_statement, str):
        return False, "problem_statement_not_string"

    problem_statement = problem_statement.strip()

    if not problem_statement:
        return False, "empty_problem_statement"

    if patch is None:
        return False, "missing_patch"

    if not isinstance(patch, str):
        return False, "patch_not_string"

    patch = patch.strip()

    if not patch:
        return False, "empty_patch"

    # -------------------------------------------------------------------------
    # Basic patch validation
    # -------------------------------------------------------------------------

    if "--- " not in patch or "+++ " not in patch:
        return False, "patch_not_git_diff"

    return True, None


# =============================================================================
# BUILD ASSISTANT RESPONSE
# =============================================================================

def build_assistant_content(data):
    """
    Build the assistant target.

    We intentionally keep the real patch as raw patch text.
    We do NOT wrap it in ```bash fences.
    """

    patch = data["patch"].strip()

    test_patch = data.get("test_patch", "")

    if isinstance(test_patch, str):
        test_patch = test_patch.strip()
    else:
        test_patch = ""

    # -------------------------------------------------------------------------
    # Keep the implementation patch as the primary answer.
    #
    # We do not append test_patch to the assistant answer because that would
    # teach the model that every repository modification must include the test
    # diff in the same response.
    # -------------------------------------------------------------------------

    return patch


# =============================================================================
# BUILD USER PROMPT
# =============================================================================

def build_user_content(data):
    """
    Build a repository-aware engineering task.

    The model is explicitly told what repository and base commit the task
    belongs to, while the actual repository contents are NOT fabricated.
    """

    repo = data.get("repo", "")
    base_commit = data.get("base_commit", "")
    problem_statement = data["problem_statement"].strip()

    parts = []

    parts.append("Resolve the following software engineering issue.")

    if repo:
        parts.append(f"Repository: {repo}")

    if base_commit:
        parts.append(f"Base commit: {base_commit}")

    parts.append("")
    parts.append("Issue:")
    parts.append(problem_statement)

    parts.append("")
    parts.append(
        "Apply the necessary code changes for this issue. "
        "Do not invent repository contents that are not provided."
    )

    return "\n".join(parts)


# =============================================================================
# DATASET BUILDER
# =============================================================================

def build_sft_dataset():

    os.makedirs(
        os.path.dirname(OUTPUT_DATASET),
        exist_ok=True,
    )

    if not os.path.exists(INPUT_TASKS):
        print("[ERROR] No se encontró tasks.jsonl en:")
        print(f"        {INPUT_TASKS}")
        return

    total = 0
    valid = 0
    skipped = 0
    invalid_json = 0

    reasons = {}

    print("=" * 70)
    print("VERTEX CORE - DATASET BUILDER")
    print("=" * 70)
    print(f"Input : {INPUT_TASKS}")
    print(f"Output: {OUTPUT_DATASET}")
    print()

    with open(
        INPUT_TASKS,
        "r",
        encoding="utf-8",
    ) as fin, open(
        OUTPUT_DATASET,
        "w",
        encoding="utf-8",
    ) as fout:

        for line_number, line in enumerate(fin, start=1):

            if not line.strip():
                continue

            total += 1

            # -----------------------------------------------------------------
            # Parse JSON
            # -----------------------------------------------------------------

            try:
                data = json.loads(line)

            except json.JSONDecodeError as exc:
                invalid_json += 1
                skipped += 1

                reason = "invalid_json"
                reasons[reason] = reasons.get(reason, 0) + 1

                print(
                    f"[SKIP] Línea {line_number}: "
                    f"JSON inválido ({exc})"
                )

                continue

            # -----------------------------------------------------------------
            # Validate semantic content
            # -----------------------------------------------------------------

            is_valid, reason = validate_record(data)

            if not is_valid:
                skipped += 1
                reasons[reason] = reasons.get(reason, 0) + 1

                print(
                    f"[SKIP] Línea {line_number}: {reason}"
                )

                continue

            # -----------------------------------------------------------------
            # Build SFT example
            # -----------------------------------------------------------------

            system_prompt = (
                "Eres un agente autónomo de ingeniería de software "
                "especializado en trabajar con repositorios de código. "
                "Tu trabajo incluye investigar issues, comprender el "
                "código existente, implementar cambios, corregir bugs, "
                "mantener seguridad y verificar los cambios mediante "
                "pruebas. "
                "Cuando trabajas con un repositorio real, inspecciona "
                "primero el código relevante antes de modificarlo. "
                "No inventes archivos, código, resultados de herramientas "
                "ni resultados de pruebas."
            )

            user_content = build_user_content(data)
            assistant_content = build_assistant_content(data)

            sft_entry = {
                "messages": [
                    {
                        "role": "system",
                        "content": system_prompt,
                    },
                    {
                        "role": "user",
                        "content": user_content,
                    },
                    {
                        "role": "assistant",
                        "content": assistant_content,
                    },
                ]
            }

            fout.write(
                json.dumps(
                    sft_entry,
                    ensure_ascii=False,
                )
                + "\n"
            )

            valid += 1

    # =========================================================================
    # REPORT
    # =========================================================================

    report = {
        "input_file": INPUT_TASKS,
        "output_file": OUTPUT_DATASET,
        "total_records": total,
        "valid_records": valid,
        "skipped_records": skipped,
        "invalid_json": invalid_json,
        "skip_reasons": reasons,
    }

    with open(
        REPORT_FILE,
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            report,
            f,
            ensure_ascii=False,
            indent=2,
        )

    # =========================================================================
    # SUMMARY
    # =========================================================================

    print()
    print("=" * 70)
    print("RESULTADO")
    print("=" * 70)

    print(f"Total registros : {total}")
    print(f"Válidos         : {valid}")
    print(f"Descartados     : {skipped}")
    print(f"JSON inválidos  : {invalid_json}")

    print()
    print("Motivos de descarte:")

    if reasons:
        for reason, count in sorted(
            reasons.items(),
            key=lambda item: item[0],
        ):
            print(f"  - {reason}: {count}")
    else:
        print("  Ninguno")

    print()
    print("[OK] Dataset generado:")
    print(f"     {OUTPUT_DATASET}")

    print()
    print("[OK] Reporte generado:")
    print(f"     {REPORT_FILE}")

    print()
    print("=" * 70)


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    build_sft_dataset()