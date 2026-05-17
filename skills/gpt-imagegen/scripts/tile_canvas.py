#!/usr/bin/env python3
"""Prepare, split, and stitch PNG canvases for tiled image workflows."""

from __future__ import annotations

import argparse
import json
import math
import sys
import zlib
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from generate_image import (
    PNG_SIGNATURE,
    parse_dimensions,
    png_chunks,
    unfilter_png_scanline,
    write_png_chunk,
)


def parse_grid(value: str) -> tuple[int, int]:
    parts = value.lower().split("x")
    if len(parts) != 2 or not all(part.isdigit() for part in parts):
        raise RuntimeError("--grid must use COLSxROWS, such as 2x2.")
    cols, rows = (int(part) for part in parts)
    if cols < 1 or rows < 1:
        raise RuntimeError("--grid values must be at least 1.")
    return cols, rows


def decode_png(path: Path) -> tuple[int, int, bytes]:
    data = path.read_bytes()
    if not data.startswith(PNG_SIGNATURE):
        raise RuntimeError(f"PNG input required: {path}")

    width = height = bit_depth = color_type = interlace = None
    idat_parts: list[bytes] = []
    for chunk_type, chunk_data in png_chunks(data):
        if chunk_type == b"IHDR":
            width = int.from_bytes(chunk_data[0:4], "big")
            height = int.from_bytes(chunk_data[4:8], "big")
            bit_depth = chunk_data[8]
            color_type = chunk_data[9]
            interlace = chunk_data[12]
        elif chunk_type == b"IDAT":
            idat_parts.append(chunk_data)

    if not width or not height or bit_depth is None or color_type is None:
        raise RuntimeError(f"PNG missing IHDR: {path}")
    if bit_depth != 8 or interlace != 0:
        raise RuntimeError("Only non-interlaced 8-bit PNG files are supported.")
    if color_type not in {2, 6}:
        raise RuntimeError("Only RGB and RGBA PNG files are supported.")

    channels = 3 if color_type == 2 else 4
    stride = width * channels
    raw = zlib.decompress(b"".join(idat_parts))
    rows: list[bytes] = []
    previous = b""
    cursor = 0
    for _ in range(height):
        filter_type = raw[cursor]
        cursor += 1
        filtered = raw[cursor : cursor + stride]
        cursor += stride
        row = unfilter_png_scanline(filter_type, filtered, previous, channels)
        rows.append(row)
        previous = row

    rgba = bytearray(width * height * 4)
    offset = 0
    for row in rows:
        if channels == 4:
            rgba[offset : offset + len(row)] = row
            offset += len(row)
            continue
        for index in range(0, len(row), 3):
            rgba[offset : offset + 4] = row[index : index + 3] + b"\xff"
            offset += 4
    return width, height, bytes(rgba)


def encode_png(width: int, height: int, rgba: bytes) -> bytes:
    stride = width * 4
    rows = bytearray()
    for row_index in range(height):
        start = row_index * stride
        rows.extend(b"\x00")
        rows.extend(rgba[start : start + stride])
    ihdr = (
        width.to_bytes(4, "big")
        + height.to_bytes(4, "big")
        + bytes([8, 6, 0, 0, 0])
    )
    compressed = zlib.compress(bytes(rows))
    return (
        PNG_SIGNATURE
        + write_png_chunk(b"IHDR", ihdr)
        + write_png_chunk(b"IDAT", compressed)
        + write_png_chunk(b"IEND", b"")
    )


def resize_rgba(
    src_width: int,
    src_height: int,
    rgba: bytes,
    dst_width: int,
    dst_height: int,
) -> bytes:
    if src_width == dst_width and src_height == dst_height:
        return rgba
    result = bytearray(dst_width * dst_height * 4)
    x_scale = src_width / dst_width
    y_scale = src_height / dst_height
    for y in range(dst_height):
        src_y = (y + 0.5) * y_scale - 0.5
        y0 = min(max(int(math.floor(src_y)), 0), src_height - 1)
        y1 = min(y0 + 1, src_height - 1)
        wy = src_y - y0
        for x in range(dst_width):
            src_x = (x + 0.5) * x_scale - 0.5
            x0 = min(max(int(math.floor(src_x)), 0), src_width - 1)
            x1 = min(x0 + 1, src_width - 1)
            wx = src_x - x0

            top_left = (y0 * src_width + x0) * 4
            top_right = (y0 * src_width + x1) * 4
            bottom_left = (y1 * src_width + x0) * 4
            bottom_right = (y1 * src_width + x1) * 4
            out = (y * dst_width + x) * 4
            for channel in range(4):
                value = (
                    rgba[top_left + channel] * (1 - wx) * (1 - wy)
                    + rgba[top_right + channel] * wx * (1 - wy)
                    + rgba[bottom_left + channel] * (1 - wx) * wy
                    + rgba[bottom_right + channel] * wx * wy
                )
                result[out + channel] = max(0, min(255, round(value)))
    return bytes(result)


def clamp_byte(value: float) -> int:
    return max(0, min(255, round(value)))


def pixel_rgb(rgba: bytes, width: int, height: int, x: int, y: int) -> tuple[int, int, int]:
    x = min(max(x, 0), width - 1)
    y = min(max(y, 0), height - 1)
    offset = (y * width + x) * 4
    return rgba[offset], rgba[offset + 1], rgba[offset + 2]


def box_blur_rgba(width: int, height: int, rgba: bytes, radius: int) -> bytes:
    if radius <= 0:
        return rgba
    result = bytearray(width * height * 4)
    for y in range(height):
        y0 = max(0, y - radius)
        y1 = min(height - 1, y + radius)
        for x in range(width):
            x0 = max(0, x - radius)
            x1 = min(width - 1, x + radius)
            totals = [0, 0, 0, 0]
            count = 0
            for sample_y in range(y0, y1 + 1):
                row_start = (sample_y * width + x0) * 4
                for sample_x in range(x0, x1 + 1):
                    offset = row_start + (sample_x - x0) * 4
                    totals[0] += rgba[offset]
                    totals[1] += rgba[offset + 1]
                    totals[2] += rgba[offset + 2]
                    totals[3] += rgba[offset + 3]
                    count += 1
            out = (y * width + x) * 4
            for channel in range(4):
                result[out + channel] = totals[channel] // count
    return bytes(result)


def enhance_rgba(
    width: int,
    height: int,
    rgba: bytes,
    sharpness: float,
    contrast: float,
    denoise: int,
    grain: float,
) -> bytes:
    smoothed = box_blur_rgba(width, height, rgba, denoise)
    result = bytearray(width * height * 4)
    for y in range(height):
        for x in range(width):
            offset = (y * width + x) * 4
            center = smoothed[offset : offset + 4]
            left = pixel_rgb(smoothed, width, height, x - 1, y)
            right = pixel_rgb(smoothed, width, height, x + 1, y)
            up = pixel_rgb(smoothed, width, height, x, y - 1)
            down = pixel_rgb(smoothed, width, height, x, y + 1)
            local_rgb = []
            for channel in range(3):
                neighbor_average = (
                    left[channel] + right[channel] + up[channel] + down[channel]
                ) / 4.0
                sharpened = center[channel] + sharpness * (center[channel] - neighbor_average)
                contrasted = (sharpened - 128.0) * contrast + 128.0
                if grain:
                    noise = ((x * 131 + y * 197 + channel * 53) % 17 - 8) * grain
                    contrasted += noise
                local_rgb.append(clamp_byte(contrasted))
            result[offset : offset + 3] = bytes(local_rgb)
            result[offset + 3] = center[3]
    return bytes(result)


def texture_score(width: int, height: int, rgba: bytes, samples: int = 120) -> float:
    step = max(1, min(width, height) // samples)
    total = 0.0
    count = 0
    for y in range(step, height - step, step):
        for x in range(step, width - step, step):
            offset = (y * width + x) * 4
            center = sum(rgba[offset : offset + 3]) / 3.0
            neighbor_offsets = (
                (y * width + x - step) * 4,
                (y * width + x + step) * 4,
                ((y - step) * width + x) * 4,
                ((y + step) * width + x) * 4,
            )
            for neighbor_offset in neighbor_offsets:
                neighbor = sum(rgba[neighbor_offset : neighbor_offset + 3]) / 3.0
                total += abs(center - neighbor)
                count += 1
    return total / count if count else 0.0


def crop_rgba(
    width: int,
    height: int,
    rgba: bytes,
    x: int,
    y: int,
    crop_width: int,
    crop_height: int,
) -> bytes:
    if x < 0 or y < 0 or x + crop_width > width or y + crop_height > height:
        raise RuntimeError("Crop rectangle is outside the canvas.")
    result = bytearray(crop_width * crop_height * 4)
    for row in range(crop_height):
        src_start = ((y + row) * width + x) * 4
        dst_start = row * crop_width * 4
        result[dst_start : dst_start + crop_width * 4] = rgba[
            src_start : src_start + crop_width * 4
        ]
    return bytes(result)


def paste_rgba(
    canvas_width: int,
    canvas_height: int,
    canvas: bytearray,
    tile_width: int,
    tile_height: int,
    tile: bytes,
    x: int,
    y: int,
) -> None:
    for row in range(tile_height):
        dst_start = ((y + row) * canvas_width + x) * 4
        src_start = row * tile_width * 4
        canvas[dst_start : dst_start + tile_width * 4] = tile[
            src_start : src_start + tile_width * 4
        ]


def paste_rgba_blended(
    canvas_width: int,
    canvas_height: int,
    canvas: bytearray,
    tile_width: int,
    tile_height: int,
    tile: bytes,
    x: int,
    y: int,
    edge_blend: int,
) -> None:
    for row in range(tile_height):
        dest_y = y + row
        for col in range(tile_width):
            dest_x = x + col
            weight = 1.0
            if edge_blend > 0:
                if x > 0 and col < edge_blend:
                    weight = min(weight, col / edge_blend)
                if x + tile_width < canvas_width and col >= tile_width - edge_blend:
                    weight = min(weight, (tile_width - 1 - col) / edge_blend)
                if y > 0 and row < edge_blend:
                    weight = min(weight, row / edge_blend)
                if y + tile_height < canvas_height and row >= tile_height - edge_blend:
                    weight = min(weight, (tile_height - 1 - row) / edge_blend)
                weight = max(0.0, min(1.0, weight))
            src = (row * tile_width + col) * 4
            dst = (dest_y * canvas_width + dest_x) * 4
            for channel in range(4):
                canvas[dst + channel] = clamp_byte(
                    tile[src + channel] * weight
                    + canvas[dst + channel] * (1.0 - weight)
                )


def rgba_channel_stats(rgba: bytes) -> tuple[list[float], list[float]]:
    pixel_count = max(1, len(rgba) // 4)
    means = [0.0, 0.0, 0.0]
    for offset in range(0, len(rgba), 4):
        for channel in range(3):
            means[channel] += rgba[offset + channel]
    means = [value / pixel_count for value in means]

    variances = [0.0, 0.0, 0.0]
    for offset in range(0, len(rgba), 4):
        for channel in range(3):
            delta = rgba[offset + channel] - means[channel]
            variances[channel] += delta * delta
    stddevs = [(value / pixel_count) ** 0.5 for value in variances]
    return means, stddevs


def color_match_rgba(reference: bytes, target: bytes, strength: float) -> bytes:
    if strength <= 0:
        return target
    ref_means, ref_stddevs = rgba_channel_stats(reference)
    target_means, target_stddevs = rgba_channel_stats(target)
    result = bytearray(target)
    for offset in range(0, len(target), 4):
        for channel in range(3):
            if target_stddevs[channel] < 1e-6:
                matched = ref_means[channel]
            else:
                matched = (
                    (target[offset + channel] - target_means[channel])
                    * (ref_stddevs[channel] / target_stddevs[channel])
                    + ref_means[channel]
                )
            result[offset + channel] = clamp_byte(
                target[offset + channel] * (1.0 - strength) + matched * strength
            )
        result[offset + 3] = target[offset + 3]
    return bytes(result)


def center_crop_to_aspect(
    width: int,
    height: int,
    rgba: bytes,
    target_width: int,
    target_height: int,
) -> tuple[int, int, bytes]:
    if target_width <= 0 or target_height <= 0:
        raise RuntimeError("Target aspect dimensions must be positive.")
    target_aspect = target_width / target_height
    current_aspect = width / height
    if abs(current_aspect - target_aspect) < 1e-6:
        return width, height, rgba
    if current_aspect > target_aspect:
        crop_width = max(1, round(height * target_aspect))
        crop_x = (width - crop_width) // 2
        return crop_width, height, crop_rgba(width, height, rgba, crop_x, 0, crop_width, height)
    crop_height = max(1, round(width / target_aspect))
    crop_y = (height - crop_height) // 2
    return width, crop_height, crop_rgba(width, height, rgba, 0, crop_y, width, crop_height)


def brightness(rgba: bytes, width: int, height: int, x: int, y: int) -> float:
    x = min(max(x, 0), width - 1)
    y = min(max(y, 0), height - 1)
    offset = (y * width + x) * 4
    return (rgba[offset] + rgba[offset + 1] + rgba[offset + 2]) / 3.0


def reference_edge_weight(
    reference: bytes,
    width: int,
    height: int,
    x: int,
    y: int,
    edge_floor: float,
    edge_gain: float,
) -> float:
    center = brightness(reference, width, height, x, y)
    diff = (
        abs(center - brightness(reference, width, height, x - 1, y))
        + abs(center - brightness(reference, width, height, x + 1, y))
        + abs(center - brightness(reference, width, height, x, y - 1))
        + abs(center - brightness(reference, width, height, x, y + 1))
    ) / 4.0
    scaled = min(1.0, (diff / 32.0) * edge_gain)
    return max(0.0, min(1.0, edge_floor + (1.0 - edge_floor) * scaled))


def transfer_detail_rgba(
    width: int,
    height: int,
    reference: bytes,
    donor: bytes,
    strength: float,
    radius: int,
    edge_floor: float,
    edge_gain: float,
) -> bytes:
    donor_blur = box_blur_rgba(width, height, donor, radius)
    result = bytearray(reference)
    for y in range(height):
        for x in range(width):
            offset = (y * width + x) * 4
            weight = reference_edge_weight(
                reference,
                width,
                height,
                x,
                y,
                edge_floor,
                edge_gain,
            )
            for channel in range(3):
                detail = donor[offset + channel] - donor_blur[offset + channel]
                result[offset + channel] = clamp_byte(
                    reference[offset + channel] + detail * strength * weight
                )
            result[offset + 3] = reference[offset + 3]
    return bytes(result)


def split_bounds(length: int, parts: int, index: int) -> tuple[int, int]:
    start = (length * index) // parts
    end = (length * (index + 1)) // parts
    return start, end


def tile_overlap_weight(
    local_x: int,
    local_y: int,
    tile: dict,
    canvas_width: int,
    canvas_height: int,
    overlap: int,
) -> float:
    if overlap <= 0:
        return 1.0
    weight = 1.0
    if tile["crop_x"] > 0 and local_x < overlap:
        weight *= max(local_x / overlap, 1e-6)
    right_margin = canvas_width - (tile["crop_x"] + tile["crop_width"])
    if right_margin > 0 and local_x >= tile["crop_width"] - overlap:
        distance = tile["crop_width"] - 1 - local_x
        weight *= max(distance / overlap, 1e-6)
    if tile["crop_y"] > 0 and local_y < overlap:
        weight *= max(local_y / overlap, 1e-6)
    bottom_margin = canvas_height - (tile["crop_y"] + tile["crop_height"])
    if bottom_margin > 0 and local_y >= tile["crop_height"] - overlap:
        distance = tile["crop_height"] - 1 - local_y
        weight *= max(distance / overlap, 1e-6)
    return weight


def manifest_tiles(canvas_width: int, canvas_height: int, cols: int, rows: int, overlap: int) -> list[dict]:
    tiles = []
    for row in range(rows):
        slot_y0, slot_y1 = split_bounds(canvas_height, rows, row)
        for col in range(cols):
            slot_x0, slot_x1 = split_bounds(canvas_width, cols, col)
            crop_x0 = max(0, slot_x0 - overlap)
            crop_y0 = max(0, slot_y0 - overlap)
            crop_x1 = min(canvas_width, slot_x1 + overlap)
            crop_y1 = min(canvas_height, slot_y1 + overlap)
            tile_id = f"r{row}c{col}"
            tiles.append(
                {
                    "id": tile_id,
                    "file": f"{tile_id}.png",
                    "slot_x": slot_x0,
                    "slot_y": slot_y0,
                    "slot_width": slot_x1 - slot_x0,
                    "slot_height": slot_y1 - slot_y0,
                    "crop_x": crop_x0,
                    "crop_y": crop_y0,
                    "crop_width": crop_x1 - crop_x0,
                    "crop_height": crop_y1 - crop_y0,
                }
            )
    return tiles


def write_manifest(path: Path, manifest: dict) -> None:
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def command_prepare(args: argparse.Namespace) -> int:
    input_path = Path(args.input).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()
    canvas_width, canvas_height = parse_dimensions(args.canvas, "canvas")
    src_width, src_height, src_rgba = decode_png(input_path)

    if args.mode == "stretch":
        resized = resize_rgba(src_width, src_height, src_rgba, canvas_width, canvas_height)
        output_rgba = resized
    else:
        scale_x = canvas_width / src_width
        scale_y = canvas_height / src_height
        scale = max(scale_x, scale_y) if args.mode == "cover" else min(scale_x, scale_y)
        resized_width = max(1, round(src_width * scale))
        resized_height = max(1, round(src_height * scale))
        resized = resize_rgba(src_width, src_height, src_rgba, resized_width, resized_height)
        canvas = bytearray(canvas_width * canvas_height * 4)
        for index in range(3, len(canvas), 4):
            canvas[index] = 255
        offset_x = (canvas_width - resized_width) // 2
        offset_y = (canvas_height - resized_height) // 2
        if args.mode == "cover":
            crop_x = max(0, (resized_width - canvas_width) // 2)
            crop_y = max(0, (resized_height - canvas_height) // 2)
            output_rgba = crop_rgba(
                resized_width,
                resized_height,
                resized,
                crop_x,
                crop_y,
                canvas_width,
                canvas_height,
            )
        else:
            paste_rgba(canvas_width, canvas_height, canvas, resized_width, resized_height, resized, offset_x, offset_y)
            output_rgba = bytes(canvas)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(encode_png(canvas_width, canvas_height, output_rgba))
    print(
        json.dumps(
            {
                "operation": "prepare",
                "input": str(input_path),
                "output": str(output_path),
                "canvas": args.canvas,
                "mode": args.mode,
            },
            indent=2,
        )
    )
    return 0


def command_split(args: argparse.Namespace) -> int:
    input_path = Path(args.input).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    cols, rows = parse_grid(args.grid)
    overlap = args.overlap
    if overlap < 0:
        raise RuntimeError("--overlap must be greater than or equal to 0.")

    width, height, rgba = decode_png(input_path)
    tiles = manifest_tiles(width, height, cols, rows, overlap)

    output_dir.mkdir(parents=True, exist_ok=True)
    for tile in tiles:
        tile_bytes = crop_rgba(
            width,
            height,
            rgba,
            tile["crop_x"],
            tile["crop_y"],
            tile["crop_width"],
            tile["crop_height"],
        )
        (output_dir / tile["file"]).write_bytes(
            encode_png(tile["crop_width"], tile["crop_height"], tile_bytes)
        )

    manifest = {
        "canvas_width": width,
        "canvas_height": height,
        "grid_cols": cols,
        "grid_rows": rows,
        "overlap": overlap,
        "source_image": str(input_path),
        "tiles": tiles,
    }
    write_manifest(output_dir / "manifest.json", manifest)
    print(
        json.dumps(
            {
                "operation": "split",
                "input": str(input_path),
                "output_dir": str(output_dir),
                "manifest": str(output_dir / "manifest.json"),
                "tiles": [str(output_dir / tile["file"]) for tile in tiles],
            },
            indent=2,
        )
    )
    return 0


def command_manifest(args: argparse.Namespace) -> int:
    manifest_path = Path(args.manifest).expanduser().resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    tiles = manifest["tiles"]
    max_tile_width = max(int(tile["crop_width"]) for tile in tiles)
    max_tile_height = max(int(tile["crop_height"]) for tile in tiles)
    summary = {
        "operation": "manifest",
        "manifest": str(manifest_path),
        "canvas_width": manifest["canvas_width"],
        "canvas_height": manifest["canvas_height"],
        "grid_cols": manifest["grid_cols"],
        "grid_rows": manifest["grid_rows"],
        "overlap": manifest["overlap"],
        "tile_count": len(tiles),
        "tile_sizes": sorted(
            {
                f'{tile["crop_width"]}x{tile["crop_height"]}'
                for tile in tiles
            }
        ),
        "detail_scale_vs_1536x1024": {
            "x": round(1536 / max_tile_width, 2),
            "y": round(1024 / max_tile_height, 2),
        },
    }
    print(json.dumps(summary, indent=2))
    return 0


def command_stitch(args: argparse.Namespace) -> int:
    manifest_path = Path(args.manifest).expanduser().resolve()
    input_dir = Path(args.input_dir).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    canvas_width = int(manifest["canvas_width"])
    canvas_height = int(manifest["canvas_height"])
    overlap = int(manifest["overlap"])
    tiles = manifest["tiles"]

    sums = [0.0] * (canvas_width * canvas_height * 4)
    weights = [0.0] * (canvas_width * canvas_height)

    for tile in tiles:
        tile_path = input_dir / tile["file"]
        tile_width, tile_height, tile_rgba = decode_png(tile_path)
        if tile_width != tile["crop_width"] or tile_height != tile["crop_height"]:
            tile_rgba = resize_rgba(
                tile_width,
                tile_height,
                tile_rgba,
                tile["crop_width"],
                tile["crop_height"],
            )
            tile_width = tile["crop_width"]
            tile_height = tile["crop_height"]

        for local_y in range(tile_height):
            dest_y = tile["crop_y"] + local_y
            for local_x in range(tile_width):
                dest_x = tile["crop_x"] + local_x
                canvas_index = dest_y * canvas_width + dest_x
                tile_index = (local_y * tile_width + local_x) * 4
                alpha = tile_rgba[tile_index + 3] / 255.0
                if alpha <= 0:
                    continue
                weight = tile_overlap_weight(
                    local_x,
                    local_y,
                    tile,
                    canvas_width,
                    canvas_height,
                    overlap,
                ) * alpha
                weights[canvas_index] += weight
                sum_index = canvas_index * 4
                for channel in range(4):
                    sums[sum_index + channel] += tile_rgba[tile_index + channel] * weight

    output_rgba = bytearray(canvas_width * canvas_height * 4)
    for pixel_index, weight in enumerate(weights):
        out = pixel_index * 4
        if weight <= 0:
            output_rgba[out : out + 4] = b"\x00\x00\x00\xff"
            continue
        for channel in range(4):
            output_rgba[out + channel] = max(
                0,
                min(255, round(sums[out + channel] / weight)),
            )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(encode_png(canvas_width, canvas_height, bytes(output_rgba)))
    print(
        json.dumps(
            {
                "operation": "stitch",
                "manifest": str(manifest_path),
                "input_dir": str(input_dir),
                "output": str(output_path),
                "canvas_width": canvas_width,
                "canvas_height": canvas_height,
            },
            indent=2,
        )
    )
    return 0


def command_stitch_slots(args: argparse.Namespace) -> int:
    manifest_path = Path(args.manifest).expanduser().resolve()
    input_dir = Path(args.input_dir).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()
    base_path = Path(args.base).expanduser().resolve() if args.base else None
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    canvas_width = int(manifest["canvas_width"])
    canvas_height = int(manifest["canvas_height"])
    tiles = manifest["tiles"]

    if base_path:
        base_width, base_height, base_rgba = decode_png(base_path)
        if base_width != canvas_width or base_height != canvas_height:
            raise RuntimeError("Base image dimensions must match manifest canvas.")
        canvas = bytearray(base_rgba)
    else:
        canvas = bytearray(canvas_width * canvas_height * 4)
        for index in range(3, len(canvas), 4):
            canvas[index] = 255

    source_width = source_height = source_rgba = None
    source_image = manifest.get("source_image")
    if source_image:
        source_path = Path(source_image)
        if source_path.exists():
            source_width, source_height, source_rgba = decode_png(source_path)

    for tile in tiles:
        tile_path = input_dir / tile["file"]
        tile_width, tile_height, tile_rgba = decode_png(tile_path)
        if tile_width != tile["crop_width"] or tile_height != tile["crop_height"]:
            tile_rgba = resize_rgba(
                tile_width,
                tile_height,
                tile_rgba,
                tile["crop_width"],
                tile["crop_height"],
            )
            tile_width = tile["crop_width"]
            tile_height = tile["crop_height"]

        slot_offset_x = tile["slot_x"] - tile["crop_x"]
        slot_offset_y = tile["slot_y"] - tile["crop_y"]
        slot_rgba = crop_rgba(
            tile_width,
            tile_height,
            tile_rgba,
            slot_offset_x,
            slot_offset_y,
            tile["slot_width"],
            tile["slot_height"],
        )

        if (
            source_rgba is not None
            and source_width == canvas_width
            and source_height == canvas_height
            and args.color_match > 0
        ):
            reference_rgba = crop_rgba(
                canvas_width,
                canvas_height,
                source_rgba,
                tile["slot_x"],
                tile["slot_y"],
                tile["slot_width"],
                tile["slot_height"],
            )
            slot_rgba = color_match_rgba(reference_rgba, slot_rgba, args.color_match)

        paste_rgba_blended(
            canvas_width,
            canvas_height,
            canvas,
            tile["slot_width"],
            tile["slot_height"],
            slot_rgba,
            tile["slot_x"],
            tile["slot_y"],
            args.edge_blend,
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(encode_png(canvas_width, canvas_height, bytes(canvas)))
    print(
        json.dumps(
            {
                "operation": "stitch-slots",
                "manifest": str(manifest_path),
                "input_dir": str(input_dir),
                "base": str(base_path) if base_path else None,
                "output": str(output_path),
                "canvas_width": canvas_width,
                "canvas_height": canvas_height,
                "color_match": args.color_match,
                "edge_blend": args.edge_blend,
            },
            indent=2,
        )
    )
    return 0


def command_stitch_upscaled_slots(args: argparse.Namespace) -> int:
    manifest_path = Path(args.manifest).expanduser().resolve()
    input_dir = Path(args.input_dir).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    source_width = int(manifest["canvas_width"])
    source_height = int(manifest["canvas_height"])
    output_width = max(1, round(source_width * args.scale))
    output_height = max(1, round(source_height * args.scale))
    tiles = manifest["tiles"]
    tile_filter = set(args.tiles or [])

    source_rgba = None
    source_image = args.base or manifest.get("source_image")
    if source_image:
        source_path = Path(source_image).expanduser().resolve()
        if source_path.exists():
            base_width, base_height, base_rgba = decode_png(source_path)
            if base_width == source_width and base_height == source_height:
                source_rgba = base_rgba

    if source_rgba is not None:
        canvas = bytearray(
            resize_rgba(source_width, source_height, source_rgba, output_width, output_height)
        )
    else:
        canvas = bytearray(output_width * output_height * 4)
        for index in range(3, len(canvas), 4):
            canvas[index] = 255

    processed = []
    for tile in tiles:
        tile_id = tile["id"]
        if tile_filter and tile_id not in tile_filter:
            continue

        tile_path = input_dir / tile["file"]
        tile_width, tile_height, tile_rgba = decode_png(tile_path)
        if args.fit == "cover":
            tile_width, tile_height, tile_rgba = center_crop_to_aspect(
                tile_width,
                tile_height,
                tile_rgba,
                tile["crop_width"],
                tile["crop_height"],
            )

        slot_offset_x = tile["slot_x"] - tile["crop_x"]
        slot_offset_y = tile["slot_y"] - tile["crop_y"]
        slot_x0 = round((slot_offset_x / tile["crop_width"]) * tile_width)
        slot_y0 = round((slot_offset_y / tile["crop_height"]) * tile_height)
        slot_x1 = round(((slot_offset_x + tile["slot_width"]) / tile["crop_width"]) * tile_width)
        slot_y1 = round(((slot_offset_y + tile["slot_height"]) / tile["crop_height"]) * tile_height)
        slot_x0 = max(0, min(slot_x0, tile_width - 1))
        slot_y0 = max(0, min(slot_y0, tile_height - 1))
        slot_x1 = max(slot_x0 + 1, min(slot_x1, tile_width))
        slot_y1 = max(slot_y0 + 1, min(slot_y1, tile_height))
        slot_rgba = crop_rgba(
            tile_width,
            tile_height,
            tile_rgba,
            slot_x0,
            slot_y0,
            slot_x1 - slot_x0,
            slot_y1 - slot_y0,
        )

        dest_x0 = round(tile["slot_x"] * args.scale)
        dest_y0 = round(tile["slot_y"] * args.scale)
        dest_x1 = round((tile["slot_x"] + tile["slot_width"]) * args.scale)
        dest_y1 = round((tile["slot_y"] + tile["slot_height"]) * args.scale)
        dest_width = max(1, dest_x1 - dest_x0)
        dest_height = max(1, dest_y1 - dest_y0)
        if slot_x1 - slot_x0 != dest_width or slot_y1 - slot_y0 != dest_height:
            slot_rgba = resize_rgba(slot_x1 - slot_x0, slot_y1 - slot_y0, slot_rgba, dest_width, dest_height)

        if source_rgba is not None and args.color_match > 0:
            reference_slot = crop_rgba(
                source_width,
                source_height,
                source_rgba,
                tile["slot_x"],
                tile["slot_y"],
                tile["slot_width"],
                tile["slot_height"],
            )
            reference_slot = resize_rgba(
                tile["slot_width"],
                tile["slot_height"],
                reference_slot,
                dest_width,
                dest_height,
            )
            slot_rgba = color_match_rgba(reference_slot, slot_rgba, args.color_match)

        paste_rgba_blended(
            output_width,
            output_height,
            canvas,
            dest_width,
            dest_height,
            slot_rgba,
            dest_x0,
            dest_y0,
            args.edge_blend,
        )
        processed.append(tile_id)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(encode_png(output_width, output_height, bytes(canvas)))
    print(
        json.dumps(
            {
                "operation": "stitch-upscaled-slots",
                "manifest": str(manifest_path),
                "input_dir": str(input_dir),
                "output": str(output_path),
                "source_width": source_width,
                "source_height": source_height,
                "output_width": output_width,
                "output_height": output_height,
                "scale": args.scale,
                "fit": args.fit,
                "color_match": args.color_match,
                "edge_blend": args.edge_blend,
                "processed_count": len(processed),
            },
            indent=2,
        )
    )
    return 0


def command_upscaled_detail_transfer(args: argparse.Namespace) -> int:
    manifest_path = Path(args.manifest).expanduser().resolve()
    input_dir = Path(args.input_dir).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    source_width = int(manifest["canvas_width"])
    source_height = int(manifest["canvas_height"])
    output_width = max(1, round(source_width * args.scale))
    output_height = max(1, round(source_height * args.scale))
    tiles = manifest["tiles"]
    tile_filter = set(args.tiles or [])

    source_image = args.base or manifest.get("source_image")
    if not source_image:
        raise RuntimeError("--base is required when manifest has no source_image.")
    source_path = Path(source_image).expanduser().resolve()
    base_width, base_height, base_rgba = decode_png(source_path)
    if base_width != source_width or base_height != source_height:
        raise RuntimeError("Base image dimensions must match the tile manifest canvas.")

    canvas = bytearray(resize_rgba(source_width, source_height, base_rgba, output_width, output_height))
    processed = []

    for tile in tiles:
        tile_id = tile["id"]
        if tile_filter and tile_id not in tile_filter:
            continue

        tile_path = input_dir / tile["file"]
        tile_width, tile_height, tile_rgba = decode_png(tile_path)
        if args.fit == "cover":
            tile_width, tile_height, tile_rgba = center_crop_to_aspect(
                tile_width,
                tile_height,
                tile_rgba,
                tile["crop_width"],
                tile["crop_height"],
            )

        slot_offset_x = tile["slot_x"] - tile["crop_x"]
        slot_offset_y = tile["slot_y"] - tile["crop_y"]
        slot_x0 = round((slot_offset_x / tile["crop_width"]) * tile_width)
        slot_y0 = round((slot_offset_y / tile["crop_height"]) * tile_height)
        slot_x1 = round(((slot_offset_x + tile["slot_width"]) / tile["crop_width"]) * tile_width)
        slot_y1 = round(((slot_offset_y + tile["slot_height"]) / tile["crop_height"]) * tile_height)
        slot_x0 = max(0, min(slot_x0, tile_width - 1))
        slot_y0 = max(0, min(slot_y0, tile_height - 1))
        slot_x1 = max(slot_x0 + 1, min(slot_x1, tile_width))
        slot_y1 = max(slot_y0 + 1, min(slot_y1, tile_height))
        donor_slot = crop_rgba(
            tile_width,
            tile_height,
            tile_rgba,
            slot_x0,
            slot_y0,
            slot_x1 - slot_x0,
            slot_y1 - slot_y0,
        )

        dest_x0 = round(tile["slot_x"] * args.scale)
        dest_y0 = round(tile["slot_y"] * args.scale)
        dest_x1 = round((tile["slot_x"] + tile["slot_width"]) * args.scale)
        dest_y1 = round((tile["slot_y"] + tile["slot_height"]) * args.scale)
        dest_width = max(1, dest_x1 - dest_x0)
        dest_height = max(1, dest_y1 - dest_y0)
        if slot_x1 - slot_x0 != dest_width or slot_y1 - slot_y0 != dest_height:
            donor_slot = resize_rgba(
                slot_x1 - slot_x0,
                slot_y1 - slot_y0,
                donor_slot,
                dest_width,
                dest_height,
            )

        reference_slot = crop_rgba(
            output_width,
            output_height,
            bytes(canvas),
            dest_x0,
            dest_y0,
            dest_width,
            dest_height,
        )
        transferred = transfer_detail_rgba(
            dest_width,
            dest_height,
            reference_slot,
            donor_slot,
            args.strength,
            args.radius,
            args.edge_floor,
            args.edge_gain,
        )
        paste_rgba_blended(
            output_width,
            output_height,
            canvas,
            dest_width,
            dest_height,
            transferred,
            dest_x0,
            dest_y0,
            args.edge_blend,
        )
        processed.append(tile_id)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(encode_png(output_width, output_height, bytes(canvas)))
    print(
        json.dumps(
            {
                "operation": "upscaled-detail-transfer",
                "base": str(source_path),
                "manifest": str(manifest_path),
                "input_dir": str(input_dir),
                "output": str(output_path),
                "source_width": source_width,
                "source_height": source_height,
                "output_width": output_width,
                "output_height": output_height,
                "scale": args.scale,
                "strength": args.strength,
                "radius": args.radius,
                "edge_floor": args.edge_floor,
                "edge_gain": args.edge_gain,
                "edge_blend": args.edge_blend,
                "processed_count": len(processed),
            },
            indent=2,
        )
    )
    return 0


def command_frequency_composite(args: argparse.Namespace) -> int:
    base_path = Path(args.base).expanduser().resolve()
    donor_path = Path(args.donor).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()
    width, height, base_rgba = decode_png(base_path)
    donor_width, donor_height, donor_rgba = decode_png(donor_path)
    if donor_width != width or donor_height != height:
        donor_rgba = resize_rgba(donor_width, donor_height, donor_rgba, width, height)

    donor_blur = box_blur_rgba(width, height, donor_rgba, args.radius)
    seam_x_values = [int(value) for value in (args.seam_x or [])]
    seam_y_values = [int(value) for value in (args.seam_y or [])]
    result = bytearray(base_rgba)

    for y in range(height):
        row_start = y * width * 4
        y_weight = 1.0
        for seam_y in seam_y_values:
            distance = abs(y - seam_y)
            if distance < args.seam_guard:
                y_weight = min(y_weight, 0.0)
            elif distance < args.seam_guard + args.seam_fade:
                y_weight = min(y_weight, (distance - args.seam_guard) / args.seam_fade)
        for x in range(width):
            x_weight = 1.0
            for seam_x in seam_x_values:
                distance = abs(x - seam_x)
                if distance < args.seam_guard:
                    x_weight = min(x_weight, 0.0)
                elif distance < args.seam_guard + args.seam_fade:
                    x_weight = min(x_weight, (distance - args.seam_guard) / args.seam_fade)
            seam_weight = min(x_weight, y_weight)
            offset = row_start + x * 4
            edge = (
                abs(brightness(base_rgba, width, height, x, y) - brightness(base_rgba, width, height, x - 1, y))
                + abs(brightness(base_rgba, width, height, x, y) - brightness(base_rgba, width, height, x, y - 1))
            )
            edge_weight = min(1.0, args.edge_floor + edge / max(args.edge_divisor, 1e-6))
            strength = args.strength * seam_weight * edge_weight
            for channel in range(3):
                detail = donor_rgba[offset + channel] - donor_blur[offset + channel]
                result[offset + channel] = clamp_byte(base_rgba[offset + channel] + detail * strength)
            result[offset + 3] = base_rgba[offset + 3]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(encode_png(width, height, bytes(result)))
    print(
        json.dumps(
            {
                "operation": "frequency-composite",
                "base": str(base_path),
                "donor": str(donor_path),
                "output": str(output_path),
                "width": width,
                "height": height,
                "strength": args.strength,
                "radius": args.radius,
                "edge_floor": args.edge_floor,
                "edge_divisor": args.edge_divisor,
                "seam_x": seam_x_values,
                "seam_y": seam_y_values,
                "seam_guard": args.seam_guard,
                "seam_fade": args.seam_fade,
            },
            indent=2,
        )
    )
    return 0


def command_enhance(args: argparse.Namespace) -> int:
    input_path = Path(args.input).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()
    width, height, rgba = decode_png(input_path)
    enhanced = enhance_rgba(
        width,
        height,
        rgba,
        args.sharpness,
        args.contrast,
        args.denoise,
        args.grain,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(encode_png(width, height, enhanced))
    print(
        json.dumps(
            {
                "operation": "enhance",
                "input": str(input_path),
                "output": str(output_path),
                "width": width,
                "height": height,
                "sharpness": args.sharpness,
                "contrast": args.contrast,
                "denoise": args.denoise,
                "grain": args.grain,
            },
            indent=2,
        )
    )
    return 0


def command_score(args: argparse.Namespace) -> int:
    before_path = Path(args.before).expanduser().resolve()
    after_path = Path(args.after).expanduser().resolve()
    before_width, before_height, before_rgba = decode_png(before_path)
    after_width, after_height, after_rgba = decode_png(after_path)
    before_score = texture_score(before_width, before_height, before_rgba, args.samples)
    after_score = texture_score(after_width, after_height, after_rgba, args.samples)
    print(
        json.dumps(
            {
                "operation": "score",
                "before": str(before_path),
                "after": str(after_path),
                "before_score": round(before_score, 2),
                "after_score": round(after_score, 2),
                "delta": round(after_score - before_score, 2),
                "ratio": round(after_score / before_score, 2) if before_score else None,
            },
            indent=2,
        )
    )
    return 0


def command_overlay(args: argparse.Namespace) -> int:
    base_path = Path(args.base).expanduser().resolve()
    manifest_path = Path(args.manifest).expanduser().resolve()
    input_dir = Path(args.input_dir).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()
    tile_ids = set(args.tiles)
    if not tile_ids:
        raise RuntimeError("--tiles must include at least one tile id.")

    width, height, base_rgba = decode_png(base_path)
    canvas = bytearray(base_rgba)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if width != int(manifest["canvas_width"]) or height != int(manifest["canvas_height"]):
        raise RuntimeError("Base image dimensions must match the tile manifest canvas.")

    tile_by_id = {tile["id"]: tile for tile in manifest["tiles"]}
    missing = sorted(tile_ids - set(tile_by_id))
    if missing:
        raise RuntimeError(f"Unknown tile id(s): {', '.join(missing)}")

    for tile_id in sorted(tile_ids):
        tile = tile_by_id[tile_id]
        tile_path = input_dir / tile["file"]
        tile_width, tile_height, tile_rgba = decode_png(tile_path)
        if tile_width != tile["crop_width"] or tile_height != tile["crop_height"]:
            tile_rgba = resize_rgba(
                tile_width,
                tile_height,
                tile_rgba,
                tile["crop_width"],
                tile["crop_height"],
            )
            tile_width = tile["crop_width"]
            tile_height = tile["crop_height"]
        paste_rgba(
            width,
            height,
            canvas,
            tile_width,
            tile_height,
            tile_rgba,
            tile["crop_x"],
            tile["crop_y"],
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(encode_png(width, height, bytes(canvas)))
    print(
        json.dumps(
            {
                "operation": "overlay",
                "base": str(base_path),
                "manifest": str(manifest_path),
                "input_dir": str(input_dir),
                "output": str(output_path),
                "tiles": sorted(tile_ids),
            },
            indent=2,
        )
    )
    return 0


def command_detail_transfer(args: argparse.Namespace) -> int:
    base_path = Path(args.base).expanduser().resolve()
    manifest_path = Path(args.manifest).expanduser().resolve()
    input_dir = Path(args.input_dir).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()
    tile_filter = set(args.tiles or [])

    canvas_width, canvas_height, base_rgba = decode_png(base_path)
    canvas = bytearray(base_rgba)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if canvas_width != int(manifest["canvas_width"]) or canvas_height != int(manifest["canvas_height"]):
        raise RuntimeError("Base image dimensions must match the tile manifest canvas.")

    processed = []
    for tile in manifest["tiles"]:
        tile_id = tile["id"]
        if tile_filter and tile_id not in tile_filter:
            continue

        tile_path = input_dir / tile["file"]
        tile_width, tile_height, tile_rgba = decode_png(tile_path)
        if tile_width != tile["crop_width"] or tile_height != tile["crop_height"]:
            tile_rgba = resize_rgba(
                tile_width,
                tile_height,
                tile_rgba,
                tile["crop_width"],
                tile["crop_height"],
            )
            tile_width = tile["crop_width"]
            tile_height = tile["crop_height"]

        slot_offset_x = tile["slot_x"] - tile["crop_x"]
        slot_offset_y = tile["slot_y"] - tile["crop_y"]
        donor_slot = crop_rgba(
            tile_width,
            tile_height,
            tile_rgba,
            slot_offset_x,
            slot_offset_y,
            tile["slot_width"],
            tile["slot_height"],
        )
        reference_slot = crop_rgba(
            canvas_width,
            canvas_height,
            base_rgba,
            tile["slot_x"],
            tile["slot_y"],
            tile["slot_width"],
            tile["slot_height"],
        )
        transferred = transfer_detail_rgba(
            tile["slot_width"],
            tile["slot_height"],
            reference_slot,
            donor_slot,
            args.strength,
            args.radius,
            args.edge_floor,
            args.edge_gain,
        )
        paste_rgba_blended(
            canvas_width,
            canvas_height,
            canvas,
            tile["slot_width"],
            tile["slot_height"],
            transferred,
            tile["slot_x"],
            tile["slot_y"],
            args.edge_blend,
        )
        processed.append(tile_id)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(encode_png(canvas_width, canvas_height, bytes(canvas)))
    print(
        json.dumps(
            {
                "operation": "detail-transfer",
                "base": str(base_path),
                "manifest": str(manifest_path),
                "input_dir": str(input_dir),
                "output": str(output_path),
                "processed_count": len(processed),
                "strength": args.strength,
                "radius": args.radius,
                "edge_floor": args.edge_floor,
                "edge_gain": args.edge_gain,
                "edge_blend": args.edge_blend,
            },
            indent=2,
        )
    )
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare, split, and stitch PNG canvases for tiled image workflows."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare_parser = subparsers.add_parser("prepare", help="Resize a PNG into a target canvas.")
    prepare_parser.add_argument("--input", required=True, help="Input PNG path.")
    prepare_parser.add_argument("--output", required=True, help="Output PNG path.")
    prepare_parser.add_argument(
        "--canvas",
        required=True,
        help="Target canvas size such as 3840x2160.",
    )
    prepare_parser.add_argument(
        "--mode",
        choices=("cover", "contain", "stretch"),
        default="cover",
        help="How the input image should fit inside the target canvas.",
    )
    prepare_parser.set_defaults(func=command_prepare)

    split_parser = subparsers.add_parser("split", help="Split a PNG canvas into overlapping tiles.")
    split_parser.add_argument("--input", required=True, help="Input PNG path.")
    split_parser.add_argument("--output-dir", required=True, help="Directory for tiles and manifest.")
    split_parser.add_argument(
        "--grid",
        default="2x2",
        help="Tile grid using COLSxROWS, such as 2x2.",
    )
    split_parser.add_argument(
        "--overlap",
        type=int,
        default=128,
        help="Tile overlap in pixels. Defaults to 128.",
    )
    split_parser.set_defaults(func=command_split)

    manifest_parser = subparsers.add_parser(
        "manifest",
        help="Print a concise summary of a tile manifest.",
    )
    manifest_parser.add_argument("--manifest", required=True, help="Path to manifest.json.")
    manifest_parser.set_defaults(func=command_manifest)

    stitch_parser = subparsers.add_parser("stitch", help="Stitch tiled PNGs back into one canvas.")
    stitch_parser.add_argument("--manifest", required=True, help="Path to manifest.json.")
    stitch_parser.add_argument("--input-dir", required=True, help="Directory containing the tile PNGs.")
    stitch_parser.add_argument("--output", required=True, help="Output stitched PNG path.")
    stitch_parser.set_defaults(func=command_stitch)

    stitch_slots_parser = subparsers.add_parser(
        "stitch-slots",
        help="Stitch only the center slot of each tile, discarding overlap context.",
    )
    stitch_slots_parser.add_argument("--manifest", required=True, help="Path to manifest.json.")
    stitch_slots_parser.add_argument("--input-dir", required=True, help="Directory containing tile PNGs.")
    stitch_slots_parser.add_argument("--output", required=True, help="Output stitched PNG path.")
    stitch_slots_parser.add_argument(
        "--base",
        help="Optional base PNG to preserve outside pasted slots and support soft edge blending.",
    )
    stitch_slots_parser.add_argument(
        "--color-match",
        type=float,
        default=0.85,
        help="Match each slot to the source crop color statistics. Defaults to 0.85.",
    )
    stitch_slots_parser.add_argument(
        "--edge-blend",
        type=int,
        default=8,
        help="Feather slot edges in pixels when a base image is provided. Defaults to 8.",
    )
    stitch_slots_parser.set_defaults(func=command_stitch_slots)

    stitch_upscaled_parser = subparsers.add_parser(
        "stitch-upscaled-slots",
        help="Stitch generated full-size tile outputs into a supersampled canvas.",
    )
    stitch_upscaled_parser.add_argument("--manifest", required=True, help="Path to manifest.json.")
    stitch_upscaled_parser.add_argument("--input-dir", required=True, help="Directory containing generated tile PNGs.")
    stitch_upscaled_parser.add_argument("--output", required=True, help="Output supersampled PNG path.")
    stitch_upscaled_parser.add_argument(
        "--scale",
        type=float,
        default=4.0,
        help="Output scale relative to the manifest canvas. Defaults to 4.0.",
    )
    stitch_upscaled_parser.add_argument(
        "--fit",
        choices=("cover", "stretch"),
        default="cover",
        help="How generated tile aspect ratios are matched to source crops. Defaults to cover.",
    )
    stitch_upscaled_parser.add_argument(
        "--base",
        help="Optional low-resolution base PNG for color matching. Defaults to manifest source_image when present.",
    )
    stitch_upscaled_parser.add_argument(
        "--color-match",
        type=float,
        default=0.85,
        help="Match each upscaled slot to the base crop color statistics. Defaults to 0.85.",
    )
    stitch_upscaled_parser.add_argument(
        "--edge-blend",
        type=int,
        default=0,
        help=(
            "Feather slot edges in final supersampled pixels. Defaults to 0; "
            "use larger values only when a matching base image is available."
        ),
    )
    stitch_upscaled_parser.add_argument(
        "--tiles",
        nargs="*",
        help="Optional tile ids to process. Defaults to all manifest tiles.",
    )
    stitch_upscaled_parser.set_defaults(func=command_stitch_upscaled_slots)

    upscaled_detail_parser = subparsers.add_parser(
        "upscaled-detail-transfer",
        help="Transfer high-frequency detail from full-size generated tiles onto an upscaled base.",
    )
    upscaled_detail_parser.add_argument("--base", help="Stable base PNG path. Defaults to manifest source_image.")
    upscaled_detail_parser.add_argument("--manifest", required=True, help="Path to manifest.json.")
    upscaled_detail_parser.add_argument("--input-dir", required=True, help="Directory containing generated tile PNGs.")
    upscaled_detail_parser.add_argument("--output", required=True, help="Output supersampled PNG path.")
    upscaled_detail_parser.add_argument(
        "--scale",
        type=float,
        default=2.0,
        help="Output scale relative to the manifest canvas. Defaults to 2.0.",
    )
    upscaled_detail_parser.add_argument(
        "--fit",
        choices=("cover", "stretch"),
        default="cover",
        help="How generated tile aspect ratios are matched to source crops. Defaults to cover.",
    )
    upscaled_detail_parser.add_argument(
        "--tiles",
        nargs="*",
        help="Optional tile ids to process. Defaults to all manifest tiles.",
    )
    upscaled_detail_parser.add_argument(
        "--strength",
        type=float,
        default=0.38,
        help="High-frequency transfer strength. Defaults to 0.38.",
    )
    upscaled_detail_parser.add_argument(
        "--radius",
        type=int,
        default=2,
        help="Blur radius used to isolate donor detail. Defaults to 2.",
    )
    upscaled_detail_parser.add_argument(
        "--edge-floor",
        type=float,
        default=0.08,
        help="Minimum transfer amount in flat areas. Defaults to 0.08.",
    )
    upscaled_detail_parser.add_argument(
        "--edge-gain",
        type=float,
        default=1.15,
        help="How much reference edges guide detail transfer. Defaults to 1.15.",
    )
    upscaled_detail_parser.add_argument(
        "--edge-blend",
        type=int,
        default=0,
        help="Feather slot edges in final supersampled pixels. Defaults to 0.",
    )
    upscaled_detail_parser.set_defaults(func=command_upscaled_detail_transfer)

    frequency_parser = subparsers.add_parser(
        "frequency-composite",
        help="Transfer high-frequency detail from a donor PNG onto a stable base PNG.",
    )
    frequency_parser.add_argument("--base", required=True, help="Stable base PNG path.")
    frequency_parser.add_argument("--donor", required=True, help="Detail donor PNG path.")
    frequency_parser.add_argument("--output", required=True, help="Output PNG path.")
    frequency_parser.add_argument(
        "--strength",
        type=float,
        default=0.55,
        help="High-frequency transfer strength. Defaults to 0.55.",
    )
    frequency_parser.add_argument(
        "--radius",
        type=int,
        default=2,
        help="Blur radius used to isolate donor detail. Defaults to 2.",
    )
    frequency_parser.add_argument(
        "--edge-floor",
        type=float,
        default=0.12,
        help="Minimum edge-aware transfer amount. Defaults to 0.12.",
    )
    frequency_parser.add_argument(
        "--edge-divisor",
        type=float,
        default=42.0,
        help="Larger values reduce edge-aware transfer strength. Defaults to 42.",
    )
    frequency_parser.add_argument(
        "--seam-x",
        nargs="*",
        help="Optional vertical seam x positions to protect from donor detail.",
    )
    frequency_parser.add_argument(
        "--seam-y",
        nargs="*",
        help="Optional horizontal seam y positions to protect from donor detail.",
    )
    frequency_parser.add_argument(
        "--seam-guard",
        type=int,
        default=24,
        help="No-transfer distance around seam positions. Defaults to 24.",
    )
    frequency_parser.add_argument(
        "--seam-fade",
        type=int,
        default=120,
        help="Fade distance after seam guard. Defaults to 120.",
    )
    frequency_parser.set_defaults(func=command_frequency_composite)

    enhance_parser = subparsers.add_parser(
        "enhance",
        help="Apply deterministic whole-image detail enhancement to a PNG.",
    )
    enhance_parser.add_argument("--input", required=True, help="Input PNG path.")
    enhance_parser.add_argument("--output", required=True, help="Output PNG path.")
    enhance_parser.add_argument(
        "--sharpness",
        type=float,
        default=0.45,
        help="Edge sharpening amount. Defaults to 0.45.",
    )
    enhance_parser.add_argument(
        "--contrast",
        type=float,
        default=1.04,
        help="Micro-contrast multiplier. Defaults to 1.04.",
    )
    enhance_parser.add_argument(
        "--denoise",
        type=int,
        default=0,
        help="Optional blur radius before sharpening. Defaults to 0.",
    )
    enhance_parser.add_argument(
        "--grain",
        type=float,
        default=0.0,
        help="Tiny deterministic grain amount. Defaults to 0.0.",
    )
    enhance_parser.set_defaults(func=command_enhance)

    score_parser = subparsers.add_parser(
        "score",
        help="Compare a rough texture/edge score between two PNGs.",
    )
    score_parser.add_argument("--before", required=True, help="Original PNG path.")
    score_parser.add_argument("--after", required=True, help="Enhanced PNG path.")
    score_parser.add_argument(
        "--samples",
        type=int,
        default=120,
        help="Approximate sampling density. Defaults to 120.",
    )
    score_parser.set_defaults(func=command_score)

    overlay_parser = subparsers.add_parser(
        "overlay",
        help="Paste selected manifest tiles over an existing base PNG.",
    )
    overlay_parser.add_argument("--base", required=True, help="Base PNG path.")
    overlay_parser.add_argument("--manifest", required=True, help="Path to manifest.json.")
    overlay_parser.add_argument("--input-dir", required=True, help="Directory containing tile PNGs.")
    overlay_parser.add_argument("--output", required=True, help="Output PNG path.")
    overlay_parser.add_argument(
        "--tiles",
        nargs="+",
        required=True,
        help="Tile ids to paste, such as r0c0 r8c4.",
    )
    overlay_parser.set_defaults(func=command_overlay)

    detail_parser = subparsers.add_parser(
        "detail-transfer",
        help="Transfer high-frequency detail from generated tiles onto a stable base image.",
    )
    detail_parser.add_argument("--base", required=True, help="Stable base PNG path.")
    detail_parser.add_argument("--manifest", required=True, help="Path to manifest.json.")
    detail_parser.add_argument("--input-dir", required=True, help="Directory containing generated tile PNGs.")
    detail_parser.add_argument("--output", required=True, help="Output PNG path.")
    detail_parser.add_argument(
        "--tiles",
        nargs="*",
        help="Optional tile ids to process. Defaults to all manifest tiles.",
    )
    detail_parser.add_argument(
        "--strength",
        type=float,
        default=0.42,
        help="High-frequency transfer strength. Defaults to 0.42.",
    )
    detail_parser.add_argument(
        "--radius",
        type=int,
        default=2,
        help="Blur radius used to isolate donor detail. Defaults to 2.",
    )
    detail_parser.add_argument(
        "--edge-floor",
        type=float,
        default=0.18,
        help="Minimum transfer amount in flat areas. Defaults to 0.18.",
    )
    detail_parser.add_argument(
        "--edge-gain",
        type=float,
        default=1.0,
        help="How much reference edges guide detail transfer. Defaults to 1.0.",
    )
    detail_parser.add_argument(
        "--edge-blend",
        type=int,
        default=8,
        help="Feather slot edges in pixels. Defaults to 8.",
    )
    detail_parser.set_defaults(func=command_detail_transfer)

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
