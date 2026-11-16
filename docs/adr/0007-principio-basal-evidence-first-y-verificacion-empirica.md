---
status: accepted
date: 2026-11-16
decision-makers: [JerbilX, Antigravity]
supersedes: []
superseded-by: []
---

# 0007 - Principio Basal Evidence-First y Verificación Empírica de Identificadores y Comandos

## Contexto y Planteamiento del Problema
Durante la interacción de agentes de IA en repositorios especializados (ej. desarrollo de addons de ESO, utilidades CLI, microservicios), se observó una recurrencia sistemática de alucinación e inferencia apresurada:
1. **Extrapolación Heurística de Entidades Técnicas:** El agente asumía o inventaba comandos de usuario (ej. slash commands de juego o CLI), nombres de métodos de API, flags, constantes y eventos guiado por memoria heurística o similitud léxica, sin verificar su existencia real en el código fuente.
2. **Insuficiencia del Veto Pasivo:** La directiva existente de *Estabilidad Lógica* actuaba como un veto negativo (*"Prohibido adivinar APIs..."*), pero carecía de un protocolo prescriptivo basal que obligase al agente a comprobar empíricamente la existencia y firma exacta de cualquier contrato antes de formular instrucciones o escribir código.

## Impulsores de la Decisión (Decision Drivers)
* **Cero Asunción / Verificación Empírica (Evidence-First):** Prohibir taxativamente cualquier emisión o instrucción de comandos o contratos técnicos sin evidencia de lectura en el turno activo.
* **Inhibición de Familiaridad Sintáctica:** La familiaridad con un dominio, lenguaje o convención de nombres no exime ni sustituye la inspección determinista del código fuente.
* **Trazabilidad y Referenciación Determinista:** Toda indicación de uso debe respaldarse con la referencia precisa al archivo y línea de código donde reside el contrato.
* **Coexistencia con Anti-Parálisis:** La verificación debe apalancarse en consultas dirigidas (`grep_search`, `view_file` acotado) para no degradar la agilidad ni violar la contención de lecturas.

## Opciones Consideradas
* **Opción A (Mantener Veto Pasivo de Estabilidad Lógica):** Dejar la regla actual y confiar en que el modelo se autorregule.
  - *Descartada:* La evidencia empírica demostró que los vetos puramente negativos son ignorados con frecuencia cuando el modelo extrapola entidades por familiaridad de dominio.
* **Opción B (Protocolo Prescriptivo Evidence-First / Zero-Assumption):** Formalizar un protocolo basal en tres ejes: verificación determinista previa obligatoria, inhibición de extrapolación heurística y trazabilidad por enlace/referencia.
  - *Aceptada:* Convierte la regla en un procedimiento activo e ineludible, alineado con el rol de Staff Systems Engineer.

## Decisión Adoptada
Opción elegida: **Opción B ("Protocolo Prescriptivo Evidence-First / Zero-Assumption")**.

Se actualiza `core/01-engineering.md` en la sección `3. Calidad y Proporcionalidad`, integrando:
1. **Protocolo Prescriptivo de Verificación Previa:**
   - Prohibido citar, sugerir, instruir o invocar cualquier comando de usuario (CLI, slash commands, atajos de teclado), nombre de función/método, constante, evento, flag o contrato de datos sin haber verificado su definición exacta en el código fuente mediante herramientas de lectura determinista (`grep_search`, `view_file` acotado) en el turno activo.
2. **Inhibición de Extrapolación Heurística:**
   - La familiaridad con un dominio, convención sintáctica o acrónimos del proyecto nunca autoriza al agente a inferir un identificador sin prueba de código. Si una entidad no ha sido leída e incorporada al contexto desde el repositorio, el agente tiene la obligación estricta de inspeccionar primero antes de afirmar o instruir al usuario.
3. **Trazabilidad y Referenciación:**
   - Toda recomendación de uso de comandos de interacción o interfaces debe estar respaldada por el enlace o referencia a la línea de código donde está definido dicho contrato.

### Consecuencias
* **Positivas:**
  - Erradicación de alucinaciones sobre comandos inexistentes, firmas erróneas de APIs y parámetros ficticios.
  - Mayor precisión y confianza en las instrucciones técnicas provistas al usuario.
  - Refuerzo de la trazabilidad documental y de código mediante enlaces directos a las líneas de definición.
* **Negativas / Trade-offs:**
  - Exige al agente realizar búsquedas deterministas puntuales antes de responder preguntas sobre comandos o contratos de interfaz, consumiendo turnos de inspección justificados.
