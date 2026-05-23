#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# nanobot Manager Deployment Script
#
# Usage:
#   GITHUB_TOKEN=ghp_xxx ./deploy.sh           # deploy or update
#   GITHUB_TOKEN=ghp_xxx ./deploy.sh --init     # first-time setup
#
# Prerequisites (auto-checked):
#   - git, python3 >=3.11 (with venv)
#   - bun (auto-installed if missing)
#   - GITHUB_TOKEN env var (for private repo access)
# =============================================================================

# --- Config ---
APP_DIR="$HOME/nanobot"
VENV_DIR="$APP_DIR/venv"
BRANCH="${BRANCH:-dev}"
REPO="vicoqi/nanobot"
SERVICE_NAME="nanobot-manager"

# --- Colors ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

# --- Pre-flight checks ---
check_prerequisites() {
    command -v git >/dev/null || error "git not found. Install: sudo apt install git"
    command -v python3 >/dev/null || error "python3 not found. Install: sudo apt install python3"
    python3 -c "import venv" 2>/dev/null || error "python3-venv not found. Install: sudo apt install python3-venv"

    # Check Python >= 3.11
    local py_version
    py_version=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    python3 -c "import sys; assert sys.version_info >= (3, 11)" 2>/dev/null \
        || error "Python >= 3.11 required, got ${py_version}"

    if ! command -v bun >/dev/null; then
        info "bun not found, installing..."
        curl -fsSL https://bun.sh/install | bash
        export PATH="$HOME/.bun/bin:$PATH"
        command -v bun >/dev/null || error "bun install failed"
        info "bun installed: $(bun --version)"
    fi
}

setup_auth() {
    if [ -z "${GITHUB_TOKEN:-}" ]; then
        error "GITHUB_TOKEN env var is required.\n  Usage: GITHUB_TOKEN=ghp_xxx $0"
    fi
    REPO_URL="https://${GITHUB_TOKEN}@github.com/${REPO}.git"
}

# --- Core steps ---
clone_or_pull() {
    if [ -d "$APP_DIR/.git" ]; then
        info "Pulling latest code from origin/${BRANCH}..."
        git -C "$APP_DIR" fetch "$REPO_URL" "$BRANCH"
        git -C "$APP_DIR" reset --hard "FETCH_HEAD"
        info "Code updated to $(git -C "$APP_DIR" rev-parse --short HEAD)"
    else
        info "Cloning repository..."
        mkdir -p "$APP_DIR"
        git clone -b "$BRANCH" "$REPO_URL" "$APP_DIR"
        info "Cloned at $(git -C "$APP_DIR" rev-parse --short HEAD)"
    fi
}

setup_venv() {
    if [ ! -d "$VENV_DIR" ]; then
        info "Creating Python venv..."
        python3 -m venv "$VENV_DIR"
    fi
    info "Installing Python dependencies..."
    (
        source "$VENV_DIR/bin/activate"
        pip install -q --upgrade pip
        pip install -q -e "$APP_DIR[manager]"
    )
    info "Python dependencies installed"
}

build_frontend() {
    info "Building webui-manager frontend..."
    ( cd "$APP_DIR/webui-manager" && bun install --frozen-lockfile 2>/dev/null || bun install && bun run build )
    info "Frontend built -> nanobot/manager/static/"
}

restart_service() {
    if systemctl is-active --quiet "$SERVICE_NAME" 2>/dev/null; then
        info "Restarting ${SERVICE_NAME}..."
        sudo systemctl restart "$SERVICE_NAME"
    else
        warn "${SERVICE_NAME} is not running. Start it manually:"
        echo "  sudo systemctl start ${SERVICE_NAME}"
        return
    fi
    sleep 3
    if systemctl is-active --quiet "$SERVICE_NAME"; then
        info "${SERVICE_NAME} is running (PID: $(systemctl show -p MainPID --value "$SERVICE_NAME"))"
    else
        error "${SERVICE_NAME} failed to start. Check: sudo journalctl -u ${SERVICE_NAME} -n 50"
    fi
}

# --- First-time init ---
init_server() {
    info "=== First-time server initialization ==="

    # Clone
    if [ ! -d "$APP_DIR/.git" ]; then
        info "Cloning repository..."
        mkdir -p "$APP_DIR"
        git clone -b "$BRANCH" "$REPO_URL" "$APP_DIR"
    fi

    # Venv
    setup_venv

    # Build frontend
    build_frontend

    # Config dir
    mkdir -p "$HOME/.nanobot"
    if [ ! -f "$HOME/.nanobot/manager-config.json" ]; then
        warn "No manager-config.json found. Create it:"
        echo "  nano $HOME/.nanobot/manager-config.json"
    fi

    # Install systemd service
    info "Installing systemd service..."
    local current_user
    current_user=$(whoami)
    sed -e "s|%USER%|${current_user}|g" -e "s|%HOME%|${HOME}|g" \
        "$APP_DIR/deploy/nanobot-manager.service" \
        | sudo tee /etc/systemd/system/"$SERVICE_NAME".service >/dev/null
    sudo systemctl daemon-reload
    sudo systemctl enable "$SERVICE_NAME"

    info ""
    info "=== Init complete! ==="
    info "Next steps:"
    echo "  1. Create config: nano $HOME/.nanobot/manager-config.json"
    echo "  2. Start service: sudo systemctl start ${SERVICE_NAME}"
    echo "  3. Test: curl http://localhost:8080/admin/"
}

# --- Main ---
main() {
    local action="${1:-deploy}"

    case "$action" in
        --init|init)
            setup_auth
            check_prerequisites
            init_server
            ;;
        --help|help|-h)
            echo "Usage:"
            echo "  GITHUB_TOKEN=xxx $0          # Deploy (pull, build, restart)"
            echo "  GITHUB_TOKEN=xxx $0 --init   # First-time server setup"
            echo ""
            echo "Config (env vars):"
            echo "  GITHUB_TOKEN    GitHub PAT for private repo (required)"
            echo "  BRANCH          Git branch (default: dev)"
            ;;
        deploy|*)
            setup_auth
            check_prerequisites
            clone_or_pull
            setup_venv
            build_frontend
            restart_service
            info "=== Deploy complete! ==="
            ;;
    esac
}

main "$@"
