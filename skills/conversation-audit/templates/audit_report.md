# Informe de Auditoría Técnica: Sesión {{SESSION_ID}}

## 1. Resumen Ejecutivo

| Métrica | Valor |
| :--- | :--- |
| **Título / Objetivo** | {{SESSION_TITLE}} |
| **Runtime** | `{{RUNTIME}}` |
| **Archivo / Origen** | `{{SOURCE_PATH}}` |
| **Fecha de Inicio** | {{START_TIME}} |
| **Fecha de Cierre** | {{END_TIME}} |
| **Duración Total (Wall-Clock)** | {{WALL_CLOCK_SECONDS}} s ({{WALL_CLOCK_MINUTES}} min) |
| **Pasos Totales** | {{TOTAL_STEPS}} (Usuario: {{USER_TURNS}}, Modelo: {{MODEL_TURNS}}, Sistema: {{SYSTEM_STEPS}}) |
| **Latencia Promedio por Paso** | {{AVG_STEP_LATENCY}} s |
| **Latencia Máxima** | {{MAX_STEP_LATENCY}} s |
| **Total Invocaciones de Herramientas** | {{TOTAL_TOOL_CALLS}} |
| **Fallos de Herramientas** | {{TOTAL_TOOL_ERRORS}} ({{TOOL_ERROR_RATE}}%) |
| **Pasos con Thinking** | {{THINKING_STEPS_COUNT}} (Total: {{TOTAL_THINKING_CHARS}} chars) |

---

## 2. Desglose de Invocaciones por Herramienta

{{TOOL_BREAKDOWN_TABLE}}

---

## 3. Pasos de Mayor Latencia (Top 5)

{{SLOWEST_STEPS_TABLE}}

---

## 4. Antipatrones y Anomalías Detectadas

{{ANTIPATTERNS_SECTION}}

---

## 5. Conclusiones y Oportunidades de Optimización

{{CONCLUSIONS_SECTION}}

---
*Generado por `agent-audit` (Dotfiles-IA-Agents).*
