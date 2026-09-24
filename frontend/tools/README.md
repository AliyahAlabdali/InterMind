# Developer tools

Local-only tooling. Nothing here is imported by the application, none of it is in any
`tsconfig` include, and none of it ships in `dist/`. It lives outside `public/` deliberately:
anything in `public/` is copied verbatim into the build and served on every deployment.

## `landing-qa.cjs`

A QA harness for the landing page, run against the **production build** rather than the dev
server, because the things it checks (bundle behaviour, the 3D scenes, the intro timeline) do not
behave identically under Vite's dev pipeline.

```bash
npm run build
node tools/landing-qa.cjs      # serves dist/ on http://127.0.0.1:5175
```

Open `http://127.0.0.1:5175/__qa` and press the button. It drives the built site inside an iframe
and collects one JSON report covering:

- **Viewports.** 1920x1080, 1440x900, 1366x768, 1024x768, 900x800, 390x844, 375x812 and 1366x580,
  scrolling each one for horizontal overflow, text/visual collisions, broken images and console
  errors, and recording the intro's phase timeline.
- **Resilience.** Returning to the hero after scrolling, WebGL context loss and restore for both
  canvases, reverse and mid-step scrubbing of the process choreography, remount after navigating
  away and back, direct hash entry, and idle frame counts.
- **Legal pages.** Privacy, terms and cookies at three widths, checking overflow, dark surface,
  word count, navigation and em dashes.

The server injects a probe into every HTML response it serves, keyed off a `?landingQA=` query
parameter. That parameter is the only thing that activates it, so the built files themselves are
unmodified:

| Mode | Effect |
|---|---|
| `normal` | Instrumentation only: frame counts, long tasks, layout shifts, phase timeline. |
| `reduced` | Also reports `prefers-reduced-motion: reduce` to the application. |
| `failure` | Also makes `getContext('webgl*')` return `null`, to exercise the fallback paths. |

The finished report is written to `<tmpdir>/intermind-thread-audit/restored-browser-report.json`.

## `bake-laptop-room.ts`

The reproducible recipe for `public/models/laptop-room.dat`, the pre-baked lighting environment
for the hero laptop. It builds the original procedural reflection room (a dark box with one soft
box above and indigo and cyan strips behind), runs Three's `PMREMGenerator` over it, and returns
the raw pixels with a small header.

Run `bakeRoom(canvas)` in a local Three-enabled browser, gzip the returned bytes, and save the
result as `public/models/laptop-room.dat`. Baking it once means the application uploads finished
PMREM data instead of recomputing that convolution in every visitor's browser, which was a large
part of the hero's old startup cost. It is never imported by the application.
