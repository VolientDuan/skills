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

The generation script defaults to:

- Model: `gpt-image-2`
- Size: `1024x1024`
- Quality: `high`
- Timeout: `300` seconds
- Transport: non-streaming JSON; use `--stream` only when intentionally requesting the official SSE event flow

## Compatibility Gate

Treat the official OpenAI Images API guide/reference as the source of truth for request fields. Do not infer support from a third-party compatible provider, old examples, or a model alias.

Before every request, check:

- Send only fields documented for the chosen request shape.
- For `gpt-image-2`, use only `1024x1024`, `1536x1024`, `1024x1536`, or `auto`.
- Do not request native `3840x2160` from `gpt-image-2`; do 4K assembly locally.
- Omit `--input-fidelity` for `gpt-image-2`; the official guide says it automatically uses high input fidelity.
- Reject `--background transparent` for `gpt-image-2`.
- Keep `--count` at `10` or below.
- Use `--resize-output` for final dimensions outside the official API size set.
- Use `--stream` only intentionally; non-streaming is the default.

When OpenAI docs disagree, prefer the Images API guide and reference pages for request construction. This skill follows the guide's streaming examples for actual request formatting while keeping the doc conflict visible in script notes.

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

Core rules:

- Do not promise native 4K from the API.
- A simple resize does not create real detail.
- Do not use `2x2` four-block supersampling as the production path for close-up texture.
- Our West Lake tests showed `2x2` tile generation caused seams, ghosting, rectangular patches, or only negligible texture gain.
- Prefer whole-image super-resolution first when available, then GPT edits for small repairs.
- If using GPT tiles, prefer `8x8` test tiles, selective `16x16`, and high-frequency/detail-transfer workflows over direct tile pasting.
- Inspect 100% crops before delivery; thumbnails hide seam and texture artifacts.

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
- `--size`: `1024x1024`, `1536x1024`, `1024x1536`, or `auto` for `gpt-image-2`.
- `--count`: number of final images to request.
- `--resize-output`: local final PNG resize for unsupported final dimensions.
- `--quality`: `auto`, `low`, `medium`, or `high`.
- `--output-format`: `png`, `jpeg`, or `webp`.
- `--background`: `auto`, `opaque`, or `transparent`; transparent is blocked for `gpt-image-2`.
- `--moderation`: `auto` or `low`.
- `--model`: default `gpt-image-2`.
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
- The script does not write raw API metadata files; return output paths and concise command output.
- If the API returns an error, summarize status code and message, then adjust parameters or ask for missing details only when needed.
