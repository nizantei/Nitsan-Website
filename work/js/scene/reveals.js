// Section effects: the "special objects" revealed around the figure. Each section's `reveal`
// in content.json picks one. They all take the same inputs every frame:
//   presence 0..1 (damped: entering/leaving), active item index (-1 = intro), layout info.
// Objects are generated from the section's items, so they follow the item count automatically.
import * as THREE from 'three';
import { roundedRect } from './helpers.js';
import { clamp, damp, lerp, stagger, easeOutBack, easeOutCubic } from '../util.js';

export function createReveal(kind, ctx) {
  const make = { orbit, stage, constellation, medals }[kind] ?? orbit;
  return make(ctx);
}

const TAU = Math.PI * 2;
const tmp = new THREE.Vector3();
const faceCamera = (obj, camera) => { obj.rotation.y = Math.atan2(camera.position.x - obj.position.x, camera.position.z - obj.position.z); };
const shortest = (d) => ((((d + Math.PI) % TAU) + TAU) % TAU) - Math.PI;

// Ring angle where the active item comes to rest: in front of the figure, on the text panel's
// side (0 = straight toward the camera, negative = screen left).
const frontAngle = (layout) => (layout.compact ? 0.35 : layout.side === 'left' ? -0.78 : 0.78);

// A ring that idles slowly, and dials the active item to the front when there is one.
function createDial(idleSpeed, angleScale = 1) {
  let spin = 0;
  return {
    update(dt, targetBase, layout) {
      if (targetBase === null) { spin += dt * idleSpeed; return spin; }
      const target = spin + shortest(frontAngle(layout) * angleScale - targetBase - spin);
      spin = damp(spin, target, 3.2, dt);
      return spin;
    },
  };
}

function mediaTexture(item, textures, onAspect) {
  if (item.image) return textures.get(item.image, (t) => onAspect?.(t.image.width / t.image.height));
  onAspect?.(1.6);
  return textures.label(item.title);
}

/* Apps: a ring of screens around the figure that turns to bring the active app to the front. */
function orbit({ chapter, textures, colors }) {
  const group = new THREE.Group();
  const items = chapter.items;
  const R = 1.3;
  const dial = createDial(0.14);
  const screens = items.map((item, i) => {
    const holder = new THREE.Group();
    const mat = new THREE.MeshBasicMaterial({ transparent: true, opacity: 0, toneMapped: false, side: THREE.DoubleSide, depthWrite: false });
    const glowMat = new THREE.MeshBasicMaterial({ color: colors.a, transparent: true, opacity: 0, blending: THREE.AdditiveBlending, depthWrite: false, toneMapped: false });
    const mesh = new THREE.Mesh(roundedRect(0.56, 0.35, 0.03), mat);
    const glow = new THREE.Mesh(roundedRect(0.6, 0.39, 0.045), glowMat);
    glow.position.z = -0.005;
    mat.map = mediaTexture(item, textures, (aspect) => {
      const w = aspect >= 1 ? 0.56 : 0.36;
      const h = w / aspect;
      mesh.geometry.dispose(); mesh.geometry = roundedRect(w, h, 0.03);
      glow.geometry.dispose(); glow.geometry = roundedRect(w + 0.04, h + 0.04, 0.045);
    });
    holder.add(glow, mesh);
    group.add(holder);
    return { holder, mat, glowMat, focus: 0, base: (i / Math.max(1, items.length)) * TAU, yOff: Math.sin(i * 2.3) * 0.22 };
  });

  return {
    group,
    update({ presence, active, dt, time, camera, layout }) {
      group.visible = presence > 0.002;
      if (!group.visible) return;
      const spin = dial.update(dt, active >= 0 ? screens[active].base : null, layout);
      screens.forEach((s, i) => {
        const p = stagger(presence, i, screens.length, 0.5);
        s.focus = damp(s.focus, i === active ? 1 : 0, 4, dt);
        const a = s.base + spin;
        s.holder.position.set(
          Math.sin(a) * R,
          lerp(1.22 + s.yOff, 1.38, s.focus) + Math.sin(time * 0.8 + i) * 0.03 - (1 - easeOutCubic(p)) * 0.9,
          Math.cos(a) * R + s.focus * 0.1,
        );
        s.holder.scale.setScalar(Math.max(0.001, easeOutBack(p)) * (0.85 + s.focus * 0.3));
        faceCamera(s.holder, camera);
        s.holder.rotation.z = (1 - s.focus) * Math.sin(a) * 0.1;
        const behind = Math.cos(a) < -0.2 ? 0.45 : 1;
        const dim = active >= 0 && i !== active ? 0.5 : 1;
        s.mat.opacity = p * dim * behind;
        s.glowMat.opacity = p * (0.08 + s.focus * 0.5);
      });
    },
  };
}

/* Talks: a stage light pours down on the figure, slides hang behind, the floor ripples. */
function stage({ chapter, textures, colors, floor }) {
  const group = new THREE.Group();
  const coneUniforms = { uOpacity: { value: 0 }, uColor: { value: new THREE.Color(colors.light) }, uTime: { value: 0 } };
  const cone = new THREE.Mesh(
    new THREE.ConeGeometry(1.3, 3.8, 64, 1, true),
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
          float a = facing * (0.15 + 0.85 * pow(vH, 1.4)) * uOpacity * 0.45;
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
  const span = Math.min(Math.PI * 0.75, 0.5 * Math.max(1, items.length - 1));
  const slides = items.map((item, i) => {
    const mat = new THREE.MeshBasicMaterial({ transparent: true, opacity: 0, toneMapped: false, depthWrite: false });
    const mesh = new THREE.Mesh(roundedRect(0.9, 0.5, 0.02), mat);
    mat.map = mediaTexture(item, textures, (aspect) => { mesh.geometry.dispose(); mesh.geometry = roundedRect(0.9, 0.9 / aspect, 0.02); });
    const a = items.length > 1 ? -span / 2 + (i / (items.length - 1)) * span : 0;
    mesh.userData.home = new THREE.Vector3(Math.sin(a) * 2.2, 1.7 + Math.cos(i * 1.7) * 0.12, -Math.cos(a) * 2.2);
    group.add(mesh);
    return { mesh, mat, focus: 0 };
  });

  return {
    group,
    persistent: [spot, spot.target],
    update({ presence, active, dt, time, camera }) {
      group.visible = presence > 0.002;
      floor.uniforms.uRipple.value = presence;
      spot.intensity = presence * 55;
      if (!group.visible) return;
      coneUniforms.uOpacity.value = easeOutCubic(presence);
      coneUniforms.uTime.value = time;
      slides.forEach((s, i) => {
        const p = stagger(presence, i, slides.length, 0.5);
        s.focus = damp(s.focus, i === active ? 1 : 0, 4, dt);
        s.mesh.position.copy(s.mesh.userData.home);
        s.mesh.position.y += (1 - easeOutCubic(p)) * 1.2 + s.focus * 0.18;
        s.mesh.position.z += s.focus * 0.35;
        s.mesh.scale.setScalar(Math.max(0.001, p) * (1 + s.focus * 0.3));
        faceCamera(s.mesh, camera);
        s.mat.opacity = p * (active >= 0 && i !== active ? 0.35 : 0.95);
      });
    },
  };
}

/* Skills: a constellation of nodes (one per skill) wrapped around the figure, with labels. */
function constellation({ chapter, colors, labels }) {
  const group = new THREE.Group();
  const nodes = [];
  chapter.items.forEach((item, g) => (item.tags.length ? item.tags : [item.title]).forEach((tag) => nodes.push({ tag, g })));
  const filler = Math.max(0, 28 - nodes.length);
  for (let i = 0; i < filler; i++) nodes.push({ tag: null, g: -1 });

  const n = nodes.length;
  nodes.forEach((node, i) => {
    const y = 1 - 2 * ((i + 0.5) / n);
    const r = Math.sqrt(1 - y * y);
    const a = i * 2.399963 + 0.4;
    node.home = new THREE.Vector3(Math.cos(a) * r * 1.2, 1.15 + y * 0.95, Math.sin(a) * r * 1.2);
    node.glow = 0;
  });

  const mesh = new THREE.InstancedMesh(new THREE.IcosahedronGeometry(1, 1), new THREE.MeshBasicMaterial({ toneMapped: false, transparent: true }), n);
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
  const world = new THREE.Vector3();
  let spin = 0;

  return {
    group,
    update({ presence, active, dt, time, camera, layout }) {
      group.visible = presence > 0.002;
      if (!group.visible) return;
      spin += dt * 0.08;
      group.rotation.y = spin;
      nodes.forEach((node, i) => {
        const p = stagger(presence, i, n, 0.6);
        node.glow = damp(node.glow, node.g >= 0 && (active === node.g || active < 0) ? 1 : 0.15, 4, dt);
        pos[i].copy(node.home).multiplyScalar(easeOutCubic(p));
        pos[i].y = lerp(1.1, node.home.y, easeOutCubic(p)) + Math.sin(time + i) * 0.015;
        const s = (node.tag ? 0.022 : 0.011) * (1 + node.glow * (active >= 0 ? 0.9 : 0.3)) * p;
        m.compose(pos[i], q, sc.setScalar(Math.max(0.0001, s)));
        mesh.setMatrixAt(i, m);
        c.copy(node.g < 0 ? white : node.g % 2 ? colB : colA).lerp(white, 0.2).multiplyScalar(0.35 + node.glow * 0.9);
        mesh.setColorAt(i, c);
      });
      mesh.instanceMatrix.needsUpdate = true;
      if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
      pairs.forEach(([a, b], k) => {
        pos[a].toArray(linePos, k * 6);
        pos[b].toArray(linePos, k * 6 + 3);
        const g = Math.min(nodes[a].glow, nodes[b].glow);
        for (let o = 0; o < 6; o += 3) { lineCol[k * 6 + o] = 0.3 + g; lineCol[k * 6 + o + 1] = 0.6 + g * 0.4; lineCol[k * 6 + o + 2] = 1; }
      });
      lineGeo.attributes.position.needsUpdate = true;
      lineGeo.attributes.color.needsUpdate = true;
      lineMat.opacity = presence * 0.35;

      // Labels for the active group's skills (all skills while on the intro card, desktop only).
      const showAll = active < 0 && !layout.compact;
      group.updateMatrixWorld();
      nodes.forEach((node, i) => {
        if (!node.tag || !(showAll || node.g === active)) return;
        world.copy(pos[i]).applyMatrix4(group.matrixWorld);
        const behind = world.z < -0.25 ? 0.35 : 1;
        labels.add(node.tag, world, camera, layout.size, presence * node.glow * behind * (showAll ? 0.6 : 1));
      });
    },
  };
}

/* Certifications: metal medallions on a tilted orbit; the active one flips to the front. */
function medals({ chapter, textures }) {
  const group = new THREE.Group();
  const orbitGroup = new THREE.Group();
  orbitGroup.rotation.x = -0.12; // front of the orbit tilts up, toward the camera's eye line
  orbitGroup.position.y = 1.36;
  group.add(orbitGroup);

  const RADIUS = 0.17, DEPTH = 0.03;
  const body = new THREE.CylinderGeometry(RADIUS, RADIUS, DEPTH, 64);
  body.rotateX(Math.PI / 2); // faces +Z
  const faceGeo = new THREE.CircleGeometry(RADIUS * 0.92, 64); // upright UVs, unlike the cylinder cap
  const rim = new THREE.MeshStandardMaterial({ color: '#d9deea', metalness: 1, roughness: 0.22, transparent: true });
  const back = new THREE.MeshStandardMaterial({ color: '#2a3050', metalness: 0.9, roughness: 0.35, transparent: true });

  const items = chapter.items;
  const R = 1.05;
  const dial = createDial(0.25, 0.8);
  const coins = items.map((item, i) => {
    const holder = new THREE.Group();
    const face = new THREE.MeshBasicMaterial({ toneMapped: false, transparent: true, map: mediaTexture(item, textures) });
    const faceMesh = new THREE.Mesh(faceGeo, face);
    faceMesh.position.z = DEPTH / 2 + 0.001;
    holder.add(new THREE.Mesh(body, [rim, back, back]), faceMesh);
    group.add(holder);
    return { holder, face, focus: 0, base: (i / Math.max(1, items.length)) * TAU };
  });

  return {
    group,
    update({ presence, active, dt, time, camera, layout }) {
      group.visible = presence > 0.002;
      if (!group.visible) return;
      const spin = dial.update(dt, active >= 0 ? coins[active].base : null, layout);
      orbitGroup.updateMatrixWorld();
      rim.opacity = back.opacity = clamp(presence * 1.5);
      coins.forEach((cn, i) => {
        const p = stagger(presence, i, coins.length, 0.5);
        cn.focus = damp(cn.focus, i === active ? 1 : 0, 4, dt);
        const a = cn.base + spin;
        const r = R * easeOutCubic(p);
        tmp.set(Math.sin(a) * r, 0, Math.cos(a) * r).applyMatrix4(orbitGroup.matrixWorld);
        tmp.z += cn.focus * 0.12;
        cn.holder.position.copy(tmp);
        cn.holder.scale.setScalar(Math.max(0.001, easeOutBack(p)) * (1 + cn.focus * 0.45));
        faceCamera(cn.holder, camera);
        // Idle wobble; the active medal does one full flip as it arrives.
        cn.holder.rotation.y += (1 - cn.focus) * Math.sin(time * 0.9 + i) * 0.6 + cn.focus * TAU;
        cn.face.opacity = p * (active >= 0 && i !== active ? 0.55 : 1);
      });
    },
  };
}
