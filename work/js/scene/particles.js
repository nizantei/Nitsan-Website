// GPU particle field around the figure. Every particle has a home position in each of four
// formations; the shader blends between them, so changing shape per station costs nothing on the CPU.
// Most particles are fine dust; a few large, faint ones read as out-of-focus bokeh. Particles fade
// near the camera and never sit in front of the body, so close-ups stay clean.
import * as THREE from 'three';

export function createParticles({ count, colors }) {
  const geo = new THREE.BufferGeometry();
  const forms = { cloud: [], helix: [], shell: [], ring: [] };
  const seed = new Float32Array(count);
  const size = new Float32Array(count);
  const rnd = mulberry32(7);

  for (let i = 0; i < count; i++) {
    const u = i / count;
    seed[i] = rnd();
    size[i] = 0.3 + Math.pow(rnd(), 9) * 3.4;

    // cloud: loose cylinder of dust around the figure
    {
      const r = 0.85 + Math.pow(rnd(), 1.1) * 2.1;
      const a = rnd() * Math.PI * 2;
      forms.cloud.push(Math.sin(a) * r, Math.pow(rnd(), 1.3) * 2.9 - 0.05, Math.cos(a) * r);
    }
    // helix: two strands spiraling up, with a little scatter
    {
      const strand = i % 2;
      const a = u * Math.PI * 9 + strand * Math.PI;
      const r = 1.0 + (rnd() - 0.5) * 0.18 + (rnd() < 0.15 ? rnd() * 0.6 : 0);
      forms.helix.push(Math.sin(a) * r, u * 2.4 + (rnd() - 0.5) * 0.05, Math.cos(a) * r);
    }
    // shell: points on an ellipsoid enclosing the figure (fibonacci sphere)
    {
      const y = 1 - 2 * ((i + 0.5) / count);
      const r = Math.sqrt(1 - y * y);
      const a = i * 2.399963;
      const j = 1 + (rnd() - 0.5) * 0.06;
      forms.shell.push(Math.cos(a) * r * 1.55 * j, 1.2 + y * 1.25 * j, Math.sin(a) * r * 1.55 * j);
    }
    // ring: concentric bands on the floor, like sound waves
    {
      const band = Math.floor(rnd() * 5);
      const r = 0.9 + band * 0.42 + (rnd() - 0.5) * 0.08;
      const a = rnd() * Math.PI * 2;
      forms.ring.push(Math.sin(a) * r, 0.02 + rnd() * 0.05 + (rnd() < 0.08 ? rnd() * 1.6 : 0), Math.cos(a) * r);
    }
  }

  geo.setAttribute('position', new THREE.Float32BufferAttribute(forms.cloud, 3));
  geo.setAttribute('aCloud', new THREE.Float32BufferAttribute(forms.cloud, 3));
  geo.setAttribute('aHelix', new THREE.Float32BufferAttribute(forms.helix, 3));
  geo.setAttribute('aShell', new THREE.Float32BufferAttribute(forms.shell, 3));
  geo.setAttribute('aRing', new THREE.Float32BufferAttribute(forms.ring, 3));
  geo.setAttribute('aSeed', new THREE.BufferAttribute(seed, 1));
  geo.setAttribute('aSize', new THREE.BufferAttribute(size, 1));
  geo.boundingSphere = new THREE.Sphere(new THREE.Vector3(0, 1.2, 0), 5);

  const uniforms = {
    uTime: { value: 0 },
    uW: { value: new THREE.Vector4(1, 0, 0, 0) },
    uSpin: { value: 0 },
    uEnergy: { value: 0 },
    uSize: { value: 13 },
    uPixelRatio: { value: 1 },
    uOpacity: { value: 0 },
    uColorA: { value: new THREE.Color(colors.a) },
    uColorB: { value: new THREE.Color(colors.b) },
  };

  const material = new THREE.ShaderMaterial({
    uniforms,
    transparent: true,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
    toneMapped: false,
    vertexShader: /* glsl */ `
      uniform float uTime, uSpin, uEnergy, uSize, uPixelRatio;
      uniform vec4 uW;
      attribute vec3 aCloud, aHelix, aShell, aRing;
      attribute float aSeed, aSize;
      varying float vSeed;
      varying float vGlow;
      varying float vSize;
      varying float vFade;
      void main() {
        vec3 p = aCloud * uW.x + aHelix * uW.y + aShell * uW.z + aRing * uW.w;
        float a = uSpin * (0.6 + aSeed * 0.9) + uTime * (0.03 + aSeed * 0.05);
        float s = sin(a), c = cos(a);
        p.xz = mat2(c, -s, s, c) * p.xz;
        p.y += sin(uTime * 0.7 + aSeed * 40.0) * 0.03 + uEnergy * (aSeed - 0.3) * 0.5;
        p.xz *= 1.0 + uEnergy * 0.25 * aSeed;
        vec4 mv = modelViewMatrix * vec4(p, 1.0);
        float depth = -mv.z;
        gl_Position = projectionMatrix * mv;
        gl_PointSize = min(uSize * aSize * (1.0 + uEnergy * 0.8) * uPixelRatio / depth, 40.0 * uPixelRatio);
        // Fade out close to the camera and far away, and keep the space in front of the body clear.
        float front = smoothstep(-0.02, 0.22, p.z) * (1.0 - smoothstep(0.2, 0.42, abs(p.x)));
        vFade = smoothstep(0.3, 0.9, depth) * smoothstep(14.0, 6.0, depth) * (1.0 - front * 0.94);
        vSeed = aSeed;
        vSize = aSize;
        vGlow = 0.55 + 0.45 * sin(uTime * 2.0 + aSeed * 60.0);
      }`,
    fragmentShader: /* glsl */ `
      uniform vec3 uColorA, uColorB;
      uniform float uOpacity;
      varying float vSeed;
      varying float vGlow;
      varying float vSize;
      varying float vFade;
      void main() {
        float d = length(gl_PointCoord - 0.5);
        float bokeh = smoothstep(1.1, 2.6, vSize);
        // Dust: a bright core with a soft falloff. Bokeh: a flatter, faint disc.
        float a = pow(smoothstep(0.5, 0.0, d), mix(2.2, 0.9, bokeh));
        vec3 col = mix(uColorA, uColorB, step(0.72, vSeed));
        col = mix(col, vec3(1.0), smoothstep(0.16, 0.0, d) * 0.5 * (1.0 - bokeh));
        gl_FragColor = vec4(col, a * uOpacity * vGlow * vFade * mix(1.0, 0.2, bokeh));
        #include <colorspace_fragment>
      }`,
  });

  const points = new THREE.Points(geo, material);
  points.name = 'particles';
  points.frustumCulled = false;
  return { points, uniforms };
}

function mulberry32(a) {
  return () => {
    a |= 0; a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
