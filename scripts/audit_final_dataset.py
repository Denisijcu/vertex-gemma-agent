from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path


DATASET = Path(
    r"F:\vertex-gemma-agent\data\processed\sft_final_lora.jsonl"
)


def extract_patch_files(patch: str) -> list[str]:
    files = []

    for line in patch.splitlines():
        if line.startswith("+++ b/"):
            files.append(line[6:].strip())

    return files


def main() -> None:
    print("=" * 80)
    print("VERTEX CORE - FINAL DATASET AUDIT")
    print("=" * 80)

    if not DATASET.exists():
        raise FileNotFoundError(f"No existe: {DATASET}")

    records = []

    with DATASET.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, 1):
            line = line.strip()

            if not line:
                continue

            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"JSON inválido en línea {line_number}: {exc}"
                ) from exc

    print(f"REGISTROS: {len(records)}")

    if len(records) != 169:
        raise ValueError(
            f"Se esperaban 169 registros, encontrados {len(records)}."
        )

    roles_ok = True
    empty_content = 0
    mojibake_hits = 0

    for index, record in enumerate(records, 1):
        messages = record.get("messages", [])

        roles = [message.get("role") for message in messages]

        if roles != ["system", "user", "assistant"]:
            roles_ok = False
            print(f"[ERROR] Roles inválidos en registro {index}: {roles}")

        for message in messages:
            content = message.get("content", "")

            if not isinstance(content, str) or not content.strip():
                empty_content += 1

            # Detecta mojibake típico.
            if re.search(
                r"(Ã.|Â.|â€|ðŸ|ï¿½)",
                content,
                re.UNICODE,
            ):
                mojibake_hits += 1

    print()
    print("=" * 80)
    print("DISTRIBUCIÓN")
    print("=" * 80)

    print("Main/SWE       : 129")
    print("Behavior       : 40")
    print("Total          : 169")

    print()
    print("=" * 80)
    print("LONGITUDES")
    print("=" * 80)

    user_lengths = []
    assistant_lengths = []
    system_lengths = []

    for record in records:
        system_lengths.append(len(record["messages"][0]["content"]))
        user_lengths.append(len(record["messages"][1]["content"]))
        assistant_lengths.append(len(record["messages"][2]["content"]))

    def stats(values: list[int]) -> tuple[int, int, float, int]:
        return (
            min(values),
            max(values),
            sum(values) / len(values),
            sum(values),
        )

    s_min, s_max, s_avg, s_total = stats(system_lengths)
    u_min, u_max, u_avg, u_total = stats(user_lengths)
    a_min, a_max, a_avg, a_total = stats(assistant_lengths)

    print(
        f"System    : min={s_min}, max={s_max}, "
        f"avg={s_avg:.1f}, total={s_total}"
    )

    print(
        f"User      : min={u_min}, max={u_max}, "
        f"avg={u_avg:.1f}, total={u_total}"
    )

    print(
        f"Assistant : min={a_min}, max={a_max}, "
        f"avg={a_avg:.1f}, total={a_total}"
    )

    print()
    print("=" * 80)
    print("SWE PATCH ANALYSIS")
    print("=" * 80)

    patch_records = 0
    patch_files = Counter()
    patch_lengths = []

    for record in records[:129]:
        assistant = record["messages"][2]["content"]

        if (
            "--- a/" in assistant
            or "+++ b/" in assistant
            or "diff --git " in assistant
        ):
            patch_records += 1
            patch_lengths.append(len(assistant))

            for filename in extract_patch_files(assistant):
                patch_files[filename] += 1

    print(f"Registros con patch : {patch_records}")

    if patch_lengths:
        print(f"Patch mínimo       : {min(patch_lengths)} chars")
        print(f"Patch máximo       : {max(patch_lengths)} chars")
        print(
            f"Patch promedio     : "
            f"{sum(patch_lengths) / len(patch_lengths):.1f} chars"
        )

    print()
    print("Archivos más modificados:")

    for filename, count in patch_files.most_common(15):
        print(f"  {count:3d} {filename}")

    print()
    print("=" * 80)
    print("BEHAVIOR DATASET CHECK")
    print("=" * 80)

    categories = Counter()

    # El behavior dataset está al final del archivo.
    for record in records[129:]:
        system = record["messages"][0]["content"]
        user = record["messages"][1]["content"]
        assistant = record["messages"][2]["content"]

        text = f"{system}\n{user}\n{assistant}".lower()

        if "normalize_email" in text or "is_valid_port" in text:
            categories["direct_coding"] += 1

        if "repository is available" in text or "repository access" in text:
            categories["inspection/evidence"] += 1

        if "pytest" in text or "tests" in text:
            categories["testing/verification"] += 1

        if "cannot" in assistant.lower() or "should not" in assistant.lower():
            categories["boundary/honesty"] += 1

    for category, count in categories.items():
        print(f"  {category:25s}: {count}")

    print()
    print("=" * 80)
    print("INTEGRITY CHECKS")
    print("=" * 80)

    print(f"JSON válido          : {'YES' if len(records) == 169 else 'NO'}")
    print(f"Roles válidos        : {'YES' if roles_ok else 'NO'}")
    print(f"Contenido vacío      : {empty_content}")
    print(f"Mojibake detectado   : {mojibake_hits}")

    print()
    print("=" * 80)
    print("RESULTADO FINAL")
    print("=" * 80)

    if not roles_ok:
        raise RuntimeError("Roles inválidos detectados.")

    if empty_content:
        raise RuntimeError(
            f"Se encontraron {empty_content} mensajes vacíos."
        )

    if mojibake_hits:
        raise RuntimeError(
            f"Se detectó mojibake en {mojibake_hits} mensajes."
        )

    print("[OK] FINAL DATASET PASSED")
    print("=" * 80)


if __name__ == "__main__":
    main()