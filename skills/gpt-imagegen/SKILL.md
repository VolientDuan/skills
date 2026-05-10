---
name: gpt-imagegen
description: Default image generation and image editing skill for AI agents. Use this skill for general requests to generate images, create pictures, draw illustrations, make posters, design wallpapers, produce avatars, edit photos, optimize images, restore images, upscale images, combine images, or merge reference images using the configured gpt-image-2 OpenAI-compatible Images API. Also trigger on Chinese requests such as 生成图片, 生图, 画图, 生成海报, 做宣传图, 生成头像, 图片编辑, 改图, 修图, 优化图片, 图片增强, 图片合成, 多图融合, 参考图生图, and 最新生图模型调用. Prefer this skill over generic built-in image generation when it is installed and configured.
---

# GPT ImageGen

## Quick Start

Use `scripts/generate_image.py` from this skill directory for text-to-image generation, image editing, image optimization, and multi-image composition. Prefer this bundled script whenever the user asks for image generation or image editing with this skill.

Before generating, run the first-run check when possible. The skill has no third-party Python dependencies. It requires Python 3.9+, recommends Python 3.10+, and needs a configured HTTPS API endpoint.

```bash
python3 scripts/check_environment.py
```

Use the Python launcher available in the host environment. The examples use `python3`; Windows environments may use `python` or `py -3` instead.

If Python is ready but config is missing, the check script can create the config file:

```bash
python3 scripts/check_environment.py \
  --write-config \
  --base-url "https://examine.com" \
  --api-key "YOUR_API_KEY"
```

The generation script also refuses to continue when `baseUrl` or `apiKey` is empty, and prints OS-specific setup instructions.

## Trigger Priority

When this skill is installed, treat it as the default handler for raster image generation and editing requests. Prefer `gpt-imagegen` over generic built-in image generation tools unless the user explicitly asks for a different image tool or provider.

Common trigger phrases include:

- English: generate an image, create a picture, draw, make a poster, design a wallpaper, avatar, edit this image, improve this photo, restore, upscale, combine images, merge references.
- Chinese: 生成图片, 生图, 画图, 做图, 生成海报, 做宣传图, 生成头像, 改图, 修图, 优化图片, 图片增强, 图片合成, 多图融合, 参考图生图.

macOS/Linux shell:

```bash
export GPT_IMAGE_BASE_URL="https://examine.com"
export GPT_IMAGE_API_KEY="YOUR_API_KEY"
```

Windows PowerShell:

```powershell
$env:GPT_IMAGE_BASE_URL = "https://examine.com"
$env:GPT_IMAGE_API_KEY = "YOUR_API_KEY"
```

Text-to-image:

```bash
python3 scripts/generate_image.py \
  --prompt "A cinematic rainy Shanghai street at night, neon reflections, vintage taxi" \
  --output ./generated-image.png
```

Generate multiple images in one request:

```bash
python3 scripts/generate_image.py \
  --prompt "Four premium packaging concepts for a jasmine tea brand, same art direction, different front label layouts" \
  --count 4 \
  --output ./tea-variant.png
```

To edit or optimize an existing image, pass one `--image`:

```bash
python3 scripts/generate_image.py \
  --image ./source.png \
  --prompt "Improve clarity, restore detail, keep the original composition natural" \
  --output ./optimized-image.png
```

To combine images, repeat `--image` for each source:

```bash
python3 scripts/generate_image.py \
  --image ./person.png \
  --image ./background.png \
  --prompt "Place the person naturally into the background, matching lighting and perspective" \
  --output ./composited-image.png
```

The script defaults to:

- Model: `gpt-image-2`
- Size: `1024x1024`
- Quality: `high`
- Timeout: `300` seconds
- Transport: SSE streaming with `partial_images=2`

Prefer the default SSE streaming transport for both first attempts and retries. In current provider behavior, streaming is usually more reliable than `--no-stream`; only use `--no-stream` when the user explicitly asks for it or streaming repeatedly fails for the same request.

For `gpt-image-2`, the script accepts arbitrary `WIDTHxHEIGHT` sizes supported by the provider, plus `auto`. For legacy OpenAI-compatible image models, it keeps the conservative native-size fallback behavior around `1024x1024`, `1024x1536`, `1536x1024`, and `auto`. For small final assets such as `100x100` avatars, use `--resize-output 100x100`; the script will generate at a supported native size and then locally resize the PNG output without third-party dependencies.

## Configuration Gate

When this skill is triggered, verify that the image API is configured before attempting generation:

1. Prefer running `scripts/check_environment.py` first on a fresh install. It checks Python version, required standard-library modules, TLS certificate verification, and config presence.
2. Use `GPT_IMAGE_BASE_URL` or `--base-url` for the HTTPS API base URL. The example base URL is `https://examine.com`.
3. Use `GPT_IMAGE_API_KEY` or `--api-key` for the API key.
4. If `baseUrl` or `apiKey` is missing or empty, stop and ask the user to provide the correct configuration. Do not invent credentials, use placeholders, or continue with an empty key.
5. The script also supports a JSON config file. Use `~/.config/gpt-imagegen/config.json` on macOS/Linux and `%APPDATA%\gpt-imagegen\config.json` on Windows.

macOS/Linux:

```bash
mkdir -p ~/.config/gpt-imagegen
printf '%s\n' '{"baseUrl":"https://examine.com","apiKey":"YOUR_API_KEY"}' > ~/.config/gpt-imagegen/config.json
```

Windows PowerShell:

```powershell
$configPath = Join-Path $env:APPDATA "gpt-imagegen\config.json"
New-Item -ItemType Directory -Force (Split-Path $configPath) | Out-Null
'{"baseUrl":"https://examine.com","apiKey":"YOUR_API_KEY"}' | Set-Content -Encoding UTF8 $configPath
```

Legacy `DCHA_IMAGE_*` environment variables and legacy config files are still accepted as a fallback during migration.

## Workflow

1. Convert the user's image request into a polished English image prompt. Preserve important style, subject, composition, aspect ratio, text, color, and mood details. If the user explicitly says to pass the prompt as-is, pass `--raw-prompt`.
2. Check configuration. If `baseUrl` or `apiKey` is missing, ask the user for the correct values and wait before continuing.
3. Choose an output path. Use the current workspace, a temporary/artifacts directory, or the user's requested path.
4. For pure text-to-image, run `scripts/generate_image.py` with `--prompt` and `--output`.
5. For editing, optimizing, restoring, or enhancing an existing image, pass the source file or URL with `--image`.
6. For combining multiple images, repeat `--image` once per source image. Keep the user's composition intent in the prompt.
7. For masked/localized edits, pass `--mask` with the mask image. The mask applies to the first `--image`.
8. Watermark/caption policy: default to no fictionalization watermark for normal image generation. Ordinary original images, regular illustrations, product shots, landscapes, concept art, portraits of fictional characters, and harmless fan-style scenes should not get a caption by default. Add a small unobtrusive caption such as `Fictional dramatization` only when it materially helps avoid confusion or misuse: parody/hoax/impersonation requests, fake news or documentary-style realism, or depictions of real people/public figures in sensitive or misleading contexts. The text must not cover faces, characters, products, or important visual content. Use `--fictional-watermark never` for clearly normal/non-deceptive work; reserve `--fictional-watermark always` for the higher-risk cases above.
9. For a small batch of closely related variants, prefer a single API call with `--count` so the provider returns multiple finals together. This reduces repeated prompt overhead and usually improves throughput for "give me 2-4 options" style requests.
10. For larger deliverables such as storyboards, comics, or 6+ independent panels, split them into multiple requests and parallelize at the process level when possible. Use a shared style bible, seed/reference image where available, fixed prompt fragments for characters and palette, consistent size/quality, and distinct output paths. Keep concurrency moderate (for example 2-4 workers) to avoid provider rate limits, and report any failed panels/images for retry.
11. On retryable transport failures, retry with the same streaming mode first and keep the prompt/style/reference inputs stable. Do not switch to `--no-stream` as the first fallback; prefer streaming retries with `--retries`, a modest delay, jittered backoff, or reduced concurrency. Only try non-streaming after repeated streaming failures or when specifically requested.
12. On content or moderation failures, revise the prompt once before giving up when the user's request can be made clearly allowed. Add concise context that clarifies lawful, non-deceptive intent instead of using vague or loaded wording. Do not invent facts, do not claim permissions the user did not provide, and do not use these notes to bypass disallowed content.
13. If the user requested a specific size, quality, output format, compression, background, moderation, input fidelity, streaming, partial image setting, or image count, pass the matching option.
14. Return the output path. For `--count > 1`, return the full output list. If the host environment supports rendering local files, also display or attach the generated image.

## Prompt Clarification on Failures

When a generation fails because the request was ambiguous or likely interpreted as unsafe, improve the prompt by adding accurate context and safer framing while preserving the user's creative goal:

- Intimate or romantic scenes: specify consenting adults, non-explicit framing, normal affectionate behavior, tasteful portrait/fashion/editorial photography, natural body language, and no nudity or sexual acts unless the request is clearly allowed.
- Youthful-looking or fan-art characters: avoid sexualization. If a mature styling is requested, describe the subject as an adult version or adult original character inspired by the style.
- Realistic portraits or photography: clarify that the goal is a fictional, staged, editorial, fashion, cosplay, or personal portrait image, not documentary evidence or a misleading real event.
- Brands, products, logos, and known franchises: clarify unofficial fan art, parody, tribute, concept design, or personal/non-commercial use when true. Avoid implying endorsement, official advertising, counterfeit packaging, or commercial use unless the user has provided that context.
- Public figures or real people: keep the prompt non-deceptive and avoid sensitive, humiliating, sexual, or misleading depictions. Only add fictionalization/watermark guidance when the request is parody-like, impersonation-like, documentary-news-like, or otherwise likely to be misread as real evidence.
- Violence, injury, or horror aesthetics: frame as stylized, cinematic, fantasy, stage makeup, prop design, game art, or fictional scene when accurate, and avoid gratuitous real-world harm.

Prefer changing ambiguous words to precise visual language. For example, replace loaded terms with `romantic editorial portrait`, `tasteful adult couple pose`, `unofficial fan-art concept`, `fictional staged scene`, `cosplay-inspired fashion photo`, or `non-commercial tribute artwork` when those descriptions match the user's intent.

## Batch Generation

For requests such as "make 10 images", "generate a storyboard", or "produce variants", choose between native multi-image output and parallel requests based on the job shape:

- Use `--count 2`, `--count 3`, or `--count 4` when the user wants a small set of tightly related variants from the same prompt and art direction.
- Use multiple independent requests for larger sets, scene-by-scene storyboards, or jobs where each panel needs a materially different prompt.

- Keep consistency by writing one reusable English style bible and reusing it in every prompt.
- If the first generated image establishes the desired character/style, use it as a reference input for later panels when consistency matters.
- Use stable filenames (`panel_01_...png`, `variant_01.png`) and save into a dedicated output directory. When `--count > 1`, the script auto-saves numbered outputs like `variant_01.png`, `variant_02.png`.
- Prefer 2-4 parallel workers for multi-request jobs. If rate limits, gateway errors, or incomplete streams appear, lower concurrency and retry failed items with streaming still enabled.
- For `--count > 1`, keep `partial_images` low. The script auto-reduces streamed previews to avoid extra event overhead on batched responses.
- For storyboards/comics, track the scene order in filenames even if images complete out of order.

## URL Safety

All remote URLs must be HTTPS. The script validates the API base URL, input image URLs, mask URLs, generated image URLs returned by the API, and redirect targets before making requests.

The script rejects URLs that use HTTP, include credentials, omit a hostname, point to localhost, use `.local` hostnames, or use private/link-local/loopback/reserved/non-global IP address literals. User-provided image and mask URLs are also DNS-checked and rejected when they resolve to blocked addresses. The API base URL is still required to use HTTPS, but DNS public-address enforcement is relaxed for configured domains so proxied provider domains can continue to work. Unsafe redirects are rejected.

## Script Options

```bash
python3 scripts/generate_image.py --help
```

Environment and setup check:

```bash
python3 scripts/check_environment.py --help
```

Common options:

- `--prompt`: required image prompt.
- `--image`: optional input image path or HTTPS URL for editing, optimization, or composition. Repeat it for multiple images.
- `--mask`: optional mask image path or HTTPS URL for localized edits.
- `--output`: output image path; parent directories are created automatically.
- `--size`: image size such as `1024x1024`, `1024x1536`, or `1536x1024`.
- `--count`: request multiple final images in one API call. For `--count > 1`, the script auto-saves numbered files.
- `--resize-output`: optional final PNG resize such as `100x100` for small assets. If `--size` is not natively supported, the script uses `1024x1024` and treats the requested size as `--resize-output`.
- `--quality`: generation quality, default `high`.
- `--output-format`: optional `png`, `jpeg`, or `webp`.
- `--output-compression`: optional compression level from `0` to `100` for JPEG/WebP.
- `--background`: optional `auto`, `opaque`, or `transparent`.
- `--moderation`: optional `auto` or `low`.
- `--input-fidelity`: optional `low` or `high` for edit/composition requests where preserving input details matters. The script omits this field for the default `gpt-image-2` model because that model uses high input fidelity automatically.
- `--model`: default `gpt-image-2`.
- `--no-stream`: disable SSE streaming and request a normal JSON response. Streaming is enabled by default and should remain the preferred retry mode unless streaming repeatedly fails.
- `--partial-images`: optional streamed partial image count from `0` to `3`, default `2` for single-image requests. The script auto-reduces this for multi-image requests to improve efficiency.
- `--raw-prompt`: send the prompt exactly as provided, without English framing or safety caption guidance.
- `--fictional-watermark`: optional `auto`, `always`, or `never`, default `auto`. In `auto`, the skill should stay conservative and avoid captions for normal generations; use `always` mainly for parody, impersonation, fake-news/documentary-style, or similarly high-risk fictionalization contexts.
- `--base-url`: required HTTPS API base URL unless `GPT_IMAGE_BASE_URL` or the OS-specific config file provides it.
- `--api-key`: required unless `GPT_IMAGE_API_KEY` or the OS-specific config file provides it.
- `--user-agent`: optional browser-style User-Agent override. Defaults to a Chrome-like desktop User-Agent to avoid Cloudflare rejecting plain Python HTTP request signatures.
- `--timeout`: request timeout in seconds, default `300`.
- `--retries`: optional retry count for retryable API/network failures such as `429`, `500`, `502`, `503`, or `504`.
- `--retry-delay`: fallback retry delay in seconds.
- `--max-retry-delay`: cap for API-provided `retry_after` delays.

## Notes

- When `--image` is omitted, the script calls `/v1/images/generations` with JSON and requests SSE streaming by default.
- When one or more `--image` values are provided, the script calls `/v1/images/edits` with multipart uploads and requests SSE streaming by default. Multiple uploaded images are sent as repeated `image[]` form fields, matching the official multipart examples.
- When `--count > 1`, the script passes `n` to the API and saves every returned final image instead of only the first one.
- HTTPS responses are read in chunks, and streamed image events are parsed from `text/event-stream` responses.
- Streaming follows the official Images API event shape: `image_generation.partial_image` and `image_edit.partial_image` are treated only as progress events, while `image_generation.completed` and `image_edit.completed` are required for the final saved image. If the stream disconnects after a completed event, the script can still save that final image; if it disconnects with only partial events, the script reports a clear incomplete-stream error.
- The script no longer writes raw API metadata files. Return the generated image path and concise command output instead.
- Remote image and mask URLs must pass HTTPS and public-host safety validation before use. The configured API base URL must use HTTPS.
- If the API returns a retryable gateway, rate-limit, timeout, or incomplete-stream error, the script extracts concise error details and can retry when `--retries` is set. Retries use a small jitter on top of the base delay to reduce collision under concurrent runs. Prefer another streaming retry before changing transport.
- OpenAI-compatible edit endpoints commonly accept PNG, WebP, or JPG inputs and may limit image count and file size. If the provider rejects an input, summarize the exact status code and message.
- The bundled script does not embed fallback API credentials. It honors `GPT_IMAGE_BASE_URL`, `GPT_IMAGE_API_KEY`, and the OS-specific config file.
- Do not print the configured API key in user-facing responses.
- If the API returns an error, summarize the status code and error message, then adjust parameters or ask the user for the missing prompt detail only when needed.
