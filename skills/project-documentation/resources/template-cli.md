# Referencia Técnica de Interfaces de Línea de Comandos (CLI Reference)

Manual de referencia formal y exhaustivo para las herramientas CLI y scripts orquestadores del proyecto.

---

## 1. Sintaxis General de Invocación

```bash
./build.sh <subcomando> [opciones] [argumentos]
```

### Parámetros Globales
- `<subcomando>`: Acción operativa requerida (ver catálogo inferior).
- `[opciones]`: Banderas de control de formato o verbosidad.
- `[argumentos]`: Parámetros contextuales dependientes del subcomando (ej. runtime específico).

---

## 2. Catálogo Exhaustivo de Subcomandos

### `build`
Compila artefactos, plantillas o módulos en sus versiones listas para distribución.
- **Sintaxis:** `./build.sh build [módulo]`
- **Comportamiento:** Si se omite `[módulo]`, procesa la totalidad de los módulos configurados en el proyecto.
- **Ejemplo:**
  ```bash
  ./build.sh build core
  ```

### `check`
Ejecuta una auditoría estática de integridad y presupuesto de sólo lectura (*read-only*), ideal para pre-commit o CI/CD.
- **Sintaxis:** `./build.sh check [módulo]`
- **Validaciones:**
  - Sintaxis y esquemas JSON.
  - Presencia física de dependencias y scripts ejecutables.
  - Presupuestos cuantitativos de palabras y líneas.
  - Integridad de enlaces relativos hacia documentación.
- **Ejemplo:**
  ```bash
  ./build.sh check
  ```

### `status`
Inspecciona el estado operativo de los enlaces simbólicos y dependencias del sistema anfitrión.
- **Sintaxis:** `./build.sh status [módulo]`
- **Salida:** Reporta estado (válido, roto, desactualizado) por cada enlace registrado.

### `rollback`
Reversión determinista al último respaldo generado (`.bak.<timestamp>`).
- **Sintaxis:** `./build.sh rollback [módulo]`
- **Comportamiento:** Restaura de forma atómica el archivo de configuración previo. Retorna error si no existen respaldos.

---

## 3. Variables de Entorno de Control

| Variable | Tipo | Valor por Defecto | Descripción |
| :--- | :---: | :---: | :--- |
| `MAX_CONTEXT_WORDS` | `integer` | `4000` | Límite máximo de palabras para compilaciones de directivas completas. |
| `MAX_MODULE_WORDS` | `integer` | `300` | Límite modular recomendado por archivo de regla individual. |
| `MAX_README_WORDS` | `integer` | `600` | Umbral de advertencia estática para el archivo `README.md` raíz. |
| `DEBUG` | `boolean` | `0` | Habilita salida detallada para diagnóstico y rastreo de ejecución. |

---

## 4. Códigos de Salida (Exit Codes)

| Código | Significado | Causa y Acción Correctiva |
| :---: | :--- | :--- |
| `0` | **Éxito (Success)** | Operación concluida sin errores ni violaciones de integridad. |
| `1` | **Error Operativo / Validación** | Esquema inválido, symlink roto, o fallo en verificación estática (`check`). |
| `2` | **Parámetros Inválidos** | Subcomando desconocido o argumentos faltantes en la invocación. |
