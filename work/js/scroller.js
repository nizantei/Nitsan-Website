// Scroll source. Native scroll stays the source of truth (scrollbar, keyboard, find-in-page and
// anchors keep working); on desktop Lenis smooths it. Touch devices keep native momentum.
import Lenis from 'lenis';

export function createScroller({ smooth, config }) {
  let lenis = null;
  let y = scrollY;
  let velocity = 0; // px per second, smoothed
  let lastInput = 0;

  const markInput = () => { lastInput = performance.now(); };
  for (const type of ['wheel', 'touchstart', 'touchmove', 'keydown', 'pointerdown']) {
    addEventListener(type, markInput, { passive: true });
  }

  function setSmooth(on) {
    if (on && !lenis) {
      lenis = new Lenis({ autoRaf: false, lerp: config.scroll.lerp, smoothWheel: true, syncTouch: false });
    } else if (!on && lenis) {
      lenis.destroy();
      lenis = null;
    }
  }
  setSmooth(smooth);

  return {
    get y() { return y; },
    get velocity() { return velocity; },
    get smooth() { return !!lenis; },
    get busy() { return !!lenis?.isScrolling; },
    idleFor: (now) => now - lastInput,
    setSmooth,
    raf(now, dt) {
      lenis?.raf(now);
      const next = lenis ? lenis.scroll : scrollY;
      const v = dt > 0 ? (next - y) / dt : 0;
      velocity += (v - velocity) * Math.min(1, dt * 10);
      y = next;
    },
    scrollTo(target, { duration = 1.2, immediate = false } = {}) {
      if (lenis) {
        lenis.scrollTo(target, { duration, immediate, force: true });
      } else {
        window.scrollTo({ top: target, behavior: immediate ? 'instant' : 'smooth' });
      }
    },
  };
}
