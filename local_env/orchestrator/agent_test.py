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
        "http://localhost:8000/tools/run_command"
    )

    model_id: str = "vertex-core-4b-v10"

    # Alternative model:
    # model_id: str = "google/gemma-4-e4b"

    temperature: float = 0.1

    max_tokens: int = 1500

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
    r"```(?:bash|BASH|sh|shell)\s*\n(.*?)```",
    re.DOTALL,
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

SYSTEM_PROMPT = r"""
You are Vertex Core, an autonomous software engineering agent.

Your job is to investigate the reported issue using real tools, inspect the real
code, make justified changes when necessary, and verify the result.

Follow this loop:

INSPECT -> UNDERSTAND -> ACT IF NECESSARY -> VERIFY -> TEST -> CONCLUDE

CORE RULES:

1. REAL EVIDENCE ONLY

The issue description is a hypothesis, not proof.

The actual source code and tool results are the source of truth.

Never invent code, files, variables, queries, configuration, dependencies,
tool output, test results, or successful changes.

2. INSPECT BEFORE MODIFYING

Before changing code, read the actual relevant implementation.

Never patch a line that you have not observed.

If you do not know the exact code that must change, inspect it first.

3. CODE OVERRIDES COMMENTS

Comments and issue descriptions may be outdated or incorrect.

Example:

# SQL injection vulnerability

does NOT prove that SQL injection exists.

If the actual code is:

cursor.execute(
    "SELECT * FROM users WHERE username = ? AND password = ?",
    (username, password)
)

then recognize that the observed query is parameterized.

Do not invent a concatenated query that you did not observe.

4. DO NOT FORCE A FIX

If the reported vulnerability actually exists:

- identify the root cause
- make the smallest justified change
- verify the change
- test the affected behavior

If the reported vulnerability does not exist:

- do NOT modify the code
- test the reported behavior when practical
- conclude that the issue was not reproduced

Do not change correct code just because the issue says it is vulnerable.

5. EXIT CODE 0 IS NOT PROOF

A command returning EXIT_CODE 0 only means the command executed successfully.

It does NOT prove that a modification occurred.

For example, sed can return 0 without replacing anything.

After every modification, read the file again and verify the intended change
actually exists.

6. TEST THE ACTUAL ISSUE

Tests must exercise the behavior described by the issue.

Example:

login("test", "pass") -> False

only proves that those credentials were rejected.

It does NOT prove that SQL injection is fixed.

If the reported attack is:

admin' --

test that behavior directly when safe and practical.

7. DO NOT OVERINTERPRET RESULTS

A test proves only what it actually tested.

One successful test does not prove complete security.

State exactly what the evidence demonstrates.

8. ABANDON WRONG HYPOTHESES

If new evidence contradicts your previous reasoning, discard the previous
reasoning.

Do not invent explanations to preserve your original hypothesis.

9. DO NOT REPEAT YOURSELF

Use previous tool results.

Do not repeatedly execute the same command with the same result.

If a strategy fails, change strategy.

10. EVERY COMMAND MUST HAVE A PURPOSE

A command must:

- inspect something
- reduce uncertainty
- modify justified code
- verify a modification
- or test behavior

Do not execute commands merely to appear active.

11. COMPLETION

The investigation may legitimately finish when one of these is true:

A. The defect was confirmed, fixed, verified, and tested.

B. The reported defect was investigated and not reproduced in the observed
   implementation.

C. There is insufficient evidence, and you clearly state what remains unknown.

Never claim success without evidence.

FINAL PRINCIPLE:

Observed code > tool results > tests > comments > issue description > assumptions.

Never let an assumption override observed evidence.

Your goal is to determine what is actually true about the software,
not to force the issue to produce a fix.
"""


# =============================================================================
# ORCHESTRATOR
# =============================================================================

class VertexKaggleOrchestrator:

    def __init__(
        self,
        config: Optional[Config] = None,
    ):

        self.cfg = config or Config()

        self.history = [
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            }
        ]

        # Number of consecutive turns without tools.
        self.no_tool_turns = 0

        # History of executed commands.
        #
        # Each element:
        #
        # {
        #     "command": "...",
        #     "result": "..."
        # }
        #
        self.command_history = []

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

        # ---------------------------------------------------------------------
        # Basic validation
        # ---------------------------------------------------------------------

        if not command:
            return (
                "TOOL_ERROR: El comando está vacío."
            )

        # ---------------------------------------------------------------------
        # Security
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
                "en el puerto 8000. "
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
        # Infrastructure
        # ---------------------------------------------------------------------

        if data.get("status") == "infra_error":

            return (
                "INFRA_ERROR: "
                f"{data.get('infra_error', 'unknown')} | "
                f"{data.get('message', 'Unknown infrastructure error')}"
            )

        # ---------------------------------------------------------------------
        # Result
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
        # Limit context
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
                commands.append(command)

        return commands

    # =========================================================================
    # CHECK VALID CONCLUSION
    # =========================================================================

    def _looks_like_valid_conclusion(
        self,
        content: str,
    ) -> bool:
        """
        Determines whether the model is presenting a final conclusion
        that can be accepted by the orchestrator.

        A conclusion is only valid when previous tool evidence exists.
        """

        if not self.command_history:
            return False

        conclusion_patterns = [

            # -----------------------------------------------------------------
            # Defect fixed
            # -----------------------------------------------------------------

            r"\bsolucionado\b",
            r"\bsolucioné\b",
            r"\bcorregido\b",
            r"\bhe corregido\b",
            r"\bhe solucionado\b",
            r"\bfixed\b",
            r"\bresolved\b",
            r"\bcompleted\b",
            r"\bdone\b",

            # -----------------------------------------------------------------
            # Defect not reproduced / issue invalid
            # -----------------------------------------------------------------

            r"\bno se requiere cambio\b",
            r"\bno requiere cambio\b",
            r"\bno se requiere ninguna modificación\b",
            r"\bno requiere ninguna modificación\b",
            r"\bno fue reproducido\b",
            r"\bno se reprodujo\b",
            r"\bno se reproduce\b",
            r"\bno está presente\b",
            r"\bno existe la vulnerabilidad\b",
            r"\bvulnerabilidad no encontrada\b",
            r"\bissue fue malinterpretado\b",
            r"\bissue no fue reproducido\b",

            # -----------------------------------------------------------------
            # Insufficient evidence
            # -----------------------------------------------------------------

            r"\bevidencia insuficiente\b",
            r"\binsufficient evidence\b",
            r"\bno hay evidencia suficiente\b",
        ]

        for pattern in conclusion_patterns:

            if re.search(
                pattern,
                content,
                re.IGNORECASE,
            ):
                return True

        return False

    # =========================================================================
    # CHECK UNSUPPORTED COMPLETION CLAIM
    # =========================================================================

    def _looks_like_completion_claim(
        self,
        content: str,
    ) -> bool:
        """
        Detects claims that the agent completed an action without deciding
        whether the claim is actually supported by evidence.
        """

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
    # LOOP DETECTION
    # =========================================================================

    def _check_for_loop(
        self,
        command: str,
        result: str,
    ) -> bool:

        command_normalized = command.strip()

        result_normalized = result.strip()

        # Search for exactly the same command + exactly the same result.

        for previous in self.command_history:

            if (
                previous["command"] == command_normalized
                and previous["result"] == result_normalized
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

        self.history.append(
            {
                "role": "user",
                "content": (
                    "ISSUE:\n"
                    f"{issue_description}\n\n"

                    "Debes trabajar sobre el repositorio real. "
                    "No simules acciones. "

                    "Cuando necesites usar la terminal, emite "
                    "un bloque ```bash```. "

                    "Continúa hasta determinar, con evidencia suficiente, "
                    "una de estas situaciones: "

                    "(1) el defecto existe y fue corregido y verificado, "
                    "(2) el defecto reportado no está presente o no pudo "
                    "reproducirse, "
                    "o (3) la evidencia disponible es insuficiente."
                ),
            }
        )

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
            # Ask model
            # -----------------------------------------------------------------

            content = self._chat_with_retries(
                {
                    "model": self.cfg.model_id,
                    "messages": self.history,
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
            # Store response
            # -----------------------------------------------------------------

            self.history.append(
                {
                    "role": "assistant",
                    "content": content,
                }
            )

            print(
                f"\n[Vertex Core - Turn {turn}]:\n"
                f"{content}\n"
            )

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

                # -------------------------------------------------------------
                # VALID CONCLUSION
                # -------------------------------------------------------------
                #
                # The model may legitimately finish without another command.
                #
                # Example:
                #
                #   Tool evidence:
                #   cursor.execute("SELECT ... ?", (...))
                #
                #   Model:
                #   "No se requiere cambio: el código ya es seguro."
                #
                # This is a valid conclusion because tool evidence exists.
                # -------------------------------------------------------------

                if self._looks_like_valid_conclusion(
                    content
                ):

                    log.info(
                        "CONCLUSIÓN VÁLIDA: el modelo concluyó "
                        "la investigación con evidencia previa."
                    )

                    log.info(
                        "Investigación finalizada en el turno %d.",
                        turn,
                    )

                    break

                # -------------------------------------------------------------
                # NO VALID CONCLUSION
                # -------------------------------------------------------------

                self.no_tool_turns += 1

                log.warning(
                    "El modelo no emitió ningún comando "
                    "(turno sin herramienta: %d).",
                    self.no_tool_turns,
                )

                # -------------------------------------------------------------
                # MODEL CLAIMS COMPLETION WITHOUT VALID CONCLUSION
                # -------------------------------------------------------------

                if self._looks_like_completion_claim(
                    content
                ):

                    warning_message = (
                        "VALIDACIÓN DEL ORQUESTADOR:\n"

                        "Afirmaste que una acción fue realizada "
                        "o que el problema fue solucionado, pero "
                        "la conclusión no tiene evidencia suficiente "
                        "para ser aceptada.\n\n"

                        "No puedes declarar la tarea completada "
                        "sin evidencia.\n\n"

                        "Continúa trabajando y, si necesitas inspeccionar, "
                        "modificar o verificar el repositorio, emite "
                        "un bloque ```bash``` con el comando exacto."
                    )

                else:

                    warning_message = (
                        "TOOL_REQUIRED:\n"

                        "No ejecutaste ninguna herramienta y tampoco "
                        "presentaste una conclusión válida.\n\n"

                        "Debes continuar trabajando en el issue.\n"

                        "Si necesitas inspeccionar, leer, modificar "
                        "o verificar el repositorio, emite ahora "
                        "un bloque ```bash``` con el comando exacto.\n\n"

                        "No describas la acción. EJECÚTALA."
                    )

                self.history.append(
                    {
                        "role": "user",
                        "content": warning_message,
                    }
                )

                # -------------------------------------------------------------
                # PREVENT ENDLESS NO-TOOL LOOP
                # -------------------------------------------------------------

                if self.no_tool_turns >= 3:

                    log.error(
                        "El modelo produjo tres respuestas "
                        "consecutivas sin ejecutar herramientas."
                    )

                    self.history.append(
                        {
                            "role": "user",
                            "content": (
                                "ÚLTIMA ADVERTENCIA DEL ORQUESTADOR:\n"

                                "Debes producir una acción ejecutable "
                                "en el siguiente turno.\n\n"

                                "Emite un bloque ```bash```.\n\n"

                                "No expliques la acción. EJECÚTALA."
                            ),
                        }
                    )

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
            # Execute every command
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

                # -------------------------------------------------------------
                # Execute
                # -------------------------------------------------------------

                result = self.run_command(
                    command
                )

                print(
                    f"[Tool Result {index}]:\n"
                    f"{result}\n"
                )

                # -------------------------------------------------------------
                # LOOP DETECTION
                # -------------------------------------------------------------

                loop_detected = self._check_for_loop(
                    command,
                    result,
                )

                # -------------------------------------------------------------
                # Store command and result
                # -------------------------------------------------------------

                self.command_history.append(
                    {
                        "command": command.strip(),
                        "result": result.strip(),
                    }
                )

                # -------------------------------------------------------------
                # Inject tool result into conversation
                # -------------------------------------------------------------

                if loop_detected:

                    loop_message = (
                        "LOOP DETECTADO POR EL ORQUESTADOR.\n\n"

                        "El comando que acabas de ejecutar produjo "
                        "exactamente el mismo resultado que una ejecución "
                        "anterior:\n\n"

                        "COMANDO:\n"
                        f"{command}\n\n"

                        "RESULTADO:\n"
                        f"{result}\n\n"

                        "NO EJECUTES ESTE MISMO COMANDO NUEVAMENTE.\n\n"

                        "Debes cambiar de estrategia y obtener nueva "
                        "evidencia.\n\n"

                        "Ejemplos de estrategias alternativas:\n"

                        "- inspeccionar directamente el archivo;\n"
                        "- utilizar otro comando de lectura;\n"
                        "- revisar otra parte relevante del repositorio;\n"
                        "- modificar el procedimiento;\n"
                        "- verificar una hipótesis diferente.\n\n"

                        "El objetivo es avanzar, no repetir la misma acción."
                    )

                    self.history.append(
                        {
                            "role": "user",
                            "content": loop_message,
                        }
                    )

                    log.warning(
                        "LOOP DETECTADO: `%s`",
                        command,
                    )

                else:

                    self.history.append(
                        {
                            "role": "user",
                            "content": (
                                "RESULTADO DE LA HERRAMIENTA "
                                "DE TERMINAL:\n\n"

                                f"{result}\n\n"

                                "Analiza este resultado antes de continuar.\n"

                                "Si necesitas otra acción, emite otro "
                                "bloque ```bash```.\n"

                                "No afirmes que una acción tuvo éxito "
                                "si el EXIT_CODE indica un error.\n"

                                "Si la estrategia anterior no funcionó, "
                                "cambia de estrategia en lugar de repetir "
                                "automáticamente el mismo comando."
                            ),
                        }
                    )

            time.sleep(
                self.cfg.sleep_between_turns
            )

        else:

            log.warning(
                "Se alcanzó el máximo de turnos "
                "sin concluir."
            )

        return self.history


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