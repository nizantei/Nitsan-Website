// Step 7: web-ready GLBs. Textures are already WebP (export.py).
//   desktop: full geometry, meshopt compression with fine quantization (the face fills the screen)
//   mobile:  meshopt simplification to ~40% of the triangles (keeps UV seams and the silhouette),
//            then the same compression; textures were halved by export.py
// Writes work/models/nitsan.glb and work/models/nitsan-mobile.glb.
// Run:  node optimize.mjs   (uses the gltf-transform install in work/tools)
import { NodeIO } from '@gltf-transform/core';
import { ALL_EXTENSIONS } from '@gltf-transform/extensions';
import { dedup, prune, weld, meshopt, simplify } from '@gltf-transform/functions';
import { MeshoptEncoder, MeshoptSimplifier } from 'meshoptimizer';
import { fileURLToPath } from 'node:url';
import { statSync } from 'node:fs';

const here = (p) => fileURLToPath(new URL(p, import.meta.url));
await Promise.all([MeshoptEncoder.ready, MeshoptSimplifier.ready]);
const io = new NodeIO().registerExtensions(ALL_EXTENSIONS).registerDependencies({ 'meshopt.encoder': MeshoptEncoder });
const quant = { quantizePosition: 16, quantizeNormal: 12, quantizeTexcoord: 14 };

for (const [src, dst, ratio] of [['build/nitsan_desktop.glb', '../../models/nitsan.glb', 1], ['build/nitsan_mobile.glb', '../../models/nitsan-mobile.glb', 0.4]]) {
  const doc = await io.read(here(src));
  doc.getRoot().getAsset().generator = 'work/tools/model (MakeHuman CC0 base + photo projection)';
  const steps = [dedup(), prune(), weld()];
  if (ratio < 1) steps.push(simplify({ simplifier: MeshoptSimplifier, ratio, error: 0.0004 }));
  steps.push(meshopt({ encoder: MeshoptEncoder, level: 'medium', ...quant }));
  await doc.transform(...steps);
  await io.write(here(dst), doc);
  const tris = doc.getRoot().listMeshes().flatMap((m) => m.listPrimitives()).reduce((n, p) => n + (p.getIndices()?.getCount() ?? 0) / 3, 0);
  console.log(`${dst.replace('../../', 'work/')}: ${(statSync(here(dst)).size / 1e6).toFixed(2)} MB, ${Math.round(tris)} triangles`);
}
