#!/usr/bin/env bash
# Rebuilds the character from the photo + character.json. Each step only needs the previous ones.
#   ./build.sh            full rebuild
#   ./build.sh texture    from texturing on (after editing texture rules)
set -euo pipefail
cd "$(dirname "$0")"
PY=.venv/bin/python
quiet() { grep -v "^Fra:\|DeprecationWarning\|use_nodes\|^W0000\|^I0000\|absl::\|XNNPACK\|inference_feedback\|Info: Baking\|^[0-9:.]* *render\|Read blend\| | INFO: " || true; }
step=${1:-all}
if [ "$step" = all ]; then
  ./fetch_mpfb.sh
  $PY analyze_photo.py 2>&1 | quiet
  $PY face_corr.py 2>&1 | quiet
  $PY fit_face.py 2>&1 | quiet
  $PY build_character.py 2>&1 | quiet
fi
if [ "$step" = all ] || [ "$step" = texture ]; then
  $PY texture.py 2>&1 | quiet
fi
$PY export.py --preview 2>&1 | quiet
node optimize.mjs
