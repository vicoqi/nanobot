#!/usr/bin/env bash
set -euo pipefail

# Start nanobot from an extracted release archive.
#
# Run from the extracted project directory:
#   ./deploy/start-from-archive.sh start
#   ./deploy/start-from-archive.sh status
#   ./deploy/start-from-archive.sh logs
#   ./deploy/start-from-archive.sh stop
#
# Optional env vars:
#   VENV_DIR           Python venv path. Defaults to <project>/venv.
#   INSTALL_EXTRAS     Package extras for pip install -e. Defaults to manager.
#   CONFIG_PATH        Manager config path. Defaults to ~/.nanobot/manager-config.json.
#   BUNDLED_CONFIG     Packaged config path. Defaults to <project>/deploy/manager-config.json.
#   SYNC_BUNDLED_CONFIG Copy BUNDLED_CONFIG to CONFIG_PATH before start. Defaults to 1.
#   HOST               Optional manager host override. Uses config default when unset.
#   PORT               Optional manager port override. Uses config default when unset.
#   BUILD_MANAGER_UI   Set to 1 to build webui-manager before starting.
#   LOG_DIR            Runtime log directory. Defaults to <project>/runtime.
#   PID_FILE           Process pid file. Defaults to <LOG_DIR>/nanobot-manager.pid.
#   LOG_FILE           Process log file. Defaults to <LOG_DIR>/nanobot-manager.log.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

VENV_DIR="${VENV_DIR:-${APP_DIR}/venv}"
INSTALL_EXTRAS="${INSTALL_EXTRAS:-manager}"
CONFIG_PATH="${CONFIG_PATH:-${HOME}/.nanobot/manager-config.json}"
BUNDLED_CONFIG="${BUNDLED_CONFIG:-${APP_DIR}/deploy/manager-config.json}"
SYNC_BUNDLED_CONFIG="${SYNC_BUNDLED_CONFIG:-1}"
HOST="${HOST:-}"
PORT="${PORT:-}"
BUILD_MANAGER_UI="${BUILD_MANAGER_UI:-0}"
LOG_DIR="${LOG_DIR:-${APP_DIR}/runtime}"
PID_FILE="${PID_FILE:-${LOG_DIR}/nanobot-manager.pid}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/nanobot-manager.log}"
STOP_TIMEOUT="${STOP_TIMEOUT:-20}"

info() { printf '[INFO] %s\n' "$*"; }
warn() { printf '[WARN] %s\n' "$*" >&2; }
error() { printf '[ERROR] %s\n' "$*" >&2; exit 1; }

usage() {
    cat <<EOF
Usage:
  $0 start       Install/update local venv and start nanobot manager in background
  $0 run         Install/update local venv and run nanobot manager in foreground
  $0 stop        Stop the background process started by this script
  $0 restart     Stop, then start
  $0 status      Show process status
  $0 logs        Tail runtime logs
  $0 install     Only create/update venv and install dependencies

Optional env vars:
  VENV_DIR           Python venv path (default: ${VENV_DIR})
  INSTALL_EXTRAS     pip editable extras (default: manager)
  CONFIG_PATH        Manager config path (default: ${CONFIG_PATH})
  BUNDLED_CONFIG     Packaged manager config (default: ${BUNDLED_CONFIG})
  SYNC_BUNDLED_CONFIG Copy bundled config to CONFIG_PATH before start (default: 1)
  HOST               Optional manager host override
  PORT               Optional manager port override
  BUILD_MANAGER_UI   Build webui-manager before start when set to 1
  LOG_DIR            Runtime log directory (default: ${LOG_DIR})
  PID_FILE           Process pid file (default: ${PID_FILE})
  LOG_FILE           Process log file (default: ${LOG_FILE})
EOF
}

require_command() {
    command -v "$1" >/dev/null 2>&1 || error "$1 not found"
}

check_python() {
    require_command python3
    python3 - <<'PY'
import sys
if sys.version_info < (3, 11):
    raise SystemExit(f"Python >= 3.11 required, got {sys.version.split()[0]}")
PY
}

install_project() {
    check_python

    if [ ! -f "${VENV_DIR}/pyvenv.cfg" ]; then
        info "Creating venv: ${VENV_DIR}"
        python3 -m venv "${VENV_DIR}"
    fi

    info "Installing Python dependencies"
    "${VENV_DIR}/bin/python" -m pip install --upgrade pip

    local install_target
    if [ -n "${INSTALL_EXTRAS}" ]; then
        install_target="${APP_DIR}[${INSTALL_EXTRAS}]"
    else
        install_target="${APP_DIR}"
    fi

    "${VENV_DIR}/bin/python" -m pip install -e "${install_target}"
}

build_manager_ui() {
    [ "${BUILD_MANAGER_UI}" = "1" ] || return 0

    if [ ! -d "${APP_DIR}/webui-manager" ]; then
        warn "BUILD_MANAGER_UI=1, but webui-manager directory does not exist; skipping"
        return 0
    fi

    require_command bun
    info "Building webui-manager"
    (
        cd "${APP_DIR}/webui-manager"
        bun install --frozen-lockfile 2>/dev/null || bun install
        bun run build
    )
}

sync_bundled_config() {
    [ "${SYNC_BUNDLED_CONFIG}" = "1" ] || return 0

    if [ ! -f "${BUNDLED_CONFIG}" ]; then
        return 0
    fi

    if [ "${BUNDLED_CONFIG}" = "${CONFIG_PATH}" ]; then
        info "Using bundled manager config: ${CONFIG_PATH}"
        chmod 600 "${CONFIG_PATH}" 2>/dev/null || true
        return 0
    fi

    info "Installing bundled manager config to ${CONFIG_PATH}"
    mkdir -p "$(dirname "${CONFIG_PATH}")"
    cp "${BUNDLED_CONFIG}" "${CONFIG_PATH}"
    chmod 600 "${CONFIG_PATH}" 2>/dev/null || true
}

is_running() {
    [ -f "${PID_FILE}" ] || return 1

    local pid
    pid="$(cat "${PID_FILE}")"
    [ -n "${pid}" ] || return 1
    kill -0 "${pid}" 2>/dev/null
}

manager_command() {
    CMD=("${VENV_DIR}/bin/nanobot" manager)

    if [ -n "${CONFIG_PATH}" ]; then
        CMD+=(--config "${CONFIG_PATH}")
    fi
    if [ -n "${HOST}" ]; then
        CMD+=(--host "${HOST}")
    fi
    if [ -n "${PORT}" ]; then
        CMD+=(--port "${PORT}")
    fi
}

warn_missing_config() {
    if [ ! -f "${CONFIG_PATH}" ]; then
        warn "Config file not found: ${CONFIG_PATH}"
        warn "nanobot manager can start with defaults, but adminPassword defaults to changeme."
    fi
}

start_background() {
    install_project
    build_manager_ui
    sync_bundled_config
    warn_missing_config

    mkdir -p "${LOG_DIR}"

    if is_running; then
        info "nanobot manager already running with PID $(cat "${PID_FILE}")"
        return 0
    fi

    manager_command
    info "Starting nanobot manager"
    info "Log file: ${LOG_FILE}"
    (
        cd "${APP_DIR}"
        nohup env PYTHONUNBUFFERED=1 "${CMD[@]}" >>"${LOG_FILE}" 2>&1 &
        printf '%s\n' "$!" >"${PID_FILE}"
    )

    sleep 2
    if is_running; then
        info "Started with PID $(cat "${PID_FILE}")"
        return 0
    fi

    warn "nanobot manager did not stay running. Recent log output:"
    tail -n 40 "${LOG_FILE}" >&2 || true
    error "start failed"
}

run_foreground() {
    install_project
    build_manager_ui
    sync_bundled_config
    warn_missing_config
    manager_command

    info "Running nanobot manager in foreground"
    cd "${APP_DIR}"
    exec env PYTHONUNBUFFERED=1 "${CMD[@]}"
}

stop_background() {
    if ! is_running; then
        warn "nanobot manager is not running"
        return 0
    fi

    local pid
    pid="$(cat "${PID_FILE}")"
    info "Stopping nanobot manager PID ${pid}"
    kill "${pid}"

    local remaining="${STOP_TIMEOUT}"
    while kill -0 "${pid}" 2>/dev/null; do
        if [ "${remaining}" -le 0 ]; then
            error "process did not stop after ${STOP_TIMEOUT}s"
        fi
        sleep 1
        remaining=$((remaining - 1))
    done

    rm -f "${PID_FILE}"
    info "Stopped"
}

show_status() {
    if is_running; then
        info "running PID $(cat "${PID_FILE}")"
    else
        info "stopped"
    fi
    info "App dir: ${APP_DIR}"
    info "Config: ${CONFIG_PATH}"
    info "Log: ${LOG_FILE}"
}

tail_logs() {
    mkdir -p "${LOG_DIR}"
    touch "${LOG_FILE}"
    tail -f "${LOG_FILE}"
}

main() {
    local action="${1:-start}"

    case "${action}" in
        start)
            start_background
            ;;
        run)
            run_foreground
            ;;
        stop)
            stop_background
            ;;
        restart)
            stop_background
            start_background
            ;;
        status)
            show_status
            ;;
        logs)
            tail_logs
            ;;
        install)
            install_project
            build_manager_ui
            sync_bundled_config
            ;;
        -h|--help|help)
            usage
            ;;
        *)
            usage
            error "unknown action: ${action}"
            ;;
    esac
}

main "$@"
