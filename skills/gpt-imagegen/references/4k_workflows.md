# 4K And Tiled Detail Workflows

Use this reference when a user asks for 4K output, zoomable texture, upscaling, tile stitching, seam repair, or close-up material detail such as leaf veins, brick grain, stone joints, water ripples, bark, fabric weave, or roof tiles.

## Hard Constraints

- Do not request native `3840x2160` from `gpt-image-2`.
- Use only official request sizes for `gpt-image-2`: `1024x1024`, `1536x1024`, `1024x1536`, or `auto`.
- Do all non-standard canvas assembly, cropping, resizing, sharpening, and delivery sizing locally.
- A 4K resize only makes a large file. Visible detail must come from a real high-detail source, dedicated super-resolution, or carefully constrained local detail transfer.

## Preferred Production Path

For production-quality 4K texture, prefer:

1. Generate or select a stable base composition at an official size such as `1536x1024`.
2. Create the target canvas locally with `tile_canvas.py prepare`.
3. Use a dedicated super-resolution tool if available.
4. Use GPT image edits only for small local repairs or texture candidates.
5. If using GPT-generated tiles, use them as high-frequency detail donors, not as direct low-frequency image patches.
6. Inspect 100% crops before delivery. Whole-image thumbnails hide seams and fake texture.

Recommended commands:

```bash
python3 scripts/tile_canvas.py prepare \
  --input ./base-reference.png \
  --output ./work/scene_4k_canvas.png \
  --canvas 3840x2160 \
  --mode cover

python3 scripts/tile_canvas.py enhance \
  --input ./work/scene_4k_canvas.png \
  --output ./work/scene_4k_enhanced.png \
  --sharpness 0.28 \
  --contrast 1.02 \
  --grain 0.03
```

## Tiled Detail Path

Use `8x8` as the normal production grid for 4K texture work. Use `4x4` for quick drafts or broad local repair. Use selective `16x16` only for stubborn fine-detail regions such as willow leaves, grass, hair, fabric weave, carved ornament, and foreground stone texture.

```bash
python3 scripts/tile_canvas.py split \
  --input ./work/scene_4k_enhanced.png \
  --output-dir ./work/scene_tiles \
  --grid 8x8 \
  --overlap 96
```

Use the model to edit representative tiles first: foliage, hard surface/architecture, and water/sky/skin/fabric depending on the scene. Regenerate all tiles only if test tiles improve readable texture without lighting drift or geometry changes.

Tile prompt template:

```text
High-detail texture refinement for this small tile from a larger 4K photorealistic image.
Preserve the exact layout, crop boundaries, lighting direction, color temperature, perspective, and overlapping borders so it can stitch back into the master image.
Add readable local material detail: [leaf veins / stone joints / brick texture / water ripples / bark / roof tiles / fabric weave].
Do not move objects, do not add new major objects, no text, no watermark.
```

Prefer `detail-transfer` when generated tiles change shadows, objects, geometry, or exposure:

```bash
python3 scripts/tile_canvas.py detail-transfer \
  --base ./work/scene_4k_enhanced.png \
  --manifest ./work/scene_tiles/manifest.json \
  --input-dir ./work/scene_tiles_gen \
  --output ./work/scene_4k_detail_transfer.png \
  --strength 0.42 \
  --radius 2 \
  --edge-floor 0.18 \
  --edge-gain 1.0 \
  --edge-blend 10
```

Use `stitch-slots` only when generated tiles are visually stable. Treat overlap as context, not final pixels. Use `stitch` only for exact crops from the same source image or when weighted overlap blending is explicitly desired.

## 2x2 Supersampling Is Experimental

The proposed workflow `1536x1024 base -> 2x2 tiles -> each tile edited to 1536x1024 -> local 4K postprocess` is API-compliant but not production-grade for close-up texture.

Observed West Lake Broken Bridge sunset test:

- Four generated tiles stitch to `3072x2048`, then local postprocess can crop/resize to `3840x2160`.
- Rough texture score improved only about `1.11x-1.13x` over ordinary upscale after seam-safe blending.
- Direct no-blend stitching produced visible block boundaries and tone jumps.
- Strong edge feathering without a base produced dark seams.
- Strong edge feathering with a base reduced hard seams but introduced haze/ghosting and weakened detail.
- `upscaled-detail-transfer` stabilized seams but improved rough texture by only about `1.0x`.
- A seam-band masked edit repaired some continuity but introduced a large rectangular redraw patch.
- A local frequency-only composite was the most seam-stable four-block variant but improved rough texture only about `1.01x`.

Conclusion: use `2x2` supersampling only as a measured experiment or preview. If texture score is below about `1.25x`, or seams/ghosting/patches are visible, stop and switch to `8x8`, selective `16x16`, high-frequency transfer, or dedicated super-resolution.

Example `2x2` experiment:

```bash
python3 scripts/tile_canvas.py split \
  --input ./work/base_1536x1024.png \
  --output-dir ./work/tiles_2x2 \
  --grid 2x2 \
  --overlap 128

python3 scripts/generate_image.py \
  --image ./work/tiles_2x2/r0c0.png \
  --prompt "High-detail texture refinement for this tile of a larger photorealistic image. Preserve exact layout, crop boundaries, lighting direction, color temperature, perspective, and overlapping borders. Add local material detail only. Do not move objects, do not add new major objects, no text, no watermark." \
  --size 1536x1024 \
  --quality high \
  --output ./work/tiles_2x2_gen/r0c0.png

python3 scripts/tile_canvas.py stitch-upscaled-slots \
  --manifest ./work/tiles_2x2/manifest.json \
  --input-dir ./work/tiles_2x2_gen \
  --output ./work/scene_supersampled_3072x2048.png \
  --scale 2 \
  --fit cover \
  --color-match 0.9 \
  --edge-blend 0
```

If edge seams are visible, rerun with a matching base image and try `--edge-blend 48-96`. Reject the result if blending creates haze, ghosting, shadow overlap, or softened local detail.

Seam-safe fallback for the same generated tiles:

```bash
python3 scripts/tile_canvas.py upscaled-detail-transfer \
  --manifest ./work/tiles_2x2/manifest.json \
  --input-dir ./work/tiles_2x2_gen \
  --output ./work/scene_detail_transfer_3072x2048.png \
  --scale 2 \
  --fit cover \
  --strength 0.38 \
  --radius 2 \
  --edge-floor 0.06 \
  --edge-gain 1.25
```

Use this fallback when continuity is more important than maximum generated texture. If it removes seams but does not improve detail enough, switch workflows instead of repeatedly raising `--strength`.

Local frequency-only fallback:

```bash
python3 scripts/tile_canvas.py frequency-composite \
  --base ./work/base_upscaled_3072x2048.png \
  --donor ./work/scene_supersampled_3072x2048.png \
  --output ./work/scene_frequency_composite_3072x2048.png \
  --strength 0.55 \
  --radius 2 \
  --edge-floor 0.12 \
  --edge-divisor 42 \
  --seam-x 1536 \
  --seam-y 1024 \
  --seam-guard 24 \
  --seam-fade 120
```

This is the safest four-block fallback because it preserves the base image's low-frequency structure and suppresses donor detail near known seams. It is not a true pixel-density solution.

## Seam Diagnosis

When a user points out visible seams or a boxed region after tiled generation, do not keep increasing feathering blindly.

- Hard seam: neighboring tiles have different tone/exposure or object placement. Direct stitching will not fix this.
- Ghost seam: large feathering blends two different mountains, bridges, shadows, people, or horizons together.
- Low-frequency drift: the model redesigned broad shapes inside each tile. Do not direct-paste independent tile interiors.
- Rectangular redraw patch: masked repair changed the whole crop region instead of only the seam band.
- Fake texture: sharpening or tile generation creates busy noise without real leaf/stone/water structure. Reject even if `score` rises.

Better alternatives when seams are unacceptable:

- Whole-image super-resolution first: use a dedicated SR model/tool when available, then use GPT image edits only for small local repairs.
- Seam-band repair: test on a crop first; reject if the model redraws a rectangular patch, shifts perspective, or rewrites objects.
- Overlapped sliding-window detail transfer: use many smaller overlapping tiles, discard generated low-frequency content, and transfer only high-frequency detail onto a stable upscaled base.
- Seam-aware tile layout: avoid placing seams through horizons, bridge rails, faces, people, buildings, strong shadows, or long straight architectural lines.

## Practical Rules

- Do not stop at `2x2` or `4x4` when the user wants close-up material texture.
- Keep `96px` overlap for `8x8` as a strong default. Use `64px` for `16x16` if tiles become too small.
- Do not assume denser is always better. Test `8x8` and `16x16` on the same material class first.
- Use `--color-match 0.75-0.95` when generated tiles show exposure or color drift.
- For `detail-transfer`, start with `--strength 0.35-0.50`, `--radius 2`, `--edge-floor 0.10-0.20`, and `--edge-gain 1.0-1.3`.
- Mention tile position in prompts, but also describe neighboring landmarks so the model keeps continuity.
- Avoid regenerating a tile boundary that cuts directly through a face, hand, logo, horizon line, bridge arch, building edge, or other continuous structure.
- Stitching does not invent detail by itself. The visible texture comes from tile-level regeneration or external super-resolution.
