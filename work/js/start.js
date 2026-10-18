// The first screen: the whole figure and a Start button. Until the visitor starts, scrolling is
// held; Start (or a scroll, swipe or arrow key on the first screen) zooms the camera from the full
// figure to the face. It is an ordinary programmatic scroll through the zoom segment, so scrolling
// back to the top zooms out again, and the gate comes back once the page rests at the top.
const DOWN_KEYS = new Set(['ArrowDown', 'PageDown', ' ', 'Spacebar', 'End']);

export function createStart({ dom, director, scroller, config, getMode }) {
  const root = document.documentElement;
  let gated = false;
  let running = false;
  let touchY = null;

  const cinematic = () => getMode() === 'cinematic';

  function arm() {
    if (!cinematic() || gated) return;
    gated = true;
    root.classList.add('is-gated');
    scroller.lock(true);
  }

  function release() {
    if (!gated) return;
    gated = false;
    root.classList.remove('is-gated');
    scroller.lock(false);
  }

  function focusFirst() {
    dom.chapters[0]?.el.focus({ preventScroll: true });
  }

  function start() {
    if (!dom.chapters.length) return;
    if (!cinematic()) {
      scroller.scrollTo(director.chapterY(0), { immediate: true });
      focusFirst();
      return;
    }
    if (running) return;
    release();
    running = true;
    root.classList.add('is-starting');
    scroller.glide(director.chapterY(0), {
      duration: config.start.duration,
      easing: scroller.easeInOutSine,
      lock: true,
      onComplete: () => {
        running = false;
        root.classList.remove('is-starting');
        focusFirst();
      },
    });
  }

  dom.start?.addEventListener('click', (e) => { e.preventDefault(); start(); });

  // On the first screen, any intent to scroll down starts the tour.
  addEventListener('wheel', (e) => { if (gated && e.deltaY > 2) start(); }, { passive: true });
  addEventListener('touchstart', (e) => { touchY = gated ? e.touches[0].clientY : null; }, { passive: true });
  addEventListener('touchmove', (e) => {
    if (gated && touchY !== null && touchY - e.touches[0].clientY > 18) { touchY = null; start(); }
  }, { passive: true });
  addEventListener('keydown', (e) => {
    if (!gated || !DOWN_KEYS.has(e.key) || e.target.closest?.('input, textarea, select, [contenteditable]')) return;
    if (e.key === ' ' && e.target.closest?.('button, a')) return; // Space activates the focused control instead
    e.preventDefault();
    start();
  });

  return {
    arm,
    release,
    start,
    get gated() { return gated; },
    get running() { return running; },
    // Re-arm once the page rests at the very top again.
    update(y, now) {
      if (!gated && !running && cinematic() && y < 2 && !scroller.busy && scroller.idleFor(now) > 700) arm();
    },
  };
}
