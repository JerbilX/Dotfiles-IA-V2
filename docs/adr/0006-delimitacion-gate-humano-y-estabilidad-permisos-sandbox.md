---
status: accepted
date: 2026-11-16
decision-makers: [JerbilX, Antigravity]
supersedes: []
superseded-by: []
---

# 0006 - Delimitación del Gate Humano y Estabilidad de Permisos en Sandbox

## Contexto y Planteamiento del Problema
En el desarrollo con el runtime de Antigravity sobre repositorios que consumen `Dotfiles-IA-V2`, se observó una inversión disfuncional de los puntos de control y fricción severa de permisos:
1. **Inversión del Gate Humano:** El agente incurría en automatización desbocada durante la fase de deliberación y arquitectura (disparando herramientas en ráfaga ante preguntas reflexivas o ignorando comandos de pausa), mientras introducía falsos gates burocráticos durante la ejecución (preguntando interactivamente si creaba issues o ramas).
2. **Degradación de Permisos en Sandbox:** El paso de wrappers propietarios de la V1 a comandos directos de `gh` introdujo una nueva fricción: el uso de cadenas dinámicas extensas en `--body "..."` dentro de llamadas unsandboxed (`BypassSandbox: true`). Esto destruye la predictibilidad del *prefix matching* de seguridad de Antigravity y satura la interfaz con diálogos masivos e irrepetibles, impidiendo al usuario otorgar *"Always allow"*.
3. **Proliferación de Scripts Ad-hoc Unsandboxed:** La ejecución de scripts ad-hoc en `scratch/` con bypass de sandbox evade las herramientas canónicas ya autorizadas y genera alertas de permisos innecesarias.

## Impulsores de la Decisión (Decision Drivers)
* **Ubicación Correcta del Control Humano:** El gate humano pertenece exclusivamente a la fase de decisión y validación de diseño/arquitectura; una vez autorizada la dirección, la ejecución operativa debe fluir sin fricción.
* **Estabilidad y Predictibilidad de Permisos en Antigravity:** Toda invocación de herramientas de red o unsandboxed debe conservar una firma CLI determinista, corta y constante para permitir el emparejamiento por prefijo (*prefix matching*) permanente.
* **Cero Cadenas Masivas en CLI:** Desacoplar los cuerpos de texto extensos de los argumentos shell hacia archivos de paso locales.
* **Consumo Exclusivo de CLIs Canónicos:** Prohibir scripts auxiliares unsandboxed cuando existen herramientas estándar ya autorizadas en el host (`agent-audit`, `gh`, `git`).

## Opciones Consideradas
* **Opción A (Reintroducir Scripts Wrappers Propietarios de la V1):** Crear nuevamente wrappers locales como `issue-create` o `gh-wrapper`.
  - *Descartada:* Vuelve a introducir capas propietarias intermediarias que inflan la base de código y requieren mantenimiento redundante.
* **Opción B (Estandarización Nativa con `--body-file` y Delimitación Normativa):** Mantener herramientas nativas estándar de GitHub (`gh`) pero normar el uso obligatorio de `--body-file` para desacoplar el contenido dinámico a un archivo temporal local, prohibir scripts ad-hoc unsandboxed en `scratch/` y formalizar la frontera del Gate Humano (diseño vs ejecución).
  - *Aceptada:* Soluciona la fricción del motor de permisos de Antigravity al 100%, preserva el uso de herramientas nativas estándar y corrige la inversión del control humano.

## Decisión Adoptada
Opción elegida: **Opción B ("Estandarización Nativa con `--body-file` y Delimitación Normativa")**.

Se actualizan las directivas basales:
1. **Frontera Estricta del Gate Humano:**
   - **Pre-Ejecución (Gate Obligatorio):** Ante planteos de arquitectura, reflexiones, dudas o comandos de parada, el agente delibera en texto, presenta opciones y espera la decisión del usuario. Prohibido mutar código o crear tareas antes de la aprobación.
   - **Post-Aprobación (Autonomía Operativa):** Una vez aprobado el enfoque (*"implementa"*, *"adelante"*), el agente ejecuta el flujo estándar (issue, rama, código, tests, PR) de forma autónoma sin interrupciones burocráticas redundantes.
2. **Estandarización de `gh` para Compatibilidad con Sandbox de Antigravity:**
   - Queda estrictamente prohibido pasar cuerpos extensos en línea mediante `--body "..."` en `gh issue create` y `gh pr create`.
   - Es obligatorio volcar el cuerpo a un archivo local temporal (ej. `scratch/issue_body.md` o `.git/PR_BODY.md`, confinado al workspace) y utilizar el flag nativo `--body-file <ruta>`.
   - Esto preserva firmas CLI compactas (`gh issue create --title "..." --body-file ...`), garantizando que la regla *"Always allow"* de Antigravity funcione deterministamente sin repreguntar al usuario.
3. **Veto a Scripts Ad-hoc Unsandboxed:**
   - Prohibido ejecutar scripts de scratch (`python3 scratch/...`) con `BypassSandbox: true`. Toda auditoría o telemetría debe consumirse directamente mediante los flags nativos de `agent-audit` en el host.

### Consecuencias
* **Positivas:**
  - El usuario puede autorizar `gh issue create` y `gh pr create` una sola vez en Antigravity con *"Always allow"* sin recibir cuadros de diálogo gigantes e irrepetibles.
  - El agente respeta el momento de deliberar y el momento de ejecutar, erradicando tanto el sesgo de acción desbocado como la burocracia de micro-permisos.
  - Se mantiene una arquitectura 100% nativa con utilidades estándar sin wrappers propietarios.
* **Negativas / Trade-offs:**
  - Requiere un paso previo de escritura de archivo (`write_to_file`) en `scratch/` antes de invocar la creación de issues o PRs.
