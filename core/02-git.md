# Flujo de Trabajo Git Estándar

## 1. Inmutabilidad de Main y Trazabilidad
- Prohibido comitear o hacer push directo a la rama `main`.
- Todo cambio se desarrolla en una rama efímera (`feat/<nombre>` o `fix/<nombre>`) y se integra mediante Pull Request.

## 2. Herramientas Estándar
- Utilizar comandos nativos y estándar de `git` y `gh` (`git checkout -b`, `git commit`, `git push`, `gh pr create`).
- Cero intermediarios: no se exigen wrappers propietarios locales para operar con GitHub.
