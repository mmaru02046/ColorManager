from __future__ import annotations

import csv
import json
import struct
from pathlib import Path

from app.models import Palette


def ensure_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def save_palette_json(palette: Palette, output_path: Path) -> None:
    ensure_directory(output_path.parent)
    payload = {
        "name": palette.name,
        "colors": [
            {"name": color.name, "hex": color.hex_code}
            for color in palette.colors
        ],
    }
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")


def save_palette_csv(palette: Palette, output_path: Path) -> None:
    ensure_directory(output_path.parent)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["name", "hex"])
        for color in palette.colors:
            writer.writerow([color.name, color.hex_code])


def save_palette_ase(palette: Palette, output_path: Path) -> None:
    ensure_directory(output_path.parent)
    blocks: list[bytes] = []
    for index, color in enumerate(palette.colors, start=1):
        name = color.name or f"Color {index}"
        encoded_name = (name + "\x00").encode("utf-16-be")
        name_block = struct.pack(">H", len(name) + 1) + encoded_name
        r, g, b = color.rgb
        color_values = struct.pack(">fff", r / 255.0, g / 255.0, b / 255.0)
        payload = name_block + b"RGB " + color_values + struct.pack(">H", 0)
        block = struct.pack(">HI", 0x0001, len(payload)) + payload
        blocks.append(block)

    header = b"ASEF" + struct.pack(">HHI", 1, 0, len(blocks))
    output_path.write_bytes(header + b"".join(blocks))


def save_originlab_pal(palette: Palette, output_path: Path, steps: int = 256) -> None:
    ensure_directory(output_path.parent)
    rgb_values = [color.rgb for color in palette.colors]
    if not rgb_values:
        return
    if len(rgb_values) == 1:
        gradient = [rgb_values[0]] * steps
    else:
        gradient = []
        for index in range(steps):
            position = index / max(1, steps - 1)
            scaled = position * (len(rgb_values) - 1)
            left_index = int(scaled)
            right_index = min(left_index + 1, len(rgb_values) - 1)
            ratio = scaled - left_index
            left = rgb_values[left_index]
            right = rgb_values[right_index]
            gradient.append(
                tuple(
                    round(left[channel] + (right[channel] - left[channel]) * ratio)
                    for channel in range(3)
                )
            )

    palette_data = struct.pack("<HH", 0x0300, len(gradient))
    palette_data += b"".join(struct.pack("<BBBB", b, g, r, 0) for r, g, b in gradient)
    data_chunk = b"data" + struct.pack("<I", len(palette_data)) + palette_data
    riff_payload = b"PAL " + data_chunk
    output_path.write_bytes(b"RIFF" + struct.pack("<I", len(riff_payload)) + riff_payload)

