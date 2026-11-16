---
status: accepted
date: 2026-11-16
decision-makers: [JerbilX, Antigravity]
supersedes: []
superseded-by: []
---

# 0002 - Directivas Basales de Disciplina de Herramientas y Contención de Lecturas

## Contexto y Planteamiento del Problema
Tras la adopción de la arquitectura *Clean-Slate* formalizada en [ADR-0001](0001-arquitectura-basal-minimalista-y-criterio-clean-slate.md), se desmantelaron los mecanismos punitivos coercitivos locales (`hooks.json`, interceptor `agent-guard` y disyuntores mecánicos de lectura).

Sin embargo, durante la auditoría de la sesión `9035a49f-8563-4c75-ad17-d03c32e2173a` mediante el CLI `agent-audit`, se constató que la ausencia de directivas equivalentes en el núcleo normativo basal provocó:
1. **Lecturas no paginadas recurrentes (15 violaciones):** Invocaciones de `view_file` sin acotar (`StartLine` y `EndLine`), generando consumo masivo innecesario de contexto y truncamientos en logs.
2. **Parálisis por inspección (4 bucles de solo lectura):** Ráfagas consecutivas de 4 a 8 lecturas pasivas continuas sin intercalar mutación ni validación en pruebas.
3. **Encadenamiento en terminal (1 violación):** Uso de operadores (`&&`, `||`, `;`) en `run_command`, rompiendo el *prefix matching* de permisos en sandbox y dificultando la trazabilidad.

Era necesario establecer límites operativos claros sin reintroducir la hipertrofia de meta-tooling punitivo descartada en ADR-0001.

## Impulsores de la Decisión (Decision Drivers)
* **Preservación del Clean-Slate (ADR-0001):** Prohibición de reintroducir interceptores policiales en cliente (`hooks.json` o scripts de 900 líneas en bash).
* **Eficiencia de Contexto:** Minimizar el desperdicio de tokens de inferencia mediante lectura quirúrgica y paginada.
* **Trazabilidad y Seguridad en Sandbox:** Garantizar comandos atómicos de terminal compatibles con el *prefix matching* de permisos.
* **Minimal Blast Radius (MBR):** Incorporar directivas concisas de alta densidad semántica directamente en `core/01-engineering.md`.

## Opciones Consideradas
* **Opción A (Reintroducción de Hooks Coercitivos Locales):** Restaurar interceptores `PreToolUse` en `hooks.json` que aborten mecánicamente llamadas sin paginar o con conectores shell.
  - *Descartada:* Trae de vuelta los falsos positivos, la fragilidad de parsing de bash y la sobrecarga de mantenimiento que motivaron el inicio de `Dotfiles-IA-V2`.
* **Opción B (Directivas Declarativas Basales en `core/` + Auditoría Periódica):** Incorporar directivas explícitas de contención de lecturas y atomicidad de terminal en `core/01-engineering.md`, compiladas en `AGENTS.md`, auditando el cumplimiento a posteriori con `agent-audit`.

## Decisión Adoptada
Opción elegida: **Opción B ("Directivas Declarativas Basales en core/ + Auditoría Periódica")**, porque establece los invariantes operativos de contención y atomicidad directamente en el contrato del agente, manteniendo el runtime ligero, sin fricción mecánica y alineado con los principios de ingeniería de Staff Systems Engineer.

### Consecuencias
* **Positivas:**
  - Se eliminan las lecturas masivas ciegas forzando paginado (`StartLine`/`EndLine`, máximo 150–200 líneas) y localización previa con `grep_search`.
  - Se previenen bucles de parálisis por análisis limitando las lecturas pasivas continuas a un máximo de 3 antes de formular hipótesis y ejecutar acciones observables.
  - Se preserva el *prefix matching* y la seguridad del sandbox mediante invocaciones atómicas en terminal.
  - Cero código de soporte o mantenimiento de hooks coercitivos en local.
* **Negativas / Trade-offs:**
  - El cumplimiento depende de la comprensión del LLM de su prompt basal y del monitoreo continuo mediante auditorías de sesión (`agent-audit`), en lugar de un bloqueo de error a nivel de runtime.
