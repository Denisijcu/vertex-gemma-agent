import os
import zipfile
import yaml
from pathlib import Path

# Rutas del entorno
SUBMISSION_DIR = Path("../submission")
OUTPUT_ZIP = Path("../submission.zip")

def validate_adk_structure(sub_dir: Path) -> bool:
    """Aplica validación estática para evitar fallos de formato en Kaggle."""
    agent_yaml_path = sub_dir / "agent.yaml"
    
    if not agent_yaml_path.exists():
        print("[!] ERROR CRÍTICO: agent.yaml no encontrado en la raíz del submission.")
        return False
        
    try:
        with open(agent_yaml_path, "r", encoding="utf-8") as f:
            yaml.safe_load(f)
    except yaml.YAMLError as e:
        print(f"[!] ERROR CRÍTICO: agent.yaml tiene sintaxis inválida. Detalle: {e}")
        return False
        
    print("[+] Validación de esquema ADK superada.")
    return True

def package_submission():
    print(f"[*] Empaquetando directorio: {SUBMISSION_DIR.resolve()}")
    
    if not SUBMISSION_DIR.exists():
        print("[!] Directorio submission/ no encontrado.")
        return

    if not validate_adk_structure(SUBMISSION_DIR):
        print("[-] Empaquetado abortado.")
        return

    # Comprimir preservando la estructura interna
    with zipfile.ZipFile(OUTPUT_ZIP, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(SUBMISSION_DIR):
            # Excluir directorios ocultos por seguridad (ej. .git)
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            
            for file in files:
                if file.startswith('.') or file.endswith('.pyc'):
                    continue
                    
                file_path = Path(root) / file
                # Calcular la ruta relativa para el interior del ZIP
                arcname = file_path.relative_to(SUBMISSION_DIR)
                
                print(f"  -> Añadiendo: {arcname}")
                zipf.write(file_path, arcname)

    print(f"\n[+] Entrega consolidada con éxito: {OUTPUT_ZIP.resolve()}")
    print("[!] Tamaño final: {:.2f} MB".format(OUTPUT_ZIP.stat().st_size / (1024 * 1024)))

if __name__ == "__main__":
    package_submission()