#!/usr/bin/env bash
# Fetches the other free assets, pinned and checksummed, into model/cache (git-ignored):
#   onnx/real_esrgan_x4.onnx  Real-ESRGAN x4 (BSD-3-Clause), photo upscaling
#   onnx/gfpgan_1.4.onnx      GFPGAN v1.4 (Apache-2.0), face detail restoration
#   shoe/...                  "Materials Variants Shoe" © 2021 Shopify (CC BY 4.0), the sneakers
set -euo pipefail
CACHE="$(cd "$(dirname "$0")" && pwd)/cache"
ONNX=https://github.com/facefusion/facefusion-assets/releases/download/models-3.0.0
SHOE=https://raw.githubusercontent.com/KhronosGroup/glTF-Sample-Assets/edc7c9e67c639d230715049ee31f9a96a6babbbe/Models/MaterialsVariantsShoe/glTF-Binary/MaterialsVariantsShoe.glb
get() {  # url, destination, sha256
  if [ -f "$2" ] && echo "$3  $2" | sha256sum -c --status; then return; fi
  mkdir -p "$(dirname "$2")"
  curl -fsSL --retry 3 -o "$2" "$1"
  echo "$3  $2" | sha256sum -c --quiet
}
get "$ONNX/real_esrgan_x4.onnx" "$CACHE/onnx/real_esrgan_x4.onnx" afa7fa42eed0315a3d7b2a54e79e4e44a672d3c0889c2828c4f84c9ab91edb0b
get "$ONNX/gfpgan_1.4.onnx" "$CACHE/onnx/gfpgan_1.4.onnx" accc4757b26bdb89b32b4d3500d4f79c9dff97c1dd7c7104bf9dcb95e3311385
get "$SHOE" "$CACHE/shoe/MaterialsVariantsShoe.glb" e1d7cb190382111e5a5b37b51e9a7f007f7eb2ab1b6185e0188e8d0a0d1265a7
if [ ! -f "$CACHE/shoe/diffuseStreet.jpg" ]; then  # unpack the textures next to it
  node -e "
const {NodeIO}=require('@gltf-transform/core');const {ALL_EXTENSIONS}=require('@gltf-transform/extensions');const fs=require('fs');
new NodeIO().registerExtensions(ALL_EXTENSIONS).read('$CACHE/shoe/MaterialsVariantsShoe.glb').then(doc=>{
for(const t of doc.getRoot().listTextures()) fs.writeFileSync('$CACHE/shoe/'+t.getName(), Buffer.from(t.getImage()));});" 
fi
echo "assets ready in $CACHE"
