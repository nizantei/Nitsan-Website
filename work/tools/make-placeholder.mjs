// Builds the placeholder figure (a stylized 1.8 m mannequin) as a meshopt-compressed GLB.
// It uses the same conventions the real model will follow, so swapping models is a file change:
//   glTF 2.0 binary, 1 unit = 1 m, Y up, facing +Z, feet on y = 0, centered on the origin.
// Run:  npm run placeholder   →  work/models/placeholder-figure.glb
import * as THREE from 'three';
import { mergeGeometries } from 'three/examples/jsm/utils/BufferGeometryUtils.js';
import { Document, NodeIO } from '@gltf-transform/core';
import { EXTMeshoptCompression, KHRMeshQuantization } from '@gltf-transform/extensions';
import { meshopt } from '@gltf-transform/functions';
import { MeshoptEncoder } from 'meshoptimizer';
import { fileURLToPath } from 'node:url';

const V = (x, y, z) => new THREE.Vector3(x, y, z);

// Parts are grouped by material. Colors are taken from the reference photo
// (black tee, khaki trousers, black belt); shoes are a guess because the photo ends above the knee.
const MATERIALS = {
  skin: { color: '#c98f74', roughness: 0.55, metalness: 0.0 },
  shirt: { color: '#141518', roughness: 0.82, metalness: 0.0 },
  pants: { color: '#a3916f', roughness: 0.78, metalness: 0.0 },
  belt: { color: '#0c0c0e', roughness: 0.35, metalness: 0.2 },
  shoes: { color: '#1a1512', roughness: 0.4, metalness: 0.1 },
};
const parts = Object.fromEntries(Object.keys(MATERIALS).map((k) => [k, []]));

function ellipsoid(mat, c, r, [sx, sy, sz] = [1, 1, 1]) {
  const g = new THREE.SphereGeometry(r, 48, 32);
  g.scale(sx, sy, sz);
  g.translate(c.x, c.y, c.z);
  parts[mat].push(g);
}

// Tapered capsule from a to b: radius r1 at a, r2 at b.
function limb(mat, a, b, r1, r2 = r1) {
  const len = a.distanceTo(b);
  const pts = [];
  const caps = 10;
  for (let i = 0; i <= caps; i++) {
    const t = -Math.PI / 2 + (i / caps) * (Math.PI / 2);
    pts.push(new THREE.Vector2(Math.cos(t) * r1, -len / 2 + Math.sin(t) * r1));
  }
  for (let i = 0; i <= caps; i++) {
    const t = (i / caps) * (Math.PI / 2);
    pts.push(new THREE.Vector2(Math.cos(t) * r2, len / 2 + Math.sin(t) * r2));
  }
  const g = new THREE.LatheGeometry(pts, 40);
  g.applyQuaternion(new THREE.Quaternion().setFromUnitVectors(V(0, 1, 0), b.clone().sub(a).normalize()));
  const m = a.clone().add(b).multiplyScalar(0.5);
  g.translate(m.x, m.y, m.z);
  parts[mat].push(g);
}

// Lathe profile [radius, height] pairs, flattened front-to-back.
function lathe(mat, profile, depth = 0.62) {
  const g = new THREE.LatheGeometry(profile.map(([r, y]) => new THREE.Vector2(r, y)), 64);
  g.scale(1, 1, depth);
  parts[mat].push(g);
}

// Torso: shirt above the belt (broad chest, tapered waist), trousers below.
lathe('shirt', [
  [0.0, 0.955], [0.148, 0.958], [0.15, 1.0], [0.146, 1.06], [0.152, 1.14], [0.172, 1.23],
  [0.192, 1.32], [0.2, 1.39], [0.196, 1.44], [0.17, 1.48], [0.12, 1.515], [0.06, 1.53], [0.0, 1.535],
]);
lathe('belt', [[0.0, 0.925], [0.153, 0.925], [0.155, 0.94], [0.153, 0.958], [0.0, 0.958]]);
lathe('pants', [[0.0, 0.84], [0.12, 0.85], [0.152, 0.89], [0.151, 0.93], [0.0, 0.93]]);

// Head and neck
ellipsoid('skin', V(0, 1.675, 0.005), 0.1, [0.9, 1.14, 1.0]);
ellipsoid('skin', V(0, 1.618, 0.02), 0.062, [1.0, 0.9, 1.0]); // jaw
limb('skin', V(0, 1.48, -0.005), V(0, 1.61, 0.0), 0.056, 0.05);

// Arms crossed over the chest, as in the photo. +x is the figure's left side.
for (const s of [-1, 1]) {
  const shoulder = V(0.205 * s, 1.43, -0.01);
  const elbow = V(0.255 * s, 1.15, 0.05);
  ellipsoid('shirt', shoulder, 0.075);
  limb('shirt', shoulder, V(0.23 * s, 1.3, 0.015), 0.068, 0.062); // sleeve
  limb('skin', V(0.23 * s, 1.31, 0.015), elbow, 0.055, 0.045);
  ellipsoid('skin', elbow, 0.046);
}
// Forearms cross: the figure's right forearm in front, left behind.
limb('skin', V(-0.255, 1.15, 0.05), V(0.17, 1.2, 0.205), 0.045, 0.034);
limb('skin', V(0.255, 1.15, 0.05), V(-0.17, 1.22, 0.145), 0.043, 0.033);
ellipsoid('skin', V(0.215, 1.215, 0.17), 0.045, [0.7, 1.0, 1.25]); // right hand on left biceps
ellipsoid('skin', V(-0.205, 1.235, 0.11), 0.042, [0.7, 1.0, 1.2]); // left hand tucked

// Legs (not in the photo): straight trousers with a slight break, dark shoes.
for (const s of [-1, 1]) {
  const hip = V(0.09 * s, 0.87, 0);
  const knee = V(0.1 * s, 0.5, 0.012);
  const ankle = V(0.105 * s, 0.1, -0.005);
  limb('pants', hip, knee, 0.088, 0.066);
  limb('pants', knee, ankle, 0.066, 0.058);
  ellipsoid('shoes', V(0.108 * s, 0.045, 0.045), 0.055, [0.92, 0.82, 2.2]);
}

const doc = new Document();
doc.getRoot().getAsset().generator = 'work/tools/make-placeholder.mjs';
const buffer = doc.createBuffer();
const accessor = (type, array) => doc.createAccessor().setType(type).setArray(array).setBuffer(buffer);
const mesh = doc.createMesh('Figure');
let triangles = 0;

for (const [name, spec] of Object.entries(MATERIALS)) {
  const merged = mergeGeometries(parts[name].map((g) => { g.deleteAttribute('uv'); return g; }));
  triangles += merged.index.count / 3;
  const c = new THREE.Color(spec.color); // hex is sRGB; THREE.Color stores linear, as glTF expects
  const material = doc.createMaterial(name)
    .setBaseColorFactor([c.r, c.g, c.b, 1])
    .setRoughnessFactor(spec.roughness)
    .setMetallicFactor(spec.metalness);
  mesh.addPrimitive(doc.createPrimitive()
    .setAttribute('POSITION', accessor('VEC3', new Float32Array(merged.attributes.position.array)))
    .setAttribute('NORMAL', accessor('VEC3', new Float32Array(merged.attributes.normal.array)))
    .setIndices(accessor('SCALAR', new Uint32Array(merged.index.array)))
    .setMaterial(material));
}
doc.createScene('Scene').addChild(doc.createNode('Figure').setMesh(mesh));

await MeshoptEncoder.ready;
await doc.transform(meshopt({ encoder: MeshoptEncoder, level: 'medium' }));

const out = fileURLToPath(new URL('../models/placeholder-figure.glb', import.meta.url));
await new NodeIO()
  .registerExtensions([EXTMeshoptCompression, KHRMeshQuantization])
  .registerDependencies({ 'meshopt.encoder': MeshoptEncoder })
  .write(out, doc);

console.log(`wrote ${out}: ${triangles} triangles`);
