---
status: accepted
date: 2026-11-15
decision-makers: [JerbilX, Antigravity]
supersedes: []
superseded-by: []
---

# 0001 - Arquitectura Basal Minimalista y Criterio Clean-Slate

## Contexto y Planteamiento del Problema
El proyecto predecesor (`Dotfiles-IA-Agents`) acumuló una hipertrofia de gobernanza: más de 400 issues, scripts wrappers locales (`issue-create`, `git-prune-gone`, `gh-pr-review`), hooks policiales complejos (`agent-guard` de 900 líneas interceptando comandos shell) y disyuntores punitivos de lecturas (`Hard Circuit Breakers`). 
Esta arquitectura generó fricción severa: falsos positivos en terminal, alto consumo innecesario de tokens en meta-debugging y pérdida de foco en el desarrollo de software real (como los addons de Elder Scrolls Online).

Era necesario cortar de raíz la deuda técnica y establecer una arquitectura basal en un nuevo repositorio (`Dotfiles-IA-V2`) que garantice máxima estabilidad, trazabilidad y cero sobrecarga de proceso.

## Impulsores de la Decisión (Decision Drivers)
* Cero intermediarios: eliminación total de scripts wrappers locales propietarios en favor de herramientas estándar nativas (`git` y `gh`).
* Eliminación del meta-tooling punitivo: prescindir de hooks locales de intercepción coercitiva (`agent-guard`, `hooks.json`) y delegar automatizaciones a GitHub Actions o directivas declarativas.
* Criterio Clean-Slate vs. Deuda Legacy: evitar el sesgo de adaptación incremental sobre código viciado; diseñar de cero contra contratos funcionales.
* Minimal Blast Radius (MBR) y Confinamiento de Workspace.
* Compatibilidad con cuotas de CI/CD: provisión remota con visibilidad pública (`--public`) para disponer de runners ilimitados en GitHub Actions.

## Opciones Consideradas
* **Opción A (Amputación incremental en `Dotfiles-IA-Agents`):** Eliminar código muerto en el repositorio existente, arriesgando herencia residual de dependencias y configuraciones cruzadas.
* **Opción B (Reinicio Greenfield en `Dotfiles-IA-V2`):** Crear un repositorio nuevo, minimalista, con un núcleo normativo reducido (`core/01-engineering.md` y `core/02-git.md`), skills nativas desacopladas y compilación determinista en `AGENTS.md`.

## Decisión Adoptada
Opción elegida: **Opción B ("Reinicio Greenfield en Dotfiles-IA-V2")**, porque corta de manera definitiva el ciclo vicioso de meta-mantenimiento, reduce el consumo de tokens en contexto y devuelve al entorno de Antigravity su rendimiento nativo para programar aplicaciones reales.

### Consecuencias
* **Positivas:**
  - Runtime de Antigravity limpio, ágil y sin disyuntores artificiales ni hooks punitivos.
  - Trazabilidad determinista mediante flujo estándar de GitHub (Issues ➔ Ramas efímeras ➔ PRs).
  - Reglas concisas compiladas en un único `AGENTS.md` (menos de 70 líneas en el prompt basal).
  - Procedimientos de soporte encapsulados como skills bajo demanda (`adr-manager`, `project-documentation`, `smokinggun`, `issue-driven-workflow`).
* **Negativas / Trade-offs:**
  - Requiere re-implementar de forma limpia y gradual las skills especializadas requeridas (ej: `eso-addon-development`).
  - La gobernanza depende de la disciplina metodológica del agente (rol de Staff Systems Engineer) y validación en CI en lugar de bloqueos mecánicos en el cliente bash.
