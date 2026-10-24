#!/usr/bin/env bash
# ==============================================================================
# ARCHIVO #11: omega_phantom_v7_install.sh
# SISTEMA: OMEGA-PHANTOM V7.0 (APEX-CHRONOS SINGULARITY)
# ==============================================================================
# Instalador Determinista Unix LF para sniper-singapur:
#   1. Reutiliza o crea el entorno virtual Python (venv) con uvloop y ccxt.
#   2. Inyecta en ~/.bashrc la utilidad forense interactiva `veromega`.
# ==============================================================================
set +e

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_DIR" || exit 1

if [ ! -d "$REPO_DIR/venv" ]; then
    if [ -d "$HOME/Tri-Brain-Sniper/venv" ]; then
        ln -s "$HOME/Tri-Brain-Sniper/venv" "$REPO_DIR/venv"
    else
        python3 -m venv "$REPO_DIR/venv"
        "$REPO_DIR/venv/bin/pip" install --upgrade pip
        "$REPO_DIR/venv/bin/pip" install -r "$REPO_DIR/requirements.txt"
    fi
fi

if [ ! -f "$REPO_DIR/.env" ] && [ -f "$HOME/Tri-Brain-Sniper/.env" ]; then
    cp -f "$HOME/Tri-Brain-Sniper/.env" "$REPO_DIR/.env"
fi

sed -i '/# >>> OMEGA-PHANTOM V7.0 CLI >>>/,/# <<< OMEGA-PHANTOM V7.0 CLI <<</d' "$HOME/.bashrc" 2>/dev/null || true

cat << 'EOF' >> "$HOME/.bashrc"
# >>> OMEGA-PHANTOM V7.0 CLI >>>
veromega() {
    set +e
    local dir_omega="$HOME/OMEGA-PHANTOM"
    local modo="${1:--s}"
    if [ "$modo" = "-l" ]; then
        tail -n 45 "$dir_omega/omega_phantom_v7.log"
    elif [ "$modo" = "--lab" ]; then
        "$dir_omega/venv/bin/python" "$dir_omega/omega_phantom_v7_oos_twin.py" --lab
    else
        "$dir_omega/venv/bin/python" "$dir_omega/omega_phantom_v7_gestor.py" "$modo"
    fi
}
# <<< OMEGA-PHANTOM V7.0 CLI <<<
EOF

echo "[INSTALL OK] Infraestructura OMEGA-PHANTOM V7.0 y comando 'veromega' configurados."