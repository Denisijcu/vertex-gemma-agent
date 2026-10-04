
from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, Field

from vertex_cyber_mcp.tools.semgrep_auditor import (
    SemgrepScanInput,
    execute_semgrep_scan,
)


# =============================================================================
# APPLICATION
# =============================================================================

app = FastAPI(
    title="Vertex Cyber MCP - Security & Audit Server",
    description=(
        "Servidor local para la ejecución de herramientas de análisis "
        "estático y ofensa/defensa de Vertex Core."
    ),
    version="1.0.0",
)


# =============================================================================
# REQUEST MODEL
# =============================================================================


class AuditRequest(BaseModel):
    target_path: str = Field(
        ...,
        description=(
            "Ruta absoluta o relativa al archivo o directorio "
            "que se va a auditar."
        ),
    )

    rule_config: str = Field(
        "auto",
        description=(
            "Configuración de reglas de Semgrep. "
            "Ejemplos: auto, p/python, p/security-audit "
            "o una ruta local."
        ),
    )


# =============================================================================
# RESPONSE MODEL
# =============================================================================


class AuditResponse(BaseModel):
    success: bool

    scan_completed: bool = False

    findings_count: int = 0

    targets_scanned: int = 0

    scanned_paths: list[Any] = Field(
        default_factory=list,
    )

    skipped_paths: list[Any] = Field(
        default_factory=list,
    )

    engine: str | None = None

    semgrep_version: str | None = None

    raw_output: str | None = None

    exit_code: int | None = None

    process_exit_code: int | None = None

    error: str | None = None

    semgrep_errors: list[str] = Field(
        default_factory=list,
    )

    semgrep_errors_count: int = 0

    stderr: str | None = None

    scan_summary: dict[str, Any] = Field(
        default_factory=dict,
    )

    interpretation: str | None = None


# =============================================================================
# SEMGREP AUDIT ENDPOINT
# =============================================================================


@app.post(
    "/api/audit/semgrep",
    response_model=AuditResponse,
)
def run_semgrep_audit(
    payload: AuditRequest,
) -> AuditResponse:
    """
    Ejecuta un análisis real con Semgrep.

    El endpoint devuelve la evidencia estructurada producida por
    execute_semgrep_scan() para que Vertex Core pueda distinguir entre:

        - análisis completado
        - findings encontrados
        - errores de Semgrep
        - errores del proceso
        - resultado lógico
        - resultado real del proceso
        - warnings/stderr
        - interpretación del análisis

    No se inventan resultados.
    """

    tool_input = SemgrepScanInput(
        target_path=payload.target_path,
        rule_config=payload.rule_config,
    )

    result = execute_semgrep_scan(
        tool_input
    )

    return AuditResponse(
        success=result.get(
            "success",
            False,
        ),

        scan_completed=result.get(
            "scan_completed",
            False,
        ),

        findings_count=result.get(
            "findings_count",
            0,
        ),

        targets_scanned=result.get(
            "targets_scanned",
            0,
        ),

        scanned_paths=result.get(
            "scanned_paths",
            [],
        ),

        skipped_paths=result.get(
            "skipped_paths",
            [],
        ),

        engine=result.get(
            "engine",
        ),

        semgrep_version=result.get(
            "semgrep_version",
        ),

        raw_output=result.get(
            "raw_output",
        ),

        exit_code=result.get(
            "exit_code",
        ),

        process_exit_code=result.get(
            "process_exit_code",
        ),

        error=result.get(
            "error",
        ),

        semgrep_errors=result.get(
            "semgrep_errors",
            [],
        ),

        semgrep_errors_count=result.get(
            "semgrep_errors_count",
            0,
        ),

        stderr=result.get(
            "stderr",
        ),

        scan_summary=result.get(
            "scan_summary",
            {},
        ),

        interpretation=result.get(
            "interpretation",
        ),
    )


# =============================================================================
# HEALTH CHECK
# =============================================================================


@app.get("/health")
def health_check() -> dict[str, str]:
    return {
        "status": "online",
        "agent": "Vertex Core Cyber MCP",
    }

