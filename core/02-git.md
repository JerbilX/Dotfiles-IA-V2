# Flujo de Trabajo Git Estándar

## 1. Inmutabilidad de Main y Trazabilidad
- Prohibido comitear o hacer push directo a la rama `main`.
- Todo cambio se desarrolla en una rama efímera (`feat/<nombre>` o `fix/<nombre>`) y se integra mediante Pull Request.

## 2. Herramientas Estándar
- Utilizar comandos nativos y estándar de `git` y `gh` (`git checkout -b`, `git commit`, `git push`, `gh pr create`).
- Cero intermediarios: no se exigen wrappers propietarios locales para operar con GitHub.
- **Acceso Directo a Red (Bypass de Sandbox):** Las operaciones que interactúan con la API de GitHub (`gh auth`, `gh issue`, `gh pr`, etc.) y con remotos de Git (`git push`, `git pull`, `git fetch`) poseen una dependencia intrínseca de red externa. En entornos con aislamiento de sandbox (como Google Antigravity), deben invocarse directamente con elevación de red (`BypassSandbox: true`), exceptuándolas de la heurística de prueba ciega en sandbox aislado para evitar fallos espurios de autenticación (HTTP 401) y consumo innecesario de tokens.
- **Estabilidad de Permisos en Sandbox con `--body-file`:** Queda estrictamente prohibido pasar cuerpos extensos en línea mediante cadenas de texto multilínea (`--body "..."`) en comandos de `gh` (`gh issue create`, `gh pr create`). Estas cadenas dinámicas extensas degradan el motor de seguridad de Antigravity al presentar diálogos de confirmación masivos e irrepetibles que impiden el funcionamiento del emparejamiento por prefijo (*prefix matching* / *"Always allow"*). Es obligatorio volcar el cuerpo a un archivo temporal confinado en el workspace (ej. `scratch/issue_body.md` o `scratch/pr_body.md`) y utilizar el flag nativo `--body-file <ruta>`. Esto garantiza que la invocación CLI conserve una firma compacta y determinista, permitiendo la autorización global permanente del sandbox sin fricción interactiva.

## 3. Autonomía en Creación de Issues
- **Autonomía en Creación de Issues:** La creación de issues en GitHub para planificar, registrar tareas, deconstrucciones o fases acordadas es una operación estándar, autónoma y de mínimo impacto destructivo.
- **Prohibición de Gates Redundantes:** Queda terminantemente prohibido solicitar confirmación humana interactiva (`ask_question`, Stop & Ask) para crear un issue en el repositorio activo o en repositorios de trabajo autorizados cuando el trabajo técnico o fase ya ha sido identificado o acordado. Los issues registran trazabilidad y no alteran código de producción.

