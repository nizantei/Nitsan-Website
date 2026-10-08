// Loads the figure (any glTF/GLB) and layers the page's effects onto its own materials, so the
// real model keeps its textures and gets the same treatment as the placeholder:
//   • dissolve: everything above uReveal (world height) is cut away with a noisy, glowing edge
//   • scan: a bright horizontal band at uScanY
//   • rim: fresnel edge light in the two brand colors
//   • holo: hologram scanlines, used while the figure turns between sections
import * as THREE from 'three';
import { GLTFLoader, MeshoptDecoder } from 'three/addons';

export function createFigureUniforms(colors) {
  return {
    uTime: { value: 0 },
    uReveal: { value: -0.2 },
    uScanY: { value: -1 },
    uScan: { value: 0 },
    uHolo: { value: 0 },
    uRim: { value: 1 },
    uRimA: { value: new THREE.Color(colors.a) },
    uRimB: { value: new THREE.Color(colors.b) },
    uScanColor: { value: new THREE.Color(colors.scan) },
  };
}

export async function loadFigure(url, { height, uniforms, onProgress }) {
  const loader = new GLTFLoader();
  loader.setMeshoptDecoder(MeshoptDecoder);
  const gltf = await loader.loadAsync(url, (e) => {
    if (e.lengthComputable && e.total) onProgress?.(e.loaded / e.total);
  });

  const model = gltf.scene;
  const patched = new WeakSet();
  model.traverse((o) => {
    if (!o.isMesh) return;
    const mats = Array.isArray(o.material) ? o.material : [o.material];
    mats.forEach((m) => {
      if (!patched.has(m)) {
        patchMaterial(m, uniforms);
        patched.add(m);
      }
    });
  });

  // Normalize: requested height, feet on the floor, centered on the vertical axis.
  const box = new THREE.Box3().setFromObject(model, true);
  const size = box.getSize(new THREE.Vector3());
  model.scale.multiplyScalar(height / (size.y || 1));
  box.setFromObject(model, true);
  const center = box.getCenter(new THREE.Vector3());
  model.position.x -= center.x;
  model.position.z -= center.z;
  model.position.y -= box.min.y;

  const root = new THREE.Group();
  root.name = 'figure';
  root.add(model);
  return { root, gltf };
}

const NOISE = /* glsl */ `
  uniform float uTime, uReveal, uScanY, uScan, uHolo, uRim;
  uniform vec3 uRimA, uRimB, uScanColor;
  varying vec3 vFigWorld;
  float figHash(vec3 p) { p = fract(p * 0.3183099 + 0.1); p *= 17.0; return fract(p.x * p.y * p.z * (p.x + p.y + p.z)); }
  float figNoise(vec3 x) {
    vec3 i = floor(x); vec3 f = fract(x); f = f * f * (3.0 - 2.0 * f);
    return mix(mix(mix(figHash(i), figHash(i + vec3(1,0,0)), f.x), mix(figHash(i + vec3(0,1,0)), figHash(i + vec3(1,1,0)), f.x), f.y),
               mix(mix(figHash(i + vec3(0,0,1)), figHash(i + vec3(1,0,1)), f.x), mix(figHash(i + vec3(0,1,1)), figHash(i + vec3(1,1,1)), f.x), f.y), f.z);
  }
`;

function patchMaterial(material, uniforms) {
  material.onBeforeCompile = (shader) => {
    Object.assign(shader.uniforms, uniforms);
    shader.vertexShader = shader.vertexShader
      .replace('#include <common>', '#include <common>\nvarying vec3 vFigWorld;')
      .replace('#include <project_vertex>', '#include <project_vertex>\nvFigWorld = (modelMatrix * vec4(transformed, 1.0)).xyz;');
    shader.fragmentShader = shader.fragmentShader
      .replace('#include <common>', `#include <common>\n${NOISE}`)
      .replace('#include <clipping_planes_fragment>', /* glsl */ `#include <clipping_planes_fragment>
        float figN = figNoise(vFigWorld * 14.0 + vec3(0.0, uTime * 0.6, 0.0));
        float figEdge = vFigWorld.y - uReveal + figN * 0.12;
        if (figEdge > 0.0) discard;
        float figEdgeGlow = smoothstep(-0.07, 0.0, figEdge);`)
      .replace('#include <emissivemap_fragment>', /* glsl */ `#include <emissivemap_fragment>
        float figFres = pow(1.0 - clamp(abs(dot(normalize(normal), normalize(vViewPosition))), 0.0, 1.0), 2.4);
        vec3 figRim = mix(uRimA, uRimB, smoothstep(0.2, 1.7, vFigWorld.y)) * figFres * uRim;
        float figScan = exp(-pow((vFigWorld.y - uScanY) / 0.03, 2.0)) * uScan;
        float figLines = smoothstep(0.86, 1.0, sin(vFigWorld.y * 260.0 - uTime * 3.0) * 0.5 + 0.5) * uHolo;
        totalEmissiveRadiance += figRim + uScanColor * (figScan * 2.5 + figEdgeGlow * 3.0) + uRimA * figLines * (0.35 + figFres);`);
  };
  material.customProgramCacheKey = () => 'work-figure-fx';
  material.needsUpdate = true;
}
