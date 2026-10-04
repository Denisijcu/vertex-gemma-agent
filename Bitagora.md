# Bitácora de Operaciones - Vertex Coders (Kaggle AI Agent Challenge)

## 1. Introducción y Origen del Proyecto
Todo comenzó al recibir la notificación oficial por correo electrónico sobre el lanzamiento de la nueva competencia de agentes autónomos de inteligencia artificial en **Kaggle**. Dicha competencia plantea un reto monumental: desarrollar un agente de ingeniería de software capaz de resolver *issues* complejos en repositorios reales de código de manera autónoma, aplicando parches funcionales (*git diff*) verificados por pruebas automatizadas.

Para abordar este desafío con rigor industrial, en **Vertex Coders LLC** diseñamos una arquitectura orientada a la eficiencia, la seguridad ofensiva/defensiva (mitigaciones OWASP LLM Top 10) y la ejecución híbrida local-nube.

---

## 2. El Plan Táctico (Roadmap)
Para garantizar el éxito de la misión, estructuramos un plan de desarrollo en cuatro fases bien definidas:
- **Fase 1: Infraestructura Base:** Topología multi-agente, despliegue del FastAPI Gateway de simulación local, aislamiento mediante contenedores Docker y conexión del orquestador con un modelo local para validación rápida.
- **Fase 2: Pipeline de Datos:** Ingesta e indexación vectorial de 20 GB de datasets de Kaggle (vectores `.npz`, grafos AST e índices en ChromaDB) y transformación de tareas a formato SFT (*Prompt -> Git Diff*).
- **Fase 3: Post-Training (Nube):** Alquiler de potencia en Runpod (A100 / RTX 6000 Ada) para el entrenamiento de adaptadores LoRA especializados (`tool_lora` para tool calling y `main_lora` para razonamiento y parches).
- **Fase 4: Evaluación y Entrega:** Ejecución del harness local, empaquetado de la solución y envíos diarios a la plataforma de Kaggle.

---

## 3. Estrategia de Desarrollo: Del Modelo Pequeño al Modelo de Producción
Para acelerar el ciclo de desarrollo y evitar bucles de prueba costosos en la nube, adoptamos una estrategia iterativa:
1. **Validación con Modelo Pequeño (Gemma 4B local vía LM Studio):** Utilizamos un modelo ligero ejecutándose localmente en la HP Omen para "conectar los cables", depurar la comunicación del orquestador, validar los tiempos de respuesta del Gateway y perfeccionar los bucles de razonamiento del agente autónomo en tareas controladas (como el parcheo de vulnerabilidades en `auth.py`).
2. **Escalamiento al Modelo Grande:** Una vez validada y pulida toda la fontanería del sistema, el pipeline está listo para transferirse al modelo principal y entrenarse con los datasets masivos procesados.

---

## 4. Obstáculos Encontrados y Soluciones Aplicadas

### Obstáculo 1: El bucle infinito del comando `git status`
- **Problema:** El agente estaba condicionado por su entrenamiento clásico a ejecutar `git status` al iniciar, pero el directorio de trabajo inicial no era un repositorio git válido, provocando un error de parada (`Exit Code 128`) y agotando los turnos.
- **Solución:** Inicializar un repositorio base (`git init`) en la carpeta de snapshots para satisfacer la expectativa del modelo y permitirle avanzar al análisis de código.

### Obstáculo 2: Alucinaciones de resolución y ausencia de tests
- **Problema:** El modelo pequeño detectaba la vulnerabilidad de inyección SQL en `auth.py`, pero en ocasiones alucinaba afirmando que ya estaba resuelta o se estancaba buscando directorios de pruebas (`pytest`) inexistentes.
- **Solución:** Ajuste estricto del *System Prompt* y las reglas operativas, prohibiendo la exploración conversacional inútil y obligando a la ejecución directa de scripts de remediación deterministas.

### Obstáculo 3: Errores HTTP 422 del Gateway por payloads gigantes
- **Problema:** Intentar enviar bloques masivos de código Python multilínea o heredocs a través de las peticiones JSON del FastAPI Gateway rompía la validación de sintaxis, lanzando errores de tipo `Unprocessable Content (422)`.
- **Solución:** Arquitectura de parcheo mediante scripts externos (`patch.py`) ejecutados con un comando de una sola línea (`python3 patch.py`), reduciendo el payload al mínimo y eliminando los errores de escape de comillas.

### Obstáculo 4: Incompatibilidad de Pydantic v1 con Python 3.14
- **Problema:** Al intentar poblar la base vectorial con los datasets de Kaggle, la versión fija de ChromaDB (`0.4.24`) dependía de Pydantic v1, la cual lanza un `ConfigError` crítico al no poder inferir tipos bajo las restricciones internas de la versión de Python 3.14.
- **Solución:** Actualización controlada de la suite ChromaDB a versiones modernas totalmente compatibles con los runtimes actuales en el entorno de Windows, restableciendo de inmediato la estabilidad del pipeline de datos.

---


Vamos a actualizar la bitácora técnica con el registro de incidencias, el análisis de impacto y las soluciones definitivas que acabamos de aplicar en este despliegue en la nube:

---

### ## Bitácora de Ingeniería: Despliegue de SFT LoRA en Runpod (Gemma-2-9b-it)

#### 1. Resumen de Ejecución y Entorno

* **Infraestructura:** Runpod con GPU NVIDIA RTX 6000 Ada (48 GB VRAM).
* **Stack Tecnológico:** PyTorch 2.8.0, Transformers, TRL, PEFT.
* **Modelo Base:** `google/gemma-2-9b-it` (precision `bfloat16`).
* **Dataset:** `sft_main_lora.jsonl` (129 ejemplos procesados).

---

#### 2. Registro de Incidencias, Errores y Mitigaciones

| Incidencia / Error Detectado | Causa Raíz | Solución Definitiva Aplicada |
| --- | --- | --- |
| **Conflicto de importación en PyTorch / TorchAO**<br>

<br>`ImportError: cannot import name 'ScalingType'` | El paquete preinstalado `torchao` en el contenedor intentaba importar funciones de módulos internos de PyTorch no soportadas por la versión 2.8.0. | Desinstalación inmediata del paquete sobrante en el entorno:<br>

<br>`pip uninstall -y torchao` |
| **Error de Repositorio Restringido (401 / 403 Forbidden)**<br>

<br>`GatedRepoError` | El modelo base de Google requiere autenticación mediante token de Hugging Face y **aceptación previa de los términos y condiciones** de la licencia en la web. | 1. Autenticación por CLI (`hf auth login`).<br>

<br>2. Aceptación explícita de la licencia del modelo en la interfaz web de Hugging Face. |
| **Incompatibilidad de Argumentos en TRL**<br>

<br>`TypeError: SFTTrainer.__init__() got an unexpected keyword argument 'max_seq_length'` | Las versiones recientes de la librería `trl` migraron los parámetros de longitud de secuencia fuera del constructor clásico del *trainer*. | Migración a la clase unificada **`SFTConfig`** importada desde `trl`, agrupando los argumentos de entrenamiento junto con `max_seq_length=2048`. |

---

#### 3. Lecciones Aprendidas para el Núcleo (Vertex Intelligence Core)

* **Gestión de Entornos Remotos:** Evitar depender de configuraciones heredadas en contenedores preconstruidos de PyTorch; siempre validar dependencias experimentales de cuantización o optimización (`torchao`, `flash-attn`) antes de lanzar corridas masivas.
* **Eficiencia de Costes y Recursos:** La transición de hardware local limitado (6 GB VRAM) a servidores cloud con GPUs de gama alta (RTX 6000 Ada con 48 GB) reduce el tiempo de entrenamiento drásticamente de 30 horas a minutos, optimizando la rentabilidad y el ciclo de iteración del equipo de desarrollo.

---



*Documento redactado para la posteridad y guía técnica del equipo de ingeniería de Vertex Coders LLC.*