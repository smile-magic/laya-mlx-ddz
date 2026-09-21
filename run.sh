#!/bin/sh
set -eu
cd "$(dirname "$0")"
PYTHON="${LAYA_PYTHON:-.venv/bin/python}"
if [ ! -x "$PYTHON" ]; then
  echo '请先按 README 创建 .venv 并安装依赖。 / Install dependencies in .venv first.' >&2
  exit 1
fi
exec "$PYTHON" -B server.py "$@"
