import sqlite3


def authenticate(username, password):
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()

    query = (
        "SELECT id, username FROM users "
        f"WHERE username = '{username}' AND password = '{password}'"
    )

    cursor.execute(query)
    user = cursor.fetchone()

    conn.close()

    return user


def login(username, password):
    user = authenticate(username, password)

    if user:
        return {
            "authenticated": True,
            "user_id": user[0],
            "username": user[1],
        }

    return {
        "authenticated": False,
        "user_id": None,
        "username": None,
    }