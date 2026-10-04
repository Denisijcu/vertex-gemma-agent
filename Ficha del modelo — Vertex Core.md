
## Ficha del modelo — Vertex Core

### Nombre recomendado

**Vertex Core — AI Software Engineering Agent**

### Model card

````markdown
---
language:
- en
- es
license: apache-2.0
base_model:
- google/gemma-2-9b-it
tags:
- vertex-coders
- code
- code-generation
- code-editing
- software-engineering
- ai-agent
- autonomous-agent
- cybersecurity
- qlora
- lora
- gemma
pipeline_tag: text-generation
library_name: transformers
---

# Vertex Core

**Vertex Core** is a specialized AI software-engineering model developed by **Vertex Coders**.

It is based on Google's **Gemma 2 9B IT** and fine-tuned using **LoRA/QLoRA** techniques to improve its behavior for software-engineering workflows, code generation, code modification, debugging, security analysis, and tool-oriented development tasks.

Vertex Core is designed to serve as the reasoning and coding core of the Vertex Coders AI agent ecosystem.

## Model Overview

| Property | Value |
|---|---|
| Model | Vertex Core |
| Base model | `google/gemma-2-9b-it` |
| Architecture | Gemma 2 9B |
| Fine-tuning | LoRA / QLoRA |
| LoRA rank | 16 |
| LoRA alpha | 32 |
| LoRA dropout | 0.05 |
| Target modules | q_proj, k_proj, v_proj, o_proj, up_proj, down_proj, gate_proj |
| Primary use | Software engineering agents |
| Secondary use | Cybersecurity and code analysis |
| Languages | English, Spanish |
| Developer | Vertex Coders LLC |

## Intended Use

Vertex Core is intended for applications involving:

- Software engineering assistance
- Code generation
- Code modification
- Debugging
- Repository analysis
- Security-oriented code analysis
- Vulnerability remediation
- Automated development workflows
- Tool-using AI agents
- Local/private AI development environments
- Code review and verification

The model is particularly intended to operate as part of an agentic system where the model can inspect files, execute tools, modify code, and verify the resulting state.

## Vertex Core Agent Architecture

Vertex Core is designed to operate inside an agent loop such as:

```text
INSPECT
   ↓
UNDERSTAND
   ↓
ACT
   ↓
VERIFY
   ↓
TEST
   ↓
CONCLUDE
````

The model itself does not automatically have access to a filesystem, shell, network, or external tools. Those capabilities must be provided by the surrounding application.

## Fine-Tuning

Vertex Core was fine-tuned using parameter-efficient fine-tuning techniques.

The adapter uses:

```text
LoRA rank:       16
LoRA alpha:      32
LoRA dropout:    0.05
```

Targeted projection modules:

```text
q_proj
k_proj
v_proj
o_proj
up_proj
down_proj
gate_proj
```

The resulting adapter contains approximately:

```text
54 million trainable LoRA parameters
```

## Available Formats

The project can be distributed in multiple formats.

### LoRA Adapter

The LoRA adapter can be loaded on top of the original base model:

```python
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel

base_model = AutoModelForCausalLM.from_pretrained(
    "google/gemma-2-9b-it"
)

model = PeftModel.from_pretrained(
    base_model,
    "PATH_TO_VERTEX_CORE_LORA"
)
```

### Merged Model

A merged version can be used when a standalone Transformers model is preferred.

### GGUF

Quantized GGUF versions are intended for local inference applications such as LM Studio and other llama.cpp-compatible runtimes.

## Local Deployment

Vertex Core has been tested in a local development environment using LM Studio.

Example API endpoint:

```text
http://127.0.0.1:1234/v1/chat/completions
```

A compatible OpenAI-style client can therefore be used for local inference.

## Hardware

The model has been tested in a local environment with:

* NVIDIA GTX 1660 Ti
* 6 GB VRAM
* CUDA-enabled PyTorch environment
* LM Studio

Quantized GGUF variants are recommended for hardware with limited VRAM.

## Safety and Security

Vertex Core is intended to assist with defensive software engineering and cybersecurity tasks.

Security capabilities should be used only on systems and code that the user is authorized to analyze or modify.

The model should not be treated as a replacement for professional security testing, code review, or operational security controls.

## Limitations

Vertex Core is a fine-tuned language model and can produce incorrect or incomplete outputs.

In particular:

* Generated code must be tested before deployment.
* Tool execution results must be independently verified.
* The model can hallucinate files, APIs, commands, or implementation details.
* A successful shell command does not necessarily mean that the requested change was successfully performed.
* Autonomous agent implementations should verify filesystem state after modifications.
* Security findings should be independently validated.

The model should therefore be deployed with an execution layer that verifies tool results rather than blindly trusting model output.

## Recommended Agent Pattern

For autonomous software-engineering applications, use an execution loop similar to:

```text
User Issue
    ↓
Inspect Repository
    ↓
Read Relevant Files
    ↓
Understand Problem
    ↓
Modify Code
    ↓
Read Modified Code
    ↓
Run Tests
    ↓
Verify Result
    ↓
Report Outcome
```

## Example

A software-engineering agent can provide Vertex Core with a repository workspace and tools such as:

```text
read_file
write_file
replace_in_file
list_directory
run_command
run_tests
security_scan
```

The orchestration layer should verify the result of every modification.

## Training Philosophy

Vertex Core is designed around the principle that an engineering agent should not merely describe a solution.

It should:

```text
Inspect → Understand → Act → Verify → Test
```

This distinction is important when integrating the model into autonomous development systems.

## Acknowledgements

Vertex Core is based on:

**Google Gemma 2 9B IT**

The original base model remains subject to its respective license and terms of use.

## Developer

**Vertex Coders LLC**

Vertex Core is part of the Vertex Coders AI engineering ecosystem.

---

# Citation

If you use Vertex Core in research, demonstrations, or derivative projects, please reference:

**Vertex Coders — Vertex Core**

A formal citation will be added in a future release.

## Status

**Experimental / Research Release**

Vertex Core is under active development.

```

### Important, brother

Hay una cosa que **no pondría todavía** en la ficha pública:

> “autonomous agent capable of reliably modifying real repositories”

Porque nuestras pruebas de hoy demostraron que **todavía no podemos afirmar eso**. El modelo tiene capacidad de edición, pero tiene ese problema específico con ciertos patrones de `auth.py`.

Eso no es malo para una primera publicación; de hecho, es más profesional declarar:

**Experimental / Research Release**.

Y yo subiría **primero el LoRA**, no solamente el GGUF. Así quien lo pruebe puede reproducir exactamente el fine-tuning sobre `google/gemma-2-9b-it`.

Si quieres, en la próxima sección podemos :contentReference[oaicite:0]{index=0}: `README.md`, `adapter_config.json`, metadata, licencia y la estructura del repositorio.
```
