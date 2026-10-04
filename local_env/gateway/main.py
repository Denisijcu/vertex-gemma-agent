import os

import docker

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field


# =============================================================================
# VIC-Kaggle-Gateway
# =============================================================================

app = FastAPI(title="VIC-Kaggle-Gateway")


# =============================================================================
# CONFIGURATION
# =============================================================================

WORKSPACE_CONTAINER = "kaggle-workspace"
WORKSPACE_IMAGE = "vertex-kaggle-sandbox:latest"

REPO_HOST_PATH = os.getenv(
    "REPO_HOST_PATH",
    r"F:\vertex-gemma-agent\repo",
)

SANDBOX_PATH = "/sandbox"

EXEC_TIMEOUT = 30
MAX_OUTPUT = 2000


# =============================================================================
# DOCKER
# =============================================================================

try:
    docker_client = docker.from_env()
    docker_client.ping()
    print("[+] Cliente de Docker conectado exitosamente.")
except Exception as e:
    print(f"[!] Docker no está accesible: {e}")
    docker_client = None


# =============================================================================
# CHROMADB
# =============================================================================

try:
    import chromadb

    chroma_client = chromadb.PersistentClient(
        path="../../data/chroma_harness"
    )

    collection = chroma_client.get_collection(
        name="repo_ast_nodes"
    )

    print("[+] ChromaDB inicializado exitosamente.")

except Exception as e:
    print(f"[!] ChromaDB deshabilitado: {e}")
    collection = None


# =============================================================================
# REQUEST MODELS
# =============================================================================

class CommandRequest(BaseModel):
    command: str = Field(
        ...,
        min_length=1,
        max_length=8000,
    )


class SearchRequest(BaseModel):
    query: list[float] = Field(
        ...,
        description="Vector pre-calculado del query",
    )

    k: int = Field(
        default=5,
        ge=1,
        le=20,
    )


# =============================================================================
# SANDBOX
# =============================================================================

def ensure_sandbox_running():
    """
    Garantiza que el contenedor sandbox exista y esté corriendo.
    """

    if docker_client is None:
        raise RuntimeError("docker_daemon_unreachable")

    try:
        container = docker_client.containers.get(
            WORKSPACE_CONTAINER
        )

        container.reload()

        if container.status != "running":
            print(
                f"[*] Contenedor '{WORKSPACE_CONTAINER}' "
                f"en estado '{container.status}'. Iniciando..."
            )

            container.start()
            container.reload()

        return container

    except docker.errors.NotFound:
        print(
            f"[!] Contenedor '{WORKSPACE_CONTAINER}' "
            f"no existe. Creándolo..."
        )

        try:
            container = docker_client.containers.run(
                image=WORKSPACE_IMAGE,
                name=WORKSPACE_CONTAINER,
                detach=True,

                volumes={
                    REPO_HOST_PATH: {
                        "bind": SANDBOX_PATH,
                        "mode": "rw",
                    }
                },

                working_dir=SANDBOX_PATH,
            )

            return container

        except docker.errors.ImageNotFound:
            raise RuntimeError(
                "sandbox_image_missing"
            )


# =============================================================================
# COMMAND EXECUTION
# =============================================================================

def execute_command(command: str) -> dict:
    """
    Ejecuta un comando dentro del sandbox Docker.
    """

    container = ensure_sandbox_running()

    try:
        exit_code, output = container.exec_run(
            cmd=[
                "/bin/bash",
                "-c",
                command,
            ],
            workdir=SANDBOX_PATH,
        )

    except Exception as e:
        return {
            "status": "infra_error",
            "infra_error": type(e).__name__,
            "message": str(e),
        }

    decoded = output.decode(
        "utf-8",
        errors="replace",
    ).strip()

    if len(decoded) > MAX_OUTPUT:
        decoded = (
            decoded[:MAX_OUTPUT]
            + "\n...[TRUNCATED]"
        )

    return {
        "exit_code": exit_code,
        "stdout": decoded,
        "status": (
            "success"
            if exit_code == 0
            else "command_error"
        ),
    }


# =============================================================================
# COMMAND TOOL
# =============================================================================

@app.post("/tools/run_command")
async def run_command(req: CommandRequest):

    try:
        result = execute_command(req.command)

        if result["status"] == "infra_error":
            raise HTTPException(
                status_code=503,
                detail=result,
            )

        return result

    except HTTPException:
        raise

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={
                "status": "infra_error",
                "infra_error": type(e).__name__,
                "message": str(e),
            },
        )


# =============================================================================
# VECTOR SEARCH
# =============================================================================

@app.post("/tools/search_similar_code")
async def search_similar_code(req: SearchRequest):

    if collection is None:
        raise HTTPException(
            status_code=503,
            detail="Vector DB no disponible.",
        )

    try:
        results = collection.query(
            query_embeddings=[req.query],
            n_results=req.k,
            include=[
                "documents",
                "metadatas",
            ],
        )

        documents = results.get(
            "documents",
            [[]],
        )[0]

        metadatas = results.get(
            "metadatas",
            [[]],
        )[0]

        nodes = []

        for doc, meta in zip(
            documents,
            metadatas,
        ):
            nodes.append(
                {
                    "filepath": meta.get(
                        "filepath",
                        "",
                    ),
                    "node_type": meta.get(
                        "type",
                        "",
                    ),
                    "content": doc,
                }
            )

        return {
            "nodes": nodes,
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e),
        )


# =============================================================================
# HEALTH
# =============================================================================

@app.get("/health")
async def health():

    docker_status = False

    if docker_client is not None:
        try:
            docker_client.ping()
            docker_status = True
        except Exception:
            docker_status = False

    return {
        "status": "ok",
        "docker": docker_status,
        "chromadb": collection is not None,
        "workspace_container": WORKSPACE_CONTAINER,
        "sandbox_path": SANDBOX_PATH,
        "repo_host_path": REPO_HOST_PATH,
    }