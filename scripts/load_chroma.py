import os
import json
import numpy as np
import chromadb
from typing import Dict, Any

# Rutas alineadas a la topología del proyecto
BASE_DIR = r"F:\vertex-gemma-agent"
GRAPHS_DIR = os.path.join(BASE_DIR, "data", "raw", "graphs")
EMBEDDINGS_DIR = os.path.join(BASE_DIR, "data", "raw", "embeddings")
CHROMA_PATH = os.path.join(BASE_DIR, "data", "chroma_harness")

def load_graph_metadata(graph_path: str) -> Dict[str, Any]:
    """Carga los nodos del AST para extraer el código fuente y tipo."""
    with open(graph_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    # Retorna un diccionario indexado por node.id
    return {node["id"]: node for node in data.get("nodes", [])}

def populate_chroma():
    print("[*] Inicializando ChromaDB local...")
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    # Kaggle usa 256 dimensiones para sus vectores Jina/Nomic
    collection = client.get_or_create_collection(
        name="repo_ast_nodes",
        metadata={"hnsw:space": "cosine"}
    )

    if not os.path.exists(EMBEDDINGS_DIR):
        print(f"[!] Directorio {EMBEDDINGS_DIR} no encontrado.")
        return

    for npz_filename in os.listdir(EMBEDDINGS_DIR):
        if not npz_filename.endswith(".npz"):
            continue

        base_name = npz_filename.replace(".npz", "")
        npz_path = os.path.join(EMBEDDINGS_DIR, npz_filename)
        graph_path = os.path.join(GRAPHS_DIR, f"{base_name}.json")

        if not os.path.exists(graph_path):
            print(f"[!] Grafo faltante para {npz_filename}. Omitiendo.")
            continue

        print(f"[*] Procesando snapshot: {base_name}")
        metadata_map = load_graph_metadata(graph_path)
        
        # Carga perezosa de los tensores NumPy
        with np.load(npz_path) as data:
            ids = []
            embeddings = []
            documents = []
            metadatas = []

            for file_key in data.files:
                # Kaggle guarda los arrays como <node_id>.npy
                node_id = file_key.replace(".npy", "")
                
                if node_id not in metadata_map:
                    continue
                
                node_data = metadata_map[node_id]
                
                ids.append(f"{base_name}_{node_id}")
                embeddings.append(data[file_key].tolist())
                documents.append(node_data.get("text", ""))
                metadatas.append({
                    "snapshot": base_name,
                    "filepath": node_data.get("name", "unknown"),
                    "type": "ast_node"
                })

            # Inserción en lotes para no saturar la RAM de tu HP Omen
            if ids:
                collection.add(
                    ids=ids,
                    embeddings=embeddings,
                    documents=documents,
                    metadatas=metadatas
                )
                print(f"[+] {len(ids)} nodos indexados para {base_name}.")

if __name__ == "__main__":
    populate_chroma()