# Roadmap Táctico - Kaggle Gemma 4

## Fase 1: Infraestructura Base (Completada/En progreso)
- [x] Diseñar topología multi-agente ADK (`agent.yaml`, `sub_agents`).
- [x] Definir mitigaciones OWASP en prompts (`system.md`, `explorer.md`).
- [x] Codificar FastAPI Gateway para simulación local.
- [X] Construir y testear el Sandbox Docker (`Dockerfile.kaggle-workspace`).
- [x] Conectar Vertex Core (LM Studio) al Gateway local.

## Fase 2: Pipeline de Datos
- [x] Descargar dataset oficial (`tasks.jsonl`, `embeddings/`, `graphs/`).
- [x] Adaptar `scripts/load_chroma.py` para leer los `.npz` de Kaggle.
- [x] Ejecutar `scripts/build_dataset.py` para formatear el SFT (Prompt -> Git Diff).

## Fase 3: Post-Training (Nube)
- [x] Alquilar Pod en Runpod (A100 o RTX 6000 Ada).
- [x] Subir dataset procesado.
- [X] Entrenar `tool_lora` (foco en JSON sintáctico y tool calling).
- [X] Entrenar `main_lora` (foco en razonamiento y parches unificados).
- [ ] Descargar `.safetensors` a `submission/adapters/`.

## Fase 4: Evaluación y Entrega
- [ ] Correr evaluación local con el script oficial del harness.
- [ ] Ejecutar `scripts/package_submission.py`.
- [ ] Subir entrega a Kaggle (Límite: 1 entrega diaria).