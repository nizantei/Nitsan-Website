#!/usr/bin/env bash
# Fetches the MakeHuman / MPFB2 data this pipeline uses (CC0 assets) at a pinned commit.
# Only the needed folders are checked out. Output: model/cache/mpfb2 (git-ignored).
set -euo pipefail
COMMIT=d0a32e57a7f915cb2f2b95410e2117648c7bbb7e
DEST="$(cd "$(dirname "$0")" && pwd)/cache/mpfb2"
if [ -f "$DEST/.fetched-$COMMIT" ]; then echo "mpfb2 data already at $COMMIT"; exit 0; fi
rm -rf "$DEST"
git clone -q --filter=blob:none --no-checkout https://github.com/makehumancommunity/mpfb2 "$DEST"
cd "$DEST"
git sparse-checkout init --no-cone
git sparse-checkout set \
  /LICENSE.ASSETS.md \
  /src/mpfb/data/3dobjs/ \
  /src/mpfb/data/mesh_metadata/ \
  /src/mpfb/data/rigs/standard/ \
  '/src/mpfb/data/targets/*' '!/src/mpfb/data/targets/_images/' '!/src/mpfb/data/targets/breast/' '!/src/mpfb/data/targets/genitals/'
git checkout -q "$COMMIT"
touch ".fetched-$COMMIT"
echo "mpfb2 data at $COMMIT in $DEST"
