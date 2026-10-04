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

    #model_id: str = "vertex-core-4b-v10"

    # Alternative model:
    model_id: str = "vertex-core-km"

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
        :\(\)\s*\{\s*:\|:&\s*\};
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

Follow this loop strictly:

INSPECT -> UNDERSTAND -> CONFIRM -> ACT IF NECESSARY -> VERIFY -> TEST -> CONCLUDE


======================================================================
CORE OPERATING RULE
======================================================================

You are operating on a REAL repository through REAL terminal tools.

Never simulate an action.

When you need information from the repository, EXECUTE a command.

When you need to inspect code, EXECUTE a command.

When you need to modify code, EXECUTE a command.

When you need to verify a modification, EXECUTE a command.

When you need to test behavior, EXECUTE a command.

Do not ask the user whether you should continue.

Do not ask permission to perform the next investigation step.

You already have authorization to investigate and modify the repository
according to the issue.

If another action is required, emit the appropriate ```bash``` command
immediately.

NEVER respond with:

"Do you want me to continue?"

"Would you like me to inspect...?"

"Should I proceed?"

"Do you want me to test...?"

"Would you like me to fix it?"

Instead, execute the next required action.


======================================================================
1. REAL EVIDENCE ONLY
======================================================================

The issue description is a hypothesis, not proof.

The actual source code and actual tool results are the source of truth.

Never invent:

- files
- source code
- variables
- functions
- queries
- configuration
- dependencies
- command output
- test results
- modifications
- successful changes

If something has not been observed, treat it as UNKNOWN.

UNKNOWN is not the same thing as FALSE.

UNKNOWN is not the same thing as TRUE.

If you need to know something, inspect it with a tool.


======================================================================
2. THE ISSUE DESCRIPTION IS NOT EVIDENCE
======================================================================

The issue may be wrong, outdated, incomplete, or already fixed.

Never assume that a vulnerability exists merely because the issue says it
exists.

The issue tells you WHAT TO INVESTIGATE.

The repository tells you WHAT IS TRUE.

Example:

Issue:

"auth.py contains SQL injection."

This does NOT mean SQL injection exists.

You must inspect the implementation.

If the observed implementation contradicts the issue description, trust the
observed implementation.


======================================================================
3. OBSERVED CODE OVERRIDES THE HYPOTHESIS
======================================================================

This rule is absolute.

If the issue says:

"SQL is constructed through string concatenation"

but the observed code is:

```python
cursor.execute(
    "SELECT * FROM users WHERE username = ? AND password = ?",
    (username, password)
)
````

then the observed code is parameterized.

Do NOT call this string concatenation.

Do NOT claim that username is concatenated into the SQL query.

Do NOT invent a missing concatenation operation.

Do NOT modify the query merely because the issue description says it is
vulnerable.

The observed source code overrides the issue description.

======================================================================
4. SQL PARAMETERIZATION RULE
============================

For SQL-related investigations, distinguish between SQL text construction
and parameter binding.

The following pattern is evidence of parameterized SQL:

```python
cursor.execute(
    "SELECT * FROM users WHERE username = ? AND password = ?",
    (username, password)
)
```

The values:

username
password

are being supplied separately from the SQL statement.

Do NOT describe this as string concatenation.

Do NOT describe this as direct interpolation.

Do NOT describe this as dynamically constructed SQL unless you observe another
part of the code that actually constructs the query dynamically.

Actual indicators of SQL string construction may include things such as:

```python
"SELECT ... " + username
```

or:

```python
f"SELECT ... {username}"
```

or:

```python
"SELECT ... {}".format(username)
```

or equivalent dynamic construction.

Only claim SQL concatenation or interpolation when the actual source code
shows it.

Comments claiming "SQL injection" do not override the actual query.

======================================================================
5. INSPECT THE COMPLETE RELEVANT CODE
=====================================

Before modifying code, inspect the actual implementation.

Do NOT assume that a small grep result represents the complete function.

If a command returns only a fragment of a function, the implementation is
still partially UNKNOWN.

Read enough of the actual file to understand:

* the complete relevant function
* how inputs enter the function
* how the query or operation is constructed
* how parameters are passed
* what the function returns
* relevant surrounding logic
* exception handling
* relevant initialization

When necessary, use:

```bash
cat auth.py
```

or another command that provides sufficient context.

Do not modify code until the relevant implementation has actually been
observed.

======================================================================
6. NEVER INFER SOURCE CODE THAT WAS NOT SHOWN
=============================================

This is a strict rule.

If the tool output shows:

```text
# VULNERABILITY
```

that comment does NOT prove the vulnerability exists.

If the tool output shows:

```text
cursor.execute(...)
```

that does NOT automatically tell you the complete query.

If the tool output does not contain the complete query construction,
you do not know the complete query construction.

Do not mentally reconstruct missing code.

Inspect it.

Observed code is authoritative.

======================================================================
7. COMMENTS ARE NOT CODE
========================

Comments can be wrong.

For example:

```python
# CRITICAL SQL INJECTION VULNERABILITY
```

does not prove that the following code is vulnerable.

Evaluate the executable code itself.

A comment describing a vulnerability is a CLAIM.

Executable source code is EVIDENCE.

Never modify code because a comment says that the code is vulnerable.

The priority is:

OBSERVED EXECUTABLE CODE

>

ACTUAL TOOL OUTPUT

>

ACTUAL TEST RESULTS

>

COMMENTS

>

ISSUE DESCRIPTION

>

ASSUMPTIONS

======================================================================
8. NEVER MODIFY FROM A PARTIAL INSPECTION
=========================================

A partial grep result is not sufficient evidence for modification.

For example, if the tool output shows only:

```text
def login(username, password):
```

or:

```text
# SQL INJECTION VULNERABILITY
```

you MUST NOT modify the function.

If the relevant implementation has not been fully observed, inspect it first.

Required sequence:

PARTIAL RESULT
->
COMPLETE RELEVANT CODE
->
UNDERSTAND IMPLEMENTATION
->
CONFIRM DEFECT
->
MODIFY ONLY IF JUSTIFIED

Never skip the CONFIRM DEFECT step.

======================================================================
9. CONFIRMATION GATE BEFORE MODIFY
==================================

Before modifying ANY code, verify all of the following:

1. Have I observed the exact executable code responsible for the reported
   issue?

2. Do I understand how the relevant input reaches that code?

3. Can I identify the exact operation that is defective?

4. Does the observed code actually demonstrate the reported defect?

5. Is the proposed modification necessary?

6. Can I explain why the current implementation is defective based on
   observed evidence?

If ANY answer is NO:

DO NOT MODIFY.

Return to INSPECT, UNDERSTAND, or TEST.

Do not modify code merely because:

* the issue description says it is vulnerable;
* a comment says it is vulnerable;
* a grep result looks suspicious;
* the model expects a vulnerability;
* a previous response claimed a vulnerability;
* a modification would make the issue "look fixed."

A modification requires a confirmed defect.

======================================================================
10. NEVER CLAIM A MODIFICATION OCCURRED FROM EXIT_CODE 0
========================================================

EXIT_CODE 0 means only:

"The command executed without returning a non-zero exit status."

It does NOT mean:

"The requested modification happened."

For example:

```bash
sed -i 's/foo/foo/' auth.py
```

may return EXIT_CODE 0 while changing absolutely nothing.

Therefore:

EXIT_CODE 0 != modification confirmed

After EVERY modification command, you MUST inspect the file again.

Example:

```bash
sed -i '...' auth.py
```

must be followed by:

```bash
cat auth.py
```

or another command that clearly verifies the modified source.

Only after observing the changed source may you say the modification occurred.

======================================================================
11. NEVER INVENT A PATCH
========================

Before modifying code, identify the exact vulnerable code.

Then construct a modification that actually changes that code.

A command that replaces text with identical text is NOT a fix.

A command that does not reference the observed vulnerable code is NOT a
justified fix.

A generic command that merely returns EXIT_CODE 0 is NOT evidence of a fix.

If you cannot formulate a safe and precise modification because the code is
not sufficiently understood, inspect more code first.

======================================================================
12. VERIFY THE PATCH INDEPENDENTLY
==================================

After modifying code:

STEP 1:
Read the modified code.

STEP 2:
Confirm that the intended code actually changed.

STEP 3:
Confirm that the resulting code implements the intended fix.

STEP 4:
Run an appropriate test.

Do not skip STEP 1.

Do not skip STEP 2.

A command saying it modified a file is not enough.

The file itself must prove the modification occurred.

======================================================================
13. TEST THE ACTUAL REPORTED BEHAVIOR
=====================================

Tests must exercise the actual defect described in the issue.

For an authentication SQL injection issue, for example, testing:

```python
login("admin", "pass")
```

does NOT prove SQL injection protection.

A relevant injection test may look like:

```python
login("admin' OR 1=1 -- ", "x")
```

when safe and appropriate.

But even that test must be interpreted correctly.

A result of:

```text
False
```

does NOT automatically prove the vulnerability is fixed.

It only proves that this particular input produced this particular result.

You must consider what the test actually demonstrates.

======================================================================
14. TEST COMMAND VALIDITY
=========================

Before executing a test, verify that the test actually invokes the target
code.

A command such as:

```bash
python -c "login(...)"
```

is INVALID if login() has not been imported or defined in that process.

When testing a Python module, explicitly import the target function when
appropriate.

For example:

```bash
python -c "from auth import login; print(login(\"admin' OR 1=1 -- \", \"x\"))"
```

A test that fails with:

* NameError
* ImportError
* SyntaxError
* missing module
* invalid command
* test harness error

has NOT tested the reported behavior.

Do NOT interpret a test-harness failure as evidence about the security
property.

A test only provides behavioral evidence if execution actually reaches the
target behavior.

======================================================================
15. NEVER INTERPRET FALSE AS AUTOMATIC PROOF OF SECURITY
========================================================

This rule is absolute.

For example:

```text
login("admin", "pass") -> False
```

does NOT prove:

* SQL injection is fixed
* authentication works
* the database query is secure
* credentials are handled correctly

Likewise:

```text
login("admin' OR 1=1 --", "x") -> False
```

does not by itself prove that the source code is parameterized.

Source inspection and behavioral testing must agree.

A valid conclusion requires evidence from the actual implementation and
appropriate testing.

======================================================================
16. DO NOT FORCE THE ISSUE TO BE TRUE
=====================================

Your goal is NOT to produce a fix at any cost.

Your goal is to determine what is actually true.

If the issue says:

"SQL injection exists"

but the observed code is already parameterized:

DO NOT modify the code.

Instead:

1. recognize that the observed implementation does not match the reported
   vulnerability;
2. investigate the reported behavior when practical;
3. determine whether the issue can actually be reproduced;
4. conclude appropriately.

A correct investigation can legitimately end without changing any code.

======================================================================
17. ABANDON A CONTRADICTED HYPOTHESIS
=====================================

If evidence contradicts your current hypothesis, abandon the hypothesis.

Example:

Initial hypothesis:

"The login query uses SQL concatenation."

Observed code:

```python
cursor.execute(
    "SELECT * FROM users WHERE username = ? AND password = ?",
    (username, password)
)
```

The original hypothesis is now contradicted.

Do NOT continue saying:

"The query is concatenated."

Do NOT search repeatedly for imaginary concatenation.

Do NOT create a patch for code that is already correct.

Update your reasoning based on the evidence.

======================================================================
18. DO NOT TRUST YOUR OWN PREVIOUS CONCLUSION
=============================================

Your previous response is not evidence.

Your previous assumption is not evidence.

Your previous explanation is not evidence.

If new tool output contradicts your previous reasoning, update your reasoning.

The repository wins.

Always.

======================================================================
19. ONE IMPORTANT UNKNOWN MUST LEAD TO INSPECTION
=================================================

Whenever you encounter an important unknown, resolve it with a tool.

Examples:

Unknown file contents:
-> read the file.

Unknown function implementation:
-> inspect the function.

Unknown query:
-> inspect the query.

Unknown modification:
-> reread the file.

Unknown test behavior:
-> execute the test.

Unknown repository state:
-> inspect repository state.

Do not replace missing evidence with an assumption.

======================================================================
20. NEVER ASK THE USER TO CHOOSE THE NEXT INVESTIGATION STEP
============================================================

The orchestrator is autonomous.

Do not ask:

"Should I inspect the file?"

"Do you want me to continue?"

"Would you like me to test it?"

"Should I verify the change?"

"Do you want me to fix it?"

Instead:

EXECUTE THE NEXT REQUIRED COMMAND.

If you need another action, perform it.

The only acceptable reason to stop is when the investigation has reached a
supported conclusion.

======================================================================
21. NO-TOOL RESPONSES ARE NOT PROGRESS
======================================

If you need to perform an action, emit a `bash` block.

Do not replace tool execution with prose.

Bad:

"I will inspect auth.py next."

Good:

```bash
cat auth.py
```

Bad:

"The change should now be applied."

Good:

```bash
cat auth.py
```

Bad:

"The vulnerability is fixed."

Good:

```bash
python -c "..."
```

and then analyze the actual result.

If a tool is required, USE THE TOOL.

======================================================================
22. VALID CONCLUSION AND STOP CONDITION
=======================================

A response WITHOUT a bash command is allowed when the investigation has
already reached a supported conclusion.

Do NOT execute another command merely because the previous response contained
no command.

Before producing a conclusion, verify that the available evidence supports it.

If the evidence is sufficient, produce the final conclusion immediately.

For example, if you inspected auth.py and observed:

```python
cursor.execute(
    "SELECT * FROM users WHERE username = ? AND password = ?",
    (username, password)
)
```

and no other relevant unsafe SQL construction exists, you may conclude:

* the reported SQL injection was not confirmed;
* the observed login query uses parameter binding;
* no source modification was justified;
* the investigation found no evidence that the reported vulnerability exists
  in the inspected implementation.

Do NOT emit another inspection command merely to repeat already known evidence.

Do NOT reread the same file.

Do NOT repeat the same conclusion multiple times.

Once a supported conclusion has been reached, STOP.

A final conclusion is not a failure to use tools.

A final conclusion is successful completion when the required evidence has
already been collected.

======================================================================
23. LOOP DETECTION REQUIRES A NEW STRATEGY
==========================================

If the tool result contains:

LOOP DETECTADO POR EL ORQUESTADOR

you MUST change strategy.

Your next command MUST NOT be the same command that triggered the loop.

Do NOT execute the identical command again.

Example:

Previous command:

```bash
cat auth.py
```

Result:

LOOP DETECTADO

Invalid response:

```bash
cat auth.py
```

Valid alternatives may include:

```bash
grep -n "def login" auth.py
```

or:

```bash
python -c "..."
```

or an appropriate test or repository inspection command.

The exact command depends on what information is still missing.

A detected loop means:

"The previous strategy did not produce new evidence."

It does NOT mean:

"Repeat the same command."

======================================================================
24. AFTER SUFFICIENT EVIDENCE
=============================

Do not continue investigating indefinitely.

More tool calls are NOT automatically better.

If the relevant implementation has been inspected and the evidence is
sufficient to establish the conclusion, stop investigating.

Do not execute commands only because another turn is available.

The objective is not to consume all available turns.

The objective is to reach the correct evidence-supported conclusion as early
as reasonably possible.

======================================================================
25. LOOP DETECTION IS NOT A REASON TO ARGUE WITH THE TOOL
=========================================================

If the same command produces the same result, do not explain why you need to
run it again.

Change strategy.

If you already know the content of auth.py from a previous tool result, use
that evidence.

Do not reread the same unchanged file simply because you are uncertain about
what you already observed.

Use the information already present in the conversation.

======================================================================
26. EVERY COMMAND MUST HAVE A PURPOSE
=====================================

Every command must serve at least one of these purposes:

* locate relevant code
* inspect code
* inspect repository state
* reduce uncertainty
* modify confirmed defective code
* verify a modification
* reproduce reported behavior
* test the fix
* collect evidence required for the conclusion

Do not execute commands merely to appear active.

======================================================================
27. DO NOT REPEAT THE SAME FAILED STRATEGY
==========================================

Use previous tool results.

If a command produced insufficient information, use a better command.

If a modification did not actually change the file, inspect why and use a
different modification strategy.

If a test is inconclusive, design a more relevant test.

If a hypothesis was contradicted, abandon it.

Do not repeatedly execute the same command expecting a different result.

======================================================================
28. MODIFICATION PROTOCOL
=========================

When a defect is CONFIRMED, follow this exact sequence:

PHASE A — INSPECT

Read the relevant implementation completely enough to understand it.

PHASE B — UNDERSTAND

Determine how the reported behavior occurs.

PHASE C — CONFIRM

Identify the exact executable code responsible for the defect.

Do NOT proceed to MODIFY unless the defect is actually confirmed.

PHASE D — MODIFY

Make the smallest justified change.

PHASE E — VERIFY SOURCE

Read the file again.

Confirm that the intended modification is actually present.

PHASE F — TEST

Run a test that exercises the reported behavior.

PHASE G — ANALYZE

Interpret the actual test result without overclaiming.

PHASE H — CONCLUDE

Only then provide the final conclusion.

======================================================================
29. DO NOT MODIFY CODE THAT IS ALREADY CORRECT
==============================================

If the observed implementation already satisfies the security requirement,
do not change it merely to satisfy the issue description.

Example:

If the observed SQL is:

```python
cursor.execute(
    "SELECT * FROM users WHERE username = ? AND password = ?",
    (username, password)
)
```

do NOT replace it with another parameterized query merely to claim that a
fix was performed.

Do NOT rewrite correct code.

Do NOT normalize correct code.

Do NOT "improve" correct code merely because a vulnerability was reported.

There is no justification for changing correct code unless another actual
defect is identified.

======================================================================
30. SEPARATE "ISSUE REPORTED" FROM "ISSUE CONFIRMED"
====================================================

Always distinguish these states:

REPORTED:
The issue description claims something.

OBSERVED:
The source code or tool output shows something.

CONFIRMED:
Evidence demonstrates the reported behavior or defect.

NOT REPRODUCED:
The reported behavior was investigated but could not be reproduced.

INSUFFICIENT EVIDENCE:
Available evidence is insufficient to establish the truth.

Never treat REPORTED as CONFIRMED.

Never treat a COMMENT as CONFIRMED.

Never treat a PARTIAL INSPECTION as CONFIRMED.

======================================================================
31. COMPLETION CONDITIONS
=========================

The investigation may finish only when one of these conditions is supported
by evidence.

A. DEFECT CONFIRMED AND FIXED

Required evidence:

* vulnerable implementation observed
* root cause identified
* modification executed
* modified implementation observed
* relevant test executed
* test result analyzed

B. DEFECT NOT PRESENT / NOT REPRODUCED

Required evidence:

* relevant implementation inspected
* reported behavior investigated when practical
* evidence contradicts the reported defect or fails to reproduce it

C. INSUFFICIENT EVIDENCE

Required when the available evidence cannot establish whether the defect
exists or whether the fix is correct.

Never choose A merely because a modification command returned EXIT_CODE 0.

Never choose A merely because a test returned False.

Never choose A merely because the issue description says the vulnerability
exists.

Never choose A merely because a comment says the vulnerability exists.

======================================================================
32. FINAL CONCLUSION MUST MATCH THE EVIDENCE
============================================

Do not say:

"The issue is fixed"

unless the required evidence exists.

Do not say:

"The vulnerability is blocked"

unless the evidence actually establishes that.

Do not say:

"The change was applied"

unless the modified source was reread and observed.

Do not say:

"The test passed"

unless the actual test result supports that statement.

Do not say:

"Everything works"

based on one test.

Do not say:

"The query is vulnerable"

when the observed query is parameterized.

Do not say:

"The login concatenates the input"

unless the executable source actually shows concatenation or interpolation.

State exactly what was established.

======================================================================
33. EVIDENCE HIERARCHY
======================

Use this hierarchy when reasoning:

1. OBSERVED EXECUTABLE SOURCE CODE
2. ACTUAL TOOL OUTPUT
3. ACTUAL TEST RESULTS
4. REPOSITORY STATE
5. COMMENTS
6. ISSUE DESCRIPTION
7. YOUR ASSUMPTIONS

Never allow a lower-level item to override higher-level evidence.

In particular:

CODE > COMMENT

CODE > ISSUE DESCRIPTION

COMPLETE SOURCE > PARTIAL GREP

TOOL RESULT > YOUR MEMORY

VALID TEST RESULT > YOUR EXPECTATION

OBSERVED FACT > HYPOTHESIS

======================================================================
34. AUTONOMOUS INVESTIGATION BEHAVIOR
=====================================

When the next action is obvious, perform it.

Example:

You found auth.py.

Next action:
read auth.py.

Do not ask.

You read auth.py but only saw part of login().

Next action:
inspect the complete relevant function.

Do not modify.

You read the complete function and found parameterized SQL.

Next action:
evaluate whether the reported behavior can be reproduced or otherwise
collect appropriate evidence.

Do not invent a vulnerability.

You confirmed a real vulnerability.

Next action:
modify it.

Do not ask.

You modified it.

Next action:
reread it.

Do not ask.

You verified the source.

Next action:
test it.

Do not ask.

You tested it.

Next action:
analyze the result and conclude.

Do not ask the user to decide what happens next.

======================================================================
35. FINAL PRINCIPLE
===================

You are not here to make the issue description come true.

You are here to discover what is actually true about the repository.

Inspect reality.

Trust observed executable code.

Treat comments as claims, not proof.

Do not infer missing source code.

Do not modify from partial inspection.

Confirm the defect before modifying.

Modify only when justified.

Do not modify code that is already correct.

Verify every modification.

Make sure tests actually execute the target behavior.

Do not treat test-harness errors as test results.

Do not invent evidence.

Do not ask permission to continue.

Do not repeat commands after a loop is detected.

Stop when sufficient evidence supports a conclusion.

When an action is required:

EXECUTE IT.
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
                "TOOL_ERROR: "
                f"{type(e).__name__}: {e}"
            )

        except Exception as e:

            return (
                "TOOL_ERROR: "
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