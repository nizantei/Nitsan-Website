// Soft contact shadow under the feet: the figure's lowest surfaces seen from below the floor,
// darker the closer they are to it, then blurred. The figure only sways around its own axis, so
// the shadow lives in the figure's space and is rendered once, after the model loads.
import * as THREE from 'three';

const BLUR = {
  uniforms: { tDiffuse: { value: null }, uStep: { value: new THREE.Vector2() } },
  vertexShader: /* glsl */ `varying vec2 vUv; void main() { vUv = uv; gl_Position = vec4(position.xy, 0.0, 1.0); }`,
  fragmentShader: /* glsl */ `
    uniform sampler2D tDiffuse; uniform vec2 uStep; varying vec2 vUv;
    void main() {
      vec4 s = texture2D(tDiffuse, vUv) * 0.2270270270;
      s += texture2D(tDiffuse, vUv + uStep * 1.3846153846) * 0.3162162162;
      s += texture2D(tDiffuse, vUv - uStep * 1.3846153846) * 0.3162162162;
      s += texture2D(tDiffuse, vUv + uStep * 3.2307692308) * 0.0702702703;
      s += texture2D(tDiffuse, vUv - uStep * 3.2307692308) * 0.0702702703;
      gl_FragColor = s;
    }`,
};

export function createContactShadow(renderer, figure, { size = 1.5, height = 0.5, darkness = 1.4, res = 512 } = {}) {
  const opts = { type: THREE.HalfFloatType };
  const rtA = new THREE.WebGLRenderTarget(res, res, opts);
  const rtB = new THREE.WebGLRenderTarget(res, res, opts);
  rtA.texture.generateMipmaps = rtB.texture.generateMipmaps = false;

  const group = new THREE.Group();
  group.name = 'contact-shadow';

  const material = new THREE.MeshBasicMaterial({ map: rtA.texture, color: 0x000000, transparent: true, depthWrite: false, opacity: 0 });
  const plane = new THREE.Mesh(new THREE.PlaneGeometry(size, size).rotateX(Math.PI / 2), material);
  plane.scale.y = -1; // faces up; the texture is seen from below
  plane.position.y = 0.002;
  plane.renderOrder = 0;
  group.add(plane);

  const cam = new THREE.OrthographicCamera(-size / 2, size / 2, size / 2, -size / 2, 0, height);
  cam.rotation.x = Math.PI / 2; // look up from the floor
  group.add(cam);

  const depth = new THREE.MeshDepthMaterial();
  depth.depthTest = false;
  depth.depthWrite = false;
  depth.onBeforeCompile = (shader) => {
    shader.uniforms.uDarkness = { value: darkness };
    shader.fragmentShader = `uniform float uDarkness;\n${shader.fragmentShader.replace(
      'gl_FragColor = vec4( vec3( 1.0 - fragCoordZ ), opacity );',
      'gl_FragColor = vec4( vec3( 0.0 ), ( 1.0 - fragCoordZ ) * uDarkness );',
    )}`;
  };

  const blur = new THREE.ShaderMaterial({ ...BLUR, uniforms: THREE.UniformsUtils.clone(BLUR.uniforms), depthTest: false, depthWrite: false });
  const quad = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), blur);
  quad.frustumCulled = false;
  const quadScene = new THREE.Scene();
  quadScene.add(quad);
  const quadCam = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);

  function pass(from, to, x, y) {
    blur.uniforms.tDiffuse.value = from.texture;
    blur.uniforms.uStep.value.set(x / res, y / res);
    renderer.setRenderTarget(to);
    renderer.render(quadScene, quadCam);
  }

  function render() {
    const prevTarget = renderer.getRenderTarget();
    const prevClear = renderer.getClearAlpha();
    const prevAuto = renderer.shadowMap.autoUpdate;
    renderer.shadowMap.autoUpdate = false;
    group.updateMatrixWorld(true);

    // The figure alone, with every mesh drawn in the depth material.
    const swapped = [];
    figure.traverse((o) => { if (o.isMesh) { swapped.push([o, o.material]); o.material = depth; } });
    renderer.setRenderTarget(rtA);
    renderer.setClearColor(0x000000, 0);
    renderer.clear();
    renderer.render(figure, cam);
    swapped.forEach(([o, m]) => { o.material = m; });

    for (const r of [2.2, 1.4, 0.7]) { pass(rtA, rtB, r, 0); pass(rtB, rtA, 0, r); }

    renderer.setRenderTarget(prevTarget);
    renderer.setClearAlpha(prevClear);
    renderer.shadowMap.autoUpdate = prevAuto;
  }

  return {
    group,
    render,
    set opacity(v) { material.opacity = v; },
    get opacity() { return material.opacity; },
  };
}
