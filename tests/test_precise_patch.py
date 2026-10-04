
import requests


LM_URL = "http://127.0.0.1:1234/v1/chat/completions"
GATEWAY_URL = "http://127.0.0.1:8001/tools/run_command"


SYSTEM_PROMPT = r"""
You are Vertex Core, an autonomous software engineering agent.

A real file named auth_test.py exists in the repository.

Its SQL injection vulnerability has already been confirmed.

Your task is to modify ONLY auth_test.py.

You MUST return exactly ONE executable bash command.

The command MUST execute Python using this structure:

python3 -c "exec('''...''')"

Inside the Python program:

1. Read auth_test.py.
2. Store the exact vulnerable block in a variable named old.
3. Store the corrected block in a variable named new.
4. Verify that old exists in the file.
5. If old does not exist, terminate with an error.
6. Replace old with new exactly once.
7. Write the modified file.
8. Do not modify any other part of the file.

The exact vulnerable block is:

query = (
    "SELECT id, username FROM users "
    f"WHERE username = '{username}' AND password = '{password}'"
)

cursor.execute(query)

The exact corrected block is:

query = (
    "SELECT id, username FROM users "
    "WHERE username = ? AND password = ?"
)

cursor.execute(query, (username, password))

CRITICAL PYTHON SYNTAX RULES:

- The generated Python MUST be valid.
- Do NOT put "with" after a semicolon.
- Do NOT put "if" after a semicolon.
- Do NOT put "for" after a semicolon.
- Do NOT put "try" after a semicolon.
- Use normal multiline Python inside exec('''...''').
- Use pathlib.Path if useful.
- Preserve the rest of auth_test.py.

Do NOT use:
sed
awk
perl
patch.py
/path/to/repo

Do not explain.
Do not output the corrected Python file.
Return ONLY the executable bash command.
"""


def ask_model():
    response = requests.post(
        LM_URL,
        json={
            "model": "vertex-core-km",
            "temperature": 0.0,
            "max_tokens": 1200,
            "messages": [
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT,
                },
                {
                    "role": "user",
                    "content": (
                        "Modify auth_test.py now. "
                        "Return the executable command only."
                    ),
                },
            ],
        },
        timeout=120,
    )

    response.raise_for_status()

    return response.json()["choices"][0]["message"]["content"].strip()


def extract_command(text):
    text = text.strip()

    if text.startswith("```"):
        lines = text.splitlines()

        if len(lines) >= 3:
            text = "\n".join(lines[1:-1]).strip()

    if not text.startswith("python3 -c"):
        raise RuntimeError(
            "MODEL_DID_NOT_RETURN_PYTHON_COMMAND\n\n"
            + text
        )

    return text


def run(command):
    print("\nCOMMAND:")
    print(command)

    response = requests.post(
        GATEWAY_URL,
        json={"command": command},
        timeout=60,
    )

    print("\nHTTP:", response.status_code)

    try:
        data = response.json()
    except Exception:
        print(response.text)
        return None

    print("STATUS:", data.get("status"))
    print("EXIT CODE:", data.get("exit_code"))
    print("OUTPUT:")
    print(data.get("stdout", ""))

    if data.get("detail"):
        print("DETAIL:")
        print(data["detail"])

    return data


print("=" * 80)
print("1. GENERANDO COMANDO CON VERTEX CORE")
print("=" * 80)

model_response = ask_model()

print(model_response)

print("\n" + "=" * 80)
print("2. EXTRAYENDO COMANDO")
print("=" * 80)

command = extract_command(model_response)

print(command)

print("\n" + "=" * 80)
print("3. EJECUTANDO COMANDO REAL EN DOCKER")
print("=" * 80)

result = run(command)

print("\n" + "=" * 80)
print("4. LEYENDO auth_test.py")
print("=" * 80)

run("cat auth_test.py")

print("\n" + "=" * 80)
print("5. VERIFICANDO SINTAXIS")
print("=" * 80)

run("python3 -m py_compile auth_test.py")

print("\n" + "=" * 80)
print("6. VERIFICANDO QUE LA VULNERABILIDAD DESAPARECIÓ")
print("=" * 80)

run(
    "grep -n \"WHERE username\" auth_test.py && "
    "grep -n \"cursor.execute\" auth_test.py"
)

print("\n" + "=" * 80)
print("PRUEBA TERMINADA")
print("=" * 80)

