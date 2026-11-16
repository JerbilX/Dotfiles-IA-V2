---
name: issue-driven-workflow
description: >-
  Orchestrate task execution via GitHub Issues, branches, and Pull Requests using standard git and gh CLI tools. ACTIVATE whenever creating or viewing issues, developing features or bugfixes under issue tracking, managing ephemeral branch lifecycles, opening PRs, or performing post-merge cleanup. Operates 100% natively with zero custom wrappers or third-party CLI dependencies.
---

# Issue-Driven Workflow & Git Standard Lifecycle

Protocolo operativo canónico para desarrollo guiado por **GitHub Issues** y **Pull Requests**, basado exclusivamente en herramientas nativas estándar (`git` y `gh`), con cero dependencias de wrappers propietarios y máxima trazabilidad.

---

## 1. Principios Fundamentales

1. **Cero Intermediarios (Herramientas Estándar):** Queda terminantemente prohibido el uso o dependencia de scripts wrappers (`issue-create`, `git-prune-gone`, `gh-pr-review`, etc.). Todas las operaciones se realizan con comandos nativos de `git` y `gh`.
2. **Inmutabilidad de `main`:** Prohibido comitear o hacer push directo a la rama `main`. Todo cambio en el código se desarrolla en una rama efímera (`feat/<nombre>` o `fix/<nombre>`) y se integra exclusivamente vía Pull Request.
3. **Trazabilidad Mandatoria (Issue ➔ Branch ➔ PR):** Ningún cambio de código de producción se inicia sin un issue que justifique el requerimiento. Todo PR debe enlazar explícitamente el cierre del issue (`Closes #<id>`).
4. **Minimal Blast Radius (MBR):** Cada rama y PR debe contener el cambio mínimo necesario para satisfacer los criterios de aceptación del issue. Prohibido mezclar refactorizaciones accesorias o cambios de formato no relacionados.
5. **Independencia de Tableros:** El flujo opera de forma autónoma con cualquier repositorio estándar de GitHub mediante Issues y PRs. La interacción con tableros (GitHub Projects v2) es puramente opcional y no bloqueante.

---

## 2. Niveles de Ceremonia y Alcance

* **Nivel 0 (N0 - Consultas / Spikes / Auditorías):**
  - Tareas de solo lectura, análisis de arquitectura, spikes en `scratch/` o respuestas a preguntas.
  - **Acción:** No se crean ramas ni PRs. Si responde a un issue informativo, se comenta directamente:
    ```bash
    gh issue comment <id> --body "Dictamen técnico: ..."
    ```
* **Nivel 1 (N1 - Correcciones Acotadas / Tareas Menores):**
  - Errores evidentes, ajustes de configuración menores o fixes con solución directa y sin ambigüedad arquitectónica.
  - **Acción:** Rama efímera, implementación directa, pruebas locales y PR estándar.
* **Nivel 2 (N2 - Features / Cambios Arquitectónicos / Nuevas Dependencias):**
  - Nuevas funcionalidades, modificaciones estructurales en `core/`, contratos o persistencia.
  - **Acción:** Plan formal previo (`implementation_plan.md`) y/o ADR propuesto (`adr-manager`). Esperar aprobación explícita del usuario antes de codificar en la rama efímera.

---

## 3. Ciclo de Vida E2E (Fase a Fase)

```
[1. Ingesta] ──> [2. Aislamiento] ──> [3. Implementación] ──> [4. Commit] ──> [5. Push & PR] ──> [6. Cierre & Poda]
```

### Fase 1: Ingesta del Issue
1. Inspeccionar el issue:
   ```bash
   gh issue view <id>
   ```
2. **Auditoría Crítica:** Contrastar los requisitos contra el código de producción y ADRs vigentes (`docs/adr/`). Si el issue contiene premisas erróneas, fallas de diseño o deuda técnica no advertida, emitir dictamen técnico antes de implementar.

### Fase 2: Aislamiento en Rama Efímera
1. Actualizar la rama base:
   ```bash
   git checkout main && git pull --ff-only
   ```
2. Crear y cambiar a la rama efímera:
   ```bash
   git checkout -b <feat|fix>/<nombre-kebab-case>
   ```

### Fase 3: Implementación y Verificación Local
1. Implementar exclusivamente lo requerido por el issue respetando contratos existentes.
2. Ejecutar pruebas automatizadas o validaciones de compilación/linting locales (`./build.sh`, tests unitarios).

### Fase 4: Commit Convencional Atómico
1. Staging explícito de archivos afectados (evitar `git add .` indiscriminado):
   ```bash
   git add <archivo1> <archivo2>
   ```
2. Commit con formato Conventional Commits:
   ```bash
   git commit -m "<tipo>(<alcance>): <descripción concisa>"
   ```
   *Tipos estándar:* `feat:`, `fix:`, `refactor:`, `test:`, `docs:`, `chore:`.

### Fase 5: Publicación y Pull Request
1. Publicar la rama en el remoto:
   ```bash
   git push -u origin <nombre-de-rama>
   ```
2. Abrir el Pull Request vinculando el issue de forma determinista:
   ```bash
   gh pr create --title "<tipo>(<alcance>): <descripción>" --body "## Resumen
   <Explicación técnica de la solución implementada>

   Closes #<id>"
   ```

### Fase 6: Cierre, Merge e Higiene Local
1. Una vez aprobado o tras la orden explícita del usuario, fusionar vía squash eliminando la rama remota:
   ```bash
   gh pr merge <id> --squash --delete-branch
   ```
2. Retornar a `main`, sincronizar cambios y podar la rama local:
   ```bash
   git checkout main
   git pull --prune
   git branch -d <nombre-de-rama>
   ```

---

## 4. Gestión Rápida de Backlog

Para registrar bugs detectados, deudas técnicas o futuras tareas directamente en GitHub Issues:

```bash
gh issue create --title "<tipo>(<alcance>): <descripción>" --body "<cuerpo con contexto, reproducción y criterios de aceptación>"
```

Para listar tareas pendientes en el repositorio:

```bash
gh issue list --state open --limit 10
```

---

## 5. Aprovisionamiento de Repositorios Remotos

Al inicializar y publicar nuevos repositorios en GitHub, priorizar visibilidad pública (`--public`) para disponer de minutos ilimitados en runners de GitHub Actions (CI/CD):

```bash
gh repo create <nombre> --public --source=. --remote=origin --push
```
