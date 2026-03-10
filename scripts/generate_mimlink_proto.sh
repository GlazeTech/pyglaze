#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PROTO_DIR="$ROOT_DIR/src/pyglaze/mimlink/proto"

command -v buf >/dev/null 2>&1 || { echo "error: missing 'buf' on PATH" >&2; exit 1; }

[ -f "$PROTO_DIR/envelope.proto" ] || { echo "error: missing $PROTO_DIR/envelope.proto" >&2; exit 1; }

buf lint
buf generate

echo "Generated: $PROTO_DIR/envelope_pb2.py, $PROTO_DIR/envelope_pb2.pyi"
