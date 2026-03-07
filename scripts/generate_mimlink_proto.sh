#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PROTO_DIR="$ROOT_DIR/src/pyglaze/mimlink/proto"
VENV_BIN="$ROOT_DIR/.venv/bin"

command -v buf >/dev/null 2>&1 || { echo "error: missing 'buf' on PATH" >&2; exit 1; }

if [ -d "$VENV_BIN" ]; then
  export PATH="$VENV_BIN:$PATH"
fi

command -v protoc-gen-mypy >/dev/null 2>&1 || { echo "error: missing 'protoc-gen-mypy' in the Python dev environment" >&2; exit 1; }

[ -f "$PROTO_DIR/envelope.proto" ] || { echo "error: missing $PROTO_DIR/envelope.proto" >&2; exit 1; }

buf lint
buf generate

echo "Generated: $PROTO_DIR/envelope_pb2.py, $PROTO_DIR/envelope_pb2.pyi"
