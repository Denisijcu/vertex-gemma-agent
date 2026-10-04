import json
from pathlib import Path


INPUT = Path("data/processed/vertex_behavior.jsonl")


def main():
    if not INPUT.exists():
        print(f"[ERROR] No existe: {INPUT}")
        return

    rows = []

    with INPUT.open("r", encoding="utf-8") as f:
        for line_number, line in enumerate(f, 1):
            if not line.strip():
                continue

            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as e:
                print(f"[ERROR] JSON inválido en línea {line_number}: {e}")
                return

    print("=" * 70)
    print("VERTEX CORE - BEHAVIOR DATASET AUDIT")
    print("=" * 70)

    print(f"REGISTROS: {len(rows)}")
    print()

    # ---------------------------------------------------------------
    # Estructura
    # ---------------------------------------------------------------

    system_ok = True
    user_ok = True
    assistant_ok = True
    structure_ok = True

    for i, row in enumerate(rows, 1):
        messages = row.get("messages")

        if not isinstance(messages, list):
            print(f"[ERROR {i:02d}] messages no es una lista")
            structure_ok = False
            continue

        if len(messages) != 3:
            print(f"[ERROR {i:02d}] Tiene {len(messages)} mensajes; esperaba 3")
            structure_ok = False
            continue

        if messages[0].get("role") != "system":
            print(f"[ERROR {i:02d}] Mensaje 0 no es system")
            system_ok = False

        if messages[1].get("role") != "user":
            print(f"[ERROR {i:02d}] Mensaje 1 no es user")
            user_ok = False

        if not messages[1].get("content", "").strip():
            print(f"[ERROR {i:02d}] USER vacío")
            user_ok = False

        if messages[2].get("role") != "assistant":
            print(f"[ERROR {i:02d}] Mensaje 2 no es assistant")
            assistant_ok = False

        if not messages[2].get("content", "").strip():
            print(f"[ERROR {i:02d}] ASSISTANT vacío")
            assistant_ok = False

    # ---------------------------------------------------------------
    # Mostrar ejemplos
    # ---------------------------------------------------------------

    print()
    print("=" * 70)
    print("EJEMPLOS")
    print("=" * 70)

    for i, row in enumerate(rows, 1):
        user_text = row["messages"][1]["content"]
        user_text = user_text.replace("\n", " ").replace("\r", " ")

        if len(user_text) > 140:
            user_text = user_text[:140] + "..."

        print(f"[{i:02d}] USER: {user_text}")

    # ---------------------------------------------------------------
    # Resultado estructural
    # ---------------------------------------------------------------

    print()
    print("=" * 70)
    print("VALIDACIÓN ESTRUCTURAL")
    print("=" * 70)

    print(f"SYSTEM:    {system_ok}")
    print(f"USER:      {user_ok}")
    print(f"ASSISTANT:  {assistant_ok}")
    print(f"STRUCTURE: {structure_ok}")

    all_ok = (
        len(rows) == 40
        and system_ok
        and user_ok
        and assistant_ok
        and structure_ok
    )

    print()

    if all_ok:
        print("[OK] BEHAVIOR DATASET STRUCTURALLY VALID")
    else:
        print("[ERROR] BEHAVIOR DATASET REQUIRES REVIEW")

    print("=" * 70)


if __name__ == "__main__":
    main()