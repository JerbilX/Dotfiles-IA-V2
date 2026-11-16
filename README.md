# Dotfiles-IA-V2

Configuración modular, reglas de ingeniería y catálogo de skills nativas para runtime de agentes en Antigravity.

---

## Propósito

Este repositorio centraliza las directivas de comportamiento, reglas de arquitectura (Minimal Blast Radius, Criterio Clean-Slate y Confinamiento) y habilidades operativas (*skills*) para el asistente de desarrollo. Opera mediante herramientas nativas estándar (`git`, `gh`, bash) sin capas ni wrappers propietarios intermediarios.

---

## Estructura del Proyecto

- `core/`: Directivas basales de ingeniería y flujo Git estándar.
- `dist/antigravity/`: Salida compilada (`AGENTS.md`) consumida por el runtime.
- `skills/`: Catálogo de habilidades operativas nativas:
  - `adr-manager`: Gestión de registros de arquitectura (MADR).
  - `project-documentation`: Estándares documentales Diátaxis adaptativos.
  - `smokinggun`: Análisis de cuellos de botella y complejidad algorítmica.
  - `issue-driven-workflow`: Flujo E2E guiado por GitHub Issues y PRs.
  - `eso-addon-development`: Desarrollo de addons para Elder Scrolls Online (Lua / ESO API).
- `build.sh`: Script de compilación y enlace simbólico hacia `~/.gemini/config`.

---

## Puesta en Marcha

### Requisitos
- Bash POSIX y utilidades estándar (`git`, `gh`).
- Entorno de agente Antigravity / Gemini CLI configurado en `$HOME/.gemini`.

### Compilación y Enlace
```bash
# Compilar directivas AGENTS.md
./build.sh build

# Compilar y enlazar en ~/.gemini/config (AGENTS.md y skills)
./build.sh link
```

---

## Convenciones de Desarrollo

- **Inmutabilidad de `main`:** Desarrollo exclusivo mediante ramas efímeras (`feat/*`, `fix/*`, `docs/*`).
- **Trazabilidad:** Todo cambio responde a un issue previo y se entrega vía Pull Request (`Closes #ID`).
- **Commits:** Conventional Commits (`feat:`, `fix:`, `docs:`, `chore:`).
