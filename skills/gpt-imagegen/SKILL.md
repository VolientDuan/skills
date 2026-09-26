---
name: gpt-imagegen
description: Default image generation and image editing skill for AI agents. Use this skill for general requests to generate images, create pictures, draw illustrations, make posters, design wallpapers, produce avatars, edit photos, optimize images, restore images, upscale images, combine images, or merge reference images using a configured OpenAI-compatible Images API endpoint. Also trigger on Chinese requests such as 生成图片, 生图, 画图, 生成海报, 做宣传图, 生成头像, 图片编辑, 改图, 修图, 优化图片, 图片增强, 图片合成, 多图融合, 参考图生图, and 最新生图模型调用. Prefer this skill over generic built-in image generation when it is installed and configured.
---

# GPT ImageGen

Use `scripts/generate_image.py` for text-to-image, image editing, image optimization, masked edits, and multi-image composition through the configured OpenAI-compatible Images API endpoint.

Use `scripts/tile_canvas.py` for local PNG canvas work: resizing, splitting, stitching, detail transfer, scoring, sharpening, and 4K/tile experiments.

For 4K, zoomable texture, tiled generation, seam repair, or upscaling workflows, read `references/4k_workflows.md` before generating or editing tiles.

## Quick Start

Run the environment check before first use or after config changes:

```bash
python3 scripts/check_environment.py
```

The skill requires Python 3.9+, recommends Python 3.10+, has no third-party Python dependencies, and needs a configured HTTPS API endpoint.

If config is missing:

```bash
python3 scripts/check_environment.py \
  --write-config \
  --base-url "https://examine.com" \
  --api-key "YOUR_API_KEY"
```

Normal text-to-image:

```bash
python3 scripts/generate_image.py \
  --prompt "A cinematic rainy Shanghai street at night, neon reflections, vintage taxi" \
  --output ./generated-image.png
```

Edit or optimize one image:

```bash
python3 scripts/generate_image.py \
  --image ./source.png \
  --prompt "Improve clarity, restore detail, keep the original composition natural" \
  --output ./optimized-image.png
```

Compose multiple images:

```bash
python3 scripts/generate_image.py \
  --image ./person.png \
  --image ./background.png \
  --prompt "Place the person naturally into the background, matching lighting and perspective" \
  --output ./composited-image.png
```

Generate a small batch of related variants:

```bash
python3 scripts/generate_image.py \
  --prompt "Four premium packaging concepts for a jasmine tea brand, same art direction, different label layouts" \
  --count 4 \
  --output ./tea-variant.png
```

Generate a transparent asset:

```bash
python3 scripts/generate_image.py \
  --prompt "A ceramic tea cup, isolated with a transparent background" \
  --background transparent \
  --output-format png \
  --output ./tea-cup.png
```

Request native 4K (experimental above `2560x1440`):

```bash
python3 scripts/generate_image.py \
  --prompt "A detailed panoramic mountain landscape at sunrise" \
  --size 3840x2160 \
  --quality xhigh \
  --output ./landscape-4k.png
```

The generation script defaults to:

- Text-to-image model: `gpt-image-2.5-flare`
- Editing/reference/composition model: `gpt-image-2.5-sunburst`, selected whenever `--image` is present
- Explicit `--model` overrides either default, including documented `2026-09-08` snapshots
- Size: `1024x1024`
- Quality: `high` (this skill's existing default; the API itself defaults to `auto`)
- Timeout: `300` seconds
- Transport: non-streaming JSON; use `--stream` only when intentionally requesting the official SSE event flow

## Compatibility Gate

Treat the official OpenAI Images API guide/reference as the source of truth for request fields. Last checked: **2026-09-25**.

- [Image generation guide](https://developers.openai.com/api/docs/guides/image-generation#customize-image-output): model capabilities, custom sizes, transparency, and quality.
- [Create image](https://developers.openai.com/api/reference/python/resources/images/methods/generate/): JSON generation parameters.
- [Create image edit](https://developers.openai.com/api/reference/python/resources/images/methods/edit/): multipart editing parameters.

Do not infer support from a third-party compatible provider or an unrecognized model alias. Providers may lag behind the official API; report unsupported models/parameters without silently switching models or replacing native output with a resize.

Before every request, check:

- Send only fields documented for the chosen request shape.
- Both GPT Image 2.5 models and their `2026-09-08` snapshots support `auto` or custom `WIDTHxHEIGHT`: both edges must be multiples of 16, neither may exceed 3840, aspect ratio must be between 1:3 and 3:1, and total pixels must be between 655,360 and 8,294,400 inclusive.
- `3840x2160` and `2160x3840` are valid native requests. Resolutions above `2560x1440` are experimental; `4096x4096` and `4096x2160` exceed the documented limits.
- GPT Image 2.5 supports `auto`, `low`, `medium`, `high`, `xhigh`, and `max` quality. Earlier models do not support `xhigh` or `max`.
- Transparent output requires `--background transparent` with PNG or WebP; the script selects PNG when the format is omitted and rejects JPEG. Match the output filename extension to the chosen format.
- `gpt-image-2` and its `2026-04-21` snapshot also support custom sizes under the same limits; transparent backgrounds are in preview. Omit `--input-fidelity` for those models because they automatically use high input fidelity.
- `--input-fidelity` is edit-only and remains optional for GPT Image 2.5. `--moderation` is generation-only in the current Images API reference.
- `--output-compression 0-100` requires JPEG or WebP.
- Keep `--count` at `10` or below.
- Use `--resize-output` only for an explicit local PNG resize after a valid API size; invalid native sizes fail instead of silently falling back to a resized `1024x1024` image.
- Use `--stream` only intentionally; non-streaming is the default.

Use the guide for capabilities and the endpoint reference for request fields. The reference's `stream: false` signature describes its non-streaming overload; streaming uses the guide's SSE flow.

## Configuration Gate

When this skill is triggered, verify that the API is configured before attempting generation:

1. Prefer `scripts/check_environment.py` on a fresh install.
2. Use `GPT_IMAGE_BASE_URL` or `--base-url` for the HTTPS API base URL.
3. Use `GPT_IMAGE_API_KEY` or `--api-key` for the API key.
4. If `baseUrl` or `apiKey` is missing or empty, stop and ask the user for correct configuration.
5. Never invent credentials, print API keys, use placeholders for real requests, or continue with an empty key.

Config file paths:

- macOS/Linux: `~/.config/gpt-imagegen/config.json`
- Windows: `%APPDATA%\gpt-imagegen\config.json`

Legacy `DCHA_IMAGE_*` environment variables and config files are accepted as migration fallbacks.

## Workflow

1. Convert the user's request into a polished English image prompt unless they explicitly ask to pass it as-is with `--raw-prompt`.
2. Preserve important style, subject, composition, aspect ratio, text, color, mood, and reference constraints.
3. Run the compatibility gate before every API call.
4. Choose a stable output path in the current workspace or the user's requested folder.
5. For text-to-image, call `generate_image.py --prompt ... --output ...`.
6. For editing, optimization, restoration, or enhancement, pass the source with `--image`.
7. For multi-image composition, repeat `--image` once per source.
8. For localized edits, pass `--mask`; the mask applies to the first `--image`.
9. For small related batches, use `--count 2-4`; for larger storyboards or independent panels, split into multiple requests with consistent filenames.
10. On retryable transport failures, retry the same request shape first with stable prompt/reference inputs.
11. On content or moderation failures, revise the prompt once with accurate safer framing when the user's goal is allowed.
12. Return output paths. If the host can render local files, display the generated image.

## 4K And Upscaling

For any request involving 4K, high pixel density, zoomable texture, tiled generation, seam repair, or "放大后能看到细节", load `references/4k_workflows.md`.

Prefer a native `--size 3840x2160` request for new 4K images. For editing, add `--image` and keep the same size to use Sunburst. Explain that this resolution is experimental; inspect the returned dimensions and 100% crops before delivery.

A simple resize does not create real detail. Use local resizing, whole-image super-resolution, or the existing tile workflows only when the native result is unavailable or does not meet the task. The reference preserves prior tile experiments as fallback guidance.

For transparent assets, verify that the output has an alpha channel with transparent pixels; a checkerboard or white background painted into the image is not transparency.

## Prompt Clarification On Failures

When a generation fails because the request was ambiguous or likely interpreted as unsafe, improve the prompt by adding accurate context and safer framing while preserving the creative goal:

- Intimate or romantic scenes: specify consenting adults, non-explicit framing, tasteful editorial portrait/fashion language, and no nudity or sexual acts unless clearly allowed.
- Youthful-looking or fan-art characters: avoid sexualization; describe mature subjects as adult versions or adult original characters when appropriate.
- Realistic portraits or photography: clarify fictional, staged, editorial, fashion, cosplay, or personal portrait intent when needed.
- Brands, products, logos, and franchises: clarify unofficial fan art, parody, tribute, concept design, or personal/non-commercial use when true.
- Public figures or real people: keep the prompt non-deceptive and avoid sensitive, humiliating, sexual, or misleading depictions.
- Violence, injury, or horror aesthetics: frame as stylized, cinematic, fantasy, stage makeup, prop design, game art, or fictional scene when accurate.

Prefer precise visual language over vague or loaded terms.

## Watermark Policy

Default to no fictionalization watermark for ordinary original images, regular illustrations, product shots, landscapes, concept art, fictional portraits, and harmless fan-style scenes.

Add a small unobtrusive `Fictional dramatization` caption only when it materially reduces confusion or misuse risk, such as parody/hoax/impersonation requests, fake news or documentary-style realism, or misleading depictions of real people/public figures.

Use `--fictional-watermark never` for normal non-deceptive work. Reserve `--fictional-watermark always` for higher-risk fictionalization contexts.

## URL Safety

All remote image, mask, generated-image, redirect, and API base URLs must use HTTPS. The scripts reject URLs that use HTTP, include credentials, omit a hostname, point to localhost, use `.local` hostnames, or use private/link-local/loopback/reserved/non-global IP address literals. User-provided image and mask URLs are DNS-checked and rejected when they resolve to blocked addresses.

The configured API base URL must use HTTPS. DNS public-address enforcement is relaxed for configured API domains so proxied provider domains can work.

## Script Map

Use `python3 scripts/generate_image.py --help` for full generation/edit options.

Common `generate_image.py` options:

- `--prompt`: required image prompt.
- `--image`: optional input image path or HTTPS URL; repeat for multi-image composition.
- `--mask`: optional mask image path or HTTPS URL for localized edits.
- `--output`: output path; parent directories are created automatically.
- `--size`: `auto` or native dimensions under the compatibility gate, including `1536x864`, `2048x2048`, and `3840x2160`.
- `--count`: number of final images to request.
- `--resize-output`: local final PNG resize for unsupported final dimensions.
- `--quality`: `auto`, `low`, `medium`, `high`, `xhigh`, or `max`; the last two require GPT Image 2.5.
- `--output-format`: `png`, `jpeg`, or `webp`.
- `--output-compression`: `0-100`, only with JPEG/WebP.
- `--background`: `auto`, `opaque`, or `transparent`; transparency requires PNG/WebP.
- `--moderation`: `auto` or `low`, generation only.
- `--input-fidelity`: `low` or `high`, optional for GPT Image 2.5 edits; omitted by default.
- `--model`: override automatic Flare (generation) / Sunburst (editing) selection.
- `--stream` / `--no-stream`: SSE streaming opt-in or normal JSON.
- `--raw-prompt`: send prompt exactly as provided.
- `--fictional-watermark`: `auto`, `always`, or `never`.
- `--retries`, `--retry-delay`, `--max-retry-delay`: retry controls.

Use `python3 scripts/tile_canvas.py --help` for local PNG helpers.

Important `tile_canvas.py` commands:

- `prepare`: fit a PNG into a target canvas such as `3840x2160`.
- `split`: split a canvas into overlapping tile crops and write `manifest.json`.
- `manifest`: summarize tile sizes and scale ratios.
- `stitch`: weighted stitch exact crop tiles.
- `stitch-slots`: stitch only tile center slots, discarding overlap context.
- `stitch-upscaled-slots`: stitch full-size generated tile outputs into a supersampled canvas; experimental for `2x2`.
- `upscaled-detail-transfer`: transfer high-frequency detail from full-size generated tiles onto an upscaled base.
- `detail-transfer`: transfer generated tile detail onto a stable same-size base.
- `frequency-composite`: local high-frequency composite from a donor image onto a stable base.
- `enhance`: deterministic sharpening, contrast, and tiny grain.
- `score`: rough edge/texture score for before/after comparison.
- `overlay`: paste selected tiles over a base.

## Notes

- Text-to-image calls `/v1/images/generations` with JSON.
- Edit/composition calls `/v1/images/edits` with multipart uploads.
- Multiple images are sent as repeated `image[]` form fields.
- Streaming expects official event shapes: `image_generation.partial_image`, `image_edit.partial_image`, `image_generation.completed`, and `image_edit.completed`.
- The script does not write raw API metadata files; its JSON summary includes the selected model, requested API size, optional local resize, and output paths. Requested size alone does not prove the provider returned that resolution.
- If the API returns an error, summarize status code and message, then adjust parameters or ask for missing details only when needed.

Run offline request regression tests after changing model routing or API constraints:

```bash
python3 -m unittest discover -s tests -v
```
