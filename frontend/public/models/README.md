# Landing assets

- `laptop.glb`: model by Taohid Animation, licensed CC BY 4.0, attributed in the landing footer. Source: https://sketchfab.com/3d-models/realistic-3d-laptop-model-high-quality-design-920fe8eceaf748a5b9ddd53385519322
- `laptop-image.png`: transparent render of that model with the landing's own materials, camera and lighting. The flat hero fallback draws it under the DOM interview screen and panels when the 3D scene is not running: no WebGL, reduced motion, or a scene that failed.
- `pose-*.webp`: transparent renders of the process instrument in its six states, used as the poster behind the canvas on mobile, under reduced motion and when WebGL fails.
- `laptop-room.dat`: gzip-compressed PMREM data from the procedural reflection room. Decompressed it is two little-endian uint32 values (width 768, height 1024) followed by RGBA float16 pixels. Rebuild it with `frontend/tools/bake-laptop-room.ts`.
