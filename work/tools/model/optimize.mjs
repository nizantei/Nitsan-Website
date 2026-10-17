// Step 7: web-ready GLBs. Meshopt geometry compression + quantization (textures are already WebP
// from export.py). Writes work/models/nitsan.glb (desktop) and work/models/nitsan-mobile.glb.
// Run:  node optimize.mjs   (uses the gltf-transform install in work/tools)
import { NodeIO } from '@gltf-transform/core';
import { ALL_EXTENSIONS } from '@gltf-transform/extensions';
import { dedup, prune, weld, meshopt } from '@gltf-transform/functions';
import { MeshoptEncoder } from 'meshoptimizer';
import { fileURLToPath } from 'node:url';
import { statSync } from 'node:fs';

const here = (p) => fileURLToPath(new URL(p, import.meta.url));
await MeshoptEncoder.ready;
const io = new NodeIO().registerExtensions(ALL_EXTENSIONS).registerDependencies({ 'meshopt.encoder': MeshoptEncoder });

for (const [src, dst] of [['build/nitsan_desktop.glb', '../../models/nitsan.glb'], ['build/nitsan_mobile.glb', '../../models/nitsan-mobile.glb']]) {
  const doc = await io.read(here(src));
  doc.getRoot().getAsset().generator = 'work/tools/model (MakeHuman CC0 base + photo projection)';
  await doc.transform(dedup(), prune(), weld(), meshopt({ encoder: MeshoptEncoder, level: 'medium' }));
  await io.write(here(dst), doc);
  const tris = doc.getRoot().listMeshes().flatMap((m) => m.listPrimitives()).reduce((n, p) => n + (p.getIndices()?.getCount() ?? 0) / 3, 0);
  console.log(`${dst.replace('../../', 'work/')}: ${(statSync(here(dst)).size / 1e6).toFixed(2)} MB, ${Math.round(tris)} triangles`);
}
