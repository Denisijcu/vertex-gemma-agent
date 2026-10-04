import re
import time
import logging
import requests

from dataclasses import dataclass
from typing import Optional


# =============================================================================
# LOGGING
# =============================================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s | %(message)s",
)

log = logging.getLogger("orchestrator")


# =============================================================================
# CONFIGURATION
# =============================================================================

@dataclass
class Config:
    lm_studio_url: str = (
        "http://127.0.0.1:1234/v1/chat/completions"
    )

    gateway_url: str = (
        "http://127.0.0.1:8001/tools/run_command"
    )

    model_id: str = "vertex-core-km"

    # model_id: str = "google/gemma-4-e4b"

    temperature: float = 0.1

    # LM Studio permite hasta 4048 tokens de contexto.
    #
    # Esto NO es el contexto del modelo.
    # Es solamente el máximo de tokens generados por respuesta.
    max_tokens: int = 600

    max_turns: int = 10

    request_timeout: int = 120

    tool_timeout: int = 15

    max_tool_output: int = 2000

    retry_attempts: int = 3

    retry_backoff: float = 2.0

    sleep_between_turns: float = 1.0


# =============================================================================
# BASH EXTRACTION
# =============================================================================

BASH_BLOCK_RE = re.compile(
    r"```bash\s*\n(.*?)```",
    re.DOTALL | re.IGNORECASE,
)


# =============================================================================
# SECURITY
# =============================================================================

BLOCKED_PATTERNS = re.compile(
    r"""
    (
        rm\s+-rf\s+/
        |
        mkfs
        |
        dd\s+if=
        |
        shutdown
        |
        reboot
        |
        :\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)


# =============================================================================
# SYSTEM PROMPT
# =============================================================================

SYSTEM_PROMPT = (
    "Eres VIC-Gemma-Orchestrator, un agente autónomo de ingeniería "
    "de software experto en resolver issues dentro de un repositorio.\n\n"

    "Tienes acceso a una herramienta de terminal mediante bloques "
    "de código bash. Los comandos que emitas serán ejecutados realmente "
    "dentro de un sandbox.\n\n"

    "======================================================================\n"
    "WORKSPACE REAL\n"
    "======================================================================\n\n"

    "El repositorio de trabajo real está montado dentro del sandbox en:\n\n"

    "/sandbox\n\n"

    "Tu directorio de trabajo es /sandbox.\n\n"

    "REGLAS DEL WORKSPACE:\n"
    "- NO inventes rutas como /path/to/repo.\n"
    "- NO uses placeholders como /path/to/repo, /workspace/repo, "
    "/repo/path o similares.\n"
    "- Cuando necesites inspeccionar el repositorio, usa /sandbox.\n"
    "- Para listar el repositorio puedes usar:\n"
    "  ls -la /sandbox\n"
    "- Para leer un archivo puedes usar su ruta real dentro de /sandbox.\n"
    "  Ejemplo: cat /sandbox/auth.py\n"
    "- Si ejecutas pwd y devuelve /sandbox, estás ubicado en el workspace real.\n"
    "- El archivo auth.py debe buscarse dentro de /sandbox si forma parte "
    "del issue.\n\n"

    "======================================================================\n"
    "REGLAS OBLIGATORIAS\n"
    "======================================================================\n\n"

    "1. EJECUTA, NO DESCRIBAS.\n"
    "Si necesitas inspeccionar, leer, crear, modificar, probar o verificar "
    "algo en el repositorio, debes emitir un bloque ```bash``` con el "
    "comando exacto que debe ejecutarse.\n\n"

    "2. NO INVENTES RESULTADOS.\n"
    "Nunca afirmes que ejecutaste un comando, modificaste un archivo, "
    "ejecutaste una prueba o solucionaste un problema si no existe "
    "un resultado de herramienta que confirme esa acción.\n\n"

    "3. NO DIGAS 'VOY A HACERLO' SIN HACERLO.\n"
    "No respondas solamente con frases como 'voy a revisar', "
    "'voy a modificar', 'voy a ejecutar' o 'ahora corregiré'. "
    "Emite inmediatamente el bloque ```bash``` correspondiente.\n\n"

    "4. NO ALUCINES.\n"
    "No inventes archivos, directorios, código, resultados, herramientas, "
    "tests ni comandos.\n"
    "No inventes rutas.\n"
    "Usa únicamente rutas que existan o rutas que puedan comprobarse "
    "mediante una herramienta.\n\n"

    "5. INSPECCIONA ANTES DE MODIFICAR.\n"
    "Antes de modificar un archivo existente:\n"
    "- inspecciona el repositorio;\n"
    "- localiza el archivo;\n"
    "- lee el contenido relevante;\n"
    "- entiende el problema;\n"
    "- aplica solamente el cambio necesario.\n\n"

    "6. PUEDES CREAR CÓDIGO NUEVO CUANDO SE SOLICITE.\n"
    "La regla de no inventar archivos significa que no debes asumir que "
    "un archivo existe.\n"
    "Si el usuario solicita explícitamente crear una función, clase, archivo "
    "o módulo, debes crearlo mediante una acción real.\n\n"

    "7. PUEDES USAR VARIOS COMANDOS.\n"
    "Una tarea puede requerir múltiples ciclos de inspección, modificación "
    "y prueba. Continúa trabajando hasta tener evidencia suficiente.\n\n"

    "8. ACTÚA CUANDO YA TENGAS EVIDENCIA SUFICIENTE.\n"
    "No repitas inspecciones que ya fueron realizadas.\n"
    "Si ya leíste el archivo afectado y el problema está confirmado, "
    "pasa a la modificación necesaria.\n"
    "No vuelvas a ejecutar ls -la /sandbox sin una razón concreta.\n"
    "No leas archivos de prueba, copias o archivos no relacionados salvo "
    "que sean necesarios para resolver el issue.\n\n"

    "9. VERIFICA LOS CAMBIOS.\n"
    "Después de modificar código, ejecuta las validaciones necesarias para "
    "confirmar que el cambio realmente ocurrió y que funciona.\n"
    "Cuando sea apropiado, lee nuevamente el archivo modificado, ejecuta "
    "una comprobación sintáctica o ejecuta una prueba relevante.\n\n"

    "10. NO DES POR TERMINADA UNA TAREA SIN EVIDENCIA.\n"
    "Una explicación de una posible solución no significa que el issue "
    "esté solucionado.\n"
    "Una propuesta de parche tampoco significa que el parche fue aplicado.\n"
    "Un comando con EXIT_CODE 0 tampoco demuestra por sí solo que el "
    "problema fue solucionado.\n"
    "Debes verificar el resultado real.\n\n"

    "11. SI UNA HERRAMIENTA FALLA, APRENDE DEL ERROR.\n"
    "Si un comando devuelve EXIT_CODE distinto de 0:\n"
    "- analiza el mensaje de error;\n"
    "- identifica la causa;\n"
    "- cambia el procedimiento;\n"
    "- ejecuta una acción corregida.\n"
    "No repitas ciegamente el mismo comando fallido.\n\n"

    "12. USA LA INFORMACIÓN OBTENIDA POR LAS HERRAMIENTAS.\n"
    "Los resultados de las herramientas son evidencia real.\n"
    "Si pwd devuelve /sandbox, utiliza /sandbox como workspace.\n"
    "Si un archivo no existe en una ruta, no vuelvas a asumir que existe.\n"
    "Si un listado muestra una ruta o archivo real, utiliza esa información "
    "en los siguientes pasos.\n\n"

    "13. NO BUSQUES TESTS INEXISTENTES.\n"
    "No pierdas turnos buscando una infraestructura de tests que no haya "
    "sido indicada o encontrada en el repositorio.\n"
    "Usa primero las validaciones directamente relacionadas con el issue.\n"
    "Para un archivo Python modificado, una comprobación sintáctica como "
    "python3 -m py_compile puede ser apropiada si está disponible.\n\n"

    "14. NO EJECUTES PARCHE PRECONFIGURADO.\n"
    "No existe ningún comando obligatorio llamado patch.py.\n"
    "No inventes ni asumas la existencia de patch.py.\n"
    "Debes determinar mediante inspección qué acción concreta es necesaria.\n\n"

    "15. CUANDO NECESITES ACTUAR, USA ESTE FORMATO EXACTO:\n"
    "```bash\n"
    "comando\n"
    "```\n\n"

    "16. NO AFIRMES ÉXITO SIN VERIFICACIÓN.\n"
    "Nunca digas que algo está solucionado, corregido, implementado, "
    "verificado o probado exitosamente a menos que los resultados de las "
    "herramientas proporcionen evidencia suficiente para afirmarlo.\n\n"

    "======================================================================\n"
    "FLUJO DE TRABAJO\n"
    "======================================================================\n\n"

    "Sigue este ciclo:\n\n"

    "INSPECCIONAR -> ENTENDER -> ACTUAR -> VERIFICAR -> PROBAR -> CONCLUIR\n\n"

    "REGLA CRÍTICA:\n"
    "Una vez que hayas leído el archivo afectado y confirmado el problema, "
    "NO vuelvas a inspeccionarlo sin una razón concreta. "
    "Actúa sobre la evidencia disponible.\n\n"

    "No saltes directamente a una solución inventada.\n"
    "No repitas comandos sin propósito.\n"
    "No termines simplemente porque hayas propuesto una solución.\n"
    "Termina cuando exista evidencia suficiente de que el issue fue "
    "investigado y, cuando corresponda, corregido y verificado.\n"
)


# =============================================================================
# ORCHESTRATOR
# =============================================================================

class VertexKaggleOrchestrator:

    def __init__(
        self,
        config: Optional[Config] = None,
    ):
        self.cfg = config or Config()

        # Solamente conservamos la evidencia necesaria para el siguiente
        # turno. No reconstruimos una conversación artificial completa.
        self.last_tool_result: Optional[str] = None

        self.last_command: Optional[str] = None

        self.no_tool_turns = 0

    # =========================================================================
    # CONTEXT MANAGEMENT
    # =========================================================================

    def _build_context(
        self,
        issue_description: str,
    ) -> list[dict]:

        messages = [
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": (
                    "ISSUE:\n"
                    f"{issue_description}\n\n"
                    "ESTADO ACTUAL:\n"
                    "Debes trabajar sobre el repositorio real ubicado "
                    "en /sandbox.\n"
                    "Ejecuta acciones reales mediante bloques ```bash```.\n"
                ),
            },
        ]

        # ---------------------------------------------------------------------
        # Solamente enviamos la evidencia más reciente.
        #
        # Esto evita que Gemma aprenda a repetir una cadena artificial de:
        #
        # assistant -> resultado -> instrucción -> resultado -> instrucción
        #
        # y reduce drásticamente el contexto.
        # ---------------------------------------------------------------------

        if self.last_tool_result is not None:

            previous_command = self.last_command or "comando desconocido"

            messages.append(
                {
                    "role": "user",
                    "content": (
                        "EVIDENCIA DE LA ÚLTIMA ACCIÓN REAL:\n\n"
                        f"COMANDO EJECUTADO:\n"
                        f"{previous_command}\n\n"
                        f"RESULTADO:\n"
                        f"{self.last_tool_result}\n\n"
                        "Usa esta evidencia para decidir el SIGUIENTE paso.\n"
                        "No repitas el mismo comando si ya obtuviste la "
                        "información necesaria.\n"
                        "Si el archivo afectado ya fue inspeccionado y el "
                        "problema está confirmado, realiza la modificación.\n"
                        "Si necesitas actuar, responde con un bloque "
                        "```bash``` ejecutable.\n"
                    ),
                }
            )

        return messages

    # =========================================================================
    # SANDBOX TOOL
    # =========================================================================

    def run_command(
        self,
        command: str,
    ) -> str:

        command = command.strip()

        log.info(
            "Sandbox → `%s`",
            command,
        )

        if not command:
            return (
                "TOOL_ERROR: El comando está vacío."
            )

        # ---------------------------------------------------------------------
        # Seguridad
        # ---------------------------------------------------------------------

        if BLOCKED_PATTERNS.search(command):

            log.warning(
                "Comando bloqueado por política de seguridad: %s",
                command,
            )

            return (
                "TOOL_ERROR: "
                "Comando rechazado por política de seguridad."
            )

        # ---------------------------------------------------------------------
        # Gateway
        # ---------------------------------------------------------------------

        try:

            response = requests.post(
                self.cfg.gateway_url,
                json={
                    "command": command,
                },
                timeout=self.cfg.tool_timeout,
            )

            response.raise_for_status()

            data = response.json()

        except requests.exceptions.ConnectionError:

            return (
                "TOOL_ERROR: "
                "No se pudo conectar con el FastAPI Gateway "
                "en el puerto 8001. "
                "Verifica que uvicorn esté ejecutándose."
            )

        except requests.exceptions.Timeout:

            return (
                "TOOL_ERROR: "
                "Timeout ejecutando el comando en el sandbox."
            )

        except requests.exceptions.RequestException as e:

            return (
                f"TOOL_ERROR: "
                f"{type(e).__name__}: {e}"
            )

        except Exception as e:

            return (
                f"TOOL_ERROR: "
                f"{type(e).__name__}: {e}"
            )

        # ---------------------------------------------------------------------
        # Infraestructura
        # ---------------------------------------------------------------------

        if data.get("status") == "infra_error":

            return (
                "INFRA_ERROR: "
                f"{data.get('infra_error', 'unknown')} | "
                f"{data.get('message', 'Unknown infrastructure error')}"
            )

        # ---------------------------------------------------------------------
        # Resultado
        # ---------------------------------------------------------------------

        exit_code = data.get(
            "exit_code",
            -1,
        )

        output = data.get(
            "stdout",
            "",
        )

        if output is None:
            output = ""

        output = str(output)

        # ---------------------------------------------------------------------
        # Limitar contexto
        # ---------------------------------------------------------------------

        if len(output) > self.cfg.max_tool_output:

            output = (
                output[:self.cfg.max_tool_output]
                + "\n... [salida truncada]"
            )

        return (
            f"EXIT_CODE: {exit_code}\n"
            f"STDOUT:\n{output}"
        )

    # =========================================================================
    # LM STUDIO
    # =========================================================================

    def _chat_with_retries(
        self,
        payload: dict,
    ) -> Optional[str]:

        for attempt in range(
            1,
            self.cfg.retry_attempts + 1,
        ):

            try:

                response = requests.post(
                    self.cfg.lm_studio_url,
                    json=payload,
                    timeout=self.cfg.request_timeout,
                )

                if not response.ok:

                    log.error(
                        "LM Studio HTTP %s",
                        response.status_code,
                    )

                    log.error(
                        "LM Studio error body: %s",
                        response.text[:4000],
                    )

                    response.raise_for_status()

                data = response.json()

                choices = data.get(
                    "choices",
                    [],
                )

                if not choices:

                    raise ValueError(
                        "LM Studio no devolvió choices."
                    )

                message = choices[0].get(
                    "message",
                    {},
                )

                content = message.get(
                    "content",
                    "",
                )

                if not content:

                    raise ValueError(
                        "LM Studio devolvió una respuesta vacía."
                    )

                return content

            except requests.exceptions.RequestException as e:

                log.warning(
                    "Intento %d/%d falló: %s",
                    attempt,
                    self.cfg.retry_attempts,
                    e,
                )

            except Exception as e:

                log.warning(
                    "Respuesta inválida de LM Studio "
                    "(intento %d/%d): %s",
                    attempt,
                    self.cfg.retry_attempts,
                    e,
                )

            if attempt < self.cfg.retry_attempts:

                delay = (
                    self.cfg.retry_backoff
                    * attempt
                )

                time.sleep(delay)

        return None

    # =========================================================================
    # EXTRACT BASH COMMANDS
    # =========================================================================

    def _extract_commands(
        self,
        content: str,
    ) -> list[str]:

        matches = BASH_BLOCK_RE.findall(
            content
        )

        commands = []

        for block in matches:

            command = block.strip()

            if command:

                commands.append(
                    command
                )

        return commands

    # =========================================================================
    # CHECK FALSE COMPLETION
    # =========================================================================

    def _looks_like_completion(
        self,
        content: str,
    ) -> bool:

        completion_patterns = [
            r"\bsolucionado\b",
            r"\bsolucioné\b",
            r"\bcorregido\b",
            r"\bhe corregido\b",
            r"\bhe solucionado\b",
            r"\bya está\b",
            r"\blist[oó]\b",
            r"\bcompleted\b",
            r"\bfixed\b",
            r"\bresolved\b",
            r"\bdone\b",
            r"\bimplemented\b",
            r"\bimplemented successfully\b",
        ]

        for pattern in completion_patterns:

            if re.search(
                pattern,
                content,
                re.IGNORECASE,
            ):
                return True

        return False

    # =========================================================================
    # MAIN AGENT LOOP
    # =========================================================================

    def run(
        self,
        issue_description: str,
    ) -> list[dict]:

        log.info(
            "Resolviendo issue: %s",
            issue_description[:120],
        )

        # ---------------------------------------------------------------------
        # Reiniciar estado
        # ---------------------------------------------------------------------

        self.last_tool_result = None
        self.last_command = None
        self.no_tool_turns = 0

        # ---------------------------------------------------------------------
        # Main loop
        # ---------------------------------------------------------------------

        for turn in range(
            1,
            self.cfg.max_turns + 1,
        ):

            log.info(
                "Turno %d/%d",
                turn,
                self.cfg.max_turns,
            )

            # -----------------------------------------------------------------
            # Contexto limpio
            # -----------------------------------------------------------------

            messages = self._build_context(
                issue_description
            )

            # -----------------------------------------------------------------
            # Ask model
            # -----------------------------------------------------------------

            content = self._chat_with_retries(
                {
                    "model": self.cfg.model_id,
                    "messages": messages,
                    "temperature": self.cfg.temperature,
                    "max_tokens": self.cfg.max_tokens,
                }
            )

            if content is None:

                log.error(
                    "Comunicación con LM Studio falló "
                    "tras todos los reintentos."
                )

                break

            # -----------------------------------------------------------------
            # Print response
            # -----------------------------------------------------------------

            print(
                f"\n[Vertex Core - Turn {turn}]:\n"
            )

            print(content)

            # -----------------------------------------------------------------
            # Extract tools
            # -----------------------------------------------------------------

            commands = self._extract_commands(
                content
            )

            # -----------------------------------------------------------------
            # NO TOOL
            # -----------------------------------------------------------------

            if not commands:

                self.no_tool_turns += 1

                log.warning(
                    "El modelo no emitió ningún comando "
                    "(turno sin herramienta: %d).",
                    self.no_tool_turns,
                )

                # -------------------------------------------------------------
                # Completion without evidence
                # -------------------------------------------------------------

                if self._looks_like_completion(
                    content
                ):

                    log.error(
                        "El modelo declaró éxito sin evidencia "
                        "de una herramienta."
                    )

                    self.last_tool_result = (
                        "VALIDACIÓN DEL ORQUESTADOR:\n"
                        "No existe evidencia de que la acción "
                        "haya sido ejecutada.\n"
                        "La tarea NO está validada.\n"
                        "Debes continuar trabajando."
                    )

                else:

                    self.last_tool_result = (
                        "VALIDACIÓN DEL ORQUESTADOR:\n"
                        "La respuesta anterior no ejecutó ninguna "
                        "herramienta.\n"
                        "Debes realizar la siguiente acción necesaria "
                        "mediante un bloque ```bash```.\n"
                        "No describas la acción: ejecútala."
                    )

                # -------------------------------------------------------------
                # Evitar loop infinito
                # -------------------------------------------------------------

                if self.no_tool_turns >= 2:

                    log.error(
                        "El modelo produjo dos respuestas "
                        "consecutivas sin ejecutar herramientas."
                    )

                    break

                time.sleep(
                    self.cfg.sleep_between_turns
                )

                continue

            # -----------------------------------------------------------------
            # TOOL FOUND
            # -----------------------------------------------------------------

            self.no_tool_turns = 0

            log.info(
                "Se detectaron %d comando(s) para ejecutar.",
                len(commands),
            )

            # -----------------------------------------------------------------
            # Ejecutar comandos
            # -----------------------------------------------------------------

            for index, command in enumerate(
                commands,
                start=1,
            ):

                log.info(
                    "Ejecutando comando %d/%d",
                    index,
                    len(commands),
                )

                result = self.run_command(
                    command
                )

                print(
                    f"[Tool Result {index}]:\n"
                    f"{result}\n"
                )

                # -------------------------------------------------------------
                # Guardamos solamente la última evidencia real.
                # -------------------------------------------------------------

                self.last_command = command

                self.last_tool_result = result

            time.sleep(
                self.cfg.sleep_between_turns
            )

        else:

            log.warning(
                "Se alcanzó el máximo de turnos "
                "sin concluir."
            )

        return []


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":

    agent = VertexKaggleOrchestrator()

    agent.run(
        "Falla crítica en el sistema de autenticación (auth.py). "
        "El login permite bypass inyectando comillas simples. "
        "Revisa el estado del repositorio ejecutando un comando "
        "de listado o lectura, localiza el archivo afectado y soluciónalo."
    )