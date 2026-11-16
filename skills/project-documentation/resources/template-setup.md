# Guía de Instalación, Configuración y Entorno (Setup)

Guía procedimental paso a paso para el aprovisionamiento, configuración de dependencias y resolución de incidencias en entornos de desarrollo y producción.

---

## 1. Precondiciones del Sistema

Antes de iniciar el aprovisionamiento, asegúrate de contar con las siguientes utilidades mínimas instaladas en tu sistema anfitrión:

| Herramienta | Versión Mínima | Propósito en el Proyecto |
| :--- | :--- | :--- |
| **Bash** | 4.0+ | Intérprete para scripts de compilación y orquestación. |
| **Python** | 3.10+ | Validación de esquemas JSON y utilidades auxiliares. |
| **Git** | 2.30+ | Control de versiones y gestión de ramas efímeras. |
| **GitHub CLI (`gh`)** | 2.20+ | Orquestación de issues, PRs y sincronización con Projects v2. |

---

## 2. Variables de Entorno y Configuración de Shell

Para garantizar que los binarios y ejecutables generados sean accesibles globalmente, configura la ruta local en tu archivo de configuración de shell (`~/.bashrc` o `~/.zshrc`):

```bash
# Agregar directorio de binarios de usuario al PATH
export PATH="${HOME}/.local/bin:${PATH}"
```

Aplica los cambios en tu sesión activa:
```bash
source ~/.bashrc  # o source ~/.zshrc
```

---

## 3. Aprovisionamiento Paso a Paso

### Paso 1: Clonado del Repositorio
```bash
mkdir -p ~/Proyectos && cd ~/Proyectos
git clone https://github.com/<owner>/<repo>.git
cd <repo>
```

### Paso 2: Ejecución del Orquestador de Bootstrap
```bash
./build.sh
```
Este comando ejecuta secuencialmente:
1. Compilación de artefactos y directivas.
2. Generación de respaldos atómicos (`.bak.<timestamp>`) de configuraciones preexistentes.
3. Creación atómica de enlaces simbólicos (`ln -sfn`) hacia las ubicaciones canónicas del host.
4. Exposición de herramientas CLI y scripts en `~/.local/bin/`.

### Paso 3: Verificación de Salud
```bash
./build.sh check
```
Confirma que la suite reporte `0 error(es)` antes de proceder con el desarrollo.

---

## 4. Resolución de Problemas Frecuentes (Troubleshooting)

### Error: Binarios no encontrados en `$PATH`
- **Síntoma:** Al ejecutar un CLI provisto por el proyecto, la terminal responde `command not found`.
- **Causa:** `~/.local/bin` no está exportado en la variable `$PATH` de la shell actual.
- **Solución:** Verifica con `echo $PATH`. Agrega `export PATH="${HOME}/.local/bin:${PATH}"` a tu `.bashrc`/`.zshrc` y reinicia la terminal.

### Advertencia: Symlinks rotos o colisiones de archivos
- **Síntoma:** `./build.sh check` reporta enlaces simbólicos inválidos.
- **Causa:** Archivos de destino eliminados o movidos manualmente fuera del flujo de build.
- **Solución:** Ejecuta `./build.sh link` para regenerar y validar los enlaces canónicos.

---

## 5. Limpieza y Desinstalación (Purga)

Para remover limpiamente los enlaces simbólicos y restaurar el estado anterior del sistema:
```bash
# Revertir al último respaldo automático
./build.sh rollback

# O eliminar enlaces simbólicos generados en el host
rm -f ~/.local/bin/<binario>
```
