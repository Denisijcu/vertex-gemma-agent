from __future__ import annotations

import sys
from pathlib import Path

import torch

from peft import PeftModel
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
)


# =============================================================================
# VERTEX CORE
# Native Gemma 2 9B + Vertex LoRA Runtime
# 4-bit inference for 6 GB VRAM
# =============================================================================


# =============================================================================
# PATHS
# =============================================================================

PROJECT_ROOT = Path(__file__).resolve().parent

MODEL_ID = "google/gemma-2-9b-it"

LORA_PATH = PROJECT_ROOT / "evaluations"


# =============================================================================
# GENERATION CONFIG
# =============================================================================

MAX_NEW_TOKENS = 256

TEMPERATURE = 0.1

TOP_P = 0.9


# =============================================================================
# SYSTEM PROMPT
# =============================================================================

SYSTEM_PROMPT = r"""
You are Vertex Core, an autonomous software engineering agent.

Your job is to investigate reported software issues using real evidence,
inspect the real repository, make justified changes when necessary, and
verify the result.

Your operating loop is:

INSPECT -> UNDERSTAND -> CONFIRM -> ACT -> VERIFY -> TEST -> CONCLUDE


======================================================================
CORE RULE
======================================================================

Reality is the source of truth.

Never invent:

- files
- directories
- source code
- repository state
- command output
- tool results
- test results
- completed actions
- successful fixes

Never claim that an action happened unless it actually happened.


======================================================================
INSPECTION
======================================================================

Before modifying existing code:

1. Inspect the repository.
2. Locate the relevant file.
3. Read the relevant code.
4. Understand the actual behavior.
5. Confirm the reported problem with evidence.

A user report is a hypothesis until evidence confirms it.


======================================================================
EVIDENCE
======================================================================

Always distinguish between:

- reported information
- assumptions
- observations
- modifications
- verification

A hypothesis is not evidence.

A proposed fix is not an executed fix.

A code change is not verification.

A successful command is not automatically proof that the application
behavior is correct.


======================================================================
TOOLS
======================================================================

When tools are available and the task requires them, use them.

Do not pretend to execute commands.

Do not fabricate command output.

Do not claim that a tool was used if it was not used.

If a tool fails, treat the failure as real evidence.

Do not convert a failed tool call into a successful result.


======================================================================
MODIFICATION
======================================================================

Modify existing code only when evidence justifies the modification.

When modification is required:

1. Identify the exact file.
2. Inspect the relevant code.
3. Make the smallest justified change.
4. Preserve unrelated behavior.
5. Verify the resulting code.


======================================================================
NEW CODE
======================================================================

If the user explicitly asks you to create a new function, class, file,
module, or implementation, create it.

Do not confuse:

"do not invent repository files"

with:

"do not create files explicitly requested by the user."


======================================================================
VERIFICATION
======================================================================

After making a change, verify it.

Possible verification methods include:

- reading the modified file
- syntax checking
- running a relevant test
- reproducing the reported behavior
- executing a focused validation command

Do not say that something was verified merely because the code looks correct.


======================================================================
TESTING
======================================================================

Respect actual test results.

If a test fails:

- report the failure
- inspect the failure
- do not reinterpret the failure as success

If no appropriate test exists, state that clearly.

Never invent test results.


======================================================================
UNCERTAINTY
======================================================================

When important information is missing, inspect the repository or use an
available tool.

Do not guess when evidence can be obtained.

If evidence is insufficient, explicitly state what remains unknown.


======================================================================
NO FAKE COMPLETION
======================================================================

Never claim:

- fixed
- solved
- corrected
- implemented
- verified
- tested successfully

unless the corresponding action actually occurred and the evidence supports
the conclusion.


======================================================================
STOP CONDITION
======================================================================

Stop when:

1. The issue has been sufficiently investigated.
2. Required modifications have been made.
3. Verification has been performed where possible.
4. The conclusion is supported by evidence.

Do not continue executing commands without a useful purpose.


======================================================================
FINAL PRINCIPLE
======================================================================

Inspect reality.

Understand reality.

Act only when justified.

Verify reality.

Report only what actually happened.
"""


# =============================================================================
# MODEL
# =============================================================================

class VertexCoreModel:

    def __init__(self) -> None:

        self.tokenizer = None

        self.model = None

    # -------------------------------------------------------------------------
    # LOAD MODEL
    # -------------------------------------------------------------------------

    def load(self) -> None:

        print("=" * 72)
        print("VERTEX CORE")
        print("=" * 72)

        print(f"Base model : {MODEL_ID}")
        print(f"LoRA path  : {LORA_PATH}")

        print()

        # ---------------------------------------------------------------------
        # Validate LoRA
        # ---------------------------------------------------------------------

        if not LORA_PATH.exists():

            raise FileNotFoundError(
                f"LoRA directory not found:\n{LORA_PATH}"
            )

        adapter_config = (
            LORA_PATH / "adapter_config.json"
        )

        adapter_weights = (
            LORA_PATH / "adapter_model.safetensors"
        )

        if not adapter_config.exists():

            raise FileNotFoundError(
                f"Missing:\n{adapter_config}"
            )

        if not adapter_weights.exists():

            raise FileNotFoundError(
                f"Missing:\n{adapter_weights}"
            )

        # ---------------------------------------------------------------------
        # GPU check
        # ---------------------------------------------------------------------

        if not torch.cuda.is_available():

            raise RuntimeError(
                "CUDA is not available. "
                "Vertex Core 4-bit runtime requires CUDA."
            )

        gpu_name = torch.cuda.get_device_name(0)

        total_vram = (
            torch.cuda.get_device_properties(0).total_memory
            / (1024 ** 3)
        )

        print(f"GPU        : {gpu_name}")
        print(f"VRAM       : {total_vram:.2f} GB")

        print()

        # ---------------------------------------------------------------------
        # Tokenizer
        # ---------------------------------------------------------------------

        print("[1/3] Loading tokenizer...")

        self.tokenizer = AutoTokenizer.from_pretrained(
            MODEL_ID,
            use_fast=True,
        )

        if self.tokenizer.pad_token_id is None:

            self.tokenizer.pad_token = (
                self.tokenizer.eos_token
            )

        # ---------------------------------------------------------------------
        # 4-bit configuration
        # ---------------------------------------------------------------------

        print("[2/3] Loading Gemma 2 9B in 4-bit...")

        quantization_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.float16,
            bnb_4bit_use_double_quant=True,
        )

        # ---------------------------------------------------------------------
        # Base model
        # ---------------------------------------------------------------------

        self.model = AutoModelForCausalLM.from_pretrained(
            MODEL_ID,
            quantization_config=quantization_config,
            device_map="cuda:0",
            dtype=torch.float16,
            max_memory={
                0: "5.5GiB",
                "cpu": "24GiB",
            },
        )

        # ---------------------------------------------------------------------
        # LoRA
        # ---------------------------------------------------------------------

        print("[3/3] Loading Vertex LoRA...")

        self.model = PeftModel.from_pretrained(
            self.model,
            str(LORA_PATH),
            is_trainable=False,
        )

        self.model.eval()

        # ---------------------------------------------------------------------
        # Adapter verification
        # ---------------------------------------------------------------------

        active_adapters = self.model.active_adapters

        print()

        print("[OK] Gemma 2 9B loaded in 4-bit.")
        print("[OK] Vertex LoRA loaded.")
        print("[OK] Vertex Core is ready.")

        print()

        print(
            f"Active adapters: {active_adapters}"
        )

        if not active_adapters:

            raise RuntimeError(
                "LoRA was loaded but no active adapter was detected."
            )

        print()

        # ---------------------------------------------------------------------
        # VRAM report
        # ---------------------------------------------------------------------

        allocated = (
            torch.cuda.memory_allocated(0)
            / (1024 ** 3)
        )

        reserved = (
            torch.cuda.memory_reserved(0)
            / (1024 ** 3)
        )

        print(
            f"VRAM allocated: {allocated:.2f} GB"
        )

        print(
            f"VRAM reserved : {reserved:.2f} GB"
        )

        print()

    # -------------------------------------------------------------------------
    # GEMMA CHAT PREPARATION
    # -------------------------------------------------------------------------

    def _build_messages(
        self,
        messages: list[dict[str, str]],
    ) -> list[dict[str, str]]:

        system_parts: list[str] = []

        conversation: list[dict[str, str]] = []

        for message in messages:

            role = message.get(
                "role",
                "",
            )

            content = message.get(
                "content",
                "",
            )

            if not content:
                continue

            if role == "system":

                system_parts.append(
                    content.strip()
                )

            elif role == "user":

                conversation.append(
                    {
                        "role": "user",
                        "content": content,
                    }
                )

            elif role == "assistant":

                conversation.append(
                    {
                        "role": "assistant",
                        "content": content,
                    }
                )

            else:

                raise ValueError(
                    f"Unsupported message role: {role}"
                )

        # ---------------------------------------------------------------------
        # Gemma 2 template does not accept system role.
        # Merge system prompt into first user message.
        # ---------------------------------------------------------------------

        system_text = "\n\n".join(
            part
            for part in system_parts
            if part
        ).strip()

        if system_text:

            if (
                conversation
                and conversation[0]["role"] == "user"
            ):

                conversation[0]["content"] = (
                    system_text
                    + "\n\n"
                    + conversation[0]["content"]
                )

            else:

                conversation.insert(
                    0,
                    {
                        "role": "user",
                        "content": system_text,
                    },
                )

        return conversation

    # -------------------------------------------------------------------------
    # GENERATE
    # -------------------------------------------------------------------------

    def generate(
        self,
        messages: list[dict[str, str]],
    ) -> str:

        if self.model is None:

            raise RuntimeError(
                "Model is not loaded."
            )

        if self.tokenizer is None:

            raise RuntimeError(
                "Tokenizer is not loaded."
            )

        conversation = self._build_messages(
            messages
        )

        if not conversation:

            raise ValueError(
                "Conversation is empty."
            )

        # ---------------------------------------------------------------------
        # Chat template
        # ---------------------------------------------------------------------

        prompt = (
            self.tokenizer.apply_chat_template(
                conversation,
                tokenize=False,
                add_generation_prompt=True,
            )
        )

        # ---------------------------------------------------------------------
        # Tokenization
        # ---------------------------------------------------------------------

        inputs = self.tokenizer(
            prompt,
            return_tensors="pt",
            padding=False,
        )

        # ---------------------------------------------------------------------
        # Model device
        # ---------------------------------------------------------------------

        model_device = next(
            self.model.parameters()
        ).device

        inputs = {
            key: value.to(model_device)
            for key, value in inputs.items()
        }

        # ---------------------------------------------------------------------
        # Generation
        # ---------------------------------------------------------------------

        with torch.inference_mode():

            output = self.model.generate(
                **inputs,
                max_new_tokens=MAX_NEW_TOKENS,
                do_sample=True,
                temperature=TEMPERATURE,
                top_p=TOP_P,
                use_cache=True,
                pad_token_id=self.tokenizer.pad_token_id,
                eos_token_id=self.tokenizer.eos_token_id,
            )

        # ---------------------------------------------------------------------
        # Remove input tokens
        # ---------------------------------------------------------------------

        input_length = (
            inputs["input_ids"].shape[1]
        )

        generated_tokens = (
            output[0][input_length:]
        )

        # ---------------------------------------------------------------------
        # Decode
        # ---------------------------------------------------------------------

        response = self.tokenizer.decode(
            generated_tokens,
            skip_special_tokens=True,
        )

        return response.strip()


# =============================================================================
# AGENT
# =============================================================================

class VertexCoreAgent:

    def __init__(self) -> None:

        self.model = VertexCoreModel()

        self.messages: list[dict[str, str]] = [
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            }
        ]

    def start(self) -> None:

        self.model.load()

    def ask(
        self,
        user_message: str,
    ) -> str:

        user_message = user_message.strip()

        if not user_message:

            return ""

        self.messages.append(
            {
                "role": "user",
                "content": user_message,
            }
        )

        response = self.model.generate(
            self.messages
        )

        self.messages.append(
            {
                "role": "assistant",
                "content": response,
            }
        )

        return response


# =============================================================================
# CLI
# =============================================================================

def main() -> None:

    print()

    print("Starting Vertex Core...")

    print()

    try:

        agent = VertexCoreAgent()

        agent.start()

    except Exception as exc:

        print()

        print("=" * 72)
        print("VERTEX CORE STARTUP ERROR")
        print("=" * 72)

        print(
            f"{type(exc).__name__}: {exc}"
        )

        print()

        sys.exit(1)

    print("=" * 72)

    print("VERTEX CORE READY")

    print("Type 'exit' or 'quit' to stop.")

    print("=" * 72)

    print()

    while True:

        try:

            user_input = input(
                "You > "
            ).strip()

        except KeyboardInterrupt:

            print()

            print(
                "Vertex Core stopped."
            )

            break

        except EOFError:

            print()

            print(
                "Vertex Core stopped."
            )

            break

        if not user_input:

            continue

        if user_input.lower() in {
            "exit",
            "quit",
        }:

            print(
                "Vertex Core stopped."
            )

            break

        try:

            response = agent.ask(
                user_input
            )

            print()

            print("Vertex Core >")

            print(response)

            print()

        except KeyboardInterrupt:

            print()

            print(
                "Generation interrupted."
            )

            print()

        except Exception as exc:

            print()

            print("=" * 72)
            print("GENERATION ERROR")
            print("=" * 72)

            print(
                f"{type(exc).__name__}: {exc}"
            )

            print()


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":

    main()