import re
import requests


LM_URL = "http://127.0.0.1:1234/v1/chat/completions"
GATEWAY_URL = "http://127.0.0.1:8000/tools/run_command"


SYSTEM = r"""
You are Vertex Core, an autonomous software engineering agent.

The real file auth.py has already been inspected.

It contains a confirmed SQL injection vulnerability caused by this code:

query = (
    "SELECT id, username FROM users "
    f"WHERE username = '{username}' AND password = '{password}'"
)

Your task is to MODIFY THE REAL FILE.

IMPORTANT:

1. You must use a bash command.
2. The command must modify auth.py.
3. Do not explain the solution.
4. Do not output Python source as your answer.
5. Do not invent files.
6. Do not use patch.py.
7. Do not use /path/to/repo.
8. Preserve the rest of auth.py.
9. Only replace the vulnerable SQL query and cursor.execute call.
10. After modifying the file, read auth.py to verify the result.

The corrected code must use:

query = (
    "SELECT id, username FROM users "
    "WHERE username = ? AND password = ?"
)

cursor.execute(query, (username, password))

Your response must contain the bash command required to perform the modification.

ACT NOW.
"""


def ask_model():
    response = requests.post(
        LM_URL,
        json={
            "model": "vertex-core-km",
            "temperature": 0.0,
            "max_tokens": 800,
            "messages": [
                {
                    "role": "system",
                    "content": SYSTEM,
                },
                {
                    "role": "user",
                    "content": (
                        "Modify auth.py now. "
                        "Preserve the rest of the file."
                    ),
                },
            ],
        },
        timeout=120,
    )

    response.raise_for_status()

    return response.json()["choices"][0]["message"]["content"]


def extract_command(text):
    # First try a fenced bash block.
    match = re.search(
        r"```(?:bash|sh|shell)\s*\n(.*?)```",
        text,
        re.DOTALL | re.IGNORECASE,
    )

    if match:
        return match.group(1).strip()

    # Otherwise accept a raw command beginning with a known shell command.
    lines = [
        line.strip()
        for line in text.strip().splitlines()
        if line.strip()
    ]

    for line in lines:
        if line.startswith(
            (
                "python3 -c ",
                "python -c ",
                "sed ",
                "perl ",
                "awk ",
            )
        ):
            return line

    raise RuntimeError(
        "MODEL_DID_NOT_RETURN_EXECUTABLE_COMMAND\n\n"
        + text
    )


def run_command(command):
    print("\nCOMMAND SENT TO GATEWAY:")
    print(command)

    response = requests.post(
        GATEWAY_URL,
        json={"command": command},
        timeout=60,
    )

    print("\nGATEWAY HTTP:", response.status_code)

    try:
        data = response.json()
    except Exception:
        print(response.text)
        return None

    print("STATUS:", data.get("status"))
    print("EXIT CODE:", data.get("exit_code"))
    print("STDOUT:")
    print(data.get("stdout", ""))

    if response.status_code >= 400:
        print("DETAIL:", data.get("detail"))

    return data


print("=" * 80)
print("1. PREGUNTANDO AL MODELO")
print("=" * 80)

model_response = ask_model()

print(model_response)

print("\n" + "=" * 80)
print("2. EXTRAYENDO COMANDO")
print("=" * 80)

command = extract_command(model_response)

print(command)

print("\n" + "=" * 80)
print("3. EJECUTANDO COMANDO REAL")
print("=" * 80)

run_command(command)

print("\n" + "=" * 80)
print("4. LEYENDO auth.py DESPUÉS DEL CAMBIO")
print("=" * 80)

run_command("cat auth.py")

print("\n" + "=" * 80)
print("5. VERIFICANDO SINTAXIS")
print("=" * 80)

run_command("python3 -m py_compile auth.py")

print("\n" + "=" * 80)
print("PRUEBA TERMINADA")
print("=" * 80)

