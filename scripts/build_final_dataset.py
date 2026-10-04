from __future__ import annotations

import json
from pathlib import Path


BASE_DIR = Path(r"F:\vertex-gemma-agent")

MAIN_DATASET = BASE_DIR / "data" / "processed" / "sft_main_lora.jsonl"
BEHAVIOR_DATASET = BASE_DIR / "data" / "processed" / "vertex_behavior.jsonl"
FINAL_DATASET = BASE_DIR / "data" / "processed" / "sft_final_lora.jsonl"


EXPECTED_MAIN = 129
EXPECTED_BEHAVIOR = 40


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(f"No existe: {path}")

    records = []

    with path.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, 1):
            line = line.strip()

            if not line:
                continue

            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"JSON inválido en {path}, línea {line_number}: {exc}"
                ) from exc

            records.append(record)

    return records


def validate_record(record: dict, index: int, source: str) -> None:
    if not isinstance(record, dict):
        raise ValueError(
            f"{source}: registro {index} no es un objeto JSON."
        )

    messages = record.get("messages")

    if not isinstance(messages, list):
        raise ValueError(
            f"{source}: registro {index} no tiene 'messages' válido."
        )

    if len(messages) != 3:
        raise ValueError(
            f"{source}: registro {index} tiene {len(messages)} mensajes; "
            f"se esperaban exactamente 3."
        )

    roles = [message.get("role") for message in messages]

    if roles != ["system", "user", "assistant"]:
        raise ValueError(
            f"{source}: registro {index} tiene roles inválidos: {roles}"
        )

    for message_index, message in enumerate(messages):
        content = message.get("content")

        if not isinstance(content, str) or not content.strip():
            raise ValueError(
                f"{source}: registro {index}, mensaje {message_index} "
                f"tiene contenido vacío."
            )


def validate_dataset(records: list[dict], source: str) -> None:
    for index, record in enumerate(records, 1):
        validate_record(record, index, source)


def main() -> None:
    print("=" * 70)
    print("VERTEX CORE - FINAL DATASET BUILDER")
    print("=" * 70)

    print(f"Main     : {MAIN_DATASET}")
    print(f"Behavior : {BEHAVIOR_DATASET}")
    print(f"Output   : {FINAL_DATASET}")
    print()

    main_records = load_jsonl(MAIN_DATASET)
    behavior_records = load_jsonl(BEHAVIOR_DATASET)

    print(f"Main records     : {len(main_records)}")
    print(f"Behavior records : {len(behavior_records)}")

    if len(main_records) != EXPECTED_MAIN:
        raise ValueError(
            f"Se esperaban {EXPECTED_MAIN} registros principales, "
            f"pero se encontraron {len(main_records)}."
        )

    if len(behavior_records) != EXPECTED_BEHAVIOR:
        raise ValueError(
            f"Se esperaban {EXPECTED_BEHAVIOR} registros de comportamiento, "
            f"pero se encontraron {len(behavior_records)}."
        )

    print()
    print("[1/4] Validando dataset principal...")
    validate_dataset(main_records, "MAIN")
    print("[OK] Main dataset válido.")

    print()
    print("[2/4] Validando behavior dataset...")
    validate_dataset(behavior_records, "BEHAVIOR")
    print("[OK] Behavior dataset válido.")

    final_records = main_records + behavior_records

    print()
    print("[3/4] Construyendo dataset final...")

    FINAL_DATASET.parent.mkdir(parents=True, exist_ok=True)

    with FINAL_DATASET.open("w", encoding="utf-8") as file:
        for record in final_records:
            file.write(
                json.dumps(
                    record,
                    ensure_ascii=False,
                )
                + "\n"
            )

    print(f"[OK] Dataset final escrito: {FINAL_DATASET}")

    print()
    print("[4/4] Verificando dataset final...")

    written_records = load_jsonl(FINAL_DATASET)

    if len(written_records) != 169:
        raise ValueError(
            f"Se esperaban 169 registros finales, "
            f"pero se encontraron {len(written_records)}."
        )

    validate_dataset(written_records, "FINAL")

    print("[OK] Dataset final válido.")

    print()
    print("=" * 70)
    print("RESULTADO")
    print("=" * 70)
    print(f"Main dataset     : {len(main_records)}")
    print(f"Behavior dataset : {len(behavior_records)}")
    print(f"Final dataset    : {len(written_records)}")
    print()
    print(f"[OK] {FINAL_DATASET}")
    print("=" * 70)


if __name__ == "__main__":
    main()