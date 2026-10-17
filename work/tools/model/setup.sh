#!/usr/bin/env bash
# One-time setup of the model pipeline's Python environment (CPU only, no GPU needed).
set -euo pipefail
cd "$(dirname "$0")"
if command -v uv >/dev/null; then
  uv venv .venv --python 3.13 -q && VIRTUAL_ENV=$PWD/.venv uv pip install -q -r requirements.txt
else
  python3.13 -m venv .venv && .venv/bin/pip install -q -r requirements.txt
fi
ldconfig -p | grep -q libEGL.so.1 || echo "note: MediaPipe needs libEGL (e.g. sudo apt-get install libegl1)"
(cd .. && npm install --no-audit --no-fund >/dev/null)  # gltf-transform for optimize.mjs
echo "ready: ./build.sh"
