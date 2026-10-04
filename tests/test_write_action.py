
import requests


URL = "http://127.0.0.1:1234/v1/chat/completions"

SYSTEM_PROMPT = """
You are Vertex Core, an autonomous software engineering agent.

A real file named auth.py has already been inspected.

The following vulnerability is CONFIRMED:

query = (
    "SELECT id, username FROM users "
    f"WHERE username = '{username}' AND password = '{password}'"
)

This is SQL injection because user input is directly concatenated into SQL.

YOUR TASK:

You must modify the REAL file auth.py.

Do NOT explain the solution.
Do NOT write the corrected Python code as your answer.
Do NOT pretend that you modified the file.

You have a terminal tool available through bash commands.

Your response MUST contain a bash command that modifies auth.py.

The command must actually write the corrected content to auth.py.

After modifying the file, you must issue another bash command that reads auth.py so the modification can be verified.

The correct SQL pattern is parameterized SQLite execution:

query = (
    "SELECT id, username FROM users "
    "WHERE username = ? AND password = ?"
)

cursor.execute(query, (username, password))

Do not merely describe this change.

ACT NOW.
"""


USER_PROMPT = """
Fix the confirmed SQL injection vulnerability in auth.py.

Inspecting the file is already done.
The vulnerability is confirmed.
Your next action must be a bash command that modifies the real file.

Then read the file again to verify the modification.
"""


payload = {
    "model": "vertex-core-km",
    "temperature": 0.0,
    "max_tokens": 1000,
    "messages": [
        {
            "role": "system",
            "content": SYSTEM_PROMPT,
        },
        {
            "role": "user",
            "content": USER_PROMPT,
        },
    ],
}


response = requests.post(
    URL,
    json=payload,
    timeout=120,
)

response.raise_for_status()

data = response.json()

content = data["choices"][0]["message"]["content"]

print("\n" + "=" * 80)
print("MODEL RESPONSE")
print("=" * 80)
print(content)
print("=" * 80)
