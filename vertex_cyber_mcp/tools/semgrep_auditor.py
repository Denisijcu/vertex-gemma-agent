from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


# =============================================================================
# INPUT MODEL
# =============================================================================


class SemgrepScanInput(BaseModel):
    target_path: str = Field(
        ...,
        description=(
            "Ruta absoluta o relativa al directorio o archivo "
            "que se va a auditar."
        ),
    )

    rule_config: str = Field(
        "auto",
        description=(
            "Configuración de reglas de Semgrep. "
            "Ejemplos: 'auto', 'p/python', "
            "'p/security-audit' o una ruta local."
        ),
    )


# =============================================================================
# JSON PARSER
# =============================================================================


def _parse_semgrep_json(
    raw_output: str,
) -> dict[str, Any] | None:
    """
    Intenta extraer el objeto JSON producido por Semgrep.

    Semgrep normalmente devuelve JSON puro con --json, pero algunas
    versiones/configuraciones pueden emitir texto adicional.

    Devuelve:
        dict si encuentra JSON válido.
        None si no puede interpretarlo.
    """

    if not raw_output:
        return None

    text = raw_output.strip()

    # -------------------------------------------------------------------------
    # Caso normal: todo stdout es JSON.
    # -------------------------------------------------------------------------

    try:
        parsed = json.loads(text)

        if isinstance(parsed, dict):
            return parsed

    except json.JSONDecodeError:
        pass

    # -------------------------------------------------------------------------
    # Recuperación: buscar posibles objetos JSON dentro de stdout.
    # -------------------------------------------------------------------------

    for index, character in enumerate(text):
        if character != "{":
            continue

        candidate = text[index:]

        try:
            parsed = json.loads(candidate)

            if isinstance(parsed, dict):
                return parsed

        except json.JSONDecodeError:
            continue

    return None


# =============================================================================
# METADATA EXTRACTION
# =============================================================================


def _extract_scan_metadata(
    semgrep_data: dict[str, Any],
) -> dict[str, Any]:
    """
    Extrae información relevante del resultado JSON de Semgrep.
    """

    results = semgrep_data.get("results", [])

    if not isinstance(results, list):
        results = []

    errors = semgrep_data.get("errors", [])

    if not isinstance(errors, list):
        errors = []

    paths = semgrep_data.get("paths", {})

    if not isinstance(paths, dict):
        paths = {}

    scanned = paths.get("scanned", [])

    if not isinstance(scanned, list):
        scanned = []

    skipped = paths.get("skipped", [])

    if not isinstance(skipped, list):
        skipped = []

    return {
        "findings_count": len(results),
        "semgrep_errors_count": len(errors),
        "scanned_paths": scanned,
        "skipped_paths": skipped,
        "targets_scanned": len(scanned),
        "engine": semgrep_data.get("engine_requested"),
        "version": semgrep_data.get("version"),
    }


# =============================================================================
# SEMGREP ERROR FORMATTER
# =============================================================================


def _format_semgrep_errors(
    errors: list[Any],
) -> list[str]:
    """
    Convierte errores estructurados de Semgrep a texto legible.
    """

    formatted: list[str] = []

    for error in errors:
        if isinstance(error, dict):
            code = error.get("code")
            level = error.get("level")
            error_type = error.get("type")
            message = error.get("message")
            path = error.get("path")

            parts: list[str] = []

            if code is not None:
                parts.append(f"code={code}")

            if level:
                parts.append(f"level={level}")

            if error_type:
                parts.append(f"type={error_type}")

            if path:
                parts.append(f"path={path}")

            if message:
                parts.append(str(message))

            if parts:
                formatted.append(" | ".join(parts))
            else:
                formatted.append(str(error))

        else:
            formatted.append(str(error))

    return formatted


# =============================================================================
# MAIN SEMGREP EXECUTOR
# =============================================================================


def execute_semgrep_scan(
    params: SemgrepScanInput,
) -> dict[str, Any]:
    """
    Ejecuta un análisis estático real con Semgrep.

    Contrato de resultado:

    success=True
        Significa que el análisis es utilizable y no existe un error fatal
        que invalide el resultado.

    scan_completed=True
        Significa que Semgrep llegó a producir información de análisis.

    findings_count
        Número de findings encontrados por las reglas ejecutadas.

    findings_count=0
        NO significa que el proyecto sea completamente seguro.
        Significa que las reglas utilizadas no produjeron findings.

    exit_code
        Resultado lógico del análisis para Vertex Core.

        0 = análisis limpio y válido.
        1 = análisis válido con findings.
        != 0 = error que invalida el análisis.

    process_exit_code
        Conserva siempre el código real devuelto por el proceso Semgrep.

    IMPORTANTE:
        JSON válido NO significa automáticamente que el análisis fue exitoso.

        Un JSON con errors de Semgrep y sin archivos escaneados, por ejemplo
        una configuración inexistente, debe considerarse un fallo.

        En cambio, si Semgrep produjo resultados válidos y los targets fueron
        realmente escaneados, un código de proceso distinto de cero puede
        corresponder a una operación posterior al análisis. En ese caso se
        conserva process_exit_code pero no se destruye automáticamente el
        resultado del análisis.
    """

    semgrep_executable: str | None = None

    try:

        # =====================================================================
        # 1. RESOLVER SEMGREP
        # =====================================================================

        venv_bin = Path(sys.executable).parent

        if sys.platform == "win32":
            candidate = venv_bin / "semgrep.exe"
        else:
            candidate = venv_bin / "semgrep"

        if candidate.exists():
            semgrep_executable = str(candidate)
        else:
            semgrep_executable = "semgrep"

        # =====================================================================
        # 2. VALIDAR TARGET
        # =====================================================================

        target = Path(
            params.target_path
        ).expanduser()

        if not target.exists():
            return {
                "success": False,
                "scan_completed": False,
                "findings_count": 0,
                "targets_scanned": 0,
                "scanned_paths": [],
                "skipped_paths": [],
                "engine": None,
                "semgrep_version": None,
                "raw_output": None,
                "exit_code": None,
                "process_exit_code": None,
                "error": (
                    "Target path does not exist: "
                    f"{target.resolve()}"
                ),
                "semgrep_errors": [],
                "semgrep_errors_count": 0,
                "stderr": None,
                "scan_summary": {},
                "interpretation": None,
            }

        # =====================================================================
        # 3. CONSTRUIR COMANDO
        # =====================================================================

        cmd = [
            semgrep_executable,
            "--config",
            params.rule_config,
            "--json",
            str(target),
        ]

        # =====================================================================
        # 4. EJECUTAR SEMGREP
        # =====================================================================

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=45,
        )

        stdout = (
            result.stdout or ""
        ).strip()

        stderr = (
            result.stderr or ""
        ).strip()

        process_exit_code = result.returncode

        # =====================================================================
        # 5. PARSEAR JSON
        # =====================================================================

        semgrep_data = _parse_semgrep_json(
            stdout
        )

        # =====================================================================
        # 6. SEMGREP PRODUJO JSON VÁLIDO
        # =====================================================================

        if semgrep_data is not None:

            metadata = _extract_scan_metadata(
                semgrep_data
            )

            findings_count = metadata[
                "findings_count"
            ]

            semgrep_errors = semgrep_data.get(
                "errors",
                [],
            )

            if not isinstance(
                semgrep_errors,
                list,
            ):
                semgrep_errors = []

            formatted_errors = (
                _format_semgrep_errors(
                    semgrep_errors
                )
            )

            targets_scanned = metadata[
                "targets_scanned"
            ]

            # =================================================================
            # DETERMINAR SI LOS ERRORES SON FATALES
            # =================================================================
            #
            # Caso fatal típico:
            #
            #   results = []
            #   errors = [...]
            #   paths.scanned = []
            #   returncode != 0
            #
            # Ejemplo:
            #   configuración inexistente.
            #
            # Esto NO debe reportarse como un scan exitoso.
            #
            # Si existen targets realmente escaneados, conservamos el
            # resultado aunque el proceso haya terminado con un código distinto
            # de cero. Esto cubre casos como errores posteriores al análisis.
            # =================================================================

            fatal_configuration_or_scan_error = (
                process_exit_code != 0
                and bool(formatted_errors)
                and targets_scanned == 0
                and findings_count == 0
            )

            # También consideramos fatal un proceso fallido sin ningún
            # resultado de análisis útil.
            fatal_process_error = (
                process_exit_code != 0
                and targets_scanned == 0
                and findings_count == 0
                and not formatted_errors
            )

            fatal_error = (
                fatal_configuration_or_scan_error
                or fatal_process_error
            )

            # =================================================================
            # CÓDIGO LÓGICO
            # =================================================================

            if fatal_error:
                logical_exit_code = (
                    process_exit_code
                )
            elif findings_count > 0:
                logical_exit_code = 1
            else:
                logical_exit_code = 0

            # =================================================================
            # STATUS
            # =================================================================

            if fatal_error:
                status = "failed"
            elif findings_count > 0:
                status = "findings"
            else:
                status = "clean"

            # =================================================================
            # RESPUESTA PRINCIPAL
            # =================================================================

            response: dict[str, Any] = {
                "success": not fatal_error,

                "scan_completed": (
                    not fatal_error
                ),

                "findings_count": findings_count,

                "targets_scanned": targets_scanned,

                "scanned_paths": (
                    metadata["scanned_paths"]
                ),

                "skipped_paths": (
                    metadata["skipped_paths"]
                ),

                "engine": metadata["engine"],

                "semgrep_version": (
                    metadata["version"]
                ),

                "raw_output": stdout or None,

                "exit_code": logical_exit_code,

                "process_exit_code": (
                    process_exit_code
                ),

                "error": None,
            }

            # =================================================================
            # ERRORES ESTRUCTURADOS
            # =================================================================

            response["semgrep_errors"] = (
                formatted_errors
            )

            response["semgrep_errors_count"] = (
                len(formatted_errors)
            )

            # =================================================================
            # STDERR
            # =================================================================

            response["stderr"] = (
                stderr or None
            )

            # =================================================================
            # ERROR PRINCIPAL
            # =================================================================

            if fatal_error:

                if formatted_errors:

                    response["error"] = (
                        "Semgrep failed to complete "
                        "a valid analysis.\n"
                        + "\n".join(
                            formatted_errors
                        )
                    )

                else:

                    response["error"] = (
                        "Semgrep process failed before "
                        "producing a usable scan result. "
                        f"Process exit code: "
                        f"{process_exit_code}."
                    )

            # =================================================================
            # RESUMEN
            # =================================================================

            response["scan_summary"] = {
                "status": status,
                "findings": findings_count,
                "targets_scanned": targets_scanned,
                "semgrep_errors": len(
                    formatted_errors
                ),
                "engine": metadata["engine"],
                "version": metadata["version"],
                "process_exit_code": (
                    process_exit_code
                ),
            }

            # =================================================================
            # INTERPRETACIÓN
            # =================================================================

            if fatal_error:

                response["interpretation"] = (
                    "Semgrep did not complete a valid "
                    "analysis. The returned errors must be "
                    "resolved before treating this result "
                    "as a clean security scan."
                )

            elif findings_count > 0:

                response["interpretation"] = (
                    "Semgrep completed successfully "
                    "and produced one or more findings. "
                    "Review the findings before drawing "
                    "conclusions."
                )

            else:

                if process_exit_code != 0:

                    response["interpretation"] = (
                        "Semgrep produced a usable scan "
                        "result with zero findings, but "
                        "the process returned a non-zero "
                        "exit code after analysis. "
                        "Review process_exit_code and stderr "
                        "for secondary warnings or "
                        "post-scan errors."
                    )

                else:

                    response["interpretation"] = (
                        "Semgrep completed successfully "
                        "with zero findings from the "
                        "executed rules. This does not "
                        "prove that the target is free "
                        "of vulnerabilities."
                    )

            return response

        # =====================================================================
        # 7. NO SE PUDO OBTENER JSON VÁLIDO
        # =====================================================================

        error_parts = [
            (
                "Semgrep did not produce a valid JSON "
                f"result. Process exited with code "
                f"{result.returncode}."
            )
        ]

        if stderr:

            error_parts.append(
                f"STDERR:\n{stderr}"
            )

        if stdout:

            error_parts.append(
                f"STDOUT:\n{stdout}"
            )

        return {
            "success": False,
            "scan_completed": False,
            "findings_count": 0,
            "targets_scanned": 0,
            "scanned_paths": [],
            "skipped_paths": [],
            "engine": None,
            "semgrep_version": None,
            "raw_output": stdout or None,
            "exit_code": result.returncode,
            "process_exit_code": result.returncode,
            "error": "\n\n".join(
                error_parts
            ),
            "semgrep_errors": [],
            "semgrep_errors_count": 0,
            "stderr": stderr or None,
            "scan_summary": {},
            "interpretation": None,
        }

    # =========================================================================
    # 8. SEMGREP NO ENCONTRADO
    # =========================================================================

    except FileNotFoundError as exc:

        return {
            "success": False,
            "scan_completed": False,
            "findings_count": 0,
            "targets_scanned": 0,
            "scanned_paths": [],
            "skipped_paths": [],
            "engine": None,
            "semgrep_version": None,
            "raw_output": None,
            "exit_code": None,
            "process_exit_code": None,
            "error": (
                "Semgrep CLI could not be found.\n"
                f"Python executable: {sys.executable}\n"
                f"Expected executable: "
                f"{semgrep_executable}\n"
                f"Original error: {exc}"
            ),
            "semgrep_errors": [],
            "semgrep_errors_count": 0,
            "stderr": None,
            "scan_summary": {},
            "interpretation": None,
        }

    # =========================================================================
    # 9. TIMEOUT
    # =========================================================================

    except subprocess.TimeoutExpired as exc:

        stdout = ""
        stderr = ""

        if exc.stdout:

            if isinstance(
                exc.stdout,
                bytes,
            ):

                stdout = exc.stdout.decode(
                    "utf-8",
                    errors="replace",
                )

            else:

                stdout = str(
                    exc.stdout
                )

        if exc.stderr:

            if isinstance(
                exc.stderr,
                bytes,
            ):

                stderr = exc.stderr.decode(
                    "utf-8",
                    errors="replace",
                )

            else:

                stderr = str(
                    exc.stderr
                )

        # ---------------------------------------------------------------------
        # Intentamos aprovechar JSON válido producido antes del timeout.
        #
        # Esto es importante porque Semgrep puede haber terminado el análisis
        # y quedarse bloqueado posteriormente en una operación secundaria.
        # ---------------------------------------------------------------------

        semgrep_data = _parse_semgrep_json(
            stdout
        )

        if semgrep_data is not None:

            metadata = _extract_scan_metadata(
                semgrep_data
            )

            findings_count = metadata[
                "findings_count"
            ]

            semgrep_errors = semgrep_data.get(
                "errors",
                [],
            )

            if not isinstance(
                semgrep_errors,
                list,
            ):
                semgrep_errors = []

            formatted_errors = (
                _format_semgrep_errors(
                    semgrep_errors
                )
            )

            targets_scanned = metadata[
                "targets_scanned"
            ]

            # Si hubo targets escaneados, podemos afirmar que el análisis
            # produjo resultados aunque el proceso haya excedido el timeout
            # posteriormente.
            scan_completed = (
                targets_scanned > 0
            )

            return {
                "success": scan_completed,
                "scan_completed": scan_completed,
                "findings_count": findings_count,
                "targets_scanned": targets_scanned,
                "scanned_paths": metadata[
                    "scanned_paths"
                ],
                "skipped_paths": metadata[
                    "skipped_paths"
                ],
                "engine": metadata["engine"],
                "semgrep_version": metadata[
                    "version"
                ],
                "raw_output": stdout or None,
                "exit_code": (
                    1
                    if findings_count > 0
                    else 0
                ),
                "process_exit_code": None,
                "error": (
                    "Semgrep exceeded the 45-second "
                    "process timeout after producing "
                    "usable scan output."
                    if scan_completed
                    else (
                        "Semgrep scan timed out "
                        "after 45 seconds."
                    )
                ),
                "semgrep_errors": formatted_errors,
                "semgrep_errors_count": len(
                    formatted_errors
                ),
                "stderr": stderr or None,
                "scan_summary": {
                    "status": (
                        "findings"
                        if findings_count > 0
                        else "clean"
                    ),
                    "findings": findings_count,
                    "targets_scanned": targets_scanned,
                    "semgrep_errors": len(
                        formatted_errors
                    ),
                    "engine": metadata["engine"],
                    "version": metadata["version"],
                },
                "interpretation": (
                    "Semgrep produced usable scan "
                    "results before the process timeout. "
                    "The timeout should still be investigated."
                    if scan_completed
                    else (
                        "Semgrep timed out before producing "
                        "a usable scan result."
                    )
                ),
            }

        error_message = (
            "Semgrep scan timed out "
            "after 45 seconds."
        )

        if stderr:

            error_message += (
                f"\nSTDERR:\n{stderr}"
            )

        return {
            "success": False,
            "scan_completed": False,
            "findings_count": 0,
            "targets_scanned": 0,
            "scanned_paths": [],
            "skipped_paths": [],
            "engine": None,
            "semgrep_version": None,
            "raw_output": (
                stdout or None
            ),
            "exit_code": None,
            "process_exit_code": None,
            "error": error_message,
            "semgrep_errors": [],
            "semgrep_errors_count": 0,
            "stderr": stderr or None,
            "scan_summary": {},
            "interpretation": None,
        }

    # =========================================================================
    # 10. EXCEPCIÓN INESPERADA
    # =========================================================================

    except Exception as exc:

        return {
            "success": False,
            "scan_completed": False,
            "findings_count": 0,
            "targets_scanned": 0,
            "scanned_paths": [],
            "skipped_paths": [],
            "engine": None,
            "semgrep_version": None,
            "raw_output": None,
            "exit_code": None,
            "process_exit_code": None,
            "error": (
                f"{type(exc).__name__}: "
                f"{exc}"
            ),
            "semgrep_errors": [],
            "semgrep_errors_count": 0,
            "stderr": None,
            "scan_summary": {},
            "interpretation": None,
        }