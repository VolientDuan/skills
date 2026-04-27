#!/usr/bin/env python3
"""Generate or edit images with gpt-image-2 through an OpenAI-compatible API."""

from __future__ import annotations

import argparse
import base64
import binascii
import http.client
import ipaddress
import json
import mimetypes
import os
import posixpath
import re
import shlex
import socket
import ssl
import struct
import sys
import time
import uuid
import zlib
from pathlib import Path


DEFAULT_BASE_URL = ""
RECOMMENDED_BASE_URL = "https://examine.com"
DEFAULT_MODEL = "gpt-image-2"
PLACEHOLDER_API_KEY = "YOUR_API_KEY"
DEFAULT_TIMEOUT = 300
HTTP_READ_CHUNK_SIZE = 1024 * 64
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
URL_PATTERN = re.compile(
    r"^(?P<scheme>[A-Za-z][A-Za-z0-9+.-]*)://"
    r"(?P<authority>[^/?#]*)"
    r"(?P<path>[^?#]*)"
    r"(?:\?(?P<query>[^#]*))?"
    r"(?:#.*)?$"
)
SCHEME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://")
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
SUPPORTED_API_SIZES = {"1024x1024", "1024x1536", "1536x1024", "auto"}


class ParsedURL:
    def __init__(
        self,
        scheme: str,
        netloc: str,
        hostname: str | None,
        port: int | None,
        path: str,
        query: str,
        username: str | None,
        password: str | None,
    ) -> None:
        self.scheme = scheme
        self.netloc = netloc
        self.hostname = hostname
        self.port = port
        self.path = path
        self.query = query
        self.username = username
        self.password = password


def default_config_path(app_name: str) -> Path:
    if os.name == "nt":
        config_root = os.environ.get("APPDATA")
        if config_root:
            return Path(config_root) / app_name / "config.json"
        return Path.home() / "AppData" / "Roaming" / app_name / "config.json"
    return Path.home() / ".config" / app_name / "config.json"


DEFAULT_CONFIG_PATH = default_config_path("gpt-imagegen")
LEGACY_CONFIG_PATH = default_config_path("dcha-imagegen")


def load_config(path: str | None = None) -> dict:
    configured_path = (
        path
        or os.environ.get("GPT_IMAGE_CONFIG")
        or os.environ.get("DCHA_IMAGE_CONFIG")
    )
    config_path = (
        Path(os.path.expandvars(configured_path)).expanduser()
        if configured_path
        else DEFAULT_CONFIG_PATH
    )
    if not configured_path and not config_path.exists() and LEGACY_CONFIG_PATH.exists():
        config_path = LEGACY_CONFIG_PATH

    if not config_path.exists():
        return {}

    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Config file is not valid JSON: {config_path}") from exc

    if not isinstance(data, dict):
        raise RuntimeError(f"Config file must contain a JSON object: {config_path}")
    return data


def config_value(config: dict, snake_case: str, camel_case: str) -> str:
    value = config.get(snake_case)
    if value is None:
        value = config.get(camel_case)
    return value or ""


def parse_args() -> argparse.Namespace:
    config = load_config()
    parser = argparse.ArgumentParser(
        description="Generate or edit images through an OpenAI-compatible Images API."
    )
    parser.add_argument("--prompt", required=True, help="Text prompt for the image.")
    parser.add_argument(
        "--image",
        dest="images",
        action="append",
        default=[],
        help=(
            "Input image path or URL for editing, optimization, or composition. "
            "Remote URLs must use HTTPS. Repeat this option to combine multiple images."
        ),
    )
    parser.add_argument(
        "--mask",
        help=(
            "Optional mask image path or URL for partial edits. "
            "Remote URLs must use HTTPS. When multiple images are provided, "
            "the mask applies to the first image."
        ),
    )
    parser.add_argument(
        "--output",
        default="generated-image.png",
        help="Output image path. Parent directories are created automatically.",
    )
    parser.add_argument("--size", default="1024x1024", help="Image size.")
    parser.add_argument(
        "--resize-output",
        help=(
            "Optional final PNG resize such as 100x100. Use this when the API "
            "does not natively support the requested output dimensions."
        ),
    )
    parser.add_argument("--quality", default="high", help="Image quality.")
    parser.add_argument(
        "--output-format",
        choices=("png", "jpeg", "webp"),
        help="Optional image output format.",
    )
    parser.add_argument(
        "--output-compression",
        type=int,
        choices=range(0, 101),
        metavar="0-100",
        help="Optional JPEG/WebP compression level from 0 to 100.",
    )
    parser.add_argument(
        "--background",
        choices=("auto", "opaque", "transparent"),
        help="Optional image background mode.",
    )
    parser.add_argument(
        "--moderation",
        choices=("auto", "low"),
        help="Optional moderation strictness for supported GPT Image models.",
    )
    parser.add_argument(
        "--input-fidelity",
        choices=("low", "high"),
        help="Optional input preservation level for edit/composition requests.",
    )
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Image model.")
    parser.add_argument(
        "--base-url",
        default=os.environ.get("GPT_IMAGE_BASE_URL")
        or os.environ.get("DCHA_IMAGE_BASE_URL")
        or config_value(config, "base_url", "baseUrl")
        or DEFAULT_BASE_URL,
        help="HTTPS API base URL, with or without /v1. Defaults to GPT_IMAGE_BASE_URL, legacy DCHA_IMAGE_BASE_URL, then the OS-specific config file.",
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("GPT_IMAGE_API_KEY")
        or os.environ.get("DCHA_IMAGE_API_KEY")
        or config_value(config, "api_key", "apiKey")
        or "",
        help="API key. Defaults to GPT_IMAGE_API_KEY, legacy DCHA_IMAGE_API_KEY, then the OS-specific config file.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        help="Request timeout in seconds. Defaults to 300 seconds.",
    )
    parser.add_argument(
        "--user-agent",
        default=os.environ.get("GPT_IMAGE_USER_AGENT")
        or os.environ.get("DCHA_IMAGE_USER_AGENT")
        or DEFAULT_USER_AGENT,
        help="HTTP User-Agent for the image API request.",
    )
    parser.add_argument(
        "--metadata",
        help="Optional path to write the raw API JSON response.",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=0,
        help="Number of retries for retryable API/network failures.",
    )
    parser.add_argument(
        "--retry-delay",
        type=int,
        default=5,
        help="Fallback retry delay in seconds.",
    )
    parser.add_argument(
        "--max-retry-delay",
        type=int,
        default=60,
        help="Maximum retry delay in seconds when the API suggests retry_after.",
    )
    return parser.parse_args()


def configuration_help() -> str:
    config_payload = (
        f'{{"baseUrl":"{RECOMMENDED_BASE_URL}","apiKey":"{PLACEHOLDER_API_KEY}"}}'
    )
    if os.name == "nt":
        config_path = str(DEFAULT_CONFIG_PATH)
        config_examples = f"""PowerShell examples:
  $env:GPT_IMAGE_BASE_URL = "{RECOMMENDED_BASE_URL}"
  $env:GPT_IMAGE_API_KEY = "{PLACEHOLDER_API_KEY}"

Or create a config file:
  $configPath = "{config_path}"
  New-Item -ItemType Directory -Force (Split-Path $configPath) | Out-Null
  '{config_payload}' | Set-Content -Encoding UTF8 $configPath"""
    else:
        config_dir = shlex.quote(str(DEFAULT_CONFIG_PATH.parent))
        config_path = shlex.quote(str(DEFAULT_CONFIG_PATH))
        json_payload = shlex.quote(config_payload)
        config_examples = f"""Shell examples:
  export GPT_IMAGE_BASE_URL="{RECOMMENDED_BASE_URL}"
  export GPT_IMAGE_API_KEY="{PLACEHOLDER_API_KEY}"

Or create a config file:
  mkdir -p {config_dir}
  printf '%s\\n' {json_payload} > {config_path}"""

    return f"""GPT ImageGen is not configured.

Required configuration:
  - baseUrl: set GPT_IMAGE_BASE_URL or pass --base-url
  - apiKey: set GPT_IMAGE_API_KEY or pass --api-key

{config_examples}

Then rerun the image generation command."""


def validate_configuration(base_url: str, api_key: str) -> None:
    missing = []
    if not base_url or not base_url.strip():
        missing.append("baseUrl")
    if not api_key or not api_key.strip():
        missing.append("apiKey")

    if missing:
        raise RuntimeError(
            f"Missing required configuration: {', '.join(missing)}.\n\n"
            + configuration_help()
        )


def parse_dimensions(value: str, label: str = "size") -> tuple[int, int]:
    match = re.fullmatch(r"([1-9][0-9]{0,4})x([1-9][0-9]{0,4})", value.strip())
    if not match:
        raise RuntimeError(f"{label} must use WIDTHxHEIGHT, such as 100x100.")
    return int(match.group(1)), int(match.group(2))


def normalize_api_size(size: str, resize_output: str | None = None) -> tuple[str, str | None]:
    normalized = size.strip().lower()
    if normalized in SUPPORTED_API_SIZES:
        return normalized, resize_output
    parse_dimensions(normalized, "size")
    if resize_output:
        raise RuntimeError(
            f"API size {size!r} is not one of {sorted(SUPPORTED_API_SIZES)}. "
            "Use a supported --size and put the final dimensions in --resize-output."
        )
    return "1024x1024", normalized


def parse_url(url: str) -> ParsedURL:
    match = URL_PATTERN.match(url)
    if not match:
        return ParsedURL("", "", None, None, "", "", None, None)

    scheme = match.group("scheme").lower()
    netloc = match.group("authority")
    path = match.group("path") or ""
    query = match.group("query") or ""
    authority = netloc
    username = None
    password = None

    if "@" in authority:
        userinfo, authority = authority.rsplit("@", 1)
        if ":" in userinfo:
            username, password = userinfo.split(":", 1)
        else:
            username = userinfo

    hostname = authority
    port = None
    if authority.startswith("["):
        closing = authority.find("]")
        if closing == -1:
            hostname = None
        else:
            hostname = authority[1:closing]
            rest = authority[closing + 1 :]
            if rest.startswith(":"):
                port = parse_port(rest[1:], url)
            elif rest:
                hostname = None
    elif ":" in authority:
        host, possible_port = authority.rsplit(":", 1)
        if possible_port.isdigit():
            hostname = host
            port = parse_port(possible_port, url)
        else:
            hostname = authority

    if hostname == "":
        hostname = None

    return ParsedURL(scheme, netloc, hostname, port, path, query, username, password)


def parse_port(value: str, url: str) -> int:
    if not value.isdigit():
        raise RuntimeError(f"URL has an invalid port: {url}")
    port = int(value)
    if not 0 < port <= 65535:
        raise RuntimeError(f"URL port is out of range: {url}")
    return port


def has_url_scheme(value: str) -> bool:
    return bool(SCHEME_PATTERN.match(value))


def percent_decode(value: str) -> str:
    result = bytearray()
    index = 0
    while index < len(value):
        char = value[index]
        if (
            char == "%"
            and index + 2 < len(value)
            and re.fullmatch(r"[0-9A-Fa-f]{2}", value[index + 1 : index + 3])
        ):
            result.append(int(value[index + 1 : index + 3], 16))
            index += 3
        else:
            result.extend(char.encode("utf-8"))
            index += 1
    return result.decode("utf-8", errors="replace")


def resolve_redirect_url(base_url: str, location: str) -> str:
    if has_url_scheme(location):
        return location
    base = validate_https_url(
        base_url,
        "Redirect base",
        require_public_resolution=False,
    )
    if location.startswith("//"):
        return f"{base.scheme}:{location}"

    origin = f"{base.scheme}://{base.netloc}"
    if location.startswith("/"):
        return origin + location

    base_dir = posixpath.dirname(base.path or "/")
    joined_path = posixpath.normpath(posixpath.join(base_dir, location))
    if not joined_path.startswith("/"):
        joined_path = "/" + joined_path
    return origin + joined_path


def unsafe_ip_reason(address: str) -> str | None:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return None

    if ip.is_loopback:
        return "loopback address"
    if ip.is_private:
        return "private address"
    if ip.is_link_local:
        return "link-local address"
    if ip.is_multicast:
        return "multicast address"
    if ip.is_reserved:
        return "reserved address"
    if ip.is_unspecified:
        return "unspecified address"
    if not ip.is_global:
        return "non-global address"
    return None


def validate_hostname_safety(
    hostname: str | None, label: str, require_public_resolution: bool = True
) -> str:
    if not hostname:
        raise RuntimeError(f"{label} URL must include a hostname.")

    normalized = hostname.strip("[]").rstrip(".").lower()
    if not normalized:
        raise RuntimeError(f"{label} URL must include a hostname.")

    if normalized == "localhost" or normalized.endswith(".localhost"):
        raise RuntimeError(f"{label} URL is not allowed to use localhost.")
    if normalized.endswith(".local"):
        raise RuntimeError(f"{label} URL is not allowed to use .local hostnames.")

    reason = unsafe_ip_reason(normalized)
    if reason:
        raise RuntimeError(f"{label} URL is not allowed to use {reason}: {hostname}")

    if not require_public_resolution:
        return normalized

    try:
        resolved = socket.getaddrinfo(
            normalized,
            None,
            family=socket.AF_UNSPEC,
            type=socket.SOCK_STREAM,
        )
    except socket.gaierror as exc:
        raise RuntimeError(
            f"Could not confirm safety for {label} URL hostname {hostname!r}: {exc}"
        ) from exc

    checked_addresses = set()
    for item in resolved:
        address = item[4][0]
        if address in checked_addresses:
            continue
        checked_addresses.add(address)
        reason = unsafe_ip_reason(address)
        if reason:
            raise RuntimeError(
                f"{label} URL hostname {hostname!r} resolves to a blocked "
                f"{reason}: {address}"
            )

    return normalized


def validate_https_url(
    url: str, label: str, require_public_resolution: bool = True
) -> ParsedURL:
    parsed = parse_url(url)
    if parsed.scheme.lower() != "https":
        raise RuntimeError(f"{label} URL must use HTTPS: {url}")
    if parsed.username or parsed.password:
        raise RuntimeError(f"{label} URL must not include credentials.")
    validate_hostname_safety(parsed.hostname, label, require_public_resolution)
    return parsed


def endpoint_from_base_url(base_url: str, operation: str = "generations") -> str:
    base = base_url.strip().rstrip("/")
    if not has_url_scheme(base):
        base = "https://" + base
    validate_https_url(base, "API base", require_public_resolution=False)
    if not base.endswith("/v1"):
        base = base + "/v1"
    return base + f"/images/{operation}"


def request_target(parsed: ParsedURL) -> str:
    target = parsed.path or "/"
    if parsed.query:
        target += "?" + parsed.query
    return target


def origin_from_url(url: str) -> str:
    parsed = validate_https_url(
        url,
        "Origin",
        require_public_resolution=False,
    )
    return f"{parsed.scheme}://{parsed.netloc}"


def request_headers(
    api_key: str | None = None,
    user_agent: str = DEFAULT_USER_AGENT,
    content_type: str | None = None,
    origin_url: str | None = None,
) -> dict:
    headers = {
        "Accept": "application/json",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "User-Agent": user_agent,
    }
    if origin_url:
        origin = origin_from_url(origin_url)
        headers["Origin"] = origin
        headers["Referer"] = origin + "/"
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    if content_type:
        headers["Content-Type"] = content_type
    return headers


def secure_ssl_context() -> ssl.SSLContext:
    context = ssl.create_default_context()
    if hasattr(ssl, "TLSVersion"):
        context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.check_hostname = True
    context.verify_mode = ssl.CERT_REQUIRED
    return context


def http_request(
    method: str,
    url: str,
    headers: dict,
    body: bytes | None,
    timeout: int,
    require_public_resolution: bool = True,
    max_redirects: int = 5,
) -> tuple[int, str, bytes]:
    parsed = validate_https_url(
        url,
        "Request",
        require_public_resolution=require_public_resolution,
    )
    try:
        port = parsed.port or 443
    except ValueError as exc:
        raise RuntimeError(f"Request URL has an invalid port: {url}") from exc

    connection = http.client.HTTPSConnection(
        parsed.hostname,
        port=port,
        timeout=timeout,
        context=secure_ssl_context(),
    )
    try:
        connection.request(method, request_target(parsed), body=body, headers=headers)
        response = connection.getresponse()
        response_body = read_response_stream(response)
        location = response.getheader("Location")
    except (OSError, http.client.HTTPException) as exc:
        raise RuntimeError(f"Network request failed for {url}: {exc}") from exc
    finally:
        connection.close()

    if response.status in {301, 302, 303, 307, 308} and location:
        if max_redirects <= 0:
            raise RuntimeError("Too many HTTP redirects.")
        if method != "GET" and response.status not in {307, 308}:
            raise RuntimeError(
                f"Refusing non-preserving redirect HTTP {response.status} for {method} request."
            )
        redirect_url = resolve_redirect_url(url, location)
        validate_https_url(
            redirect_url,
            "Redirect",
            require_public_resolution=require_public_resolution,
        )
        return http_request(
            method,
            redirect_url,
            headers,
            body,
            timeout,
            require_public_resolution=require_public_resolution,
            max_redirects=max_redirects - 1,
        )

    return response.status, response.reason, response_body


def read_response_stream(response: http.client.HTTPResponse) -> bytes:
    chunks = []
    while True:
        chunk = response.read(HTTP_READ_CHUNK_SIZE)
        if not chunk:
            break
        chunks.append(chunk)
    return b"".join(chunks)


def retry_delay_from_body(response_body: bytes, fallback: int, maximum: int) -> int:
    delay = fallback
    try:
        data = json.loads(response_body.decode("utf-8"))
    except Exception:
        data = {}
    if isinstance(data, dict):
        retry_after = data.get("retry_after")
        if isinstance(retry_after, (int, float)) and retry_after >= 0:
            delay = int(retry_after)
    return max(0, min(delay, maximum))


def format_api_error(status: int, response_body: bytes) -> str:
    details = response_body.decode("utf-8", errors="replace")
    try:
        data = json.loads(details)
    except json.JSONDecodeError:
        return details
    if not isinstance(data, dict):
        return details

    parts = []
    title = data.get("title") or data.get("error_name") or data.get("message")
    detail = data.get("detail") or data.get("error")
    retryable = data.get("retryable")
    retry_after = data.get("retry_after")
    if title:
        parts.append(str(title))
    if detail and detail != title:
        parts.append(str(detail))
    if retryable is not None:
        parts.append(f"retryable={retryable}")
    if retry_after is not None:
        parts.append(f"retry_after={retry_after}s")
    return "; ".join(parts) if parts else details


def request_api_json(
    url: str,
    headers: dict,
    body: bytes,
    timeout: int,
    retries: int,
    retry_delay: int,
    max_retry_delay: int,
) -> dict:
    retryable_statuses = {429, 500, 502, 503, 504}
    attempts = max(0, retries) + 1
    last_status = 0
    last_body = b""
    last_reason = ""

    for attempt in range(attempts):
        try:
            status, reason, response_body = http_request(
                "POST",
                url,
                headers,
                body,
                timeout,
                require_public_resolution=False,
            )
        except RuntimeError:
            if attempt + 1 >= attempts:
                raise
            time.sleep(max(0, retry_delay))
            continue

        if status < 400:
            try:
                return json.loads(response_body.decode("utf-8"))
            except json.JSONDecodeError as exc:
                raise RuntimeError(
                    f"API response was not valid JSON. HTTP {status} {reason}."
                ) from exc

        last_status = status
        last_body = response_body
        last_reason = reason
        if status not in retryable_statuses or attempt + 1 >= attempts:
            break
        time.sleep(retry_delay_from_body(response_body, retry_delay, max_retry_delay))

    raise RuntimeError(
        f"API request failed with HTTP {last_status}: "
        f"{format_api_error(last_status, last_body) or last_reason}"
    )


def request_json(
    url: str,
    payload: dict,
    api_key: str,
    timeout: int,
    user_agent: str,
    retries: int,
    retry_delay: int,
    max_retry_delay: int,
) -> dict:
    body = json.dumps(payload).encode("utf-8")
    headers = request_headers(
        api_key,
        user_agent,
        "application/json",
        origin_url=url,
    )
    return request_api_json(
        url,
        headers,
        body,
        timeout,
        retries,
        retry_delay,
        max_retry_delay,
    )


def request_multipart(
    url: str,
    fields: list[tuple[str, str]],
    files: list[tuple[str, str, str, bytes]],
    api_key: str,
    timeout: int,
    user_agent: str,
    retries: int,
    retry_delay: int,
    max_retry_delay: int,
) -> dict:
    body, content_type = encode_multipart(fields, files)
    headers = request_headers(
        api_key,
        user_agent,
        content_type,
        origin_url=url,
    )
    return request_api_json(
        url,
        headers,
        body,
        timeout,
        retries,
        retry_delay,
        max_retry_delay,
    )


def encode_multipart(
    fields: list[tuple[str, str]],
    files: list[tuple[str, str, str, bytes]],
) -> tuple[bytes, str]:
    boundary = f"----gpt-imagegen-{uuid.uuid4().hex}"
    chunks: list[bytes] = []

    def append(value: str | bytes) -> None:
        chunks.append(value if isinstance(value, bytes) else value.encode("utf-8"))

    for name, value in fields:
        append(f"--{boundary}\r\n")
        append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n')
        append(value)
        append("\r\n")

    for name, filename, content_type, data in files:
        escaped_name = name.replace('"', "%22")
        escaped_filename = filename.replace('"', "%22")
        append(f"--{boundary}\r\n")
        append(
            f'Content-Disposition: form-data; name="{escaped_name}"; '
            f'filename="{escaped_filename}"\r\n'
        )
        append(f"Content-Type: {content_type}\r\n\r\n")
        append(data)
        append("\r\n")

    append(f"--{boundary}--\r\n")
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def download_url(url: str, timeout: int, user_agent: str = DEFAULT_USER_AGENT) -> bytes:
    validate_https_url(url, "Image")
    headers = request_headers(user_agent=user_agent)
    headers["Accept"] = "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8"
    status, reason, response_body = http_request(
        "GET",
        url,
        headers,
        None,
        timeout,
        require_public_resolution=True,
    )
    if status >= 400:
        raise RuntimeError(f"Image download failed with HTTP {status}: {reason}")
    return response_body


def png_chunks(data: bytes):
    if not data.startswith(PNG_SIGNATURE):
        raise RuntimeError("--resize-output currently supports PNG responses only.")
    offset = len(PNG_SIGNATURE)
    while offset + 8 <= len(data):
        length = struct.unpack(">I", data[offset : offset + 4])[0]
        chunk_type = data[offset + 4 : offset + 8]
        chunk_data = data[offset + 8 : offset + 8 + length]
        crc = data[offset + 8 + length : offset + 12 + length]
        if len(chunk_data) != length or len(crc) != 4:
            raise RuntimeError("PNG data is truncated.")
        yield chunk_type, chunk_data
        offset += 12 + length
        if chunk_type == b"IEND":
            break


def bytes_per_pixel(color_type: int) -> int:
    channels = {0: 1, 2: 3, 4: 2, 6: 4}.get(color_type)
    if not channels:
        raise RuntimeError(f"Unsupported PNG color type for resize: {color_type}")
    return channels


def unfilter_png_scanline(
    filter_type: int, raw: bytes, previous: bytes, bytes_per_pixel_value: int
) -> bytes:
    result = bytearray(raw)
    for index in range(len(result)):
        left = result[index - bytes_per_pixel_value] if index >= bytes_per_pixel_value else 0
        up = previous[index] if previous else 0
        upper_left = (
            previous[index - bytes_per_pixel_value]
            if previous and index >= bytes_per_pixel_value
            else 0
        )
        if filter_type == 0:
            value = result[index]
        elif filter_type == 1:
            value = result[index] + left
        elif filter_type == 2:
            value = result[index] + up
        elif filter_type == 3:
            value = result[index] + ((left + up) // 2)
        elif filter_type == 4:
            predictor = left + up - upper_left
            distances = (
                abs(predictor - left),
                abs(predictor - up),
                abs(predictor - upper_left),
            )
            value = result[index] + (left, up, upper_left)[distances.index(min(distances))]
        else:
            raise RuntimeError(f"Unsupported PNG filter type: {filter_type}")
        result[index] = value & 0xFF
    return bytes(result)


def write_png_chunk(chunk_type: bytes, chunk_data: bytes) -> bytes:
    crc = binascii.crc32(chunk_type)
    crc = binascii.crc32(chunk_data, crc) & 0xFFFFFFFF
    return struct.pack(">I", len(chunk_data)) + chunk_type + chunk_data + struct.pack(">I", crc)


def resize_png_bytes(image_bytes: bytes, dimensions: str) -> bytes:
    target_width, target_height = parse_dimensions(dimensions, "resize-output")
    width = height = bit_depth = color_type = interlace = None
    idat_parts = []

    for chunk_type, chunk_data in png_chunks(image_bytes):
        if chunk_type == b"IHDR":
            width, height, bit_depth, color_type, _compression, _filter, interlace = struct.unpack(
                ">IIBBBBB", chunk_data
            )
        elif chunk_type == b"IDAT":
            idat_parts.append(chunk_data)

    if not width or not height or bit_depth is None or color_type is None:
        raise RuntimeError("PNG response did not include a valid IHDR chunk.")
    if bit_depth != 8 or interlace != 0:
        raise RuntimeError("--resize-output supports non-interlaced 8-bit PNG images only.")
    if target_width == width and target_height == height:
        return image_bytes

    pixel_size = bytes_per_pixel(color_type)
    stride = width * pixel_size
    raw = zlib.decompress(b"".join(idat_parts))
    rows = []
    previous = b""
    cursor = 0
    for _row in range(height):
        filter_type = raw[cursor]
        cursor += 1
        filtered = raw[cursor : cursor + stride]
        cursor += stride
        row = unfilter_png_scanline(filter_type, filtered, previous, pixel_size)
        rows.append(row)
        previous = row

    resized_rows = []
    for target_y in range(target_height):
        source_y = min(height - 1, (target_y * height) // target_height)
        source_row = rows[source_y]
        output_row = bytearray()
        for target_x in range(target_width):
            source_x = min(width - 1, (target_x * width) // target_width)
            start = source_x * pixel_size
            output_row.extend(source_row[start : start + pixel_size])
        resized_rows.append(b"\x00" + bytes(output_row))

    ihdr = struct.pack(">IIBBBBB", target_width, target_height, bit_depth, color_type, 0, 0, 0)
    compressed = zlib.compress(b"".join(resized_rows))
    return (
        PNG_SIGNATURE
        + write_png_chunk(b"IHDR", ihdr)
        + write_png_chunk(b"IDAT", compressed)
        + write_png_chunk(b"IEND", b"")
    )


def is_url(source: str) -> bool:
    return parse_url(source).scheme in {"http", "https"}


def filename_from_url(url: str) -> str:
    parsed = parse_url(url)
    name = Path(percent_decode(parsed.path)).name
    return name or "image.png"


def file_part_from_source(
    source: str, timeout: int, user_agent: str
) -> tuple[str, str, bytes]:
    if is_url(source):
        filename = filename_from_url(source)
        data = download_url(source, timeout, user_agent)
    else:
        path = Path(source).expanduser()
        if not path.exists():
            raise RuntimeError(f"Input image does not exist: {path}")
        if not path.is_file():
            raise RuntimeError(f"Input image is not a file: {path}")
        filename = path.name
        data = path.read_bytes()

    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    return filename, content_type, data


def image_bytes_from_response(
    data: dict, timeout: int, user_agent: str = DEFAULT_USER_AGENT
) -> bytes:
    items = data.get("data")
    if not isinstance(items, list) or not items:
        raise RuntimeError("API response did not include data[0].")

    first = items[0]
    if not isinstance(first, dict):
        raise RuntimeError("API response data[0] is not an object.")

    b64_image = first.get("b64_json") or first.get("image_base64")
    if b64_image:
        return base64.b64decode(b64_image)

    image_url = first.get("url")
    if image_url:
        return download_url(image_url, timeout, user_agent)

    raise RuntimeError("API response did not include b64_json or url for the image.")


def default_metadata_path(output: Path) -> Path:
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    return output.with_name(f"{output.stem}-{timestamp}.response.json")


def image_payload_fields(args: argparse.Namespace) -> list[tuple[str, str]]:
    fields = [
        ("model", args.model),
        ("prompt", args.prompt),
        ("size", args.size),
        ("quality", args.quality),
    ]
    optional_values = {
        "output_format": args.output_format,
        "background": args.background,
        "moderation": args.moderation,
    }
    if args.input_fidelity and args.model != "gpt-image-2":
        optional_values["input_fidelity"] = args.input_fidelity
    if args.output_compression is not None:
        optional_values["output_compression"] = str(args.output_compression)

    for key, value in optional_values.items():
        if value is not None:
            fields.append((key, value))
    return fields


def image_payload_json(args: argparse.Namespace) -> dict:
    payload = {
        "model": args.model,
        "prompt": args.prompt,
        "size": args.size,
        "quality": args.quality,
    }
    optional_values = {
        "output_format": args.output_format,
        "output_compression": args.output_compression,
        "background": args.background,
        "moderation": args.moderation,
    }
    for key, value in optional_values.items():
        if value is not None:
            payload[key] = value
    return payload


def main() -> int:
    args = parse_args()
    args.base_url = args.base_url.strip()
    args.api_key = args.api_key.strip()
    args.size, args.resize_output = normalize_api_size(args.size, args.resize_output)
    validate_configuration(args.base_url, args.api_key)
    if args.mask and not args.images:
        raise RuntimeError("--mask requires at least one --image input.")

    output = Path(args.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    if args.images:
        fields = image_payload_fields(args)
        files = []
        for image_source in args.images:
            filename, content_type, data = file_part_from_source(
                image_source, args.timeout, args.user_agent
            )
            files.append(("image[]", filename, content_type, data))
        if args.mask:
            filename, content_type, data = file_part_from_source(
                args.mask, args.timeout, args.user_agent
            )
            files.append(("mask", filename, content_type, data))
        url = endpoint_from_base_url(args.base_url, "edits")
        response_json = request_multipart(
            url,
            fields,
            files,
            args.api_key,
            args.timeout,
            args.user_agent,
            args.retries,
            args.retry_delay,
            args.max_retry_delay,
        )
        operation = "edit"
    else:
        payload = image_payload_json(args)
        url = endpoint_from_base_url(args.base_url, "generations")
        response_json = request_json(
            url,
            payload,
            args.api_key,
            args.timeout,
            args.user_agent,
            args.retries,
            args.retry_delay,
            args.max_retry_delay,
        )
        operation = "generate"

    image_bytes = image_bytes_from_response(
        response_json, args.timeout, args.user_agent
    )
    if args.resize_output:
        image_bytes = resize_png_bytes(image_bytes, args.resize_output)
    output.write_bytes(image_bytes)

    if args.metadata:
        metadata_path = Path(args.metadata).expanduser().resolve()
        metadata_path.parent.mkdir(parents=True, exist_ok=True)
        metadata_path.write_text(
            json.dumps(response_json, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    guessed_type = mimetypes.guess_type(str(output))[0] or "image"
    print(
        json.dumps(
            {
                "operation": operation,
                "output": str(output),
                "content_type": guessed_type,
                "api_size": args.size,
                "resize_output": args.resize_output,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"generate_image.py: error: {exc}", file=sys.stderr)
        raise SystemExit(1)
