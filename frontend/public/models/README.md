# Landing assets

- `laptop.glb` is the existing model by Taohid Animation, licensed CC BY 4.0. Attribution remains in the landing footer. Source: https://sketchfab.com/3d-models/realistic-3d-laptop-model-high-quality-design-920fe8eceaf748a5b9ddd53385519322
- `laptop-image.png` is a transparent render of that exact model with the original landing materials, camera, and lighting. It is used with the existing DOM interview screen and panels when desktop WebGL is unavailable or disabled.
- `pose-*.webp` are transparent renders of InterMind's original process instrument and its six existing configurations. They are not generated illustrations. They provide the mobile, reduced-motion, and WebGL-failure views.
- `laptop-room.dat` is gzip-compressed half-float PMREM data from the original procedural reflection room. Its decompressed format is two little-endian uint32 values (width 768, height 1024), followed by RGBA float16 pixels. This preserves the original lighting without recomputing its convolution for each visitor. The reproducible recipe is `frontend/tools/bake-laptop-room.ts`.

The shared candidate instrument source was not changed to produce these assets.
