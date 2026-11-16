# Flujo de Trabajo Git Estándar

## 1. Inmutabilidad de Main y Trazabilidad
- Prohibido comitear o hacer push directo a la rama `main`.
- Todo cambio se desarrolla en una rama efímera (`feat/<nombre>` o `fix/<nombre>`) y se integra mediante Pull Request.

## 2. Herramientas Estándar
- Utilizar comandos nativos y estándar de `git` y `gh` (`git checkout -b`, `git commit`, `git push`, `gh pr create`).
- Cero intermediarios: no se exigen wrappers propietarios locales para operar con GitHub.
- **Acceso Directo a Red (Bypass de Sandbox):** Las operaciones que interactúan con la API de GitHub (`gh auth`, `gh issue`, `gh pr`, etc.) y con remotos de Git (`git push`, `git pull`, `git fetch`) poseen una dependencia intrínseca de red externa. En entornos con aislamiento de sandbox (como Google Antigravity), deben invocarse directamente con elevación de red (`BypassSandbox: true`), exceptuándolas de la heurística de prueba ciega en sandbox aislado para evitar fallos espurios de autenticación (HTTP 401) y consumo innecesario de tokens.

