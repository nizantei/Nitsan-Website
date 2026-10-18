// Scroll source. Native scroll stays the source of truth (scrollbar, keyboard, find-in-page and
// anchors keep working); on desktop Lenis smooths it. Touch devices keep native momentum, and
// programmatic moves (Start, navigation, snapping) use a small tween of our own there.
import Lenis from 'lenis';
import { clamp, lerp } from './util.js';

const easeInOutSine = (t) => -(Math.cos(Math.PI * t) - 1) / 2;
const easeOutQuart = (t) => 1 - Math.pow(1 - t, 4);

export function createScroller({ smooth, config }) {
  const root = document.documentElement;
  let lenis = null;
  let y = scrollY;
  let velocity = 0; // px per second, smoothed
  let lastInput = 0;
  let tween = null; // native path: { from, to, start, ms, easing, onComplete }
  let locked = false;

  const markInput = () => { lastInput = performance.now(); };
  for (const type of ['wheel', 'touchstart', 'touchmove', 'keydown', 'pointerdown']) {
    addEventListener(type, markInput, { passive: true });
  }
  // While locked, or during a locked programmatic move on the native path, user scrolling is held;
  // an unlocked move (navigation, snapping) gives way as soon as the visitor scrolls.
  const hold = (e) => {
    if (locked || (tween && tween.lock)) e.preventDefault();
    else if (tween) tween = null;
  };
  addEventListener('touchstart', () => { if (tween && !tween.lock) tween = null; }, { passive: true });
  addEventListener('wheel', hold, { passive: false });
  addEventListener('touchmove', hold, { passive: false });

  function setSmooth(on) {
    if (on && !lenis) {
      lenis = new Lenis({ autoRaf: false, lerp: config.scroll.lerp, smoothWheel: true, syncTouch: false });
      if (locked) lenis.stop();
    } else if (!on && lenis) {
      lenis.destroy();
      lenis = null;
    }
  }
  setSmooth(smooth);

  function lock(on) {
    locked = on;
    root.classList.toggle('is-locked', on);
    if (lenis) on ? lenis.stop() : lenis.start();
  }

  // Move to `target` over `duration` seconds. `lock` holds user input until it arrives.
  function glide(target, { duration = 1.2, easing = easeOutQuart, lock: hold = false, onComplete } = {}) {
    target = clamp(target, 0, Math.max(0, root.scrollHeight - innerHeight));
    if (lenis) {
      lenis.scrollTo(target, { duration, easing, lock: hold, force: true, onComplete: () => onComplete?.() });
    } else {
      tween = { from: scrollY, to: target, start: performance.now(), ms: duration * 1000, easing, lock: hold, onComplete };
    }
  }

  return {
    get y() { return y; },
    get velocity() { return velocity; },
    get smooth() { return !!lenis; },
    get busy() { return !!lenis?.isScrolling || !!tween; },
    get locked() { return locked; },
    idleFor: (now) => now - lastInput,
    setSmooth,
    lock,
    glide,
    easeInOutSine,
    raf(now, dt) {
      if (tween) {
        const p = clamp((now - tween.start) / tween.ms);
        window.scrollTo(0, lerp(tween.from, tween.to, tween.easing(p)));
        if (p >= 1) { const done = tween.onComplete; tween = null; done?.(); }
      }
      lenis?.raf(now);
      const next = lenis ? lenis.scroll : scrollY;
      const v = dt > 0 ? (next - y) / dt : 0;
      velocity += (v - velocity) * Math.min(1, dt * 10);
      y = next;
    },
    scrollTo(target, { duration = 1.2, immediate = false } = {}) {
      if (immediate) {
        tween = null;
        if (lenis) lenis.scrollTo(target, { immediate: true, force: true });
        else window.scrollTo(0, target);
        return;
      }
      glide(target, { duration });
    },
  };
}
