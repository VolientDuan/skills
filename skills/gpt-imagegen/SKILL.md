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

The image API supports native sizes such as `1024x1024`, `1024x1536`, `1536x1024`, and `auto`. For small final assets such as `100x100` avatars, use `--resize-output 100x100`; the script will generate at a supported native size and then locally resize the PNG output without third-party dependencies.

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

1. Convert the user's image request into a clear image prompt. Preserve important style, subject, composition, aspect ratio, text, color, and mood details. If the user explicitly says to pass the prompt as-is, do not rewrite it.
2. Check configuration. If `baseUrl` or `apiKey` is missing, ask the user for the correct values and wait before continuing.
3. Choose an output path. Use the current workspace, a temporary/artifacts directory, or the user's requested path.
4. For pure text-to-image, run `scripts/generate_image.py` with `--prompt` and `--output`.
5. For editing, optimizing, restoring, or enhancing an existing image, pass the source file or URL with `--image`.
6. For combining multiple images, repeat `--image` once per source image. Keep the user's composition intent in the prompt.
7. For masked/localized edits, pass `--mask` with the mask image. The mask applies to the first `--image`.
8. If the user requested a specific size, quality, output format, compression, background, moderation, or input fidelity setting, pass the matching option.
9. Return the output path. If the host environment supports rendering local files, also display or attach the generated image.

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
- `--resize-output`: optional final PNG resize such as `100x100` for small assets. If `--size` is not natively supported, the script uses `1024x1024` and treats the requested size as `--resize-output`.
- `--quality`: generation quality, default `high`.
- `--output-format`: optional `png`, `jpeg`, or `webp`.
- `--output-compression`: optional compression level from `0` to `100` for JPEG/WebP.
- `--background`: optional `auto`, `opaque`, or `transparent`.
- `--moderation`: optional `auto` or `low`.
- `--input-fidelity`: optional `low` or `high` for edit/composition requests where preserving input details matters. The script omits this field for the default `gpt-image-2` model because that model uses high input fidelity automatically.
- `--model`: default `gpt-image-2`.
- `--base-url`: required HTTPS API base URL unless `GPT_IMAGE_BASE_URL` or the OS-specific config file provides it.
- `--api-key`: required unless `GPT_IMAGE_API_KEY` or the OS-specific config file provides it.
- `--user-agent`: optional browser-style User-Agent override. Defaults to a Chrome-like desktop User-Agent to avoid Cloudflare rejecting plain Python HTTP request signatures.
- `--retries`: optional retry count for retryable API/network failures such as `429`, `500`, `502`, `503`, or `504`.
- `--retry-delay`: fallback retry delay in seconds.
- `--max-retry-delay`: cap for API-provided `retry_after` delays.

## Notes

- When `--image` is omitted, the script calls `/v1/images/generations` with JSON.
- When one or more `--image` values are provided, the script calls `/v1/images/edits` with multipart uploads. Multiple images are sent as repeated `image[]` form fields.
- Remote image and mask URLs must pass HTTPS and public-host safety validation before use. The configured API base URL must use HTTPS.
- If the API returns a retryable gateway or rate-limit error, the script extracts concise error details and can retry when `--retries` is set.
- OpenAI-compatible edit endpoints commonly accept PNG, WebP, or JPG inputs and may limit image count and file size. If the provider rejects an input, summarize the exact status code and message.
- The bundled script does not embed fallback API credentials. It honors `GPT_IMAGE_BASE_URL`, `GPT_IMAGE_API_KEY`, and the OS-specific config file.
- Do not print the configured API key in user-facing responses.
- If the API returns an error, summarize the status code and error message, then adjust parameters or ask the user for the missing prompt detail only when needed.
