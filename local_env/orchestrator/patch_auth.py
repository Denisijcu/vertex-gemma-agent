import os

target_path = os.path.abspath(r"F:\vertex-gemma-agent\data\raw\snapshots\auth.py")

vulnerable_code = '''    query = f"SELECT * FROM users WHERE username = '{username}' AND password = '{password}'"
    
    try:
        cursor.execute(query)
        user = cursor.fetchone()
        conn.close()
        if user:
            return True
        return False'''

secure_code = '''    try:
        cursor.execute("SELECT * FROM users WHERE username = ? AND password = ?", (username, password))
        user = cursor.fetchone()
        conn.close()
        return bool(user)'''

if os.path.exists(target_path):
    with open(target_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    if vulnerable_code in content:
        new_content = content.replace(vulnerable_code, secure_code)
        with open(target_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print("[+] ¡Parche aplicado con éxito en auth.py!")
    else:
        print("[!] No se encontró el fragmento vulnerable exacto (quizás ya fue modificado).")
else:
    print(f"[!] No se encontró el archivo en: {target_path}")