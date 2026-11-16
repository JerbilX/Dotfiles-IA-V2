---
status: accepted
date: 2026-11-16
decision-makers: [JerbilX, Antigravity]
supersedes: []
superseded-by: []
---

# 0003 - Directiva de Bypass Directo de Sandbox para Comandos de Red (GitHub CLI y Git Remoto)

## Contexto y Planteamiento del Problema
En el runtime de ejecución de Google Antigravity, las herramientas de terminal (`run_command`) operan de forma predeterminada bajo un sandbox de aislamiento estricto (`BypassSandbox: false`). En este modo, el acceso al sistema de archivos local del workspace está habilitado, pero el tráfico de red externa se encuentra completamente bloqueado salvo autorización explícita.

Al ejecutar comandos dependientes del ecosistema de GitHub, tales como la invocación del CLI oficial (`gh auth status`, `gh issue view`, `gh pr create`, etc.) o comandos de transporte de Git hacia remotos (`git push`, `git pull`, `git fetch`), las llamadas fallaban sistemáticamente con errores espurios de autenticación:
- `HTTP 401: Requires authentication (https://api.github.com/graphql)`
- `The token in default is invalid. To re-authenticate, run: gh auth login -h github.com`

Estos errores inducían al agente a sospechar de corrupción de credenciales o a efectuar reintentos reactivos tardíos elevando a `BypassSandbox: true`. Esto producía:
1. Latencia operativa evitable (múltiples llamadas redundantes por turno).
2. Desperdicio de tokens de inferencia en el historial de conversación.
3. Fricción e inconsistencia en los flujos de trabajo guiados por issues (`issue-driven-workflow`).

## Impulsores de la Decisión (Decision Drivers)
* **Eficiencia y Cero Reintentos Espurios:** Eliminar la penalización de latencia y consumo de tokens causada por el fallo garantizado de red en sandbox cerrado.
* **Minimal Blast Radius y Principio del Menor Privilegio:** Mantener todas las operaciones locales (`git checkout`, `git add`, `git commit`, `git status`, `git branch`, scripts de build) estrictamente dentro del sandbox (`BypassSandbox: false`), elevando únicamente las operaciones con dependencia ontológica de red externa.
* **Claridad Normativa:** Clarificar explícitamente en el núcleo basal (`core/02-git.md`) y en las especificaciones operativas (`skills/issue-driven-workflow/SKILL.md`) cuándo procede la elevación directa.

## Opciones Consideradas
* **Opción A (Heurística Genérica de Reintento Reactivo):** Mantener la instrucción general de "probar primero en sandbox estándar" y dejar que el agente reintente con `BypassSandbox: true` tras experimentar el error 401.
  - *Descartada:* Ineficiente y generadora de fricción; el fallo de red es determinista cuando el sandbox no tiene conectividad, por lo que el primer intento está destinado al fracaso.
* **Opción B (Elevación Global de Comandos Git):** Ejecutar cualquier comando de Git y GitHub fuera del sandbox sin distinción.
  - *Descartada:* Vulneraría el principio de confinamiento del workspace y la protección del host para comandos locales que no requieren red.
* **Opción C (Directiva Basal Determinista de Excepción de Red):** Establecer normativamente que las operaciones con destino `api.github.com` o servidores Git remotos (`gh`, `git push`, `git pull`, `git fetch`) son operaciones de transporte que se invocan directamente con `BypassSandbox: true`. Las operaciones locales permanecen 100% sandboxed.

## Decisión Adoptada
Opción elegida: **Opción C ("Directiva Basal Determinista de Excepción de Red")**, documentada formalmente en `core/02-git.md` y en `skills/issue-driven-workflow/SKILL.md`.

### Consecuencias
* **Positivas:**
  - Invocación fluida y determinista de comandos de GitHub CLI y operaciones remotas de Git sin fallos 401 ni tokens desperdiciados.
  - Preservación íntegra de la seguridad y confinamiento para todas las operaciones locales de desarrollo, commit y testing.
  - Alineación con los criterios de Staff Systems Engineer (diagnóstico preciso de causa raíz y MBR).
* **Negativas / Trade-offs:**
  - Las invocaciones con `BypassSandbox: true` requieren la aprobación del usuario en terminales donde el comando no haya sido pre-autorizado (comportamiento intrínseco de seguridad del entorno).
