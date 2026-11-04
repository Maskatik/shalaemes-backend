#!/bin/sh
set -e

DATA_DIR="${SHALAEMES_DATA_DIR:-/data}"

if [ "$(id -u)" = "0" ]; then
    mkdir -p "$DATA_DIR"
    chown -R app:app "$DATA_DIR"
    exec gosu app python run_server.py
fi

exec python run_server.py
