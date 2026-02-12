#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PROTO_DIR="$ROOT_DIR/src/pyglaze/mimlink/proto"
NANOPB_FALLBACK_PLUGIN="$ROOT_DIR/../MimLink/extern/nanopb/generator/protoc-gen-nanopb"
NANOPB_VENV_PLUGIN="$ROOT_DIR/.venv/bin/protoc-gen-nanopb"

fail() {
  echo "error: $*" >&2
  exit 1
}

require_cmd() {
  local cmd="$1"
  command -v "$cmd" >/dev/null 2>&1 || fail "missing '$cmd' on PATH"
}

require_cmd "buf"
require_cmd "protoc"

if command -v protoc-gen-nanopb >/dev/null 2>&1; then
  NANOPB_PLUGIN_DIR="$(dirname "$(command -v protoc-gen-nanopb)")"
elif [ -x "$NANOPB_VENV_PLUGIN" ]; then
  NANOPB_PLUGIN_DIR="$(dirname "$NANOPB_VENV_PLUGIN")"
  echo "info: using nanopb plugin from local venv at $NANOPB_VENV_PLUGIN"
elif [ -x "$NANOPB_FALLBACK_PLUGIN" ]; then
  NANOPB_PLUGIN_DIR="$(dirname "$NANOPB_FALLBACK_PLUGIN")"
  echo "info: using fallback nanopb plugin at $NANOPB_FALLBACK_PLUGIN"
else
  fail "missing 'protoc-gen-nanopb'. Install with 'uv pip install nanopb' or provide $NANOPB_FALLBACK_PLUGIN"
fi

if [ ! -f "$PROTO_DIR/envelope.proto" ]; then
  fail "missing proto schema at $PROTO_DIR/envelope.proto"
fi

PATH="$NANOPB_PLUGIN_DIR:$PATH" buf lint
PATH="$NANOPB_PLUGIN_DIR:$PATH" buf generate

echo "Generated:"
echo "  - $PROTO_DIR/envelope_pb2.py"
echo "  - $PROTO_DIR/nanopb/envelope.pb.h"
echo "  - $PROTO_DIR/nanopb/envelope.pb.c"
