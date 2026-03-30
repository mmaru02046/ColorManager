from __future__ import annotations

import csv
import json
import struct
from collections import defaultdict
from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QImage

from app.models import ColorEntry, Palette


PALETTE_EXTENSIONS = {".ase", ".csv", ".json", ".gpl", ".pal"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tif", ".tiff"}
PDF_EXTENSIONS = {".pdf"}
SUPPORTED_EXTENSIONS = PALETTE_EXTENSIONS | IMAGE_EXTENSIONS | PDF_EXTENSIONS


def scan_palettes(directory: Path, source_group: str = "materials", image_color_count: int = 5) -> list[Palette]:
    palettes: list[Palette] = []
    if not directory.exists():
        return palettes
    for path in sorted(directory.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        try:
            palette = load_palette(path, color_count=image_color_count)
        except Exception:
            continue
        if palette.colors:
            palette.source_group = source_group
            palettes.append(palette)
    return palettes


def load_palette(path: Path, color_count: int = 5) -> Palette:
    suffix = path.suffix.lower()
    if suffix == ".json":
        return load_json_palette(path)
    if suffix == ".csv":
        return load_csv_palette(path)
    if suffix == ".gpl":
        return load_gpl_palette(path)
    if suffix == ".ase":
        return load_ase_palette(path)
    if suffix == ".pal":
        return load_pal_palette(path)
    if suffix in PDF_EXTENSIONS:
        return load_pdf_palette(path, color_count=color_count)
    if suffix in IMAGE_EXTENSIONS:
        return load_image_palette(path, color_count=color_count)
    raise ValueError(f"Unsupported file type: {path.suffix}")


def load_json_palette(path: Path) -> Palette:
    payload = json.loads(path.read_text(encoding="utf-8"))
    name = payload.get("name") or path.stem
    colors: list[ColorEntry] = []
    for item in payload.get("colors", []):
        color_name = item.get("name") or f"Color {len(colors) + 1}"
        hex_code = item.get("hex")
        if not hex_code and "rgb" in item:
            rgb = item["rgb"]
            hex_code = rgb_to_hex(rgb[0], rgb[1], rgb[2])
        if hex_code:
            colors.append(ColorEntry(name=color_name, hex_code=normalize_hex(hex_code)))
    return Palette(name=name, colors=colors, source_path=path, source_format="json")


def load_csv_palette(path: Path) -> Palette:
    colors: list[ColorEntry] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            color_name = (row.get("name") or row.get("Name") or "").strip()
            hex_code = (row.get("hex") or row.get("HEX") or row.get("Hex") or "").strip()
            if not hex_code:
                red = row.get("r") or row.get("R")
                green = row.get("g") or row.get("G")
                blue = row.get("b") or row.get("B")
                if red is not None and green is not None and blue is not None:
                    hex_code = rgb_to_hex(int(red), int(green), int(blue))
            if not hex_code:
                continue
            if not color_name:
                color_name = f"Color {len(colors) + 1}"
            colors.append(ColorEntry(name=color_name, hex_code=normalize_hex(hex_code)))
    return Palette(name=path.stem, colors=colors, source_path=path, source_format="csv")


def load_gpl_palette(path: Path) -> Palette:
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    name = path.stem
    colors: list[ColorEntry] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("Name:"):
            value = stripped.split(":", 1)[1].strip()
            if value:
                name = value
            continue
        if stripped.startswith(("GIMP Palette", "Columns:")):
            continue
        parts = stripped.split()
        if len(parts) < 3:
            continue
        try:
            red, green, blue = map(int, parts[:3])
        except ValueError:
            continue
        color_name = " ".join(parts[3:]).strip() or f"Color {len(colors) + 1}"
        colors.append(ColorEntry(name=color_name, hex_code=rgb_to_hex(red, green, blue)))
    return Palette(name=name, colors=colors, source_path=path, source_format="gpl")


def load_ase_palette(path: Path) -> Palette:
    data = path.read_bytes()
    if data[:4] != b"ASEF":
        raise ValueError("Invalid ASE signature")
    offset = 12
    colors: list[ColorEntry] = []
    palette_name = path.stem

    while offset + 6 <= len(data):
        block_type, block_length = struct.unpack(">HI", data[offset:offset + 6])
        block_data = data[offset + 6:offset + 6 + block_length]
        offset += 6 + block_length

        if block_type == 0xC001:
            group_name, _ = read_utf16_string(block_data, 0)
            if group_name:
                palette_name = group_name
            continue
        if block_type != 0x0001:
            continue

        color_name, name_offset = read_utf16_string(block_data, 0)
        model = block_data[name_offset:name_offset + 4].decode("ascii", errors="ignore").strip()
        value_offset = name_offset + 4

        if model == "RGB":
            red, green, blue = struct.unpack(">fff", block_data[value_offset:value_offset + 12])
            hex_code = rgb_to_hex(
                round(clamp01(red) * 255),
                round(clamp01(green) * 255),
                round(clamp01(blue) * 255),
            )
        elif model == "GRAY":
            gray = struct.unpack(">f", block_data[value_offset:value_offset + 4])[0]
            value = round(clamp01(gray) * 255)
            hex_code = rgb_to_hex(value, value, value)
        elif model == "CMYK":
            c, m, y, k = struct.unpack(">ffff", block_data[value_offset:value_offset + 16])
            hex_code = cmyk_to_hex(c, m, y, k)
        else:
            continue

        colors.append(ColorEntry(name=color_name or f"Color {len(colors) + 1}", hex_code=hex_code))

    return Palette(name=palette_name, colors=colors, source_path=path, source_format="ase")


def load_pal_palette(path: Path) -> Palette:
    data = path.read_bytes()
    if len(data) < 24 or data[:4] != b"RIFF" or data[8:12] != b"PAL ":
        raise ValueError("Unsupported PAL format")
    if data[12:16] != b"data":
        raise ValueError("Missing PAL data chunk")
    chunk_size = struct.unpack("<I", data[16:20])[0]
    payload = data[20:20 + chunk_size]
    version, color_count = struct.unpack("<HH", payload[:4])
    if version != 0x0300:
        raise ValueError("Unsupported PAL version")
    colors: list[ColorEntry] = []
    offset = 4
    for index in range(color_count):
        if offset + 4 > len(payload):
            break
        blue, green, red, _flags = struct.unpack("<BBBB", payload[offset:offset + 4])
        colors.append(ColorEntry(name=f"Color {index + 1}", hex_code=rgb_to_hex(red, green, blue)))
        offset += 4
    return Palette(name=path.stem, colors=colors, source_path=path, source_format="pal")


def load_image_palette(path: Path, color_count: int = 5) -> Palette:
    image = load_qimage(path)
    return extract_palette_from_qimage(
        image,
        color_count=color_count,
        name=path.stem,
        source_path=path,
        source_format="image",
    )


def load_pdf_palette(path: Path, color_count: int = 5, page_index: int = 0) -> Palette:
    image = render_pdf_page(path, page_index=page_index, max_edge=960)
    palette = extract_palette_from_qimage(
        image,
        color_count=color_count,
        name=path.stem,
        source_path=path,
        source_format="pdf",
    )
    palette.metadata["page_count"] = pdf_page_count(path)
    palette.metadata["preview_page"] = page_index + 1
    return palette


def load_pdf_region_palette(
    path: Path,
    page_index: int,
    crop_bounds: tuple[int, int, int, int],
    color_count: int = 5,
) -> Palette:
    image = render_pdf_page(path, page_index=page_index, max_edge=1800)
    left, top, right, bottom = crop_bounds
    region = image.copy(left, top, max(1, right - left), max(1, bottom - top))
    palette = extract_palette_from_qimage(
        region,
        color_count=color_count,
        name=f"{path.stem}_p{page_index + 1:03d}_region",
        source_path=path,
        source_format="pdf_region",
    )
    palette.metadata["page"] = page_index + 1
    return palette


def load_pdf_grid_palette(
    path: Path,
    page_index: int,
    rows: int,
    cols: int,
    sample_ratio: float = 0.6,
    crop_bounds: tuple[int, int, int, int] | None = None,
) -> Palette:
    image = render_pdf_page(path, page_index=page_index, max_edge=1800)
    rows = max(1, rows)
    cols = max(1, cols)
    sample_ratio = max(0.2, min(0.9, sample_ratio))
    if crop_bounds is None:
        crop_left, crop_top, crop_right, crop_bottom = detect_grid_bounds(image, prefer_bottom=rows == 1)
    else:
        crop_left, crop_top, crop_right, crop_bottom = crop_bounds
    crop_width = max(1, crop_right - crop_left)
    crop_height = max(1, crop_bottom - crop_top)
    cell_width = crop_width / cols
    cell_height = crop_height / rows
    colors: list[ColorEntry] = []

    for row in range(rows):
        for col in range(cols):
            center_x = crop_left + (col + 0.5) * cell_width
            center_y = crop_top + (row + 0.5) * cell_height
            sample_width = max(1, round(cell_width * sample_ratio))
            sample_height = max(1, round(cell_height * sample_ratio))
            left = max(crop_left, round(center_x - sample_width / 2))
            top = max(crop_top, round(center_y - sample_height / 2))
            right = min(crop_right, left + sample_width)
            bottom = min(crop_bottom, top + sample_height)
            rgb = average_image_region(image, left, top, right, bottom)
            colors.append(ColorEntry(name=f"R{row + 1}C{col + 1}", hex_code=rgb_to_hex(*rgb)))

    palette = Palette(
        name=f"{path.stem}_p{page_index + 1:03d}_grid_{rows}x{cols}",
        colors=colors,
        source_path=path,
        source_format="pdf_grid",
    )
    palette.metadata["page"] = page_index + 1
    return palette


def load_image_grid_palette(
    path: Path,
    rows: int,
    cols: int,
    sample_ratio: float = 0.6,
    crop_bounds: tuple[int, int, int, int] | None = None,
) -> Palette:
    image = load_qimage(path, max_size=0)
    rows = max(1, rows)
    cols = max(1, cols)
    sample_ratio = max(0.2, min(0.9, sample_ratio))
    if crop_bounds is None:
        crop_left, crop_top, crop_right, crop_bottom = detect_grid_bounds(image, prefer_bottom=rows == 1)
    else:
        crop_left, crop_top, crop_right, crop_bottom = crop_bounds
    crop_width = max(1, crop_right - crop_left)
    crop_height = max(1, crop_bottom - crop_top)
    cell_width = crop_width / cols
    cell_height = crop_height / rows
    colors: list[ColorEntry] = []

    for row in range(rows):
        for col in range(cols):
            center_x = crop_left + (col + 0.5) * cell_width
            center_y = crop_top + (row + 0.5) * cell_height
            sample_width = max(1, round(cell_width * sample_ratio))
            sample_height = max(1, round(cell_height * sample_ratio))
            left = max(crop_left, round(center_x - sample_width / 2))
            top = max(crop_top, round(center_y - sample_height / 2))
            right = min(crop_right, left + sample_width)
            bottom = min(crop_bottom, top + sample_height)
            rgb = average_image_region(image, left, top, right, bottom)
            colors.append(ColorEntry(name=f"R{row + 1}C{col + 1}", hex_code=rgb_to_hex(*rgb)))

    return Palette(name=f"{path.stem}_grid_{rows}x{cols}", colors=colors, source_path=path, source_format="grid")


def extract_palette_from_qimage(
    image: QImage,
    color_count: int,
    name: str,
    source_path: Path | None,
    source_format: str,
) -> Palette:
    buckets: dict[tuple[int, int, int], list[int]] = defaultdict(lambda: [0, 0, 0, 0])
    for y in range(image.height()):
        for x in range(image.width()):
            pixel = image.pixelColor(x, y)
            if pixel.alpha() < 24:
                continue
            key = quantize_rgb(pixel.red(), pixel.green(), pixel.blue())
            bucket = buckets[key]
            bucket[0] += pixel.red()
            bucket[1] += pixel.green()
            bucket[2] += pixel.blue()
            bucket[3] += 1

    ranked = sorted(buckets.items(), key=lambda item: item[1][3], reverse=True)
    colors: list[ColorEntry] = []
    used_rgbs: list[tuple[int, int, int]] = []
    target_count = max(1, min(24, color_count))

    for _key, (r_sum, g_sum, b_sum, total) in ranked:
        if total <= 0:
            continue
        rgb = (round(r_sum / total), round(g_sum / total), round(b_sum / total))
        if any(color_distance(rgb, existing) < 42 for existing in used_rgbs):
            continue
        used_rgbs.append(rgb)
        colors.append(ColorEntry(name=f"Color {len(colors) + 1}", hex_code=rgb_to_hex(*rgb)))
        if len(colors) >= target_count:
            break

    if len(colors) < target_count:
        for _key, (r_sum, g_sum, b_sum, total) in ranked:
            if total <= 0:
                continue
            rgb = (round(r_sum / total), round(g_sum / total), round(b_sum / total))
            hex_code = rgb_to_hex(*rgb)
            if any(item.hex_code == hex_code for item in colors):
                continue
            colors.append(ColorEntry(name=f"Color {len(colors) + 1}", hex_code=hex_code))
            if len(colors) >= target_count:
                break

    return Palette(name=name, colors=colors, source_path=source_path, source_format=source_format)


def pdf_page_count(path: Path) -> int:
    document = load_pdf_document(path)
    page_count = document.pageCount()
    if page_count <= 0:
        raise ValueError(f"Unable to read PDF pages: {path}")
    return page_count


def render_pdf_page(path: Path, page_index: int = 0, max_edge: int = 1400) -> QImage:
    document = load_pdf_document(path)
    page_count = document.pageCount()
    if page_count <= 0:
        raise ValueError(f"Unable to read PDF pages: {path}")
    if page_index < 0 or page_index >= page_count:
        raise IndexError(f"PDF page out of range: {page_index}")

    page_size = document.pagePointSize(page_index)
    width = float(page_size.width()) if hasattr(page_size, "width") else 595.0
    height = float(page_size.height()) if hasattr(page_size, "height") else 842.0
    if width <= 0 or height <= 0:
        width = 595.0
        height = 842.0
    scale = max_edge / max(width, height)
    target_size = QSize(max(1, round(width * scale)), max(1, round(height * scale)))
    image = document.render(page_index, target_size)
    if image.isNull():
        raise ValueError(f"Unable to render PDF page {page_index + 1}: {path}")
    if image.format() != QImage.Format.Format_ARGB32:
        image = image.convertToFormat(QImage.Format.Format_ARGB32)
    return image


def load_pdf_document(path: Path):
    try:
        from PySide6.QtPdf import QPdfDocument
    except ImportError as exc:
        raise RuntimeError("PySide6 QtPdf support is not available in this environment") from exc

    document = QPdfDocument()
    document.load(str(path))
    return document


def detect_grid_bounds(image: QImage, prefer_bottom: bool = False) -> tuple[int, int, int, int]:
    width = image.width()
    height = image.height()
    row_scores = [0] * height

    for y in range(height):
        for x in range(width):
            pixel = image.pixelColor(x, y)
            if pixel.alpha() < 24:
                continue
            if pixel.hsvSaturationF() > 0.12 and pixel.valueF() < 0.98:
                row_scores[y] += 1

    if max(row_scores, default=0) == 0:
        return 0, 0, width, height

    start_row = round(height * 0.45) if prefer_bottom else 0
    end_row = round(height * 0.98)
    max_row_score = max(row_scores[start_row:end_row] or row_scores)
    threshold = max(2, round(max_row_score * 0.35))

    best_top = 0
    best_bottom = height
    best_rank = -1.0
    run_start = None
    run_total = 0
    run_len = 0
    for index in range(start_row, end_row):
        score = row_scores[index]
        if score >= threshold:
            if run_start is None:
                run_start = index
                run_total = 0
                run_len = 0
            run_total += score
            run_len += 1
        elif run_start is not None:
            center = run_start + run_len / 2
            rank = run_total + (center / max(1, height) * max_row_score * 4 if prefer_bottom else 0)
            if rank > best_rank:
                best_rank = rank
                best_top = run_start
                best_bottom = index
            run_start = None
    if run_start is not None:
        center = run_start + run_len / 2
        rank = run_total + (center / max(1, height) * max_row_score * 4 if prefer_bottom else 0)
        if rank > best_rank:
            best_top = run_start
            best_bottom = end_row

    band_top = max(0, best_top - round(height * 0.01))
    band_bottom = min(height, best_bottom + round(height * 0.02))
    col_scores = [0] * width
    for y in range(band_top, band_bottom):
        for x in range(width):
            pixel = image.pixelColor(x, y)
            if pixel.alpha() < 24:
                continue
            if pixel.hsvSaturationF() > 0.12 and pixel.valueF() < 0.98:
                col_scores[x] += 1

    max_col_score = max(col_scores, default=0)
    if max_col_score == 0:
        return 0, band_top, width, band_bottom
    col_threshold = max(1, round(max_col_score * 0.25))
    left = next((index for index, score in enumerate(col_scores) if score >= col_threshold), 0)
    right = next((index for index in range(width - 1, -1, -1) if col_scores[index] >= col_threshold), width - 1)
    margin_x = max(2, round((right - left + 1) * 0.03))
    margin_y = max(2, round((band_bottom - band_top) * 0.08))
    return max(0, left - margin_x), max(0, band_top - margin_y), min(width, right + margin_x + 1), min(height, band_bottom + margin_y)


def load_qimage(path: Path, max_size: int = 160) -> QImage:
    image = QImage(str(path))
    if image.isNull():
        raise ValueError(f"Unable to load image: {path}")
    image = image.convertToFormat(QImage.Format.Format_ARGB32)
    if max_size > 0 and (image.width() > max_size or image.height() > max_size):
        image = image.scaled(max_size, max_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    return image


def average_image_region(image: QImage, left: int, top: int, right: int, bottom: int) -> tuple[int, int, int]:
    r_sum = 0
    g_sum = 0
    b_sum = 0
    count = 0
    for y in range(top, bottom):
        for x in range(left, right):
            pixel = image.pixelColor(x, y)
            if pixel.alpha() < 24:
                continue
            r_sum += pixel.red()
            g_sum += pixel.green()
            b_sum += pixel.blue()
            count += 1
    if count == 0:
        return (255, 255, 255)
    return (round(r_sum / count), round(g_sum / count), round(b_sum / count))


def quantize_rgb(r: int, g: int, b: int, step: int = 16) -> tuple[int, int, int]:
    return (r // step, g // step, b // step)


def color_distance(first: tuple[int, int, int], second: tuple[int, int, int]) -> int:
    return max(abs(first[0] - second[0]), abs(first[1] - second[1]), abs(first[2] - second[2]))


def read_utf16_string(data: bytes, offset: int) -> tuple[str, int]:
    char_count = struct.unpack(">H", data[offset:offset + 2])[0]
    start = offset + 2
    raw = data[start:start + char_count * 2]
    text = raw.decode("utf-16-be", errors="ignore").rstrip("\x00")
    return text, start + char_count * 2


def normalize_hex(value: str) -> str:
    text = value.strip().lstrip("#")
    if len(text) == 3:
        text = "".join(ch * 2 for ch in text)
    if len(text) != 6:
        raise ValueError(f"Invalid hex color: {value}")
    return f"#{text.upper()}"


def rgb_to_hex(r: int, g: int, b: int) -> str:
    return f"#{r:02X}{g:02X}{b:02X}"


def cmyk_to_hex(c: float, m: float, y: float, k: float) -> str:
    red = round(255 * (1 - clamp01(c)) * (1 - clamp01(k)))
    green = round(255 * (1 - clamp01(m)) * (1 - clamp01(k)))
    blue = round(255 * (1 - clamp01(y)) * (1 - clamp01(k)))
    return rgb_to_hex(red, green, blue)


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))
