# Vertex Gemma 4 Developer Agent 

Plataforma de orquestación y post-entrenamiento para la competencia "Gemma 4 Developer Agent" de Google DeepMind. Desarrollado bajo la arquitectura de **Vertex Intelligence Core (VIC)**.

## Arquitectura
Este repositorio implementa un patrón de **Orquestador-Ejecutor** utilizando el Google ADK. Aisla el razonamiento complejo del uso de herramientas mediante múltiples adaptadores LoRA, mitigando vulnerabilidades OWASP LLM (LLM01, LLM08).

*   **Orquestador (`main_lora`)**: Razonamiento puro. Único con permisos para `submit_patch`.
*   **Sub-agentes (`tool_lora`)**: Exploración de grafos (RAG) y mutación segura del sistema de archivos.

## Entorno Local de Simulación
Requiere Docker y un modelo local (ej. Vertex Core Qwen o Gemma 12B) corriendo en LM Studio.
1. Compilar el sandbox: `cd local_env/sandbox && ./run_sandbox.sh`
2. Levantar FastAPI Gateway: `cd local_env/gateway && uvicorn main:app --reload`
3. Ejecutar agente local: `python local_env/orchestrator/local_agent_runner.py`