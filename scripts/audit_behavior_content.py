import json
import re
from pathlib import Path


INPUT = Path("data/processed/vertex_behavior.jsonl")


DANGEROUS_PATTERNS = {
    "git_diff": re.compile(r"(^|\n)\s*(diff --git|---\s+a/|\+\+\+\s+b/)", re.IGNORECASE),
    "git_diff_command": re.compile(r"\bgit\s+diff\b", re.IGNORECASE),
    "claims_execution": re.compile(
        r"\b(I ran|I executed|I tested|tests passed|pytest passed|"
        r"ejecut[eé]|corr[ií]|ejecuté|las pruebas pasaron)\b",
        re.IGNORECASE,
    ),
}


def load_rows():
    if not INPUT.exists():
        raise FileNotFoundError(f"No existe: {INPUT}")

    rows = []

    with INPUT.open("r", encoding="utf-8") as f:
        for line_number, line in enumerate(f, 1):
            if not line.strip():
                continue

            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"JSON inválido en línea {line_number}: {exc}"
                ) from exc

    return rows


def main():
    rows = load_rows()

    print("=" * 80)
    print("VERTEX CORE - BEHAVIOR DATASET CONTENT AUDIT")
    print("=" * 80)

    print(f"REGISTROS: {len(rows)}")
    print()

    suspicious = []

    for index, row in enumerate(rows, 1):
        messages = row["messages"]

        user = messages[1]["content"]
        assistant = messages[2]["content"]

        print("=" * 80)
        print(f"EJEMPLO {index:02d}")
        print("=" * 80)

        print()
        print("USER:")
        print(user)

        print()
        print("ASSISTANT:")
        print(assistant)

        print()

        found = []

        for name, pattern in DANGEROUS_PATTERNS.items():
            if pattern.search(assistant):
                found.append(name)

        if found:
            suspicious.append((index, found))
            print("!!! REVISAR:", ", ".join(found))
        else:
            print("[OK] Sin patrones peligrosos detectados.")

        print()

    print("=" * 80)
    print("RESUMEN")
    print("=" * 80)

    print(f"Total ejemplos : {len(rows)}")
    print(f"Sospechosos   : {len(suspicious)}")

    if suspicious:
        print()
        print("EJEMPLOS PARA REVISAR:")

        for index, patterns in suspicious:
            print(
                f"  [{index:02d}] "
                f"{', '.join(patterns)}"
            )

        print()
        print(
            "[!] Esto NO significa automáticamente que estén mal."
        )
        print(
            "    Algunos ejemplos legítimamente pueden mencionar "
            "comandos o resultados."
        )
    else:
        print()
        print("[OK] No se detectaron patrones sospechosos.")

    print("=" * 80)


if __name__ == "__main__":
    main()