// The 3D stage: renderer, camera, lights, the figure, particles, floor and section reveals.
// Driven each frame by the director's state; owns no timing of its own beyond smoothing.
import * as THREE from 'three';
import { RoomEnvironment } from 'three/addons';
import { createFigureUniforms, loadFigure } from './figure.js';
import { createParticles } from './particles.js';
import { createFloor } from './floor.js';
import { createReveal } from './reveals.js';
import { createTextures, createLabels } from './helpers.js';
import { asset, damp, lerp, smoothstep, easeInOutCubic } from '../util.js';
import { COMPACT_QUERY } from '../env.js';

export async function createStage({ canvas, env, content, config, onProgress }) {
  const quality = config.quality[env.quality];
  const C = config.colors;

  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true, powerPreference: 'high-performance' });
  renderer.setClearColor(0x000000, 0);
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.05;
  let dpr = Math.min(window.devicePixelRatio || 1, quality.maxDpr);
  renderer.setPixelRatio(dpr);

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(30, 1, 0.1, 60);

  const pmrem = new THREE.PMREMGenerator(renderer);
  scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
  scene.environmentIntensity = 0.55;
  pmrem.dispose();

  const key = new THREE.DirectionalLight(C.light, 1.4);
  key.position.set(2.2, 4, 3.5);
  const rimA = new THREE.DirectionalLight(C.a, 2.4);
  rimA.position.set(-3.5, 2.2, -2.5);
  const rimB = new THREE.DirectionalLight(C.b, 1.8);
  rimB.position.set(3.5, 1.6, -3);
  scene.add(key, rimA, rimB, new THREE.HemisphereLight('#3a4a9a', '#05060d', 0.6));

  const figureUniforms = createFigureUniforms(C);
  const { root: figure } = await loadFigure(asset(config.model.url), {
    height: config.model.height,
    uniforms: figureUniforms,
    onProgress,
  });
  const turntable = new THREE.Group();
  turntable.add(figure);
  scene.add(turntable);

  const floor = createFloor({ colors: C });
  const particles = createParticles({ count: quality.particles, colors: C });
  scene.add(floor.mesh, particles.points);

  let dirty = 3; // frames still to render in on-demand (static) mode
  const textures = createTextures(renderer, { onChange: () => { dirty = 3; } });
  const labels = createLabels(document.querySelector('.labels'));
  const size = new THREE.Vector2();
  const layout = { compact: false, size };

  const reveals = content.chapters.map((chapter) => {
    const r = createReveal(chapter.reveal, { chapter, textures, colors: C, floor, labels });
    scene.add(r.group);
    r.persistent?.forEach((o) => scene.add(o));
    r.presence = 0;
    r.layout = { compact: false, side: chapter.side, size };
    return r;
  });

  // Compile every material up front so sections don't hitch the first time they appear.
  reveals.forEach((r) => { r.group.visible = true; });
  await renderer.compileAsync(scene, camera);
  reveals.forEach((r) => { r.group.visible = false; });

  // ---- sizing: ignore mobile address-bar height jitter by sizing to the large viewport ----
  const lvh = document.createElement('div');
  lvh.style.cssText = 'position:absolute;left:0;top:0;width:1px;height:100vh;height:100lvh;visibility:hidden;pointer-events:none';
  document.body.appendChild(lvh);

  function resize() {
    const w = window.innerWidth;
    const h = lvh.offsetHeight || window.innerHeight;
    layout.compact = matchMedia(COMPACT_QUERY).matches;
    reveals.forEach((r) => { r.layout.compact = layout.compact; });
    if (w === size.x && h === size.y) return;
    size.set(w, h);
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    particles.uniforms.uPixelRatio.value = dpr;
    dirty = 3;
  }
  resize();

  // ---- pointer parallax (desktop) ----
  const pointer = { x: 0, y: 0, tx: 0, ty: 0 };
  if (!env.touch) {
    addEventListener('pointermove', (e) => {
      pointer.tx = (e.clientX / window.innerWidth) * 2 - 1;
      pointer.ty = (e.clientY / window.innerHeight) * 2 - 1;
    }, { passive: true });
  }

  const cur = { rot: 0, camY: 1, lookY: 1, dist: 5, fov: 30, shiftX: 0, shiftY: 0 };
  const formation = new THREE.Vector4(1, 0, 0, 0);
  const target4 = new THREE.Vector4();
  let motion = env.mode === 'cinematic';
  let first = true;
  let introT = motion ? 0 : 1;
  let introStart = -1; // wall-clock based, so slow devices don't get a slow intro
  let spin = 0;
  let lastStop = -1;
  const perf = { acc: 0, n: 0, fps: 0, warm: 0 };

  function frame(state, dt, time, velocity = 0) {
    const L = (a, b, lambda) => (motion && !first ? damp(a, b, lambda, dt) : b);
    const P = state.pose;
    const t = motion ? time : 0;

    // camera and figure
    for (const k of ['camY', 'lookY', 'dist', 'fov', 'shiftX', 'shiftY']) cur[k] = L(cur[k], P[k], 3.2);
    cur.rot = L(cur.rot, P.rot, 3.6);
    pointer.x = L(pointer.x, motion ? pointer.tx : 0, 2.5);
    pointer.y = L(pointer.y, motion ? pointer.ty : 0, 2.5);

    camera.fov = cur.fov;
    camera.position.set(pointer.x * 0.18, cur.camY - pointer.y * 0.1, cur.dist);
    camera.lookAt(0, cur.lookY, 0);
    camera.setViewOffset(size.x, size.y, -cur.shiftX * size.x, cur.shiftY * size.y, size.x, size.y);
    camera.updateProjectionMatrix();

    const energy = Math.sin(Math.PI * state.travel); // 0 at stops, 1 mid-transition
    turntable.rotation.y = cur.rot + (motion ? Math.sin(t * 0.55) * 0.05 * (1 - energy) : 0);
    turntable.scale.y = 1 + (motion ? Math.sin(t * 1.3) * 0.003 : 0);

    // materialize from the floor up, then scan sweeps during transitions
    if (introStart >= 0 && introT < 1) introT = Math.min(1, (performance.now() - introStart) / 2600);
    const intro = easeInOutCubic(introT);
    const H = config.model.height;
    figureUniforms.uTime.value = t;
    figureUniforms.uReveal.value = lerp(-0.15, H + 0.3, intro);
    const introScan = introT > 0 && introT < 1;
    figureUniforms.uScanY.value = introScan ? figureUniforms.uReveal.value - 0.02 : lerp(-0.1, H + 0.1, state.travel);
    figureUniforms.uScan.value = motion ? (introScan ? 1 : energy) : 0;
    figureUniforms.uHolo.value = L(figureUniforms.uHolo.value, motion ? energy * 0.9 : 0, 6);
    figureUniforms.uRim.value = 0.9 + energy * 0.7;

    // particles
    formation.lerp(target4.fromArray(state.formation), motion && !first ? 1 - Math.exp(-2.2 * dt) : 1);
    particles.uniforms.uW.value.copy(formation);
    const u = particles.uniforms;
    u.uEnergy.value = L(u.uEnergy.value, motion ? Math.max(energy, Math.min(1, Math.abs(velocity) / 5000)) : 0, 4);
    spin += motion ? dt * (0.12 + u.uEnergy.value * 2.4) : 0;
    u.uSpin.value = spin;
    u.uTime.value = t;
    u.uOpacity.value = intro * 0.75;

    floor.uniforms.uTime.value = t;
    floor.uniforms.uPulse.value = figureUniforms.uScan.value * smoothstep(0.35, 0.0, figureUniforms.uScanY.value);

    // section reveals
    const rdt = motion ? dt : 10; // on-demand mode: settle instantly
    labels.begin();
    reveals.forEach((r, i) => {
      r.presence = L(r.presence, state.presence[i] * (introT >= 1 ? 1 : 0), 2.2);
      const active = state.chapter === i ? state.items[i] : -1;
      r.update({ presence: r.presence, active, dt: rdt, time: t, camera, layout: r.layout });
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
    renderer.render(scene, camera);
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
      renderer.setPixelRatio(dpr);
      renderer.setSize(size.x, size.y, false);
      particles.uniforms.uPixelRatio.value = dpr;
    }
    perf.acc = 0; perf.n = 0;
  }

  return {
    frame,
    resize,
    startIntro() { if (motion) introStart = performance.now(); else introT = 1; dirty = 3; },
    setMotion(on) { motion = on; if (!on) introT = 1; first = true; dirty = 3; },
    get info() { return { dpr, fps: perf.fps, calls: renderer.info.render.calls, tris: renderer.info.render.triangles }; },
  };
}
