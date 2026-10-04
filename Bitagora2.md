Sí, brother. Y **esta bitácora sí vale oro**, porque no solo registra lo que hicimos: registra **qué estaba mal, por qué estaba mal, qué NO debemos repetir y qué validaciones debemos hacer antes de gastar horas de GPU**.

# Bitácora — Vertex Core V2

## Limpieza, dataset, entrenamiento y lecciones para el próximo modelo

**Proyecto:** Vertex Core
**Base:** `google/gemma-2-9b-it`
**Objetivo:** crear un agente de ingeniería de software que inspeccione, razone, use herramientas honestamente, escriba código cuando corresponde y no invente repositorios, archivos, cambios ni ejecuciones.

---

# 1. El problema original

El problema principal no era simplemente que el modelo "fuera malo".

Había un **problema de entrenamiento**.

El modelo había aprendido un patrón muy fuerte:

```text
software issue
      ↓
inventar/seleccionar un archivo
      ↓
generar un patch/diff
      ↓
afirmar una solución
```

El comportamiento observado era especialmente malo cuando no existía suficiente información.

Ejemplo conceptual:

```text
Usuario:
"Hay un problema de autenticación."

Modelo:
"Voy a modificar rich/console.py..."
```

El modelo incluso inventaba:

* archivos
* rutas
* código existente
* cambios
* ejecuciones
* resultados de pruebas

---

# 2. Descubrimos el error crítico del dataset original

El dataset original contenía campos como:

```text
instance_id
repo
base_commit
patch
test_patch
problem_statement
hints_text
created_at
```

Pero el primer conversor estaba buscando:

```python
description
```

cuando el campo correcto era:

```python
problem_statement
```

### Consecuencia

El prompt del usuario podía quedar vacío o incorrectamente construido mientras el `assistant` recibía el patch.

Eso enseñaba una asociación extremadamente peligrosa:

```text
problema → patch
```

en lugar de:

```text
problema → investigar → entender → modificar → verificar
```

### Corrección

Se creó:

```text
F:\vertex-gemma-agent\scripts\build_dataset.py
```

y se cambió para utilizar:

```python
problem_statement
```

además de validar los registros.

---

# 3. Dataset SWE corregido

Después de reconstruirlo:

```text
129 registros válidos
0 descartados
0 JSON inválidos
```

Distribución:

```text
fastapi/fastapi       67
Textualize/rich       48
psf/requests          13
encode/httpx           1
```

Los archivos más frecuentes incluían:

```text
fastapi/dependencies/utils.py
fastapi/routing.py
fastapi/_compat/v2.py
fastapi/openapi/utils.py
fastapi/applications.py
rich/console.py
...
```

Esto último es importante.

**`rich/console.py` aparecía realmente en el dataset**, por lo que podía convertirse en un fuerte ancla para el modelo.

Y eso ayuda a explicar por qué posteriormente aparecía tanto en respuestas inventadas.

---

# 4. Auditoría del dataset

Se creó una auditoría:

```text
F:\vertex-gemma-agent\scripts\audit_final_dataset.py
```

La auditoría terminó:

```text
JSON válido          : YES
Roles válidos        : YES
Contenido vacío      : 0
Mojibake detectado   : 0

[OK] FINAL DATASET PASSED
```

Esto es una regla para futuros modelos:

> **Nunca comenzar entrenamiento solamente porque el JSON abre correctamente.**

Hay que validar:

* estructura
* roles
* campos
* contenido
* caracteres
* longitudes
* distribución
* duplicados si corresponde
* ejemplos problemáticos
* coherencia entre prompt y respuesta

---

# 5. Creamos un dataset específico de comportamiento

Este fue uno de los pasos más importantes.

Se creó:

```text
F:\vertex-gemma-agent\scripts\build_behavior_dataset.py
```

Generó:

```text
F:\vertex-gemma-agent\data\processed\vertex_behavior.jsonl
```

Con:

```text
40 ejemplos
```

Categorías:

```text
diagnosis
direct_coding
inspect_first
no_hallucination
provided_code
requirements
tool_failure
tool_honesty
verification
```

Esto es lo que realmente necesitábamos para corregir el comportamiento.

El SWE dataset enseñaba:

> resolver issues.

El behavior dataset enseña:

> **cómo debe comportarse Vertex Core mientras resuelve issues.**

---

# 6. Auditoría del behavior dataset

Se creó:

```text
F:\vertex-gemma-agent\scripts\audit_behavior_dataset.py
```

Y posteriormente una auditoría de contenido:

```text
F:\vertex-gemma-agent\scripts\audit_behavior_content.py
```

Se revisaron los 40 ejemplos.

También corregimos varios problemas concretos.

### Ejemplo 06

Se corrigió a código Python válido:

```python
def safe_filename(name: str) -> str:
    return name.strip().replace("/", "_").replace("\\", "_")
```

### Ejemplo 13

Se corrigió la implementación PowerShell:

```powershell
function Parse-WindowsUsername {
    param([string]$Username)

    $characters = foreach ($character in $Username.ToCharArray()) {
        [char]$character
    }

    return -join $characters
}
```

### Ejemplo 20

Se corrigió a:

```python
def greet(name: str) -> str:
    return f"Hello {name}"
```

También corregimos problemas de Unicode/mojibake en el system prompt.

---

# 7. Algo MUY importante: los falsos positivos de la auditoría

La auditoría marcó seis ejemplos relacionados con:

```text
claims_execution
```

como posibles problemas.

Pero eran **intencionales**.

Esos ejemplos enseñaban precisamente la diferencia entre:

```text
"propongo ejecutar X"
```

y:

```text
"ejecuté X y obtuve Y"
```

Los ejemplos eran:

```text
08
14
15
27
34
40
```

No se eliminaron.

### Lección

Una auditoría automática no debe reemplazar la revisión semántica.

Puede decir:

```text
WARNING
```

sin significar:

```text
DATASET BAD
```

Hay que revisar qué está enseñando realmente el ejemplo.

---

# 8. Dataset final

Se creó:

```text
F:\vertex-gemma-agent\scripts\build_final_dataset.py
```

Combinando:

```text
SWE      = 129
Behavior = 40
----------------
TOTAL    = 169
```

Output:

```text
F:\vertex-gemma-agent\data\processed\sft_final_lora.jsonl
```

Validación:

```text
Main records     129
Behavior records  40
Final            169
```

---

# 9. Auditoría final

Se creó:

```text
F:\vertex-gemma-agent\scripts\audit_final_dataset.py
```

Resultado:

```text
REGISTROS: 169

Main/SWE       : 129
Behavior       : 40
Total          : 169
```

Y:

```text
JSON válido          : YES
Roles válidos        : YES
Contenido vacío      : 0
Mojibake detectado   : 0

[OK] FINAL DATASET PASSED
```

---

# 10. Problema importante que dejamos documentado

El patch máximo era enorme:

```text
308,489 caracteres
```

Promedio:

```text
6,740.5 caracteres
```

pero el entrenamiento usa:

```text
MAX_SEQ_LENGTH = 2048
```

Por tanto, los ejemplos que superan 2048 tokens son truncados.

Esto **no invalidó el dataset**, pero queda como deuda técnica para una futura versión.

Para el experimento actual decidimos **no cambiarlo**, porque queríamos comparar el comportamiento con una configuración controlada.

---

# 11. Evaluación antes del nuevo entrenamiento

Se utilizaron 12 tests.

Entre ellos:

```text
T01_CONTEXT
T02_NO_INVENTED_FILES
T03_INSPECT_FIRST
T04_WRITE_FUNCTION
T05_NO_FAKE_EXECUTION
T06_TOOL_FAILURE
T07_VERIFY
T08_REQUIREMENT_TRACKING
T09_AMBIGUOUS
T10_TEST_FAILURE
T11_NOVEL_BUG
T12_DOCKER
```

Y aquí encontramos el problema real.

El modelo fallaba especialmente en:

```text
T02
T03
T04
T05
T06
T07
T08
```

Mientras que:

```text
T10
T11
T12
```

eran relativamente mejores.

---

# 12. Qué NO debemos hacer con el próximo modelo

Esta es probablemente la sección más importante de toda la bitácora.

## Nunca hacer esto:

```text
problema
↓
buscar automáticamente un archivo conocido
↓
inventar código
↓
inventar diff
```

Especialmente:

```text
rich/console.py
```

porque ese archivo estaba sobrerrepresentado en el dataset y terminó funcionando como una especie de "respuesta por defecto".

---

# 13. Regla de oro de Vertex Core

El modelo debe distinguir:

### CONOCIDO

Información proporcionada por:

* usuario
* archivo inspeccionado
* herramienta
* comando ejecutado
* resultado real

### INFERIDO

Algo razonable pero que todavía no está confirmado.

### REQUERIDO

Información que falta para continuar.

### PROPUESTO

Una posible solución que todavía no ha sido ejecutada.

Nunca convertir:

```text
inferencia
```

en:

```text
hecho
```

---

# 14. System behavior que queremos

El ciclo oficial:

```text
INSPECT
   ↓
UNDERSTAND
   ↓
ACT IF NECESSARY
   ↓
VERIFY
   ↓
TEST
   ↓
CONCLUDE
```

Pero con una condición fundamental:

> **No todas las tareas requieren todas las fases.**

Por ejemplo:

### Si el usuario dice:

```text
Write this function:
def normalize_email(...)
```

No hay que responder:

```text
I need to inspect the repository first.
```

Hay que escribir la función.

---

### Si dice:

```text
The login is broken. Fix it.
```

sin código, repo, logs ni herramientas:

No inventar:

```text
auth.py
```

No inventar:

```text
database.py
```

No inventar:

```text
diff
```

Hay que identificar la información necesaria.

---

### Si existe repo pero todavía no fue inspeccionado:

```text
INSPECT FIRST
```

No parchear.

---

### Si una herramienta devuelve:

```text
ModuleNotFoundError:
No module named 'requests'
```

Eso demuestra:

```text
el proceso no pudo importar requests
```

Pero **no demuestra automáticamente cuál es la solución correcta**.

Hay que investigar:

```text
requirements
pyproject.toml
environment
dependency management
```

---

### Si tests dicen:

```text
47 passed
3 failed
```

No decir:

```text
Fixed successfully.
```

---

# 15. Primera versión de LoRA

La configuración utilizada anteriormente fue:

```text
Base:
google/gemma-2-9b-it

GPU:
RTX 6000 Ada 48 GB

dtype:
BF16

Dataset:
129 ejemplos

Epochs:
3

Batch:
2

Gradient accumulation:
4

Effective batch:
8

Learning rate:
1e-4

LoRA r:
16

LoRA alpha:
32

LoRA dropout:
0.05

Max sequence:
2048

Seed:
42
```

Adapter:

```text
/workspace/vertex_lora_final
```

**NO SOBRESCRIBIR.**

---

# 16. Vertex Core V2

Dataset nuevo:

```text
/workspace/sft_final_lora.jsonl
```

Total:

```text
169
```

Output:

```text
/workspace/vertex_lora_v2
```

La configuración se mantuvo deliberadamente igual:

```text
3 epochs
batch 2
gradient accumulation 4
LR 1e-4
LoRA r=16
alpha=32
dropout=.05
2048 tokens
seed 42
BF16
```

La idea es que la comparación sea:

```text
BASE
   vs
LoRA 129
   vs
LoRA V2 169
```

---

# 17. Problema #1 durante el entrenamiento V2

El primer intento murió antes de entrenar.

Error:

```text
TrainingArguments.__init__()
got an unexpected keyword argument 'warmup_ratio'
```

Causa:

La versión instalada de Transformers en RunPod no soportaba ese argumento.

Corrección:

```python
warmup_ratio=0.03
```

→

```python
warmup_steps=5
```

---

# 18. Problema #2 — batching

Después llegó:

```text
ValueError:
expected sequence of length 2048 at dim 1 (got 581)
```

La tokenización estaba usando:

```python
padding=False
```

y los ejemplos tenían longitudes distintas.

Además, habíamos creado manualmente:

```python
encoded["labels"] = encoded["input_ids"].copy()
```

El `Trainer` intentaba crear un batch con secuencias incompatibles.

---

# 19. La solución final que está entrenando ahora

La solución definitiva fue volver al enfoque simple:

```python
encoded = tokenizer(
    text,
    truncation=True,
    max_length=MAX_SEQ_LENGTH,
    padding="max_length",
)
```

Así:

```text
input_ids      = 2048
attention_mask = 2048
labels         = 2048
```

para cada ejemplo.

Y eliminamos:

```python
DataCollatorForLanguageModeling
```

El `Trainer` utiliza nuevamente su comportamiento normal.

Además añadimos una validación **antes de gastar GPU**:

```python
if input_length != MAX_SEQ_LENGTH:
    raise ValueError(...)
```

Esto es importantísimo para futuros entrenamientos.

---

# 20. Otro detalle corregido

Transformers avisaba:

```text
`torch_dtype` is deprecated!
Use `dtype` instead!
```

Cambiamos:

```python
torch_dtype=torch.bfloat16
```

por:

```python
dtype=torch.bfloat16
```

No era un error de entrenamiento, pero quedó limpio.

---

# 21. Estado actual

Ahora mismo el entrenamiento V2 está avanzando:

```text
23 / 66 steps
```

Eso significa que **esta vez ya superamos los problemas anteriores de carga, tokenización y batching**.

El entrenamiento realmente está ocurriendo.

Output esperado:

```text
/workspace/vertex_lora_v2
```

con:

```text
adapter
tokenizer
training_metrics.json
```

y checkpoints según `save_strategy="epoch"`.

---

# 22. Regla para futuros entrenamientos

Antes de lanzar otro modelo, debemos hacer este checklist:

```text
[ ] Dataset existe
[ ] JSON válido
[ ] Cantidad de registros correcta
[ ] Roles correctos
[ ] No hay contenido vacío
[ ] No hay mojibake
[ ] System/user/assistant coherentes
[ ] Dataset auditado semánticamente
[ ] Distribución revisada
[ ] Longitudes revisadas
[ ] Ejemplos extremadamente largos identificados
[ ] Chat template validado
[ ] Tokenización probada
[ ] Shapes de input_ids comprobadas
[ ] Shapes de attention_mask comprobadas
[ ] Shapes de labels comprobadas
[ ] Data collator compatible
[ ] TrainingArguments compatible con versión instalada
[ ] GPU/dtype comprobados
[ ] Output separado del adapter anterior
[ ] Smoke test del Trainer antes del entrenamiento completo
```

### Y una regla todavía más importante:

> **Nunca gastar horas de GPU antes de ejecutar un batch real de prueba.**

Idealmente, el próximo script debe hacer:

```text
load dataset
      ↓
tokenize
      ↓
validate shapes
      ↓
build Trainer
      ↓
fetch ONE batch
      ↓
forward pass
      ↓
verify loss
      ↓
ONLY THEN start full training
```

Eso nos habría detectado el segundo problema prácticamente gratis.

---

# 23. Lo que Gemini se saltó

Este es el aprendizaje más valioso.

No bastaba con:

```text
"el dataset tiene 169 registros"
```

Había que comprobar **qué estaba aprendiendo cada registro**.

No bastaba con:

```text
"JSON válido"
```

Había que comprobar:

```text
roles
contenido
mojibake
behavior
hallucination
execution claims
direct coding
verification
```

Y no bastaba con:

```text
"tokenized successfully"
```

Había que comprobar:

```text
¿qué longitud tienen realmente?
¿cómo se van a agrupar?
¿labels tiene la misma dimensión?
¿Trainer puede crear el batch?
```

**Esa es la diferencia entre "el script corre" y preparar un entrenamiento serio.**

---

# 24. El objetivo final de esta V2

No estamos intentando simplemente bajar el `loss`.

Queremos comprobar si el modelo cambia estos comportamientos:

### Antes

```text
Issue
 ↓
rich/console.py
 ↓
invented diff
```

### Queremos

```text
Issue
 ↓
¿Qué evidencia tengo?
 ↓
¿Tengo acceso al repo?
 ↓
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
```

Y cuando la información no existe:

```text
NO INVENTAR
```

Ese es el verdadero benchmark de Vertex Core V2.

---

## Archivo maestro que debemos conservar

Esta bitácora debería quedar guardada dentro del proyecto como:

```text
F:\vertex-gemma-agent\TRAINING_LOG.md
```

Y para cada futuro modelo agregar:

```text
V1
V2
V3
...
```

con:

```text
dataset
dataset audit
behavior audit
training config
transformers version
torch version
GPU
token length
training loss
evaluation results
known failures
changes from previous version
```

**Y ahora no tocamos absolutamente nada mientras ese `23/66` siga avanzando.** Ese entrenamiento finalmente está corriendo.
