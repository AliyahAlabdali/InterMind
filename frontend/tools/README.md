# Developer tools

Local-only tooling: nothing here is imported by the application, no `tsconfig` includes it, and
none of it ships in `dist/`. It stays outside `public/`, whose contents are copied verbatim into
every build.

## `landing-qa.cjs`

A QA harness for the landing page. It runs against the production build, not the dev server:
bundle behaviour, the 3D scenes and the intro timeline differ under Vite's dev pipeline.

```bash
npm run build
node tools/landing-qa.cjs      # serves dist/ on http://127.0.0.1:5175
```

Open `http://127.0.0.1:5175/__qa` and press the button. It drives the built site inside an iframe
and collects one JSON report covering:

- **Viewports.** Eight sizes from 1920x1080 down to 375x812, each scrolled for horizontal
  overflow, text and visual collisions, broken images and console errors, with the intro's phase
  timeline recorded.
- **Resilience.** Returning to the hero after scrolling, WebGL context loss and restore for both
  canvases, reverse and mid-step scrubbing of the process choreography, remount after navigating
  away and back, direct hash entry, and idle frame counts.
- **Legal pages.** Privacy, terms and cookies at three widths, checking overflow, dark surface,
  word count, navigation and em dashes.

The server injects a probe into every HTML response it serves, activated only by a `?landingQA=`
query parameter, so the built files themselves stay unmodified:

| Mode | Effect |
|---|---|
| `normal` | Instrumentation only: frame counts, long tasks, layout shifts, phase timeline. |
| `reduced` | Also reports `prefers-reduced-motion: reduce` to the application. |
| `failure` | Also makes `getContext('webgl*')` return `null`, to exercise the fallback paths. |

The finished report is written to `<tmpdir>/intermind-thread-audit/restored-browser-report.json`.

## `bake-laptop-room.ts`

The reproducible recipe for `public/models/laptop-room.dat`, the pre-baked lighting environment
for the hero laptop. It rebuilds the procedural reflection room (a dark box with one soft box
above and indigo and cyan strips behind), runs Three's `PMREMGenerator` over it, and returns the
raw pixels behind a small header. Run `bakeRoom(canvas)` in a local Three-enabled browser, gzip
the returned bytes, and save them as `public/models/laptop-room.dat`, so the application uploads
finished PMREM data instead of recomputing that convolution in every visitor's browser.
