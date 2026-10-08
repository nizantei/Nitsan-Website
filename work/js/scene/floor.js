// Floor: a soft contact shadow under the feet, a glowing ring that lights up when the scan
// passes the feet, faint concentric guides, and expanding ripples (used by the talks stage).
import * as THREE from 'three';

export function createFloor({ colors }) {
  const uniforms = {
    uTime: { value: 0 },
    uRipple: { value: 0 },
    uPulse: { value: 0 },
    uOpacity: { value: 1 },
    uColorA: { value: new THREE.Color(colors.a) },
    uColorB: { value: new THREE.Color(colors.b) },
  };
  const material = new THREE.ShaderMaterial({
    uniforms,
    transparent: true,
    depthWrite: false,
    toneMapped: false,
    vertexShader: /* glsl */ `
      varying vec2 vP;
      void main() { vP = position.xy; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`,
    fragmentShader: /* glsl */ `
      uniform float uTime, uRipple, uPulse, uOpacity;
      uniform vec3 uColorA, uColorB;
      varying vec2 vP;
      void main() {
        float r = length(vP);
        float fade = smoothstep(5.5, 0.6, r);
        float shadow = smoothstep(0.75, 0.0, r) * 0.75;
        float guides = smoothstep(0.012, 0.0, abs(fract(r * 1.25) - 0.5) - 0.488) * 0.10 * fade;
        float halo = smoothstep(0.03, 0.0, abs(r - 0.62)) * (0.25 + uPulse * 1.6);
        float ripple = 0.0;
        for (int i = 0; i < 3; i++) {
          float rr = fract(uTime * 0.22 + float(i) / 3.0) * 4.5;
          ripple += smoothstep(0.05, 0.0, abs(r - rr)) * (1.0 - rr / 4.5);
        }
        ripple *= uRipple;
        // Shadow darkens what is behind (the canvas is transparent); glow adds light on top.
        vec3 glow = mix(uColorA, uColorB, smoothstep(0.5, 4.0, r)) * (guides + halo + ripple * 0.7);
        float a = clamp(shadow + max(glow.r, max(glow.g, glow.b)), 0.0, 1.0);
        gl_FragColor = vec4(min(glow / max(a, 0.001), vec3(1.0)), a * uOpacity);
        #include <colorspace_fragment>
      }`,
  });
  const mesh = new THREE.Mesh(new THREE.PlaneGeometry(12, 12), material);
  mesh.rotation.x = -Math.PI / 2;
  mesh.position.y = 0.001;
  mesh.renderOrder = -1;
  mesh.name = 'floor';
  return { mesh, uniforms };
}
