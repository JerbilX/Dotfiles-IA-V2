---
status: accepted
date: 2026-11-16
decision-makers: [JerbilX, Antigravity]
supersedes: [0006]
superseded-by: []
---

# 0008 - Veto Universal a Cuerpos en Línea en GitHub CLI y Uso Mandatorio de `--body-file`

## Contexto y Planteamiento del Problema
En el [ADR 0006](0006-delimitacion-gate-humano-y-estabilidad-permisos-sandbox.md) se formalizó el uso de `--body-file` para evitar la degradación de permisos en el sandbox de Google Antigravity. Sin embargo, la directiva se redactó con alcance restringido a dos subcomandos específicos (`gh issue create` y `gh pr create`) y mencionando únicamente `--body "..."`.

Esta formulación puntual generó una brecha operativa:
1. **Fuga Normativa en Subcomandos Adicionales:** Agentes operando en repositorios del ecosistema ejecutaron comandos como `gh issue comment <id> -b "..."`, interpretando literalmente que los comentarios y el flag corto `-b` no estaban alcanzados por el veto.
2. **Degradación Recurrente del Sandbox:** Al pasar textos dinámicos o multilínea en CLI mediante `-b`, el motor de seguridad de Antigravity no puede aislar un prefijo determinista (`gh issue comment`), disparando diálogos interactivos masivos con múltiples opciones irrepetibles que imposibilitan la autorización permanente (*"Always allow"*).
3. **Contradicción Documental en Skills:** La skill canónica `skills/issue-driven-workflow` aún contenía ejemplos oficiales que utilizaban `--body "..."` para comentar issues y crear PRs, reforzando el antipatrón.

## Impulsores de la Decisión (Decision Drivers)
* **Principio Categórico Universal vs. Casos Particulares:** Las directivas de interacción CLI con herramientas externas deben formularse a nivel de principio y herramienta, no mediante listas finitas de subcomandos que dejan vacíos normativos.
* **Estabilidad y Determinismo del Sandbox:** Toda invocación a GitHub CLI (`gh`) con bypass de red debe conservar una firma CLI invariante, compacta y determinista para permitir el *prefix matching* permanente.
* **Cero Contradicciones en Skills:** Los recursos de instrucción y skills del repositorio deben alinearse estrictamente con el núcleo normativo de `core/`.

## Opciones Consideradas
* **Opción A (Parchear Enumeración con `gh issue comment`):** Añadir `gh issue comment` a la lista existente en `core/02-git.md`.
  - *Descartada:* Mantiene el antipatrón de enumeración finita; dejaría sin cobertura a `gh pr comment`, `gh pr review`, `gh release create`, etc.
* **Opción B (Veto Universal Categórico a Flags de Cuerpo en Línea en `gh`):** Prohibir taxativamente `-b`, `--body`, `-c`, `--comment` con cadenas de texto para **cualquier** comando de `gh`, obligando de forma universal a volcar el contenido a archivos temporales en `scratch/` y usar `--body-file` (`-F`).
  - *Aceptada:* Cierra de raíz cualquier ambigüedad en toda la superficie de herramientas de GitHub CLI y unifica la práctica en todo el ecosistema.

## Decisión Adoptada
Opción elegida: **Opción B ("Veto Universal Categórico a Flags de Cuerpo en Línea en `gh`")**.

1. **Actualización Normativa en `core/02-git.md`:**
   - Queda terminantemente prohibido el uso de flags en línea de cuerpo o notas (`-b`, `--body`, `-c`, `--comment`) con cadenas de texto en cualquier comando de `gh` (`gh issue create`, `gh issue comment`, `gh pr create`, `gh pr comment`, `gh pr review`, `gh release create`, etc.).
   - Es mandato obligatorio y universal volcar cualquier texto destinado a GitHub a un archivo temporal en `scratch/` (ej. `scratch/issue_body.md`, `scratch/comment_body.md`, `scratch/pr_body.md`) y consumirlo exclusivamente mediante el flag nativo `--body-file <ruta>` (o `-F <ruta>`).
2. **Saneamiento Integral de `skills/issue-driven-workflow`:**
   - Incorporación del Principio Fundamental 7 sobre estabilidad de permisos.
   - Reemplazo de todos los ejemplos de la skill por el patrón determinista de dos pasos (escritura en `scratch/` + `--body-file`).

### Consecuencias
* **Positivas:**
  - Garantía absoluta de que ninguna invocación a `gh` disparará diálogos modales irrepetibles por contenido dinámico en CLI.
  - El usuario puede otorgar *"Always allow"* a nivel de prefijo (`gh issue comment`, `gh issue create`, `gh pr create`) con total predictibilidad.
  - Consistencia plena entre las directivas del núcleo (`core/`) y la documentación operativa de las skills.
* **Negativas / Trade-offs:**
  - Requiere siempre el paso previo de escribir un archivo de paso en `scratch/` antes de ejecutar cualquier comando de `gh` que envíe texto.
