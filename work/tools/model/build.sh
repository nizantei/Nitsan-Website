#!/usr/bin/env bash
# Rebuilds the character from the photo + character.json. Each step only needs the previous ones.
#   ./build.sh             the page's low-poly character (default, ~2 minutes)
#   ./build.sh lowpoly     only re-run the low-poly step (after editing character.json → lowpoly)
#   ./build.sh realistic   the earlier photoreal pipeline (~25 minutes); output stays in build/
set -euo pipefail
cd "$(dirname "$0")"
PY=.venv/bin/python
quiet() { grep -v "^Fra:\|DeprecationWarning\|use_nodes\|^W0000\|^I0000\|absl::\|XNNPACK\|inference_feedback\|Info: Baking\|^[0-9:.]* *render\|Read blend\| | INFO: \|Draco\|MeshOptimizer" || true; }
step=${1:-all}
if [ "$step" = all ] || [ "$step" = realistic ]; then
  ./fetch_mpfb.sh
  $PY analyze_photo.py 2>&1 | quiet
  $PY face_corr.py 2>&1 | quiet
  $PY fit_face.py 2>&1 | quiet
fi
if [ "$step" = realistic ]; then
  ./fetch_assets.sh
  $PY enhance_photo.py 2>&1 | quiet
  $PY -c 'import json, shoes; shoes.prep_textures(json.load(open("character.json"))["outfit"]["sneakers"])'
  $PY build_character.py 2>&1 | quiet
  $PY texture.py 2>&1 | quiet
  $PY export.py --preview 2>&1 | quiet
  echo "realistic model: build/nitsan_desktop.glb, build/nitsan_mobile.glb (node optimize.mjs installs them)"
  exit 0
fi
if [ "$step" = all ]; then
  $PY build_character.py --guide 2>&1 | quiet
fi
$PY lowpoly.py --preview 2>&1 | quiet
cp build/nitsan_lowpoly.glb ../../models/nitsan.glb
echo "installed work/models/nitsan.glb; station heights: build/lowpoly_stations.json"
