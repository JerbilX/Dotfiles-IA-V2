---
name: adr-manager
description: >-
  Manage, record, and consult Architecture Decision Records (ADRs) using the MADR (Markdown Architectural Decision Records) standard compatible with adr-tools. ACTIVATE this skill whenever proposing architectural changes, introducing or changing dependencies/libraries, modifying persistence engines or data schemas, refactoring core modules, evaluating technical tradeoffs, or documenting technical decisions. Operates 100% natively without external CLI dependencies.
---

# Architecture Decision Records (ADR) Manager

Guía operativa y protocolo estricto para la consulta, detección de conflictos, redacción y ciclo de vida de Registros de Decisiones de Arquitectura (ADR) basados en el estándar **MADR (Markdown Architectural Decision Records)** y compatibles con la nomenclatura y estructura de **adr-tools**, operando de forma 100% nativa mediante herramientas de archivos del agente.

---

## 1. Principios Fundamentales y Compatibilidad

1. **Estándar MADR + adr-tools:** Estructura basada en Markdown con YAML frontmatter legible por máquina y estructurado para humanos. Compatible en nomenclatura con `adr-tools` (`docs/adr/NNNN-titulo-en-kebab-case.md`). Prohibido `HISTORIAL.md` o bitácoras informales; las decisiones arquitectónicas se registran exclusivamente en `docs/adr/` (`proposed` -> `accepted`).
2. **Directivas de Agente:** Directivas de agente solo como `AGENTS.md` compilado; prohibido `GEMINI.md` (bloqueado mecánicamente por guard P0).
3. **Operación 100% Nativa (Zero-CLI):** Queda **terminantemente prohibido** invocar herramientas de línea de comandos externas (como `adr-init`, `adr-new`, binarios de `adr-tools` o scripts bash equivalentes). Todas las operaciones de lectura, cálculo correlativo y escritura deben ejecutarse mediante las herramientas nativas de archivos del agente (listado de directorios, lectura, escritura y edición atómica de archivos).
4. **Inmutabilidad Histórica:** Una decisión registrada refleja el contexto y los trade-offs en el momento en que se tomó. Los ADRs históricos nunca se borran ni se reescriben en su cuerpo explicativo. Las modificaciones posteriores se gestionan mediante nuevos ADRs que reemplazan (supersede) a los anteriores.
5. **Gate Humano de Aprobación:** El agente puede proponer decisiones, pero la aceptación definitiva de una decisión arquitectónica es prerrogativa exclusiva del usuario.

---

## 2. Protocolo Obligatorio para Agentes (Flujo de Trabajo)

Cualquier agente que trabaje en un proyecto de software debe aplicar rigurosamente las siguientes fases:

```
[Pre-flight Check] --> ¿docs/adr/ existe?
        │
        ├── No ──> ¿Existe HISTORIAL.md legacy? ──> [Gate de Eliminación] Consultar usuario antes de borrar.
        │
        └── Sí ──> Inspeccionar YAML frontmatters (status: accepted / rejected)
                     │
                     ├── ¿Conflicto detectado con decisión accepted?
                     │     └── [Stop & Warn] Detenerse y advertir al usuario antes de codificar.
                     │
                     └── ¿Se requiere nueva decisión arquitectónica?
                           └── [Creación Nativa] Crear NNNN-*.md con status: proposed en In Planning
                                 │
                                 ├── [Aprobación de Plan] Transición a status: accepted al pasar a In Progress
                                 │
                                 └── [Gate Humano: Merge de PR] ──> Integración atómica en main como accepted
```

---

### Fase 1: Consulta Previa (Pre-flight Check)

Antes de:
- Proponer cambios arquitectónicos estructurales.
- Introducir o sustituir librerías, frameworks o dependencias principales.
- Modificar motores de persistencia, almacenamiento o esquemas de bases de datos.
- Refactorizar módulos centrales o contratos de interfaces críticas.

El agente **DEBE verificar proactivamente** si existe el directorio `docs/adr/` en la raíz del workspace activo:

1. Listar los archivos en `docs/adr/` mediante herramientas nativas de listado o búsqueda de archivos.
2. Si existen ADRs, inspeccionar su YAML frontmatter (particularmente el campo `status`):
   - **`status: accepted`**: Representa lineamientos arquitectónicos vigentes y de cumplimiento obligatorio.
   - **`status: rejected`**: Identifica enfoques y alternativas previamente evaluadas y descartadas. El agente no debe volver a proponer soluciones idénticas sin justificar qué condiciones cambiaron.
   - **`status: superseded by ADR-NNNN`**: La decisión ya no rige; debe consultarse el ADR sucesor indicado.

#### Detección y Retiro Controlado de `HISTORIAL.md` (Legacy Gate)
Si durante la inspección del workspace el agente detecta un archivo `HISTORIAL.md` en la raíz:
- **Prohibición de Borrado Silencioso:** Queda estrictamente prohibido eliminar `HISTORIAL.md` de manera autónoma sin avisar. Podría tratarse de un changelog legítimo o notas manuales del usuario.
- **Aviso y Gate de Confirmación:** El agente debe consultar explícitamente al usuario:
  > *"He detectado `HISTORIAL.md` en la raíz del proyecto, correspondiente al formato legacy de historial. Para evitar duplicidad e inconsistencias con el estándar MADR (`docs/adr/`), ¿deseas que lo elimine del repositorio?"*
- **Ejecución Post-Aprobación:** Solo tras la confirmación afirmativa del usuario, el agente procederá a removerlo del árbol de trabajo (`git rm HISTORIAL.md` o remoción del archivo).

---

### Fase 2: Detección de Conflictos (Stop & Warn)

Si una directiva del usuario, requerimiento funcional o cambio técnico planificado **entra en conflicto directo** con un ADR existente con `status: accepted`:

1. **Freno Inmediato:** El agente **NO DEBE escribir código** ni aplicar parches que vulneren la decisión aceptada.
2. **Advertencia Explícita:** Detener la ejecución y notificar el conflicto citando puntualmente el registro relevante (ej. `ADR-0003` / `docs/adr/0003-uso-de-sqlite.md`):
   > *"He detectado un conflicto con la decisión arquitectónica vigente en ADR-0003 ('Uso de SQLite como motor de persistencia local'). El cambio solicitado introduce PostgreSQL, lo cual contradice la restricción acordada. ¿Deseas mantener ADR-0003 y adaptar la solución, o abrimos un nuevo ADR (ej. ADR-0007) para revocar y sustituir formalmente la decisión anterior?"*
3. **Punto de Sincronización:** Aguardar la respuesta del usuario antes de proceder.

---

### Fase 3: Creación Compatible con `adr-tools` (I/O Nativo)

Cuando se acuerde entre el usuario y el agente documentar una nueva decisión:

1. **Verificación / Creación del Directorio:**
   - Si `docs/adr/` no existe, se creará automáticamente al escribir el primer archivo mediante herramientas nativas de archivos.
2. **Cálculo Determinista del Correlativo:**
   - Inspeccionar los archivos existentes en `docs/adr/` con las herramientas nativas de listado.
   - Extraer el prefijo numérico de mayor valor (ej. si existen `0001-...` y `0002-...`, el siguiente es `3`).
   - Formatear el nuevo correlativo con 4 dígitos rellenos con ceros a la izquierda (`0001`, `0002`, `0003`, ..., `0010`, etc.). Si la carpeta está vacía, comenzar en `0001`.
3. **Nomenclatura Canónica:**
   - Formato exacto: `docs/adr/NNNN-titulo-en-kebab-case.md`
   - Reglas de título: Minúsculas, palabras separadas por guión medio (`-`), sin tildes, caracteres especiales ni espacios (ej. `0004-adopcion-de-pydantic-v2.md`).
4. **Escritura Nativa:**
   - Cargar el contenido de la plantilla base ubicada en este skill (`resources/template.md`).
   - Rellenar los campos y escribir el archivo en destino utilizando las herramientas nativas de escritura de archivos.
   - **PROHIBIDO** invocar scripts CLI externos (`adr-new`, etc.).

---

### Fase 4: Gate de Aprobación Humana y Ciclo de Vida Atómico

1. **Estado Inicial Obligatorio (Borrador / Propuesta):**
   - Todo nuevo ADR redactado por el agente nace estrictamente con `status: proposed` durante la etapa de ideación, borrador o discusión previa a la aprobación del plan (`implementation_plan.md` o chat) en la fase `📐 In Planning`.
2. **Transición a Accepted en Desarrollo (`⚙️ In Progress`):**
   - La aprobación humana explícita del plan de implementación (`RequestFeedback` afirmativo o fast-path ejecutivo) constituye la ratificación humana de la decisión arquitectónica.
   - Al pasar a `⚙️ In Progress`, el YAML frontmatter del ADR se actualiza a `status: accepted` dentro de la rama de trabajo.
   - Todo nuevo ADR viaja en el Pull Request con `status: accepted`, de modo que al fusionarse en la rama principal (`main`), entra de forma atómica y ratificada sin requerir ediciones posteriores sobre `main`.
3. **Resiliencia ante Regresiones del Tablero:**
   - Si la tarea experimenta un retroceso en el ciclo de vida (ej. replanteo de arquitectura `In Review` -> `In Planning` o bloqueo técnico `In Progress` -> `In Planning`):
     - El ADR regresa a `status: proposed` mientras se redefine el nuevo diseño.
     - Si la propuesta técnica es descartada o rechazada definitivamente, transiciona a `status: rejected` documentando los motivos en el cuerpo del ADR.
     - Si la rama efímera se descarta o el PR se cierra sin merge, Git garantiza que la decisión nunca entra a `main`.
4. **ADRs Desacoplados de Código (Propuestas Puras / RFCs):**
   - Si un ADR se formula de manera puramente exploratoria o como propuesta arquitectónica aislada sin código, se gestiona mediante su propio PR como propuesta (`status: proposed`). Si es aceptado por el usuario, se actualiza a `status: accepted` antes del merge o se fusiona como tal.

---

### Fase 5: Reemplazo e Inmutabilidad (Superseding)

Cuando una nueva decisión técnica modifica, anula o sustituye una decisión previa:

1. **Inmutabilidad del Cuerpo:** Nunca eliminar ni modificar el contexto, opciones o consecuencias del ADR previo. La historia permanece intacta.
2. **Vinculación en el Nuevo ADR (`ADR-NNNN`):**
   - Declarar en el frontmatter del nuevo documento el archivo sustituido:
     ```yaml
     supersedes: ["0002-uso-de-persistencia-en-memoria.md"]
     ```
3. **Actualización Atómica del ADR Reemplazado:**
   - Modificar **exclusivamente el YAML frontmatter** del ADR antiguo mediante herramientas nativas de edición:
     ```yaml
     status: superseded by ADR-0005
     superseded-by: ["0005-migracion-a-sqlite.md"]
     ```
   - No alterar el resto de las secciones históricas del archivo sustituido.

---

### Fase 6: Trazabilidad en Código

Una decisión aceptada debe reflejarse en los puntos neurálgicos del código fuente para que futuros desarrolladores y agentes comprendan el fundamento técnico de la implementación:

1. **Comentarios de Referencia:**
   - Al implementar código derivado de un ADR con `status: accepted`, agregar un comentario breve en el archivo principal, módulo de inicialización o archivo de configuración relevante:
     - En Python / Shell / YAML: `# Ref: docs/adr/0003-uso-de-sqlite.md`
     - En JavaScript / TypeScript / C / Go / Java: `// Ref: docs/adr/0003-uso-de-sqlite.md`
     - En Lua: `-- Ref: docs/adr/0003-uso-de-sqlite.md`
2. **Precisión de Enlace:** Vincular siempre la ruta relativa exacta al documento dentro del repositorio.

---

## 3. Especificación del YAML Frontmatter (MADR)

Cada ADR debe comenzar con el bloque YAML delimitado por `---`:

```yaml
---
status: proposed | accepted | rejected | superseded by ADR-NNNN | deprecated
date: YYYY-MM-DD
decision-makers: [Usuario, Agente]
supersedes: []
superseded-by: []
---
```

### Definición de Estados (`status`)

| Estado | Significado y Política de Agente |
| :--- | :--- |
| `proposed` | Decisión formulada por el agente o usuario. En evaluación. No autoriza cambios arquitectónicos de producción hasta su aprobación. |
| `accepted` | Decisión aprobada explícitamente por el usuario. De cumplimiento obligatorio en todo desarrollo posterior. |
| `rejected` | Propuesta descartada. Documenta por qué no se adoptó para evitar reincidir en discusiones ya resueltas. |
| `superseded by ADR-NNNN` | Decisión revocada y sustituida por un ADR posterior. Conserva valor histórico pero no rige implementaciones actuales. |
| `deprecated` | Decisión que ya no aplica debido a cambios de entorno, eliminación de funcionalidades o desuso, sin sustituto directo. |

---

## 4. Recursos Disponibles

- **Plantilla Oficial:** `resources/template.md` (ubicada dentro del directorio de este skill). Utilizar su estructura como base para la redacción de todo nuevo ADR.
