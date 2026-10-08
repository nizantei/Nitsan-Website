# From one photo to the hero 3D model

Source: `Nitsan photo/Profile Picture.jpg` (1209×1600). Nothing below has been generated or paid
for yet; steps marked **paid** need approval first.

## What the photo gives us

- Waist-up, front-facing, even daylight on a plain wall: clean cutout, few baked shadows. Good input.
- Arms crossed. Generators fuse crossed arms into the torso. That's fine for this page, which turns
  the whole figure, but it rules out posing or rigging unless we make a separate A-pose version.
- Ends at the upper thigh: legs and shoes must be invented.
- Front only: back and sides are guessed (a buzz cut and a plain tee make that easy).
- Open smile with teeth: the riskiest part for likeness. Expect "recognizably you", not a scan.
- Fine details (chain, bead bracelet, arm hair, belt buckle) end up as texture, not geometry.

## Pipeline

Every step after generation is a script in this folder, so each round of notes is a re-run, not
a manual redo. Generation goes through a REST API for the same reason: a regeneration is one command.

| Step | Where | Cost | Iterable by |
|---|---|---|---|
| 0. Cut out and normalize the photo | here (open-source background removal, CPU) | free | script |
| 1. Complete to full body: same trousers, belt, chosen shoes, head to toe; face and torso pixels untouched; optional side and back views | image-editing model with a mask, **or** you make it in an app you already use and push it | **paid** (cents per image) | re-prompting; you approve the image before any 3D spend |
| 2. Image(s) → textured 3D | Meshy API, multi-image (front + side + back), keep the crossed-arms pose | **paid** (credits per generation) | regenerate, retexture only, or remesh |
| 3. Clean up and build for the web | here: Blender 5.2 headless (`pip install bpy`) + glTF-Transform | free | script parameters |
| 4. Drop into the page | `work/models/`, `CONFIG.model.url`, `npm run poster` | free | n/a |

Why Meshy: it's the most complete scriptable set for this job. Multi-image input, pose control,
remeshing to a target polycount, texture-only regeneration, and auto-rigging if we later want
gestures, all over one REST API with GLB output. Paid plans keep outputs private (the free tier
is CC BY). Fallback: Tripo has the same building blocks. Not chosen: Rodin (possibly stronger
faces, but unclear API pricing), TRELLIS.2 (open source, MIT, but needs a 24 GB GPU; this
container has none).

Legs without an image model (free alternative to step 1): generate from the waist-up photo,
then I build the trousers and shoes in Blender on a CC0 MakeHuman/MPFB2 body and join them at the
belt line. Fully in my control, but it tends to look assembled; step 1 is the better default.

## How notes map to work

| Note type | Fix | Regenerate? |
|---|---|---|
| Proportions, stance, height | Blender script parameters | no |
| Colors, materials, shoe color | texture edits in step 3, or Meshy retexture | no / texture only |
| Trousers, shoes, leg shape | redo step 1 image, then one generation | yes (one) |
| Face likeness | extra face photo as input, regenerate; if still off, a human 3D artist pass on the head | yes |
| "Too uncanny at this size" | stylized finish in code (clay, chrome, hologram mix) | no |

## Web targets

- glTF 2.0 binary (`.glb`), Y-up, meters, feet at the origin, facing +Z (the page also normalizes).
- Desktop: 80–150k triangles; 2048² base color + 2048² normal + 1024–2048² packed
  occlusion/roughness/metal; meshopt geometry; WebP textures → ≤ 5 MB.
- Phone variant: 30–50k triangles, 1024² textures → ≤ 2 MB.
- No skeleton needed for the current choreography. Raw generator output is usually several
  hundred thousand triangles and tens of MB, so it always goes through step 3.

## Needed before the paid steps

1. Go-ahead on spend, a Meshy API key on a paid plan saved as an environment secret
   (`MESHY_API_KEY`), and `api.meshy.ai` plus its download host allowed in the environment's
   network settings. The same applies to the image-editing API for step 1, unless you make that
   image yourself.
2. Shoes and trouser length (default if you don't mind: full-length straight khakis with a slight
   break, dark brown leather shoes).
3. Optional: your height, so proportions match.
