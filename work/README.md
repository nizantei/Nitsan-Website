# /work/: scroll-driven 3D portfolio page

The page opens on the whole figure with a **Start** button. Start (or a scroll, swipe or ↓ on that
first screen) zooms the camera smoothly to the face. From there, scrolling moves the camera down
the body through **stations** (head, hands, legs, feet by default): the body stays centered and
the works of each station appear on its left and right.

A separate page next to the main site. Nothing in the main site links here yet, and the page is
`noindex` until launch (`<meta name="robots">` in `index.html`). The main site's files are untouched.

## Preview

```bash
# from the repo root
npx http-server . -p 8080 -c-1        # or: cd work/tools && npm install && npm run serve
# open http://localhost:8080/work/
```

On Vercel, every push to a branch gets a preview deployment; the page is at `<preview-url>/work/`.
Asset paths are absolute (`/work/...`), so `/work` and `/work/` both work.

Test switches (add to the URL):

| Switch | Effect |
|---|---|
| `?mode=static` | Reduced-motion layout (what users with "reduce motion" get) |
| `?mode=poster` | No-WebGL fallback: still image + static layout |
| `?quality=low` | Phone tier (fewer particles, lower resolution, no smooth scroll on touch) |
| `?debug` | HUD with mode, fps, scroll segment, station and beat; exposes `window.__work` |

## Add or change content

Everything is in **`data/content.json`**. Add an item by adding an object to a section's
`items`; drop its image in `media/`. The scroll length, dots, counters and 3D objects all adapt
to the number of items. On desktop each beat of scroll shows a pair of works (first on the
left, second on the right); on phones, one per beat.

```jsonc
{
  "title": "Required",
  "meta": "Year · platform · venue · issuer (optional)",
  "description": "Optional",
  "image": "media/my-app.webp",   // optional; webp/jpg/png/svg, ~1600px wide is plenty
  "alt": "Describe the image",
  "tags": ["Optional", "chips"],
  "links": [{ "label": "Live", "url": "https://..." }]
}
```

Sections (`chapters`) take `id`, `label`, `title`, `intro`, `items`, and:
- `station`: where on the body the section sits: `head`, `chest`, `hands`, `waist`, `legs` or
  `feet` (presets in `js/config.js`). Sections without one are spread down the body in order.
  Keep them in top-to-bottom order so the camera always moves down.
- `reveal`: the 3D effect around the figure: `orbit` (ring of screens), `stage` (spotlight,
  slides, floor ripples), `constellation` (skill nodes with labels), `medals` (flipping badges).
  These play while the camera travels to the station and step back once the cards are on screen.

Name, tagline, email and outro links are under `meta`.

## Tune the choreography

`js/config.js`:

| Key | What it changes |
|---|---|
| `start.duration` | Length of the zoom from the full figure to the face (seconds) |
| `stations.<name>` | Each station's height on the body (`y`, 0 = floor, 1 = top of the head), how much of the body is in view (`span`, m), body width there (`width`, m: the camera pulls back so the body stays clear of the cards), camera height above it (`up`), particle `formation` |
| `stationFov` | Lens for the station close-ups (degrees) |
| `layout.clear` | Width of the clear center column between the cards (fraction of the screen; keep `--clear` in `css/work.css` in sync) |
| `layout.compact*` | Phone framing: body above the bottom sheet |
| `travel.sway` / `travel.turns` | How much the figure sways during a travel / full turns per travel (0 = always faces you) |
| `scroll.snap*` | Gliding onto the nearest station when the visitor stops in between |
| `poses.hero` / `poses.outro` | Full-figure framings at the start and the end |
| `quality.high` / `quality.low` | Resolution cap, particles, MSAA samples, bloom, shadows per tier |
| `bloom`, `exposure` | Glow on emissive highlights; overall brightness (Khronos PBR Neutral tone mapping) |

`css/work.css`: `--intro` (scroll length of the zoom), `--lead` (travel between stations),
`--beat` (scroll per pair of works), `--card` (card width).

## The 3D character

`models/nitsan.glb` is a stylized low-poly character (~5k triangles, ~500 KB, one file for every
device) in the style of hand-made low-poly characters, built from the photo in `Nitsan photo/`
with free tools only (MakeHuman CC0 body, MediaPipe, Blender as a Python module). Its head is
box-modeled to measurements of a head fitted to your photo, with the features on your landmarks.
The pipeline, how to rebuild it, and how notes map to settings: `tools/model/README.md`.

Any glTF works in the page: it is scaled to `CONFIG.model.height`, stood on the floor, and the
scan, dissolve and rim effects are layered onto its own materials. `CONFIG.figure.materials`
tunes materials by name. After changing the model, regenerate the no-WebGL still:
`cd tools && npm run serve` (one terminal), then `npm run poster`. `tools/model/stations.mjs`
renders close-ups of every station.

## How it works

```
index.html          layers: backdrop (giant name) → WebGL canvas → grain/vignette → 3D labels → page
css/work.css        layout, Start screen, stations, compact (phone) layout, static/poster layouts
data/content.json   all content
fonts/              self-hosted Geist, Geist Mono, Instrument Serif (OFL)
js/main.js          boot: mode → content → 3D → measure → frame loop
js/env.js           mode and quality detection (+ URL switches)
js/content.js       renders stations from the JSON
js/director.js      scroll position → state (camera framing, station, beat, transition progress)
js/scroller.js      native scroll + Lenis smoothing on desktop; glides for Start, nav and snapping
js/start.js         the Start screen: holds scrolling until Start, then plays the zoom
js/ui.js            cards on screen, nav, keyboard focus, progress, height rail, debug HUD
js/scene/           Three.js: stage (post-processing, lights), figure effects, particles, floor,
                    contact shadow, reveals, helpers
vendor/             pinned three.js + Lenis builds (see vendor/VERSIONS.txt)
tools/              dev scripts: vendoring, media, poster, screenshots; tools/model = character pipeline
```

Scroll model: the Start zoom is an ordinary scroll segment (Start just glides through it), so
scrolling back to the top zooms out again and the Start screen returns. Each station is a tall
track with a sticky full-screen frame, so the page "stops" on it while each beat of scrolling
shows the next pair of works. Between stations the camera glides down the body while the scan,
rim light and particles play and the next station's title assembles. Native scroll is the
source of truth, so keyboard, scrollbar, find-in-page and deep links (`/work/#talks`, which skip
the Start screen) keep working; a reload returns to the same place.

Rendering (high tier): MSAA, a bloom that only catches emissive highlights, soft shadows from
the key light, a contact shadow under the feet, film grain and vignette (CSS, over the canvas).

Fallbacks:
- **Reduced motion** (`prefers-reduced-motion`, followed live): no zoom or travel animation;
  content flows as a normal grid, the figure cuts between framings, Start jumps to the first
  station.
- **No WebGL / 3D load failure**: same static layout over a still image (`media/poster.webp`).
  `three.js` is loaded on demand, so this path doesn't download it.
- **Phones**: the body centered above a bottom sheet (one work per beat), capped resolution,
  fewer particles, no post-processing, native touch scrolling; resolution steps down
  automatically if frames run slow.

## Tools

```bash
cd work/tools && npm install
npm run vendor        # rebuild vendor/ and fonts/ after changing versions in package.json
npm run placeholder   # the old stand-in mannequin (models/placeholder-figure.glb), if ever needed
npm run media         # regenerate placeholder images
npm run serve         # local server on :8080 (repo root)
npm run poster        # render media/poster.webp (needs the server)
npm run shots -- out  # plays Start, visits every station in every mode, saves screenshots and
                      # console errors (needs the server; ONLY=desktop,wide,small,mobile,reduced,poster)
```

Headless runs need `CHROMIUM=/path/to/chrome` if Playwright's bundled browser isn't installed.
