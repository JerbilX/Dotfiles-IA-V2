#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DIST_DIR="${SCRIPT_DIR}/dist/antigravity"
CONFIG_DIR="${HOME}/.gemini/config"
SKILLS_SRC="${SCRIPT_DIR}/skills"
SKILLS_DST="${CONFIG_DIR}/skills"

cmd_build() {
    mkdir -p "${DIST_DIR}"
    cat "${SCRIPT_DIR}/core/01-engineering.md" \
        <(echo -e "\n---\n") \
        "${SCRIPT_DIR}/core/02-git.md" > "${DIST_DIR}/AGENTS.md"
    echo "[✓] Build completado: ${DIST_DIR}/AGENTS.md generado."
}

cmd_link() {
    cmd_build
    mkdir -p "${CONFIG_DIR}" "${SKILLS_DST}"
    ln -sf "${DIST_DIR}/AGENTS.md" "${CONFIG_DIR}/AGENTS.md"
    rm -f "${CONFIG_DIR}/hooks.json"
    echo "[✓] Enlazado AGENTS.md en ${CONFIG_DIR}/AGENTS.md"
    echo "[✓] hooks.json eliminado de ${CONFIG_DIR}/hooks.json (cero hooks punitivos)"

    for skill in adr-manager project-documentation smokinggun issue-driven-workflow; do
        if [ -d "${SKILLS_SRC}/${skill}" ]; then
            ln -sfn "${SKILLS_SRC}/${skill}" "${SKILLS_DST}/${skill}"
            echo "[✓] Skill enlazada en host: ${skill}"
        fi
    done
}

case "${1:-link}" in
    build) cmd_build ;;
    link)  cmd_link ;;
    *)     echo "Uso: $0 {build|link}"; exit 1 ;;
esac
