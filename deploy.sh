#!/usr/bin/env bash
set -euo pipefail

# Configuration
REMOTE_USER="${DEPLOY_USER:-root}"
REMOTE_HOST="${DEPLOY_HOST:-}"
REMOTE_DIR="/opt/polydrop"

# Allow passing host as first argument (takes priority)
if [ "${1:-}" ]; then
    REMOTE_HOST="$1"
fi

if [ -z "$REMOTE_HOST" ]; then
    echo "Error: Set DEPLOY_HOST env var or pass as argument"
    echo "Usage: DEPLOY_HOST=1.2.3.4 ./deploy.sh"
    echo "   or: ./deploy.sh 1.2.3.4"
    exit 1
fi

TARGET="${REMOTE_USER}@${REMOTE_HOST}"

echo "==> Syncing to ${TARGET}:${REMOTE_DIR}"
rsync -avz --delete \
    --exclude '.venv' \
    --exclude '.git' \
    --exclude '__pycache__' \
    --exclude '.ruff_cache' \
    --exclude 'ui/node_modules' \
    --exclude 'ui/dist' \
    --exclude 'data/*.db' \
    --exclude 'data/*.db-journal' \
    --exclude 'docs/' \
    --exclude 'scripts/' \
    --exclude '.claude/' \
    ./ "${TARGET}:${REMOTE_DIR}/"

echo "==> Building and starting services"
ssh "${TARGET}" "cd ${REMOTE_DIR} && docker compose up -d --build"

echo "==> Showing logs (Ctrl+C to stop)"
ssh "${TARGET}" "cd ${REMOTE_DIR} && docker compose logs -f --tail=50"
