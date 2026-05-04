#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
TARGET="${BE_MY_LENS_WINDOWS_REPO:-/mnt/c/Users/Keenan/be-my-lens}"

if [[ ! -d "$TARGET" ]]; then
    echo "Windows repo not found: $TARGET" >&2
    exit 1
fi

cd "$ROOT"

rsync -a --delete \
    --exclude='.git/' \
    --exclude='.gradle/' \
    --exclude='.idea/' \
    --exclude='.kotlin/' \
    --exclude='app/build/' \
    --exclude='build/' \
    --exclude='captures/' \
    --exclude='local.properties' \
    --exclude='server/.env' \
    --exclude='server/.venv/' \
    --exclude='__pycache__/' \
    --exclude='*.iml' \
    --exclude='*.apk' \
    --exclude='*.aab' \
    --exclude='*.deb' \
    --exclude='screenshot.png' \
    --exclude='phonelens/' \
    "$ROOT/" "$TARGET/"

echo "Synced $ROOT -> $TARGET"
