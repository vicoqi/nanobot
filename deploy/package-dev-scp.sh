#!/usr/bin/env bash
set -euo pipefail

# Pull the GitHub dev branch into this script directory, package it as a tarball,
# and send the tarball to a remote server with scp.
#
# Usage:
#   ./deploy/package-dev-scp.sh
#   ./deploy/package-dev-scp.sh user@server:/path/to/releases/  # optional override
#
# Optional env vars:
#   REPO_URL       Git repository URL. Defaults to this repo's origin URL, then vicoqi/nanobot.
#   BRANCH         Git branch to package. Defaults to dev.
#   CHECKOUT_DIR   Local checkout path. Defaults to <script_dir>/.checkout-dev.
#   ARTIFACT_DIR   Local archive output path. Defaults to <script_dir>/artifacts.
#   SCP_OPTS       Extra options passed to scp, for example "-P 2222".
#   BUNDLED_CONFIG Local manager config copied into the archive when present.
#   REMOTE_DEST    scp destination. Defaults to ubuntu@124.221.70.154:~/

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

BRANCH="${BRANCH:-dev}"
DEFAULT_REPO_URL="https://github.com/vicoqi/nanobot.git"
if [ -d "${PROJECT_ROOT}/.git" ]; then
    DEFAULT_REPO_URL="$(git -C "${PROJECT_ROOT}" config --get remote.origin.url || printf '%s' "${DEFAULT_REPO_URL}")"
fi
REPO_URL="${REPO_URL:-${DEFAULT_REPO_URL}}"

DEFAULT_REMOTE_DEST="ubuntu@124.221.70.154:~/"
CHECKOUT_DIR="${CHECKOUT_DIR:-${SCRIPT_DIR}/.checkout-${BRANCH}}"
ARTIFACT_DIR="${ARTIFACT_DIR:-${SCRIPT_DIR}/artifacts}"
REMOTE_DEST="${1:-${REMOTE_DEST:-${DEFAULT_REMOTE_DEST}}}"
SCP_OPTS="${SCP_OPTS:-}"
BUNDLED_CONFIG="${BUNDLED_CONFIG:-${SCRIPT_DIR}/manager-config.json}"

mkdir -p "$(dirname "${CHECKOUT_DIR}")" "$(dirname "${ARTIFACT_DIR}")"
CHECKOUT_DIR="$(cd "$(dirname "${CHECKOUT_DIR}")" && pwd)/$(basename "${CHECKOUT_DIR}")"
ARTIFACT_DIR="$(cd "$(dirname "${ARTIFACT_DIR}")" && pwd)/$(basename "${ARTIFACT_DIR}")"

info() { printf '[INFO] %s\n' "$*"; }
warn() { printf '[WARN] %s\n' "$*" >&2; }
error() { printf '[ERROR] %s\n' "$*" >&2; exit 1; }

usage() {
    cat <<EOF
Usage:
  $0
  $0 user@server:/remote/path/          # optional override
  REMOTE_DEST=user@server:/remote/path/ $0

Optional env vars:
  REPO_URL       Git repository URL (default: ${REPO_URL})
  BRANCH         Git branch to package (default: dev)
  CHECKOUT_DIR   Checkout dir (default: ${SCRIPT_DIR}/.checkout-dev)
  ARTIFACT_DIR   Archive dir (default: ${SCRIPT_DIR}/artifacts)
  REMOTE_DEST    scp destination (default: ${DEFAULT_REMOTE_DEST})
  SCP_OPTS       Extra scp options, for example "-P 2222"
  BUNDLED_CONFIG Local manager config copied into archive when present
                 (default: ${SCRIPT_DIR}/manager-config.json)
EOF
}

require_command() {
    command -v "$1" >/dev/null 2>&1 || error "$1 not found"
}

require_script_dir_path() {
    case "$1" in
        "${SCRIPT_DIR}"/*) ;;
        *) error "$2 must be inside the script directory: ${SCRIPT_DIR}" ;;
    esac
}

clone_or_update() {
    require_script_dir_path "${CHECKOUT_DIR}" "CHECKOUT_DIR"

    if [ -d "${CHECKOUT_DIR}/.git" ]; then
        info "Updating ${CHECKOUT_DIR} from ${REPO_URL} (${BRANCH})"
        git -C "${CHECKOUT_DIR}" remote set-url origin "${REPO_URL}"
        git -C "${CHECKOUT_DIR}" fetch --prune origin "${BRANCH}"
        git -C "${CHECKOUT_DIR}" reset --hard "origin/${BRANCH}"
        git -C "${CHECKOUT_DIR}" clean -fdx
    else
        if [ -e "${CHECKOUT_DIR}" ]; then
            error "CHECKOUT_DIR exists but is not a git checkout: ${CHECKOUT_DIR}"
        fi
        info "Cloning ${REPO_URL} (${BRANCH}) into ${CHECKOUT_DIR}"
        git clone --branch "${BRANCH}" --single-branch "${REPO_URL}" "${CHECKOUT_DIR}"
    fi
}

overlay_deploy_files() {
    mkdir -p "${CHECKOUT_DIR}/deploy"

    if [ -f "${SCRIPT_DIR}/start-from-archive.sh" ]; then
        info "Adding deploy/start-from-archive.sh to archive source"
        cp "${SCRIPT_DIR}/start-from-archive.sh" "${CHECKOUT_DIR}/deploy/start-from-archive.sh"
        chmod +x "${CHECKOUT_DIR}/deploy/start-from-archive.sh"
    else
        warn "deploy/start-from-archive.sh not found; archive will not include a start script"
    fi

    if [ -f "${BUNDLED_CONFIG}" ]; then
        info "Adding deploy/manager-config.json to archive source"
        cp "${BUNDLED_CONFIG}" "${CHECKOUT_DIR}/deploy/manager-config.json"
        chmod 600 "${CHECKOUT_DIR}/deploy/manager-config.json" 2>/dev/null || true
    else
        warn "manager config not found at ${BUNDLED_CONFIG}; archive will not include it"
    fi
}

create_archive() {
    require_script_dir_path "${ARTIFACT_DIR}" "ARTIFACT_DIR"
    mkdir -p "${ARTIFACT_DIR}"

    local short_sha timestamp archive_name
    short_sha="$(git -C "${CHECKOUT_DIR}" rev-parse --short HEAD)"
    timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
    archive_name="nanobot-${BRANCH}-${short_sha}-${timestamp}.tar.gz"
    ARCHIVE_PATH="${ARTIFACT_DIR}/${archive_name}"

    info "Creating archive ${ARCHIVE_PATH}"
    tar \
        --exclude=".git" \
        --exclude=".venv" \
        --exclude="venv" \
        --exclude="__pycache__" \
        --exclude=".pytest_cache" \
        --exclude=".mypy_cache" \
        --exclude=".ruff_cache" \
        --exclude="node_modules" \
        -czf "${ARCHIVE_PATH}" \
        -C "${CHECKOUT_DIR}" \
        .
}

send_archive() {
    info "Sending archive to ${REMOTE_DEST}"
    if [ -n "${SCP_OPTS}" ]; then
        # shellcheck disable=SC2086
        scp ${SCP_OPTS} "${ARCHIVE_PATH}" "${REMOTE_DEST}"
    else
        scp "${ARCHIVE_PATH}" "${REMOTE_DEST}"
    fi
}

main() {
    if [ "${REMOTE_DEST}" = "-h" ] || [ "${REMOTE_DEST}" = "--help" ]; then
        usage
        exit 0
    fi

    [ -n "${REMOTE_DEST}" ] || { usage; error "remote destination is required"; }

    require_command git
    require_command tar
    require_command scp

    clone_or_update
    overlay_deploy_files
    create_archive
    send_archive

    info "Done: ${ARCHIVE_PATH}"
}

main "$@"
