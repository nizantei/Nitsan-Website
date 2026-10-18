// The 3D stage: renderer and post-processing, camera, lights, the figure, particles, floor and
// station reveals. Driven each frame by the director's state; owns no timing beyond smoothing.
import * as THREE from 'three';
import { RoomEnvironment, EffectComposer, RenderPass, UnrealBloomPass, OutputPass } from 'three/addons';
import { createFigureUniforms, loadFigure } from './figure.js';
import { createParticles } from './particles.js';
import { createFloor } from './floor.js';
import { createContactShadow } from './contact-shadow.js';
import { createReveal } from './reveals.js';
import { createTextures, createLabels } from './helpers.js';
import { asset, damp, lerp, smoothstep, easeInOutCubic } from '../util.js';
import { COMPACT_QUERY } from '../env.js';

export async function createStage({ canvas, env, content, config, onProgress }) {
  const quality = config.quality[env.quality];
  const C = config.colors;
  const post = quality.msaa > 0 || quality.bloom;

  const renderer = new THREE.WebGLRenderer({ canvas, antialias: !post, alpha: true, powerPreference: 'high-performance' });
  renderer.setClearColor(0x000000, 0);
  // Khronos PBR Neutral keeps the photo-based skin and fabric colors faithful.
  renderer.toneMapping = THREE.NeutralToneMapping;
  renderer.toneMappingExposure = config.exposure;
  renderer.shadowMap.enabled = !!quality.shadows;
  renderer.shadowMap.type = THREE.PCFShadowMap;
  let dpr = Math.min(window.devicePixelRatio || 1, quality.maxDpr);
  renderer.setPixelRatio(dpr);

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(30, 1, 0.05, 60);

  // Soft studio reflections: gives eyes, leather and metal their highlights.
  const pmrem = new THREE.PMREMGenerator(renderer);
  scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
  scene.environmentIntensity = 0.5;
  pmrem.dispose();

  // Studio lighting: warm key from the front right (casts the figure's own shadows), a cool soft
  // fill from the left, and two brand-colored rims from behind.
  const key = new THREE.DirectionalLight(C.light, 2.0);
  key.position.set(1.7, 3.3, 3.4);
  key.target.position.set(0, 1.0, 0);
  if (quality.shadows) {
    key.castShadow = true;
    key.shadow.mapSize.set(2048, 2048);
    Object.assign(key.shadow.camera, { left: -0.7, right: 0.7, top: 1.2, bottom: -1.2, near: 2.5, far: 7.5 });
    key.shadow.bias = -0.0005;
    key.shadow.normalBias = 0.015;
    key.shadow.radius = 3;
  }
  const fill = new THREE.DirectionalLight('#cfd8ff', 0.6);
  fill.position.set(-3, 1.3, 2.4);
  const rimA = new THREE.DirectionalLight(C.a, 1.1);
  rimA.position.set(-3.5, 2.4, -2.6);
  const rimB = new THREE.DirectionalLight(C.b, 0.8);
  rimB.position.set(3.5, 1.8, -3);
  scene.add(key, key.target, fill, rimA, rimB, new THREE.HemisphereLight('#3a4a9a', '#05060d', 0.35));

  const figureUniforms = createFigureUniforms(C);
  const modelUrl = env.quality === 'low' && config.model.urlLow ? config.model.urlLow : config.model.url;
  const { root: figure } = await loadFigure(asset(modelUrl), {
    height: config.model.height,
    uniforms: figureUniforms,
    materials: config.figure.materials,
    onProgress,
  });
  const anisotropy = Math.min(8, renderer.capabilities.getMaxAnisotropy());
  figure.traverse((o) => {
    if (!o.isMesh) return;
    o.castShadow = o.receiveShadow = !!quality.shadows;
    (Array.isArray(o.material) ? o.material : [o.material]).forEach((m) => {
      for (const k of ['map', 'normalMap', 'roughnessMap', 'metalnessMap', 'aoMap', 'clearcoatNormalMap']) if (m[k]) m[k].anisotropy = anisotropy;
    });
  });
  const turntable = new THREE.Group();
  turntable.add(figure);
  scene.add(turntable);

  const contact = createContactShadow(renderer, figure, { size: 1.5, height: 0.45 });
  turntable.add(contact.group);
  contact.render();

  const floor = createFloor({ colors: C });
  const particles = createParticles({ count: quality.particles, colors: C });
  const halo = createHalo(C);
  scene.add(floor.mesh, particles.points, halo.mesh);

  let dirty = 3; // frames still to render in on-demand (static) mode
  const textures = createTextures(renderer, { onChange: () => { dirty = 3; } });
  const labels = createLabels(document.querySelector('.labels'));
  const size = new THREE.Vector2();
  const layout = { compact: false, size, clear: config.layout.clear };

  const reveals = content.chapters.map((chapter) => {
    const r = createReveal(chapter.reveal, { chapter, textures, colors: C, floor, labels });
    scene.add(r.group);
    r.persistent?.forEach((o) => scene.add(o));
    r.presence = 0;
    r.calm = 0;
    r.focus = [];
    r.anchor = { y: chapter.station.y * config.model.height, span: chapter.station.span, width: chapter.station.width };
    return r;
  });

  // ---- post-processing (high tier): MSAA, a bloom that only catches emissive highlights ----
  let composer = null;
  if (post) {
    const target = new THREE.WebGLRenderTarget(1, 1, { type: THREE.HalfFloatType, samples: quality.msaa });
    composer = new EffectComposer(renderer, target);
    composer.addPass(new RenderPass(scene, camera));
    if (quality.bloom) {
      const bloom = new UnrealBloomPass(new THREE.Vector2(1, 1), config.bloom.strength, config.bloom.radius, config.bloom.threshold);
      // Add the glow to the color only: the canvas stays transparent over the page backdrop, and
      // glow over empty areas lights the backdrop additively.
      Object.assign(bloom.blendMaterial, {
        blending: THREE.CustomBlending, blendEquation: THREE.AddEquation,
        blendSrc: THREE.OneFactor, blendDst: THREE.OneFactor, blendSrcAlpha: THREE.ZeroFactor, blendDstAlpha: THREE.OneFactor,
      });
      composer.addPass(bloom);
    }
    composer.addPass(new OutputPass());
  }
  const draw = () => (composer ? composer.render() : renderer.render(scene, camera));

  // Compile every material up front so stations don't hitch the first time they appear.
  reveals.forEach((r) => { r.group.visible = true; });
  await renderer.compileAsync(scene, camera);
  reveals.forEach((r) => { r.group.visible = false; });

  // ---- sizing: ignore mobile address-bar height jitter by sizing to the large viewport ----
  const lvh = document.createElement('div');
  lvh.style.cssText = 'position:absolute;left:0;top:0;width:1px;height:100vh;height:100lvh;visibility:hidden;pointer-events:none';
  document.body.appendChild(lvh);

  function applySize() {
    renderer.setPixelRatio(dpr);
    renderer.setSize(size.x, size.y, false);
    if (composer) { composer.setPixelRatio(dpr); composer.setSize(size.x, size.y); }
    particles.uniforms.uPixelRatio.value = dpr;
  }

  function resize() {
    const w = window.innerWidth;
    const h = lvh.offsetHeight || window.innerHeight;
    layout.compact = matchMedia(COMPACT_QUERY).matches;
    if (w === size.x && h === size.y) return;
    size.set(w, h);
    camera.aspect = w / h;
    applySize();
    dirty = 3;
  }
  resize();

  // Station anchors follow the director's framings (they depend on the screen's shape).
  function setStops(stops) {
    stops.forEach((s) => { if (s.kind === 'chapter') reveals[s.chapter].anchor.span = s.pose.span; });
    dirty = 3;
  }

  // ---- pointer parallax (desktop) ----
  const pointer = { x: 0, y: 0, tx: 0, ty: 0 };
  if (!env.touch) {
    addEventListener('pointermove', (e) => {
      pointer.tx = (e.clientX / window.innerWidth) * 2 - 1;
      pointer.ty = (e.clientY / window.innerHeight) * 2 - 1;
    }, { passive: true });
  }

  const cur = { rot: 0, camY: 1, lookY: 1, dist: 5, fov: 30, shiftX: 0, shiftY: 0, span: 2 };
  const formation = new THREE.Vector4(1, 0, 0, 0);
  const target4 = new THREE.Vector4();
  let motion = env.mode === 'cinematic';
  let first = true;
  let introT = motion ? 0 : 1;
  let introStart = -1; // wall-clock based, so slow devices don't get a slow intro
  let spin = 0;
  let lastStop = -1;
  let haloY = 0, haloA = 0;
  const perf = { acc: 0, n: 0, fps: 0, warm: 0 };

  function frame(state, dt, time, velocity = 0) {
    const L = (a, b, lambda) => (motion && !first ? damp(a, b, lambda, dt) : b);
    const P = state.pose;
    const t = motion ? time : 0;

    // camera and figure
    for (const k of ['camY', 'lookY', 'dist', 'fov', 'shiftX', 'shiftY', 'span']) cur[k] = L(cur[k], P[k], 3.4);
    cur.rot = L(cur.rot, P.rot, 3.2);
    pointer.x = L(pointer.x, motion ? pointer.tx : 0, 2.5);
    pointer.y = L(pointer.y, motion ? pointer.ty : 0, 2.5);

    const par = cur.dist * 0.035; // parallax scales with distance, so close-ups stay steady
    camera.fov = cur.fov;
    camera.position.set(pointer.x * par, cur.camY - pointer.y * par * 0.5, cur.dist);
    camera.lookAt(0, cur.lookY, 0);
    camera.setViewOffset(size.x, size.y, -cur.shiftX * size.x, cur.shiftY * size.y, size.x, size.y);
    camera.updateProjectionMatrix();

    const energy = Math.sin(Math.PI * state.travel); // 0 at stops, 1 mid-transition
    turntable.rotation.y = cur.rot + (motion ? Math.sin(t * 0.5) * 0.035 * (1 - energy) : 0);
    turntable.scale.y = 1 + (motion ? Math.sin(t * 1.3) * 0.0016 : 0); // breathing

    // materialize from the floor up, then the scan crosses the view during transitions
    if (introStart >= 0 && introT < 1) introT = Math.min(1, (performance.now() - introStart) / 2600);
    const intro = easeInOutCubic(introT);
    const H = config.model.height;
    figureUniforms.uTime.value = t;
    figureUniforms.uReveal.value = lerp(-0.15, H + 0.3, intro);
    const introScan = introT > 0 && introT < 1;
    figureUniforms.uScanY.value = introScan ? figureUniforms.uReveal.value - 0.02 : state.scanY;
    figureUniforms.uScan.value = motion ? (introScan ? 1 : energy) : 0;
    figureUniforms.uScanW.value = Math.min(0.035, Math.max(0.008, cur.span * 0.016)); // thin at close range
    figureUniforms.uHolo.value = L(figureUniforms.uHolo.value, motion ? energy * 0.6 : 0, 6);
    figureUniforms.uRim.value = config.figure.rim + energy * config.figure.rimTravel;
    contact.opacity = intro * 0.9;

    // particles
    formation.lerp(target4.fromArray(state.formation), motion && !first ? 1 - Math.exp(-2.2 * dt) : 1);
    particles.uniforms.uW.value.copy(formation);
    const u = particles.uniforms;
    u.uEnergy.value = L(u.uEnergy.value, motion ? Math.max(energy, Math.min(1, Math.abs(velocity) / 5000)) : 0, 4);
    spin += motion ? dt * (0.1 + u.uEnergy.value * 2.2) : 0;
    u.uSpin.value = spin;
    u.uTime.value = t;
    u.uOpacity.value = intro * 0.8;

    floor.uniforms.uTime.value = t;
    floor.uniforms.uPulse.value = figureUniforms.uScan.value * smoothstep(0.35, 0.0, figureUniforms.uScanY.value);

    // halo: a thin ring around the body under the station in view
    const atStation = state.chapter >= 0 && state.chapter < reveals.length && state.segment === 'stop';
    haloY = L(haloY, Math.max(0.012, cur.lookY - cur.span * 0.34), 4);
    haloA = L(haloA, atStation && introT >= 1 ? 1 : 0, 3);
    halo.update(haloY, atStation ? reveals[state.chapter].anchor.width : 0.5, haloA, t);

    // station reveals
    const rdt = motion ? dt : 10; // on-demand mode: settle instantly
    const compact = layout.compact;
    labels.begin();
    reveals.forEach((r, i) => {
      r.presence = L(r.presence, state.presence[i] * (introT >= 1 ? 1 : 0), 2.2);
      const beat = state.chapter === i ? state.beats[i] : -1;
      r.focus.length = 0;
      if (beat >= 0) {
        if (compact) r.focus.push(beat);
        else r.focus.push(beat * 2, beat * 2 + 1);
      }
      r.calm = L(r.calm, beat >= 0 || !motion ? 1 : 0, 2.6); // the static layout always shows its cards
      r.update({ presence: r.presence, focus: r.focus, calm: r.calm, dt: rdt, time: t, camera, layout, anchor: r.anchor });
    });
    labels.end();

    first = false;
    if (!motion) {
      if (state.stop !== lastStop) dirty = 2;
      lastStop = state.stop;
      if (dirty <= 0) return;
      dirty--;
    } else {
      adaptQuality(dt);
    }
    draw();
  }

  // If frames run slow, step resolution down (never below 1x).
  function adaptQuality(dt) {
    if (perf.warm < 2) { perf.warm += dt; return; }
    perf.acc += dt; perf.n++;
    if (perf.n < 90) return;
    const avg = perf.acc / perf.n;
    perf.fps = Math.round(1 / avg);
    if (avg > 1 / 36 && dpr > 1) {
      dpr = Math.max(1, dpr - 0.25);
      applySize();
    }
    perf.acc = 0; perf.n = 0;
  }

  return {
    frame,
    resize,
    setStops,
    startIntro() { if (motion) introStart = performance.now(); else introT = 1; dirty = 3; },
    setMotion(on) { motion = on; if (!on) introT = 1; first = true; dirty = 3; },
    settle() { first = true; dirty = 3; }, // jump straight to the target framing (debug/screenshots)
    get info() { return { dpr, fps: perf.fps, calls: renderer.info.render.calls, tris: renderer.info.render.triangles }; },
  };
}

// A thin glowing ring around the body. Drawn with depth so the body hides its back half, and
// faded in front of the body's center so it never crosses the figure.
function createHalo(colors) {
  const uniforms = {
    uA: { value: 0 }, uTime: { value: 0 },
    uColorA: { value: new THREE.Color(colors.a) }, uColorB: { value: new THREE.Color(colors.b) },
  };
  const mesh = new THREE.Mesh(
    new THREE.RingGeometry(0.97, 1.03, 160, 1).rotateX(-Math.PI / 2),
    new THREE.ShaderMaterial({
      uniforms, transparent: true, depthWrite: false, toneMapped: false, side: THREE.DoubleSide,
      // Light added to the color only, so the transparent canvas keeps its alpha.
      blending: THREE.CustomBlending, blendSrc: THREE.SrcAlphaFactor, blendDst: THREE.OneFactor,
      blendSrcAlpha: THREE.ZeroFactor, blendDstAlpha: THREE.OneFactor,
      vertexShader: /* glsl */ `
        varying vec3 vP;
        void main() { vP = position; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`,
      fragmentShader: /* glsl */ `
        uniform float uA, uTime; uniform vec3 uColorA, uColorB;
        varying vec3 vP;
        void main() {
          float r = length(vP.xz);
          float line = smoothstep(0.03, 0.0, abs(r - 1.0));
          float ang = atan(vP.x, vP.z);
          float back = smoothstep(0.25, -0.35, cos(ang)); // only the half behind the body
          float dash = 0.65 + 0.35 * smoothstep(0.2, 0.8, sin(ang * 18.0 - uTime * 0.8));
          vec3 col = mix(uColorA, uColorB, 0.5 + 0.5 * sin(ang + uTime * 0.3));
          gl_FragColor = vec4(col, line * dash * back * uA);
          #include <colorspace_fragment>
        }`,
    }),
  );
  mesh.renderOrder = 2;
  mesh.name = 'halo';
  return {
    mesh,
    update(y, width, a, time) {
      mesh.visible = a > 0.003;
      mesh.position.y = y;
      mesh.scale.setScalar(width / 2 + 0.06);
      uniforms.uA.value = a * 0.55;
      uniforms.uTime.value = time;
    },
  };
}
