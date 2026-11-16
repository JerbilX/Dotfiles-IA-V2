---
status: accepted
date: 2026-11-16
decision-makers: [JerbilX, Antigravity]
supersedes: []
superseded-by: []
---

# 0004 - Desacople de Compilación y Despliegue en build.sh y Aislamiento en Sandbox

## Contexto y Planteamiento del Problema
En el runtime de Google Antigravity y entornos con aislamiento de sandbox (`BypassSandbox: false`), el sistema de archivos externo al workspace activo (incluyendo `$HOME/.gemini/config/`) se monta como sistema de solo lectura (*Read-only file system* / `EROFS`) para blindar el host contra modificaciones no autorizadas.

Anteriormente, el orquestador [`build.sh`](file:///home/jerbilx/Proyectos-IA-V3/Dotfiles-IA-V2/build.sh) adoptaba por omisión el subcomando `link` (`case "${1:-link}" in`). Al ejecutarse `./build.sh` sin parámetros —conducta estándar de agentes de IA y pipelines de verificación en la fase de validación estática guiada por [`issue-driven-workflow`](file:///home/jerbilx/Proyectos-IA-V3/Dotfiles-IA-V2/skills/issue-driven-workflow/SKILL.md)—, el script intentaba crear enlaces simbólicos en `~/.gemini/config/AGENTS.md` y directorios de skills, provocando el fallo recurrente:
`ln: failed to create symbolic link '/home/jerbilx/.gemini/config/AGENTS.md': Read-only file system`.

## Impulsores de la Decisión (Decision Drivers)
* **Principio de Mínima Sorpresa:** Un script de compilación debe compilar artefactos por omisión, nunca desplegar ni alterar el entorno del host sin solicitud explícita.
* **Confinamiento Estricto de Workspace:** Las operaciones de verificación y compilación deben ejecutarse 100% confinadas al workspace activo (`dist/antigravity/`), sin dependencias de escritura en rutas externas.
* **Observabilidad y Cero Fallos Silenciosos:** Si un operador ejecuta deliberadamente `link` en un entorno de solo lectura, la herramienta debe fallar de forma rápida y explícita (`exit 1`) con diagnóstico descriptivo, evitando tanto errores crudos de utilidades del sistema como el antipatrón de silenciar el fallo con código de retorno cero.

## Opciones Consideradas
* **Opción A (Silenciamiento Condicional en `link`):** Mantener `link` por omisión y capturar el error de solo lectura ignorándolo o retornando `0` con una advertencia en consola.
  - *Descartada:* Viola el principio de observabilidad. Si un despliegue falla en el host, retornar código de salida cero falsea el éxito del proceso y oculta la ausencia de los enlaces requeridos.
* **Opción B (Desacople Estructural: Default `build` + Guardia Ruidosa en `link`):** Establecer `build` como subcomando por defecto de `build.sh`. Limitar la mutación de `$HOME/.gemini/config` a la invocación explícita de `link`, validando pre-condiciones de escritura y abortando con `exit 1` y diagnóstico claro ante entornos de solo lectura (sandbox).
  - *Aceptada:* Restaura la predictibilidad operativa, garantiza compatibilidad nativa con sandboxes y preserva la integridad del despliegue en el host.

## Decisión Adoptada
Opción elegida: **Opción B ("Desacople Estructural: Default build + Guardia Ruidosa en link")**.

Se actualiza:
1. [`build.sh`](file:///home/jerbilx/Proyectos-IA-V3/Dotfiles-IA-V2/build.sh):
   - Subcomando por defecto: `build` (`${1:-build}`).
   - Guardia determinista en `cmd_link`: verificación de permisos de escritura en `CONFIG_DIR` con fallo explícito (`exit 1`).
2. [`skills/issue-driven-workflow/SKILL.md`](file:///home/jerbilx/Proyectos-IA-V3/Dotfiles-IA-V2/skills/issue-driven-workflow/SKILL.md):
   - Especificación explícita de `./build.sh build` en la fase de verificación local.

### Consecuencias
* **Positivas:**
  - Invocaciones `./build.sh` y `./build.sh build` completamente idénticas, idempotentes y seguras en sandbox estándar sin fallos `EROFS`.
  - Diagnóstico claro para el operador si invoca `link` dentro de un sandbox aislado.
  - Alineación total con el estándar MADR y el principio de Minimal Blast Radius.
* **Negativas / Trade-offs:**
  - El usuario debe invocar explícitamente `./build.sh link` (en su terminal del host o con elevación) cuando desee refrescar los enlaces simbólicos de su entorno real.
