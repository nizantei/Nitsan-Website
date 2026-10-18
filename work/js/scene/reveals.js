// Station effects: the "special objects" revealed around the figure. Each section's `reveal` in
// content.json picks one. They all take the same inputs every frame:
//   presence 0..1 (damped: entering/leaving), focus (indices of the works on screen),
//   calm 0..1 (1 while the cards are on screen: objects step back and dim, so the 3D plays
//   while the camera travels and the cards own the stop),
//   anchor { y, span, width } (station height, how much of the body is in view, body width).
// Everything is sized from the anchor, so a reveal works at any station. Objects never sit in front
// of the body: anything passing in front of the figure fades out, so the face stays clear.
// Objects are generated from the section's items, so they follow the item count automatically.
import * as THREE from 'three';
import { roundedRect } from './helpers.js';
import { clamp, damp, lerp, smoothstep, stagger, easeOutBack, easeOutCubic } from '../util.js';

export function createReveal(kind, ctx) {
  const make = { orbit, stage, constellation, medals }[kind] ?? orbit;
  return make(ctx);
}

const TAU = Math.PI * 2;
const tmp = new THREE.Vector3();
const faceCamera = (obj, camera) => { obj.rotation.y = Math.atan2(camera.position.x - obj.position.x, camera.position.z - obj.position.z); };

// 0 when an object (half size r) is in front of the body, 1 elsewhere.
function clearOfBody(x, z, anchor, r) {
  const front = smoothstep(-0.03, 0.06, z);
  const inside = 1 - smoothstep(anchor.width / 2, anchor.width / 2 + r + 0.05, Math.abs(x));
  return 1 - front * inside;
}

// While the cards are on screen: dimmer, a little smaller, a little further out.
const calmAlpha = (calm) => lerp(1, 0.3, calm);
const calmScale = (calm) => lerp(1, 0.82, calm);

// While the cards are on screen, objects behind them (the side columns on desktop, the bottom
// sheet on phones) all but disappear, so nothing peeks out around a card.
const ndc = new THREE.Vector3();
function screenFade(pos, camera, layout, calm) {
  if (calm < 0.01) return 1;
  ndc.copy(pos).project(camera);
  // Phones: the sheet covers the bottom, and the narrow screen leaves little room beside the body.
  const covered = layout.compact
    ? Math.max(smoothstep(0.1, -0.2, ndc.y), 0.7)
    : smoothstep(layout.clear - 0.05, layout.clear + 0.08, Math.abs(ndc.x));
  return 1 - covered * calm * 0.9;
}

// Ring radius around the body that stays inside the view.
const ringRadius = (anchor, layout, k) => Math.min(anchor.width / 2 + anchor.span * k, anchor.span * (layout.size.x / layout.size.y) * 0.4);

function mediaTexture(item, textures, onAspect) {
  if (item.image) return textures.get(item.image, (t) => onAspect?.(t.image.width / t.image.height));
  onAspect?.(1.6);
  return textures.label(item.title);
}

/* Apps: a ring of small screens orbiting the body; the works on screen glow. */
function orbit({ chapter, textures, colors }) {
  const group = new THREE.Group();
  const items = chapter.items;
  let spin = 0;
  const screens = items.map((item, i) => {
    const holder = new THREE.Group();
    const mat = new THREE.MeshBasicMaterial({ transparent: true, opacity: 0, toneMapped: false, side: THREE.DoubleSide, depthWrite: false });
    const glowMat = new THREE.MeshBasicMaterial({ color: colors.a, transparent: true, opacity: 0, blending: THREE.AdditiveBlending, depthWrite: false, toneMapped: false });
    const mesh = new THREE.Mesh(roundedRect(1, 0.625, 0.05), mat);
    const glow = new THREE.Mesh(roundedRect(1.06, 0.685, 0.07), glowMat);
    glow.position.z = -0.004;
    mat.map = mediaTexture(item, textures, (aspect) => {
      const w = aspect >= 1 ? 1 : 0.64;
      const h = w / aspect;
      mesh.geometry.dispose(); mesh.geometry = roundedRect(w, h, 0.05);
      glow.geometry.dispose(); glow.geometry = roundedRect(w + 0.06, h + 0.06, 0.07);
    });
    holder.add(glow, mesh);
    group.add(holder);
    return { holder, mat, glowMat, focus: 0, base: (i / Math.max(1, items.length)) * TAU, yOff: Math.sin(i * 2.3) };
  });

  return {
    group,
    update({ presence, focus, calm, dt, time, camera, anchor, layout }) {
      group.visible = presence > 0.002;
      if (!group.visible) return;
      spin += dt * (0.22 - calm * 0.12);
      const R = ringRadius(anchor, layout, 0.34) * lerp(1, 1.08, calm);
      const size = anchor.span * 0.19 * calmScale(calm);
      screens.forEach((s, i) => {
        const p = stagger(presence, i, screens.length, 0.5);
        s.focus = damp(s.focus, focus.includes(i) ? 1 : 0, 3.5, dt);
        const a = s.base + spin;
        const x = Math.sin(a) * R;
        const z = Math.cos(a) * R;
        s.holder.position.set(
          x,
          anchor.y + s.yOff * anchor.span * 0.18 + Math.sin(time * 0.8 + i) * anchor.span * 0.012 - (1 - easeOutCubic(p)) * anchor.span * 0.6,
          z,
        );
        s.holder.scale.setScalar(Math.max(0.001, easeOutBack(p)) * size * (1 + s.focus * 0.15));
        faceCamera(s.holder, camera);
        s.holder.rotation.z = Math.sin(a) * 0.12;
        const clear = clearOfBody(x, z, anchor, size * 0.5) * screenFade(s.holder.position, camera, layout, calm);
        const behind = z < -0.1 * R ? 0.55 : 1;
        s.mat.opacity = p * behind * clear * calmAlpha(calm) * (1 + s.focus * calm * 0.8);
        s.glowMat.opacity = p * clear * (0.08 + s.focus * 0.35) * calmAlpha(calm);
      });
    },
  };
}

/* Talks: a stage light pours down on the figure, slides hang behind it, the floor ripples. */
function stage({ chapter, textures, colors, floor }) {
  const group = new THREE.Group();
  const coneUniforms = { uOpacity: { value: 0 }, uColor: { value: new THREE.Color(colors.light) }, uTime: { value: 0 } };
  const cone = new THREE.Mesh(
    new THREE.ConeGeometry(1.1, 3.8, 96, 1, true),
    new THREE.ShaderMaterial({
      uniforms: coneUniforms,
      transparent: true, depthWrite: false, side: THREE.DoubleSide, blending: THREE.AdditiveBlending, toneMapped: false,
      vertexShader: /* glsl */ `
        varying vec3 vN; varying vec3 vV; varying float vH;
        void main() {
          vH = position.y / 3.8 + 0.5;
          vec4 mv = modelViewMatrix * vec4(position, 1.0);
          vN = normalize(normalMatrix * normal); vV = normalize(-mv.xyz);
          gl_Position = projectionMatrix * mv;
        }`,
      fragmentShader: /* glsl */ `
        uniform vec3 uColor; uniform float uOpacity, uTime;
        varying vec3 vN; varying vec3 vV; varying float vH;
        void main() {
          float facing = pow(abs(dot(vN, vV)), 2.5);
          float a = facing * (0.12 + 0.88 * pow(vH, 1.4)) * uOpacity * 0.32;
          a *= 0.85 + 0.15 * sin(vH * 40.0 - uTime * 1.5);
          gl_FragColor = vec4(uColor, a);
          #include <colorspace_fragment>
        }`,
    }),
  );
  cone.position.y = 1.9;
  group.add(cone);

  // Lights stay in the scene permanently (intensity 0 when unused): adding or removing a light
  // would recompile every lit material mid-scroll.
  const spot = new THREE.SpotLight(colors.light, 0, 9, 0.42, 0.7, 1.5);
  spot.position.set(0, 4.3, 0.4);
  spot.target.position.set(0, 0.9, 0);

  const items = chapter.items;
  const slides = items.map((item, i) => {
    const mat = new THREE.MeshBasicMaterial({ transparent: true, opacity: 0, toneMapped: false, depthWrite: false });
    const mesh = new THREE.Mesh(roundedRect(1, 0.5625, 0.025), mat);
    mat.map = mediaTexture(item, textures, (aspect) => { mesh.geometry.dispose(); mesh.geometry = roundedRect(1, 1 / aspect, 0.025); });
    group.add(mesh);
    return { mesh, mat, focus: 0, t: items.length > 1 ? i / (items.length - 1) - 0.5 : 0, lift: Math.cos(i * 1.7) };
  });

  return {
    group,
    persistent: [spot, spot.target],
    update({ presence, focus, calm, dt, time, camera, anchor, layout }) {
      group.visible = presence > 0.002;
      floor.uniforms.uRipple.value = presence;
      spot.intensity = presence * 40;
      if (!group.visible) return;
      coneUniforms.uOpacity.value = easeOutCubic(presence) * lerp(1, 0.6, calm);
      coneUniforms.uTime.value = time;
      const R = ringRadius(anchor, layout, 0.42) * lerp(1, 1.08, calm);
      const size = anchor.span * 0.26 * calmScale(calm);
      slides.forEach((s, i) => {
        const p = stagger(presence, i, slides.length, 0.5);
        s.focus = damp(s.focus, focus.includes(i) ? 1 : 0, 3.5, dt);
        // An arc behind the figure that drifts slowly.
        const a = Math.PI + s.t * 2.4 + Math.sin(time * 0.15) * 0.12;
        s.mesh.position.set(Math.sin(a) * R, anchor.y + anchor.span * (0.14 + s.lift * 0.08) + (1 - easeOutCubic(p)) * anchor.span * 0.7, Math.cos(a) * R);
        s.mesh.scale.setScalar(Math.max(0.001, p) * size * (1 + s.focus * 0.12));
        faceCamera(s.mesh, camera);
        s.mat.opacity = p * 0.95 * calmAlpha(calm) * (1 + s.focus * calm * 0.8) * clearOfBody(s.mesh.position.x, s.mesh.position.z, anchor, size * 0.5) * screenFade(s.mesh.position, camera, layout, calm);
      });
    },
  };
}

/* Skills: a constellation of nodes (one per skill) around the body, with labels for the works on screen. */
function constellation({ chapter, colors, labels }) {
  const group = new THREE.Group();
  const nodes = [];
  chapter.items.forEach((item, g) => (item.tags.length ? item.tags : [item.title]).forEach((tag) => nodes.push({ tag, g })));
  const filler = Math.max(0, 36 - nodes.length);
  for (let i = 0; i < filler; i++) nodes.push({ tag: null, g: -1 });

  // Unit sphere positions (fibonacci); scaled around the station every frame.
  const n = nodes.length;
  nodes.forEach((node, i) => {
    const y = 1 - 2 * ((i + 0.5) / n);
    const r = Math.sqrt(1 - y * y);
    const a = i * 2.399963 + 0.4;
    node.home = new THREE.Vector3(Math.cos(a) * r, y, Math.sin(a) * r);
    node.glow = 0;
  });

  const mesh = new THREE.InstancedMesh(new THREE.IcosahedronGeometry(1, 2), new THREE.MeshBasicMaterial({ toneMapped: false, transparent: true }), n);
  mesh.frustumCulled = false;
  const colA = new THREE.Color(colors.a), colB = new THREE.Color(colors.b), white = new THREE.Color('#ffffff');
  const c = new THREE.Color();
  group.add(mesh);

  // Each node links to its two nearest neighbors.
  const pairs = [];
  nodes.forEach((a, i) => {
    nodes.map((b, j) => ({ j, d: a.home.distanceTo(b.home) })).filter((x) => x.j !== i).sort((x, y) => x.d - y.d).slice(0, 2)
      .forEach(({ j }) => { if (!pairs.some(([p, q]) => p === j && q === i)) pairs.push([i, j]); });
  });
  const linePos = new Float32Array(pairs.length * 6);
  const lineCol = new Float32Array(pairs.length * 6);
  const lineGeo = new THREE.BufferGeometry();
  lineGeo.setAttribute('position', new THREE.BufferAttribute(linePos, 3));
  lineGeo.setAttribute('color', new THREE.BufferAttribute(lineCol, 3));
  const lineMat = new THREE.LineBasicMaterial({ vertexColors: true, transparent: true, opacity: 0, blending: THREE.AdditiveBlending, depthWrite: false, toneMapped: false });
  const lines = new THREE.LineSegments(lineGeo, lineMat);
  lines.frustumCulled = false;
  group.add(lines);

  const m = new THREE.Matrix4();
  const q = new THREE.Quaternion();
  const sc = new THREE.Vector3();
  const pos = nodes.map(() => new THREE.Vector3());
  const vis = new Float32Array(n);
  let spin = 0;

  return {
    group,
    update({ presence, focus, calm, dt, time, camera, anchor, layout }) {
      group.visible = presence > 0.002;
      if (!group.visible) return;
      spin += dt * 0.07;
      const rx = ringRadius(anchor, layout, 0.26) * lerp(1, 1.08, calm);
      const ry = anchor.span * 0.32;
      const cs = Math.cos(spin), sn = Math.sin(spin);
      nodes.forEach((node, i) => {
        const p = stagger(presence, i, n, 0.6);
        const lit = node.g >= 0 && (focus.includes(node.g) || !focus.length);
        node.glow = damp(node.glow, lit ? 1 : 0.15, 4, dt);
        const hx = node.home.x * cs - node.home.z * sn, hz = node.home.x * sn + node.home.z * cs;
        const e = easeOutCubic(p);
        pos[i].set(hx * rx * e, anchor.y + lerp(-ry * 0.3, node.home.y * ry, e) + Math.sin(time + i) * anchor.span * 0.006, hz * rx * e);
        vis[i] = clearOfBody(pos[i].x, pos[i].z, anchor, 0.02) * (pos[i].z < -rx * 0.4 ? 0.45 : 1) * calmAlpha(calm * (1 - node.glow * 0.6)) * screenFade(pos[i], camera, layout, calm);
        const s = anchor.span * (node.tag ? 0.011 : 0.0055) * (1 + node.glow * 0.7) * p * vis[i];
        m.compose(pos[i], q, sc.setScalar(Math.max(0.00001, s)));
        mesh.setMatrixAt(i, m);
        c.copy(node.g < 0 ? white : node.g % 2 ? colB : colA).lerp(white, 0.25).multiplyScalar(0.35 + node.glow * 0.9);
        mesh.setColorAt(i, c);
      });
      mesh.instanceMatrix.needsUpdate = true;
      if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
      pairs.forEach(([a, b], k) => {
        pos[a].toArray(linePos, k * 6);
        pos[b].toArray(linePos, k * 6 + 3);
        const v = Math.min(vis[a], vis[b]);
        const g = Math.min(nodes[a].glow, nodes[b].glow);
        for (let o = 0; o < 6; o += 3) { lineCol[k * 6 + o] = (0.2 + g) * v; lineCol[k * 6 + o + 1] = (0.45 + g * 0.5) * v; lineCol[k * 6 + o + 2] = 0.9 * v; }
      });
      lineGeo.attributes.position.needsUpdate = true;
      lineGeo.attributes.color.needsUpdate = true;
      lineMat.opacity = presence * 0.3;

      // Labels for the skills of the works on screen (desktop only).
      if (layout.compact) return;
      group.updateMatrixWorld();
      nodes.forEach((node, i) => {
        if (!node.tag || !focus.includes(node.g) || vis[i] < 0.5) return;
        tmp.copy(pos[i]).applyMatrix4(group.matrixWorld);
        labels.add(node.tag, tmp, camera, layout.size, presence * node.glow * vis[i]);
      });
    },
  };
}

/* Certifications: metal medallions on a tilted orbit; the two on screen flip to the front. */
function medals({ chapter, textures }) {
  const group = new THREE.Group();
  const orbitGroup = new THREE.Group();
  orbitGroup.rotation.x = -0.14; // front of the orbit tilts up, toward the camera's eye line
  group.add(orbitGroup);

  const DEPTH = 0.16;
  const body = new THREE.CylinderGeometry(1, 1, DEPTH, 96);
  body.rotateX(Math.PI / 2); // faces +Z
  const faceGeo = new THREE.CircleGeometry(0.92, 96); // upright UVs, unlike the cylinder cap
  const rim = new THREE.MeshStandardMaterial({ color: '#d9deea', metalness: 1, roughness: 0.2, transparent: true });
  const back = new THREE.MeshStandardMaterial({ color: '#2a3050', metalness: 0.9, roughness: 0.35, transparent: true });

  const items = chapter.items;
  let spin = 0;
  const coins = items.map((item, i) => {
    const holder = new THREE.Group();
    const face = new THREE.MeshBasicMaterial({ toneMapped: false, transparent: true, map: mediaTexture(item, textures) });
    const faceMesh = new THREE.Mesh(faceGeo, face);
    faceMesh.position.z = DEPTH / 2 + 0.002;
    holder.add(new THREE.Mesh(body, [rim, back, back]), faceMesh);
    group.add(holder);
    return { holder, face, focus: 0, base: (i / Math.max(1, items.length)) * TAU };
  });

  return {
    group,
    update({ presence, focus, calm, dt, time, camera, anchor, layout }) {
      group.visible = presence > 0.002;
      if (!group.visible) return;
      spin += dt * (0.24 - calm * 0.12);
      orbitGroup.position.y = anchor.y + anchor.span * 0.06;
      orbitGroup.updateMatrixWorld();
      const R = ringRadius(anchor, layout, 0.28) * lerp(1, 1.08, calm);
      const size = anchor.span * 0.07 * calmScale(calm);
      coins.forEach((cn, i) => {
        const p = stagger(presence, i, coins.length, 0.5);
        cn.focus = damp(cn.focus, focus.includes(i) ? 1 : 0, 3.5, dt);
        const a = cn.base + spin;
        const r = R * easeOutCubic(p);
        tmp.set(Math.sin(a) * r, 0, Math.cos(a) * r).applyMatrix4(orbitGroup.matrixWorld);
        cn.holder.position.copy(tmp);
        cn.holder.scale.setScalar(Math.max(0.0001, easeOutBack(p)) * size * (1 + cn.focus * 0.25));
        faceCamera(cn.holder, camera);
        // Idle wobble; the medals on screen do one full flip.
        cn.holder.rotation.y += (1 - cn.focus) * Math.sin(time * 0.9 + i) * 0.6 + cn.focus * TAU;
        const vis = clearOfBody(tmp.x, tmp.z, anchor, size) * calmAlpha(calm * (1 - cn.focus * 0.5)) * screenFade(tmp, camera, layout, calm);
        cn.face.opacity = p * vis;
        cn.holder.visible = vis > 0.02;
      });
      rim.opacity = back.opacity = clamp(presence * 1.5) * calmAlpha(calm);
    },
  };
}
