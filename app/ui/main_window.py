from __future__ import annotations
import colorsys
import json
import math
import shutil
import subprocess
from pathlib import Path
from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal, QUrl, QMimeData, QTimer
from PySide6.QtGui import QColor, QGuiApplication, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QButtonGroup,
    QDialog,
    QDialogButtonBox,
    QComboBox,
    QColorDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)
from app.config import AppConfig
from app.models import ColorEntry, Palette
from app.parsers import load_image_grid_palette, load_palette, load_pdf_palette, pdf_page_count, render_pdf_page, scan_palettes
from app.storage import ensure_directory, save_originlab_pal, save_palette_ase, save_palette_csv, save_palette_json
from app.ui.pdf_dialog import PdfExtractDialog
class ClickableColorCard(QFrame):
    clicked = Signal(object)
    toggled = Signal(object, bool)

    def __init__(self, color: ColorEntry) -> None:
        super().__init__()
        self.color = color
        self.selected = False
        self.base_selected = False
        self.setObjectName("colorCard")
        self.setCursor(Qt.PointingHandCursor)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        swatch = QFrame()
        swatch.setMinimumHeight(52)
        swatch.setStyleSheet(
            f"background-color: {color.hex_code}; border-radius: 10px; border: 1px solid #64748B;"
        )
        layout.addWidget(swatch)
        name_label = QLabel(color.name)
        name_label.setWordWrap(True)
        name_label.setStyleSheet("color: #0F172A; font-weight: 700; background: transparent;")
        layout.addWidget(name_label)
        rgb = color.rgb
        meta_label = QLabel(f"{color.hex_code}\nRGB {rgb[0]}, {rgb[1]}, {rgb[2]}")
        meta_label.setStyleSheet("color: #334155; background: transparent;")
        meta_label.setWordWrap(True)
        layout.addWidget(meta_label)
        hint_label = QLabel("左键复制   右键加入拼配区")
        hint_label.setStyleSheet("color: #64748B; font-size: 12px; background: transparent;")
        layout.addWidget(hint_label)
        self.refresh_style()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.color)
        elif event.button() == Qt.RightButton:
            self.selected = not self.selected
            self.refresh_style()
            self.toggled.emit(self.color, self.selected)
        super().mousePressEvent(event)

    def set_selected(self, selected: bool) -> None:
        self.selected = selected
        self.refresh_style()

    def set_base_selected(self, selected: bool) -> None:
        self.base_selected = selected
        self.refresh_style()

    def refresh_style(self) -> None:
        if self.base_selected:
            border = "#D97706"
            background = "#FEF3C7"
        elif self.selected:
            border = "#1D4ED8"
            background = "#DBEAFE"
        else:
            border = "#CBD5E1"
            background = "#FFFFFF"
        self.setStyleSheet(
            f"#colorCard {{ border: 3px solid {border}; border-radius: 12px; background: {background}; }}"
        )

class FlowContainer(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(4, 4, 4, 4)
        self.grid.setSpacing(12)
        self.grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)

    def clear(self) -> None:
        while self.grid.count():
            item = self.grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def add_widget(self, widget: QWidget, index: int, columns: int = 3) -> None:
        row = index // columns
        column = index % columns
        self.grid.addWidget(widget, row, column)

class PaletteListCard(QFrame):
    def __init__(self, palette: Palette, is_favorite: bool) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 5, 6, 5)
        layout.setSpacing(4)
        title_text = f"{'★ ' if is_favorite else ''}{palette.name}"
        title = QLabel(title_text)
        title.setWordWrap(True)
        title.setStyleSheet("font-weight: 700; color: #0F172A; background: transparent;")
        layout.addWidget(title)
        if palette.source_format == "pal":
            gradient_label = QLabel()
            gradient_label.setPixmap(build_gradient_pixmap([color.hex_code for color in palette.colors], 156, 16))
            gradient_label.setStyleSheet("background: transparent;")
            layout.addWidget(gradient_label)
        else:
            swatch_row = QHBoxLayout()
            swatch_row.setSpacing(3)
            for color in palette.preview_colors:
                swatch = QFrame()
                swatch.setFixedSize(14, 14)
                swatch.setStyleSheet(
                    f"background: {color.hex_code}; border: 1px solid #64748B; border-radius: 4px;"
                )
                swatch_row.addWidget(swatch)
            swatch_row.addStretch(1)
            layout.addLayout(swatch_row)
        meta = QLabel(f"{palette.source_group} | {len(palette.colors)} colors | {palette.source_format.upper()}")
        meta.setContentsMargins(0, 0, 0, 0)
        meta.setStyleSheet("color: #64748B; background: transparent;")
        layout.addWidget(meta)
class SelectedColorWidget(QFrame):
    def __init__(self, color: ColorEntry) -> None:
        super().__init__()
        self.setStyleSheet("background: #FFFFFF; border: 1px solid #CBD5E1; border-radius: 10px;")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        swatch = QFrame()
        swatch.setFixedSize(28, 28)
        swatch.setStyleSheet(
            f"background: {color.hex_code}; border: 1px solid #64748B; border-radius: 6px;"
        )
        layout.addWidget(swatch)
        text = QLabel(color.hex_code)
        text.setStyleSheet("color: #0F172A; background: transparent; font-weight: 600;")
        layout.addWidget(text, 1)
def build_gradient_pixmap(colors: list[str], width: int, height: int) -> QPixmap:
    pixmap = QPixmap(width, height)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    gradient = QLinearGradient(0, 0, width, 0)
    if not colors:
        colors = ["#FFFFFF", "#FFFFFF"]
    if len(colors) == 1:
        colors = [colors[0], colors[0]]
    for index, hex_code in enumerate(colors):
        gradient.setColorAt(index / max(1, len(colors) - 1), QColor(hex_code))
    painter.setPen(QPen(QColor("#64748B"), 1))
    painter.setBrush(gradient)
    painter.drawRoundedRect(0, 0, width - 1, height - 1, 8, 8)
    painter.end()
    return pixmap
def normalize_hex_code(value: str) -> str:
    value = value.strip().lstrip("#")
    if len(value) == 3:
        value = "".join(ch * 2 for ch in value)
    if len(value) != 6:
        raise ValueError("HEX color must be 6 digits")
    int(value, 16)
    return f"#{value.upper()}"

def clamp_channel(value: float) -> int:
    return max(0, min(255, round(value)))


def simulate_colorblind(hex_code: str, mode: str) -> QColor:
    source = QColor(hex_code)
    red = source.red()
    green = source.green()
    blue = source.blue()
    matrices = {
        "colorblind_protan": (
            (0.152286, 1.052583, -0.204868),
            (0.114503, 0.786281, 0.099216),
            (-0.003882, -0.048116, 1.051998),
        ),
        "colorblind_deutan": (
            (0.367322, 0.860646, -0.227968),
            (0.280085, 0.672501, 0.047413),
            (-0.011820, 0.042940, 0.968881),
        ),
        "colorblind_tritan": (
            (1.255528, -0.076749, -0.178779),
            (-0.078411, 0.930809, 0.147602),
            (0.004733, 0.691367, 0.303900),
        ),
    }
    matrix = matrices.get(mode)
    if matrix is None:
        return source
    return QColor(
        clamp_channel(matrix[0][0] * red + matrix[0][1] * green + matrix[0][2] * blue),
        clamp_channel(matrix[1][0] * red + matrix[1][1] * green + matrix[1][2] * blue),
        clamp_channel(matrix[2][0] * red + matrix[2][1] * green + matrix[2][2] * blue),
    )
def rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    r, g, b = (max(0, min(255, int(round(component)))) for component in rgb)
    return f"#{r:02X}{g:02X}{b:02X}"
def mix_hex_colors(hex_a: str, hex_b: str, ratio: float) -> str:
    ratio = max(0.0, min(1.0, ratio))
    a = ColorEntry(name="a", hex_code=normalize_hex_code(hex_a)).rgb
    b = ColorEntry(name="b", hex_code=normalize_hex_code(hex_b)).rgb
    rgb = tuple(a[index] * (1.0 - ratio) + b[index] * ratio for index in range(3))
    return rgb_to_hex(rgb)
def interpolate_hue(value: float, source: list[float], target: list[float]) -> float:
    value = value % 360.0
    for index in range(len(source) - 1):
        left = source[index]
        right = source[index + 1]
        if left <= value <= right:
            span = right - left
            if span == 0:
                return target[index]
            ratio = (value - left) / span
            return target[index] + (target[index + 1] - target[index]) * ratio
    return target[-1]

def rotate_color_hue(hex_code: str, degrees: float, wheel_mode: str = "rgb") -> str:
    red, green, blue = ColorEntry(name="base", hex_code=normalize_hex_code(hex_code)).rgb
    hue, saturation, value = colorsys.rgb_to_hsv(red / 255.0, green / 255.0, blue / 255.0)
    hue_degrees = (hue * 360.0 + degrees) % 360.0
    if wheel_mode == "ryb":
        source = [0.0, 60.0, 120.0, 180.0, 240.0, 300.0, 360.0]
        target = [0.0, 30.0, 60.0, 120.0, 180.0, 240.0, 360.0]
        hue_degrees = interpolate_hue(hue_degrees, target, source)
    red_value, green_value, blue_value = colorsys.hsv_to_rgb(
        hue_degrees / 360.0,
        saturation,
        value,
    )
    return rgb_to_hex((red_value * 255.0, green_value * 255.0, blue_value * 255.0))

def build_similar_colors(hex_code: str, wheel_mode: str = "rgb", count: int = 5) -> list[str]:
    count = max(2, min(9, count))
    colors = [normalize_hex_code(hex_code)]
    step = 18
    distance = 1
    while len(colors) < count:
        colors.append(rotate_color_hue(hex_code, -step * distance, wheel_mode))
        if len(colors) < count:
            colors.append(rotate_color_hue(hex_code, step * distance, wheel_mode))
        distance += 1
    return colors[:count]

def build_complementary_colors(hex_code: str, wheel_mode: str = "rgb", count: int = 4) -> list[str]:
    count = max(2, min(9, count))
    colors = [normalize_hex_code(hex_code), rotate_color_hue(hex_code, 180, wheel_mode)]
    offsets = [150, 210, 120, 240, 90, 270, 60]
    for offset in offsets:
        if len(colors) >= count:
            break
        colors.append(rotate_color_hue(hex_code, offset, wheel_mode))
    return colors[:count]

def build_interpolated_colors(hex_codes: list[str], count: int) -> list[str]:
    anchors = [normalize_hex_code(value) for value in hex_codes if value]
    if len(anchors) < 2:
        return anchors
    count = max(len(anchors), min(9, count))
    segments = len(anchors) - 1
    output: list[str] = []
    for index in range(count):
        position = index / max(1, count - 1)
        segment_position = position * segments
        left_index = min(int(segment_position), segments - 1)
        local_ratio = segment_position - left_index
        output.append(mix_hex_colors(anchors[left_index], anchors[left_index + 1], local_ratio))
    return output

def build_tint_ramp(hex_code: str, bias: str, steps: int = 5) -> list[str]:
    whites = {
        "neutral": "#F7F4EE",
        "warm": "#FAF1E5",
        "cool": "#EEF5FA",
    }
    white_target = whites.get(bias, whites["neutral"])
    colors = [normalize_hex_code(hex_code)]
    for index in range(1, steps):
        ratio = index / max(1, steps - 1)
        colors.append(mix_hex_colors(hex_code, white_target, ratio * 0.88))
    return colors

def build_tint_ramp_mode(hex_code: str, bias: str, mode: str, steps: int = 5) -> list[str]:
    whites = {
        "neutral": "#F7F4EE",
        "warm": "#FAF1E5",
        "cool": "#EEF5FA",
    }
    white_target = whites.get(bias, whites["neutral"])
    base = normalize_hex_code(hex_code)
    dark_target = mix_hex_colors(base, "#111827", 0.72)
    if mode == "Base lightest":
        return build_interpolated_colors([dark_target, base], steps)
    if mode == "Base center":
        half = max(2, steps // 2 + 1)
        darker = build_interpolated_colors([dark_target, base], half)
        lighter = build_interpolated_colors([base, mix_hex_colors(base, white_target, 0.88)], half)
        return (darker[:-1] + lighter)[:steps]
    return build_interpolated_colors([base, mix_hex_colors(base, white_target, 0.88)], steps)
def build_diverging_colors(start_hex: str, end_hex: str, steps: int = 5, midpoint_hex: str = "#F4F1EB") -> list[str]:
    steps = max(3, min(9, steps))
    left_count = steps // 2 + 1
    right_count = steps - left_count + 1
    left = build_interpolated_colors([normalize_hex_code(start_hex), midpoint_hex], left_count)
    right = build_interpolated_colors([midpoint_hex, normalize_hex_code(end_hex)], right_count)
    return (left[:-1] + right)[:steps]


PREVIEW_PHYLO_NEWICK = """((((A1:0.05,A2:0.1):0.15,A3:0.25):0.2,(B1:0.3,(B2:0.05,B3:0.1):0.25):0.3):0.4,
((C1:0.1,C2:0.15):0.2,(C3:0.2,C4:0.25):0.3):0.35,
(((D1:0.05,D2:0.05):0.1,D3:0.2):0.25,(D4:0.3,D5:0.35):0.4):0.45,
((E1:0.15,E2:0.2):0.3,E3:0.4):0.5);"""
CHINA_BOUNDARY_GEOJSON = Path(__file__).resolve().parent.parent / "assets" / "china_boundary.geojson"
_PREVIEW_PHYLO_CACHE: tuple[dict[str, object], list[dict[str, object]], float] | None = None
_CHINA_PREVIEW_SHAPES_CACHE: list[list[tuple[float, float]]] | None = None


def parse_preview_newick(newick: str) -> dict[str, object]:
    text = "".join(character for character in newick.strip() if not character.isspace())
    index = 0

    def parse_name() -> str:
        nonlocal index
        start = index
        while index < len(text) and text[index] not in ':,();':
            index += 1
        return text[start:index]

    def parse_length() -> float:
        nonlocal index
        if index >= len(text) or text[index] != ':':
            return 0.0
        index += 1
        start = index
        while index < len(text) and text[index] not in ',();':
            index += 1
        try:
            return float(text[start:index])
        except ValueError:
            return 0.0

    def parse_node() -> dict[str, object]:
        nonlocal index
        children: list[dict[str, object]] = []
        name = ""
        if index < len(text) and text[index] == '(':
            index += 1
            while index < len(text):
                children.append(parse_node())
                if index < len(text) and text[index] == ',':
                    index += 1
                    continue
                if index < len(text) and text[index] == ')':
                    index += 1
                    break
            name = parse_name()
        else:
            name = parse_name()
        return {
            'name': name,
            'length': parse_length(),
            'children': children,
        }

    return parse_node()


def _count_preview_leaves(node: dict[str, object]) -> int:
    children = node.get('children', [])
    if not children:
        return 1
    return sum(_count_preview_leaves(child) for child in children)


def _layout_preview_tree(
    node: dict[str, object],
    start_index: int,
    total_leaves: int,
    parent_distance: float,
    leaves: list[dict[str, object]],
) -> tuple[int, float]:
    distance = parent_distance + float(node.get('length', 0.0))
    node['distance'] = distance
    children = node.get('children', [])
    if not children:
        angle = -90.0 + 360.0 * ((start_index + 0.5) / max(1, total_leaves))
        node['leaf_start'] = start_index
        node['leaf_end'] = start_index + 1
        node['angle'] = angle
        node['angle_start'] = angle
        node['angle_end'] = angle
        leaves.append(node)
        return start_index + 1, distance

    current_index = start_index
    max_distance = distance
    for child in children:
        current_index, child_max_distance = _layout_preview_tree(
            child,
            current_index,
            total_leaves,
            distance,
            leaves,
        )
        max_distance = max(max_distance, child_max_distance)
    node['leaf_start'] = start_index
    node['leaf_end'] = current_index
    node['angle_start'] = children[0]['angle_start']
    node['angle_end'] = children[-1]['angle_end']
    node['angle'] = (float(node['angle_start']) + float(node['angle_end'])) / 2.0
    return current_index, max_distance


def get_preview_phylo_layout() -> tuple[dict[str, object], list[dict[str, object]], float]:
    global _PREVIEW_PHYLO_CACHE
    if _PREVIEW_PHYLO_CACHE is not None:
        return _PREVIEW_PHYLO_CACHE
    root = parse_preview_newick(PREVIEW_PHYLO_NEWICK)
    total_leaves = max(1, _count_preview_leaves(root))
    leaves: list[dict[str, object]] = []
    _, max_distance = _layout_preview_tree(root, 0, total_leaves, 0.0, leaves)
    _PREVIEW_PHYLO_CACHE = (root, leaves, max(max_distance, 1e-6))
    return _PREVIEW_PHYLO_CACHE


def _ring_area(points: list[tuple[float, float]]) -> float:
    if len(points) < 3:
        return 0.0
    area = 0.0
    for index, (x_value, y_value) in enumerate(points):
        next_x, next_y = points[(index + 1) % len(points)]
        area += x_value * next_y - next_x * y_value
    return area / 2.0


def load_china_preview_shapes() -> list[list[tuple[float, float]]]:
    global _CHINA_PREVIEW_SHAPES_CACHE
    if _CHINA_PREVIEW_SHAPES_CACHE is not None:
        return _CHINA_PREVIEW_SHAPES_CACHE
    if not CHINA_BOUNDARY_GEOJSON.exists():
        _CHINA_PREVIEW_SHAPES_CACHE = []
        return _CHINA_PREVIEW_SHAPES_CACHE

    payload = None
    for encoding in ('utf-8', 'utf-8-sig', 'gb18030'):
        try:
            payload = json.loads(CHINA_BOUNDARY_GEOJSON.read_text(encoding=encoding))
            break
        except UnicodeDecodeError:
            continue
    if payload is None:
        _CHINA_PREVIEW_SHAPES_CACHE = []
        return _CHINA_PREVIEW_SHAPES_CACHE

    shapes: list[list[tuple[float, float]]] = []
    for feature in payload.get('features', []):
        properties = feature.get('properties') or {}
        adcode = properties.get('adcode')
        if properties.get('level') != 'province' or not isinstance(adcode, int):
            continue
        geometry = feature.get('geometry') or {}
        geometry_type = geometry.get('type')
        coordinates = geometry.get('coordinates') or []
        candidate_rings: list[list[tuple[float, float]]] = []
        if geometry_type == 'Polygon' and coordinates:
            candidate_rings.append([(float(x_value), float(y_value)) for x_value, y_value in coordinates[0]])
        elif geometry_type == 'MultiPolygon':
            for polygon in coordinates:
                if polygon:
                    candidate_rings.append([(float(x_value), float(y_value)) for x_value, y_value in polygon[0]])
        if not candidate_rings:
            continue
        largest_ring = max(candidate_rings, key=lambda ring: abs(_ring_area(ring)))
        if len(largest_ring) >= 3:
            shapes.append(largest_ring)
    _CHINA_PREVIEW_SHAPES_CACHE = shapes
    return _CHINA_PREVIEW_SHAPES_CACHE

class ImagePreviewLabel(QLabel):
    color_picked = Signal(str)
    region_picked = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self._source_pixmap: QPixmap | None = None
        self._sample_enabled = False
        self._drag_start: QPointF | None = None
        self._drag_current: QPointF | None = None
        self.setAlignment(Qt.AlignCenter)

    def set_source_pixmap(self, pixmap: QPixmap, sample_enabled: bool) -> None:
        self._source_pixmap = pixmap
        self._sample_enabled = sample_enabled
        self._refresh_pixmap()

    def clear_preview(self) -> None:
        self._source_pixmap = None
        self._sample_enabled = False
        self._drag_start = None
        self._drag_current = None
        self.clear()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._refresh_pixmap()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() != Qt.LeftButton or not self._sample_enabled or self._source_pixmap is None:
            super().mousePressEvent(event)
            return
        local_point = self._to_display_point(event.position())
        if local_point is None:
            super().mousePressEvent(event)
            return
        self._drag_start = local_point
        self._drag_current = local_point
        self.update()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._drag_start is None:
            super().mouseMoveEvent(event)
            return
        local_point = self._to_display_point(event.position())
        if local_point is None:
            return
        self._drag_current = local_point
        self.update()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self._drag_start is None or self._source_pixmap is None:
            super().mouseReleaseEvent(event)
            return
        local_point = self._to_display_point(event.position())
        if local_point is None:
            self._drag_start = None
            self._drag_current = None
            self.update()
            super().mouseReleaseEvent(event)
            return
        rect = QRectF(self._drag_start, local_point).normalized()
        if rect.width() < 8 or rect.height() < 8:
            sample = self._sample_average_color(QRectF(local_point.x() - 2, local_point.y() - 2, 4, 4))
            if sample is not None:
                self.color_picked.emit(sample.name().upper())
        else:
            image_rect = self._to_image_rect(rect)
            if image_rect is not None:
                self.region_picked.emit(image_rect)
        self._drag_start = None
        self._drag_current = None
        self.update()
        super().mouseReleaseEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        if self._drag_start is None or self._drag_current is None:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self._drag_start, self._drag_current).normalized()
        painter.setPen(QPen(QColor("#2563EB"), 2))
        painter.setBrush(QColor(37, 99, 235, 40))
        painter.drawRoundedRect(rect, 6, 6)
        painter.end()

    def _refresh_pixmap(self) -> None:
        if self._source_pixmap is None or self._source_pixmap.isNull():
            self.clear()
            return
        scaled = self._source_pixmap.scaled(self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.setPixmap(scaled)

    def _to_display_point(self, position: QPointF) -> QPointF | None:
        displayed = self.pixmap()
        if displayed is None or displayed.isNull():
            return None
        offset_x = (self.width() - displayed.width()) / 2
        offset_y = (self.height() - displayed.height()) / 2
        local_x = position.x() - offset_x
        local_y = position.y() - offset_y
        if local_x < 0 or local_y < 0 or local_x > displayed.width() or local_y > displayed.height():
            return None
        return QPointF(local_x, local_y)

    def _sample_average_color(self, display_rect: QRectF) -> QColor | None:
        displayed = self.pixmap()
        if displayed is None or displayed.isNull() or self._source_pixmap is None:
            return None
        image = self._source_pixmap.toImage()
        x_scale = self._source_pixmap.width() / displayed.width()
        y_scale = self._source_pixmap.height() / displayed.height()
        left = max(0, min(self._source_pixmap.width() - 1, int(display_rect.left() * x_scale)))
        top = max(0, min(self._source_pixmap.height() - 1, int(display_rect.top() * y_scale)))
        right = max(left + 1, min(self._source_pixmap.width(), int(math.ceil(display_rect.right() * x_scale))))
        bottom = max(top + 1, min(self._source_pixmap.height(), int(math.ceil(display_rect.bottom() * y_scale))))
        total_red = 0
        total_green = 0
        total_blue = 0
        count = 0
        for y_index in range(top, bottom):
            for x_index in range(left, right):
                sample = image.pixelColor(x_index, y_index)
                total_red += sample.red()
                total_green += sample.green()
                total_blue += sample.blue()
                count += 1
        if count == 0:
            return None
        return QColor(total_red // count, total_green // count, total_blue // count)

    def _to_image_rect(self, display_rect: QRectF) -> tuple[int, int, int, int] | None:
        displayed = self.pixmap()
        if displayed is None or displayed.isNull() or self._source_pixmap is None:
            return None
        x_scale = self._source_pixmap.width() / displayed.width()
        y_scale = self._source_pixmap.height() / displayed.height()
        left = max(0, min(self._source_pixmap.width() - 1, int(display_rect.left() * x_scale)))
        top = max(0, min(self._source_pixmap.height() - 1, int(display_rect.top() * y_scale)))
        right = max(left + 1, min(self._source_pixmap.width(), int(math.ceil(display_rect.right() * x_scale))))
        bottom = max(top + 1, min(self._source_pixmap.height(), int(math.ceil(display_rect.bottom() * y_scale))))
        return left, top, right, bottom
        right = max(left + 1, min(self._source_pixmap.width(), int(math.ceil(display_rect.right() * x_scale))))
        bottom = max(top + 1, min(self._source_pixmap.height(), int(math.ceil(display_rect.bottom() * y_scale))))
        total_red = 0
        total_green = 0
        total_blue = 0
        count = 0
        for y_index in range(top, bottom):
            for x_index in range(left, right):
                sample = image.pixelColor(x_index, y_index)
                total_red += sample.red()
                total_green += sample.green()
                total_blue += sample.blue()
                count += 1
        if count == 0:
            return None
        return QColor(total_red // count, total_green // count, total_blue // count)

    def _to_image_rect(self, display_rect: QRectF) -> tuple[int, int, int, int] | None:
        displayed = self.pixmap()
        if displayed is None or displayed.isNull() or self._source_pixmap is None:
            return None
        x_scale = self._source_pixmap.width() / displayed.width()
        y_scale = self._source_pixmap.height() / displayed.height()
        left = max(0, min(self._source_pixmap.width() - 1, int(display_rect.left() * x_scale)))
        top = max(0, min(self._source_pixmap.height() - 1, int(display_rect.top() * y_scale)))
        right = max(left + 1, min(self._source_pixmap.width(), int(math.ceil(display_rect.right() * x_scale))))
        bottom = max(top + 1, min(self._source_pixmap.height(), int(math.ceil(display_rect.bottom() * y_scale))))
        return left, top, right, bottom
class ChartPreviewWidget(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.colors: list[str] = []
        self.chart_type = "line"
        self.series_count = 5
        self.group_count = 4
        self.line_width = 2
        self.marker_size = 5
        self.marker_shape = "circle"
        self.alpha = 100
        self.preview_mode = "normal"
        self.highlighted_indices: set[int] = set()
        self.setMinimumHeight(240)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_preview_state(
        self,
        colors: list[str],
        chart_type: str,
        series_count: int,
        group_count: int,
        line_width: int,
        marker_size: int,
        marker_shape: str,
        alpha: int,
        preview_mode: str,
        highlighted_indices: set[int] | None = None,
    ) -> None:
        self.colors = colors
        self.chart_type = chart_type
        self.series_count = max(1, series_count)
        self.group_count = max(2, group_count)
        self.line_width = max(1, line_width)
        self.marker_size = max(2, marker_size)
        self.marker_shape = marker_shape
        self.alpha = max(10, min(100, alpha))
        self.preview_mode = preview_mode
        self.highlighted_indices = set(highlighted_indices or [])
        self.update()

    def preview_color(self, hex_code: str) -> QColor:
        source = QColor(hex_code)
        red = source.red()
        green = source.green()
        blue = source.blue()
        if self.preview_mode == "grayscale":
            gray = round(0.299 * red + 0.587 * green + 0.114 * blue)
            return QColor(gray, gray, gray)
        if self.preview_mode.startswith("colorblind"):
            return simulate_colorblind(hex_code, self.preview_mode)
        return source

    def effective_color(self, index: int, colors: list[str], has_focus: bool) -> QColor:
        color = self.preview_color(colors[index % len(colors)])
        is_highlighted = index in self.highlighted_indices
        alpha_scale = self.alpha if (not has_focus or is_highlighted) else max(18, self.alpha // 3)
        color.setAlpha(round(255 * alpha_scale / 100))
        return color

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor("#FFFFFF"))
        plot = self.rect().adjusted(42, 20, -20, -40)
        colors = self.colors or ["#2563EB", "#DC2626", "#059669", "#D97706", "#7C3AED"]
        has_focus = bool(self.highlighted_indices)
        if self.chart_type == "heatmap":
            self.paint_heatmap(painter, plot, colors, has_focus)
        elif self.chart_type == "phylo":
            self.paint_phylo(painter, plot, colors, has_focus)
        elif self.chart_type == "map":
            self.paint_map(painter, plot, colors, has_focus)
        else:
            self.paint_standard_chart(painter, plot, colors, has_focus)
        painter.end()

    def paint_standard_chart(self, painter: QPainter, plot: QRectF, colors: list[str], has_focus: bool) -> None:
        painter.setPen(QPen(QColor("#CBD5E1"), 1))
        for index in range(5):
            y_value = plot.top() + plot.height() * index / 4
            painter.drawLine(plot.left(), int(y_value), plot.right(), int(y_value))
        painter.setPen(QPen(QColor("#64748B"), 1.2))
        painter.drawLine(plot.left(), plot.bottom(), plot.right(), plot.bottom())
        series_total = min(self.series_count, len(colors))
        total_points = self.group_count
        for s_idx in range(series_total):
            color = self.effective_color(s_idx, colors, has_focus)
            is_highlighted = s_idx in self.highlighted_indices
            values = []
            for point_idx in range(total_points):
                base = math.sin((point_idx + 1) * 0.8 + s_idx * 0.9)
                value = 0.48 + 0.18 * base + 0.06 * s_idx
                values.append(max(0.08, min(0.92, value)))
            points = []
            for point_idx, value in enumerate(values):
                x_value = plot.left() + (plot.width() * point_idx / max(1, total_points - 1))
                y_value = plot.bottom() - value * plot.height()
                points.append(QPointF(x_value, y_value))
            stroke_width = float(self.line_width + 2) if is_highlighted else float(self.line_width)
            if self.chart_type == "line":
                painter.setPen(QPen(color, stroke_width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
                for idx in range(1, len(points)):
                    painter.drawLine(points[idx - 1], points[idx])
                for point in points:
                    self.draw_marker(painter, point, color, is_highlighted)
            elif self.chart_type == "scatter":
                for point in points:
                    self.draw_marker(painter, point, color, is_highlighted)
            else:
                slot_width = plot.width() / total_points
                bar_width = max(6, slot_width / (series_total + 0.8))
                painter.setPen(Qt.NoPen)
                for point_idx, value in enumerate(values):
                    left = plot.left() + slot_width * point_idx + s_idx * bar_width - (series_total - 1) * bar_width / 2
                    top = plot.bottom() - value * plot.height()
                    rect = QRectF(left, top, bar_width - 2, plot.bottom() - top)
                    painter.fillRect(rect, color)
                    if is_highlighted:
                        painter.setPen(QPen(QColor("#0F172A"), 2))
                        painter.setBrush(Qt.NoBrush)
                        painter.drawRect(rect)
                        painter.setPen(Qt.NoPen)
        painter.setPen(QPen(QColor("#475569"), 1))
        for point_idx in range(total_points):
            x_value = plot.left() + (plot.width() * point_idx / max(1, total_points - 1))
            painter.drawText(int(x_value - 4), plot.bottom() + 22, str(point_idx + 1))

    def paint_heatmap(self, painter: QPainter, plot: QRectF, colors: list[str], has_focus: bool) -> None:
        rows = max(8, min(18, self.series_count * 3))
        cols = max(8, min(18, self.group_count * 3))
        top_dendro_h = plot.height() * 0.16
        left_dendro_w = plot.width() * 0.12
        top_bar_h = plot.height() * 0.045
        left_bar_w = plot.width() * 0.03
        matrix = QRectF(
            plot.left() + left_dendro_w + left_bar_w + 8,
            plot.top() + top_dendro_h + top_bar_h + 8,
            plot.width() - left_dendro_w - left_bar_w - 28,
            plot.height() - top_dendro_h - top_bar_h - 28,
        )
        cell_w = matrix.width() / cols
        cell_h = matrix.height() / rows

        painter.setPen(QPen(QColor("#111827"), 1.2))
        cluster_w = matrix.width() / 4
        top_base = matrix.top() - 8
        top_mid = top_base - top_dendro_h * 0.45
        top_high = top_base - top_dendro_h * 0.82
        for idx in range(4):
            center_x = matrix.left() + cluster_w * idx + cluster_w / 2
            painter.drawLine(int(center_x), int(top_base), int(center_x), int(top_mid))
        for idx in range(0, 4, 2):
            left_x = matrix.left() + cluster_w * idx + cluster_w / 2
            right_x = matrix.left() + cluster_w * (idx + 1) + cluster_w / 2
            painter.drawLine(int(left_x), int(top_mid), int(right_x), int(top_mid))
            painter.drawLine(int((left_x + right_x) / 2), int(top_mid), int((left_x + right_x) / 2), int(top_high))
        painter.drawLine(int(matrix.left() + cluster_w), int(top_high), int(matrix.left() + cluster_w * 3), int(top_high))

        left_base = matrix.left() - 8
        left_mid = left_base - left_dendro_w * 0.45
        left_high = left_base - left_dendro_w * 0.82
        cluster_h = matrix.height() / 4
        for idx in range(4):
            center_y = matrix.top() + cluster_h * idx + cluster_h / 2
            painter.drawLine(int(left_base), int(center_y), int(left_mid), int(center_y))
        for idx in range(0, 4, 2):
            top_y = matrix.top() + cluster_h * idx + cluster_h / 2
            bottom_y = matrix.top() + cluster_h * (idx + 1) + cluster_h / 2
            painter.drawLine(int(left_mid), int(top_y), int(left_mid), int(bottom_y))
            painter.drawLine(int(left_high), int((top_y + bottom_y) / 2), int(left_mid), int((top_y + bottom_y) / 2))
        painter.drawLine(int(left_high), int(matrix.top() + cluster_h), int(left_high), int(matrix.top() + cluster_h * 3))

        top_bar = QRectF(matrix.left(), matrix.top() - top_bar_h - 2, matrix.width(), top_bar_h)
        left_bar = QRectF(matrix.left() - left_bar_w - 2, matrix.top(), left_bar_w, matrix.height())
        for col in range(cols):
            color = self.effective_color(col, colors, has_focus)
            rect = QRectF(top_bar.left() + col * cell_w, top_bar.top(), cell_w, top_bar.height())
            painter.fillRect(rect, color)
        for row in range(rows):
            color = self.effective_color(row, colors, has_focus)
            rect = QRectF(left_bar.left(), left_bar.top() + row * cell_h, left_bar.width(), cell_h)
            painter.fillRect(rect, color)

        painter.setPen(QPen(QColor("#E5E7EB"), 0.8))
        for row in range(rows):
            base_color = self.effective_color(row, colors, has_focus)
            for col in range(cols):
                wave = 0.5 + 0.5 * math.sin((row + 1) * 0.48 + (col + 1) * 0.35)
                lift = 0.92 + 0.08 * wave
                cell_color = QColor(
                    clamp_channel(255 - (255 - base_color.red()) * lift),
                    clamp_channel(255 - (255 - base_color.green()) * lift),
                    clamp_channel(255 - (255 - base_color.blue()) * lift),
                    255,
                )
                if (row + col) % 13 == 0:
                    cell_color = QColor(
                        clamp_channel(255 - (255 - base_color.red()) * 0.97),
                        clamp_channel(255 - (255 - base_color.green()) * 0.97),
                        clamp_channel(255 - (255 - base_color.blue()) * 0.97),
                        255,
                    )
                rect = QRectF(matrix.left() + col * cell_w, matrix.top() + row * cell_h, cell_w, cell_h)
                painter.fillRect(rect, cell_color)
                painter.drawRect(rect)

        painter.setPen(QPen(QColor("#475569"), 1))
        painter.drawText(int(matrix.left()), int(plot.bottom() + 18), "Clustered heatmap preview")

    def paint_phylo(self, painter: QPainter, plot: QRectF, colors: list[str], has_focus: bool) -> None:
        root, leaves, max_distance = get_preview_phylo_layout()
        if not leaves:
            painter.setPen(QPen(QColor("#475569"), 1))
            painter.drawText(plot, Qt.AlignCenter, "Phylogenetic preview unavailable")
            return

        leaf_count = len(leaves)
        legend_items = max(1, len(colors))
        legend_columns = max(1, math.ceil(legend_items / 8))
        legend_width = 132 + max(0, legend_columns - 1) * 120
        circle_rect = plot.adjusted(26, 18, -(legend_width + 40), -34)
        center = QPointF(circle_rect.center().x() - 24, circle_rect.center().y() - 12)
        base_size = min(circle_rect.width(), circle_rect.height()) * 0.86
        gap_degrees = 62.0
        span_degrees = 360.0 - gap_degrees
        start_angle = 118.0
        end_angle = start_angle + span_degrees
        title_radius = base_size * 0.18
        tree_inner_radius = title_radius + 20
        tree_outer_radius = base_size * 0.34
        ring_count = max(4, min(7, self.series_count + 1))
        ring_width = base_size * 0.048
        label_radius = tree_outer_radius + ring_count * ring_width + 12

        def leaf_angle(index: float) -> float:
            return start_angle + span_degrees * (index / max(1, leaf_count))

        def point_at(radius: float, angle_deg: float) -> QPointF:
            angle_rad = math.radians(angle_deg)
            return QPointF(
                center.x() + math.cos(angle_rad) * radius,
                center.y() + math.sin(angle_rad) * radius,
            )

        def radius_for(distance: float) -> float:
            return tree_inner_radius + (tree_outer_radius - tree_inner_radius) * (distance / max_distance)

        def node_angle(node: dict[str, object]) -> float:
            start = float(node['leaf_start'])
            end = float(node['leaf_end'])
            return leaf_angle((start + end) / 2.0)

        def arc_path(radius: float, start_deg: float, end_deg: float) -> QPainterPath:
            rect = QRectF(center.x() - radius, center.y() - radius, radius * 2.0, radius * 2.0)
            path = QPainterPath()
            path.moveTo(point_at(radius, start_deg))
            path.arcTo(rect, -start_deg, -(end_deg - start_deg))
            return path

        palette_hexes = colors or ["#2563EB", "#DC2626", "#059669", "#D97706", "#7C3AED"]
        palette_colors: list[QColor] = []
        for hex_code in palette_hexes:
            color = self.preview_color(str(hex_code))
            if not color.isValid():
                color = QColor("#2563EB")
            color.setAlpha(255)
            palette_colors.append(color)

        def lighten_color(color: QColor, strength: float) -> QColor:
            lifted = QColor(
                clamp_channel(255 - (255 - color.red()) * strength),
                clamp_channel(255 - (255 - color.green()) * strength),
                clamp_channel(255 - (255 - color.blue()) * strength),
                255,
            )
            return lifted

        def palette_color(index: int) -> QColor:
            return QColor(palette_colors[index % len(palette_colors)])

        def draw_subtree(node: dict[str, object]) -> None:
            children = node.get('children', [])
            if not children:
                return
            node_radius = radius_for(float(node['distance']))
            child_angles = [node_angle(child) for child in children]
            if len(children) > 1:
                painter.drawPath(arc_path(node_radius, child_angles[0], child_angles[-1]))
            for child, angle_deg in zip(children, child_angles):
                child_radius = radius_for(float(child['distance']))
                painter.drawLine(point_at(node_radius, angle_deg), point_at(child_radius, angle_deg))
                draw_subtree(child)

        painter.setPen(QPen(QColor('#111827'), 1.3, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.setBrush(Qt.NoBrush)
        draw_subtree(root)

        painter.setPen(QPen(QColor('#E5E7EB'), 1.0))
        painter.setBrush(QColor('#FFFFFF'))
        painter.drawEllipse(center, title_radius, title_radius)
        painter.setPen(QPen(QColor('#475569'), 1))
        painter.drawText(
            QRectF(center.x() - title_radius, center.y() - title_radius * 0.55, title_radius * 2, title_radius * 1.1),
            Qt.AlignCenter,
            'Tree',
        )

        for ring_index in range(ring_count):
            radius_in = tree_outer_radius + ring_index * ring_width + 4
            radius_out = radius_in + ring_width - 2
            mid_radius = (radius_in + radius_out) / 2.0
            arc_rect = QRectF(center.x() - mid_radius, center.y() - mid_radius, mid_radius * 2.0, mid_radius * 2.0)
            pen_width = max(2.0, ring_width - 3.0)
            for leaf_index, leaf in enumerate(leaves):
                start_deg = leaf_angle(leaf_index)
                end_deg = leaf_angle(leaf_index + 1)
                base_index = (leaf_index + ring_index) % len(palette_colors)
                base_color = palette_color(base_index)
                if ring_index == 0:
                    tile_color = QColor(base_color)
                else:
                    strength = 0.9 - min(0.24, ring_index * 0.035)
                    strength += 0.04 * abs(math.sin((leaf_index + 1) * 0.52 + ring_index * 0.73))
                    strength = max(0.68, min(0.96, strength))
                    tile_color = lighten_color(base_color, strength)
                painter.setPen(QPen(tile_color, pen_width, Qt.SolidLine, Qt.FlatCap, Qt.RoundJoin))
                painter.drawArc(arc_rect, int(-end_deg * 16), int((end_deg - start_deg) * 16))
            painter.setPen(QPen(QColor('#E2E8F0'), 0.5))
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(center, mid_radius, mid_radius)

        painter.setPen(QPen(QColor('#334155'), 0.85))
        for leaf_index, leaf in enumerate(leaves):
            angle_deg = leaf_angle(leaf_index + 0.5)
            label = str(leaf.get('name') or f'L{leaf_index + 1}')
            label_point = point_at(label_radius, angle_deg)
            text_angle = angle_deg + 90.0
            right_side = math.cos(math.radians(angle_deg)) >= 0
            if not right_side:
                text_angle += 180.0
            painter.save()
            painter.translate(label_point)
            painter.rotate(text_angle)
            if right_side:
                text_rect = QRectF(4, -7, 52, 14)
                alignment = Qt.AlignLeft | Qt.AlignVCenter
            else:
                text_rect = QRectF(-56, -7, 52, 14)
                alignment = Qt.AlignRight | Qt.AlignVCenter
            painter.drawText(text_rect, alignment, label)
            painter.restore()

        legend_x = circle_rect.right() + 18
        legend_y = plot.top() + 18
        painter.setPen(QPen(QColor('#475569'), 1))
        painter.drawText(QRectF(legend_x, legend_y - 12, legend_width - 12, 14), Qt.AlignLeft | Qt.AlignVCenter, 'Circular tracks')
        for idx in range(len(palette_colors)):
            column = idx // 8
            row = idx % 8
            item_x = legend_x + column * 120
            item_y = legend_y + row * 18
            swatch_color = palette_color(idx)
            painter.fillRect(QRectF(item_x, item_y, 12, 12), swatch_color)
            painter.setPen(QPen(QColor('#CBD5E1'), 0.8))
            painter.drawRect(QRectF(item_x, item_y, 12, 12))
            painter.setPen(QPen(QColor('#475569'), 1))
            painter.drawText(QRectF(item_x + 18, item_y - 1, 96, 14), Qt.AlignLeft | Qt.AlignVCenter, f'Track {idx + 1}')

        painter.setPen(QPen(QColor('#475569'), 1))
        painter.drawText(int(plot.left()), int(plot.bottom() + 18), 'Circular phylogenetic heatmap preview')


    def paint_map(self, painter: QPainter, plot: QRectF, colors: list[str], has_focus: bool) -> None:
        shapes = load_china_preview_shapes()
        if not shapes:
            painter.setPen(QPen(QColor("#475569"), 1))
            painter.drawText(plot, Qt.AlignCenter, "China map preview unavailable")
            return

        def project_point(lon: float, lat: float) -> tuple[float, float]:
            lon_rad = math.radians(lon)
            lat_clamped = max(-85.0, min(85.0, lat))
            lat_rad = math.radians(lat_clamped)
            mercator_y = math.log(math.tan(math.pi / 4.0 + lat_rad / 2.0))
            return lon_rad, mercator_y

        projected_shapes = [[project_point(lon, lat) for lon, lat in shape] for shape in shapes]
        min_x = min(point[0] for shape in projected_shapes for point in shape)
        max_x = max(point[0] for shape in projected_shapes for point in shape)
        min_y = min(point[1] for shape in projected_shapes for point in shape)
        max_y = max(point[1] for shape in projected_shapes for point in shape)
        bounds_w = max(max_x - min_x, 1e-6)
        bounds_h = max(max_y - min_y, 1e-6)

        content_rect = plot.adjusted(34, 12, -34, -30)
        aspect = bounds_w / bounds_h
        draw_w = content_rect.width()
        draw_h = draw_w / aspect
        if draw_h > content_rect.height():
            draw_h = content_rect.height()
            draw_w = draw_h * aspect
        draw_w *= 0.9
        draw_h *= 0.9
        map_rect = QRectF(
            content_rect.center().x() - draw_w / 2.0,
            content_rect.center().y() - draw_h / 2.0,
            draw_w,
            draw_h,
        )

        scale = min(map_rect.width() / bounds_w, map_rect.height() / bounds_h)
        offset_x = map_rect.left() + (map_rect.width() - bounds_w * scale) / 2.0
        offset_y = map_rect.top() + (map_rect.height() - bounds_h * scale) / 2.0

        def map_point(lon: float, lat: float) -> QPointF:
            px, py = project_point(lon, lat)
            return QPointF(
                offset_x + (px - min_x) * scale,
                offset_y + (max_y - py) * scale,
            )

        border_pen = QPen(QColor('#CBD5E1'), 0.55)
        outer_pen = QPen(QColor('#94A3B8'), 0.9)

        painter.setPen(border_pen)
        for index, shape in enumerate(shapes):
            if len(shape) < 3:
                continue
            path = QPainterPath()
            path.moveTo(map_point(*shape[0]))
            for lon, lat in shape[1:]:
                path.lineTo(map_point(lon, lat))
            path.closeSubpath()
            painter.fillPath(path, self.effective_color(index, colors, has_focus))
            painter.drawPath(path)

        painter.setPen(outer_pen)
        painter.setBrush(Qt.NoBrush)
        for shape in shapes:
            if len(shape) < 3:
                continue
            path = QPainterPath()
            path.moveTo(map_point(*shape[0]))
            for lon, lat in shape[1:]:
                path.lineTo(map_point(lon, lat))
            path.closeSubpath()
            painter.drawPath(path)

        painter.setPen(QPen(QColor("#475569"), 1))
        painter.drawText(int(plot.left()), int(plot.bottom() + 18), "China map preview")


    def draw_marker(self, painter: QPainter, point: QPointF, color: QColor, highlighted: bool = False) -> None:
        painter.setPen(QPen(color, 1.2))
        painter.setBrush(color)
        size = float(self.marker_size + 2) if highlighted else float(self.marker_size)
        if self.marker_shape == "square":
            rect = QRectF(point.x() - size / 2, point.y() - size / 2, size, size)
            painter.drawRect(rect)
            return
        if self.marker_shape == "triangle":
            path = QPainterPath()
            path.moveTo(point.x(), point.y() - size / 1.2)
            path.lineTo(point.x() - size / 1.2, point.y() + size / 1.4)
            path.lineTo(point.x() + size / 1.2, point.y() + size / 1.4)
            path.closeSubpath()
            painter.drawPath(path)
            return
        painter.drawEllipse(point, size / 2, size / 2)

class PaletteCreateDialog(QDialog):
    def __init__(self, colors: list[ColorEntry], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Export Palette")
        self._output_key = "clipboard"
        layout = QVBoxLayout(self)
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Palette name")
        layout.addWidget(QLabel(f"Selected colors: {len(colors)}"))
        layout.addWidget(self.name_input)
        self.target_combo = QComboBox()
        self.target_combo.addItems(["OriginLab", "General", "R", "Python", "MATLAB", "All Formats"])
        self.target_combo.setCurrentIndex(0)
        layout.addWidget(self.target_combo)
        self.order_combo = QComboBox()
        self.order_combo.addItems(["Current order", "Reverse order", "Light to dark", "Dark to light"])
        layout.addWidget(self.order_combo)
        button_row = QHBoxLayout()
        clipboard_button = QPushButton("Clipboard")
        files_button = QPushButton("Files")
        both_button = QPushButton("Both")
        clipboard_button.clicked.connect(lambda: self.submit("clipboard"))
        files_button.clicked.connect(lambda: self.submit("files"))
        both_button.clicked.connect(lambda: self.submit("both"))
        button_row.addWidget(clipboard_button)
        button_row.addWidget(files_button)
        button_row.addWidget(both_button)
        layout.addLayout(button_row)

    @property
    def palette_name(self) -> str:
        return self.name_input.text().strip()

    @property
    def target_key(self) -> str:
        mapping = {
            "General": "general",
            "OriginLab": "originlab",
            "R": "r",
            "Python": "python",
            "MATLAB": "matlab",
            "All Formats": "all_formats",
        }
        return mapping[self.target_combo.currentText()]

    @property
    def order_key(self) -> str:
        mapping = {
            "Current order": "current",
            "Reverse order": "reverse",
            "Light to dark": "light_to_dark",
            "Dark to light": "dark_to_light",
        }
        return mapping[self.order_combo.currentText()]

    @property
    def output_key(self) -> str:
        return self._output_key

    def submit(self, output_key: str) -> None:
        self._output_key = output_key
        self.accept()

class AdvancedPreviewDialog(QDialog):
    def __init__(self, preview_state: dict[str, object], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Advanced Preview")
        self.resize(760, 980)
        self.setMinimumSize(720, 900)
        self.preview_state = preview_state.copy()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("Mode"))
        self.normal_button = QPushButton("Normal")
        self.normal_button.setCheckable(True)
        self.colorblind_button = QPushButton("Colorblind")
        self.colorblind_button.setCheckable(True)
        self.colorblind_type_combo = QComboBox()
        self.colorblind_type_combo.addItems(["Protan", "Deutan", "Tritan"])
        self.grayscale_button = QPushButton("Grayscale")
        self.grayscale_button.setCheckable(True)
        self.normal_button.clicked.connect(lambda: self.set_preview_mode("normal"))
        self.colorblind_button.clicked.connect(self.activate_colorblind_preview)
        self.colorblind_type_combo.currentIndexChanged.connect(self.on_colorblind_type_changed)
        self.grayscale_button.clicked.connect(lambda: self.set_preview_mode("grayscale"))
        mode_row.addWidget(self.normal_button)
        mode_row.addWidget(self.colorblind_button)
        mode_row.addWidget(self.colorblind_type_combo)
        mode_row.addWidget(self.grayscale_button)
        mode_row.addStretch(1)
        layout.addLayout(mode_row)

        chart_row = QHBoxLayout()
        chart_row.addWidget(QLabel("Chart"))
        self.chart_buttons: dict[str, QPushButton] = {}
        for label, value in (("Line", "line"), ("Bar", "bar"), ("Scatter", "scatter"), ("Clustered", "heatmap"), ("Circular", "phylo"), ("Map", "map")):
            button = QPushButton(label)
            button.setCheckable(True)
            button.clicked.connect(lambda _checked, chart=value: self.set_chart_type(chart))
            self.chart_buttons[value] = button
            chart_row.addWidget(button)
        chart_row.addStretch(1)
        layout.addLayout(chart_row)

        metric_row = QHBoxLayout()
        metric_row.setSpacing(6)
        metric_row.addWidget(QLabel("Series"))
        self.series_input = QLineEdit(str(int(self.preview_state.get("series_count", 5))))
        self.series_input.setFixedWidth(52)
        self.series_input.editingFinished.connect(self.refresh_preview)
        metric_row.addWidget(self.series_input)
        metric_row.addWidget(QLabel("Group"))
        self.group_input = QLineEdit(str(int(self.preview_state.get("group_count", 4))))
        self.group_input.setFixedWidth(52)
        self.group_input.editingFinished.connect(self.refresh_preview)
        metric_row.addWidget(self.group_input)
        metric_row.addWidget(QLabel("Colors"))
        self.color_count_input = QLineEdit(str(max(1, len(list(self.preview_state.get("colors", []))))))
        self.color_count_input.setFixedWidth(52)
        self.color_count_input.editingFinished.connect(self.refresh_preview)
        metric_row.addWidget(self.color_count_input)
        metric_row.addStretch(1)
        layout.addLayout(metric_row)

        hint = QLabel("???Advanced Preview ?????? Cart ??????Series / Group / Colors ?????????")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #475569; background: transparent;")
        layout.addWidget(hint)

        self.chart_preview = ChartPreviewWidget()
        self.chart_preview.setMinimumHeight(520)
        layout.addWidget(self.chart_preview, 1)

        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        layout.addWidget(close_button)

        preview_mode = str(self.preview_state.get("preview_mode", "normal"))
        if preview_mode == "grayscale":
            self.grayscale_button.setChecked(True)
        elif preview_mode.startswith("colorblind"):
            self.colorblind_button.setChecked(True)
            mapping = {"colorblind_protan": 0, "colorblind_deutan": 1, "colorblind_tritan": 2}
            self.colorblind_type_combo.setCurrentIndex(mapping.get(preview_mode, 1))
        else:
            self.normal_button.setChecked(True)
        self.sync_buttons()
        self.refresh_preview()

    def set_chart_type(self, chart_type: str) -> None:
        self.preview_state["chart_type"] = chart_type
        self.sync_buttons()
        self.refresh_preview()

    def set_preview_mode(self, preview_mode: str) -> None:
        self.preview_state["preview_mode"] = preview_mode
        self.normal_button.setChecked(preview_mode == "normal")
        self.colorblind_button.setChecked(preview_mode.startswith("colorblind"))
        self.grayscale_button.setChecked(preview_mode == "grayscale")
        self.refresh_preview()

    def activate_colorblind_preview(self) -> None:
        mapping = {0: "colorblind_protan", 1: "colorblind_deutan", 2: "colorblind_tritan"}
        self.set_preview_mode(mapping.get(self.colorblind_type_combo.currentIndex(), "colorblind_deutan"))

    def on_colorblind_type_changed(self, _index: int) -> None:
        if str(self.preview_state.get("preview_mode", "normal")).startswith("colorblind"):
            self.activate_colorblind_preview()

    def sync_buttons(self) -> None:
        chart_type = str(self.preview_state.get("chart_type", "line"))
        for value, button in self.chart_buttons.items():
            button.setChecked(value == chart_type)

    def refresh_preview(self) -> None:
        raw_colors = list(self.preview_state.get("colors", []))
        base_colors: list[str] = []
        for value in raw_colors:
            try:
                base_colors.append(normalize_hex_code(str(value)))
            except ValueError:
                continue
        color_count = self.read_int(self.color_count_input.text(), max(1, len(base_colors) or 1), 1, 64)
        colors = [base_colors[index % len(base_colors)] for index in range(color_count)] if base_colors else []
        series_count = self.read_int(self.series_input.text(), int(self.preview_state.get("series_count", 5)), 1, 24)
        group_count = self.read_int(self.group_input.text(), int(self.preview_state.get("group_count", 4)), 2, 48)
        self.chart_preview.set_preview_state(
            colors,
            str(self.preview_state.get("chart_type", "line")),
            series_count,
            group_count,
            int(self.preview_state.get("line_width", 2)),
            int(self.preview_state.get("point_size", 5)),
            str(self.preview_state.get("marker_shape", "circle")),
            int(self.preview_state.get("alpha", 100)),
            str(self.preview_state.get("preview_mode", "normal")),
            set(self.preview_state.get("highlighted_indices", set())),
        )

    def read_int(self, text: str, fallback: int, minimum: int, maximum: int) -> int:
        try:
            value = int(text)
        except ValueError:
            value = fallback
        return max(minimum, min(maximum, value))

class MainWindow(QMainWindow):
    def __init__(self, base_dir: Path) -> None:
        super().__init__()
        self.base_dir = base_dir
        self.config = AppConfig(base_dir / "user_config.json")
        self.palettes: list[Palette] = []
        self.filtered_palettes: list[Palette] = []
        self.current_palette: Palette | None = None
        self.selected_colors: list[ColorEntry] = []
        self.base_color_hex = "#4E74B3"
        self.active_source_filter = "all"
        self.sort_mode = "folder"
        self.group_mode = "folder"
        self.chart_type = "line"
        self.marker_shape = "circle"
        self.preview_mode = "normal"
        self.pending_select_source_path: str | None = None
        self.setWindowTitle("Color Library Manager")
        self.resize(1720, 980)
        self.setAcceptDrops(True)
        self.setStyleSheet(
            """
            QMainWindow, QWidget {
                background: #E2E8F0;
                color: #0F172A;
                font-size: 13px;
            }
            QLabel { color: #0F172A; }
            QLineEdit, QListWidget, QScrollArea, QTreeWidget {
                background: #FFFFFF;
                color: #0F172A;
                border: 1px solid #94A3B8;
                border-radius: 10px;
                padding: 3px 5px;
            }
            QListWidget::item { padding: 6px; border: none; }
            QListWidget::item:selected { background: #DBEAFE; color: #0F172A; }
            QTreeWidget::item { padding: 2px 0px; }
            QTreeWidget::item:selected { background: #DBEAFE; color: #0F172A; }
            QPushButton {
                background: #0F172A;
                color: #F8FAFC;
                border: 1px solid #0F172A;
                border-radius: 10px;
                padding: 8px 12px;
                font-weight: 700;
                min-height: 18px;
            }
            QPushButton:hover { background: #1E293B; }
            QPushButton:pressed { background: #334155; }
            QPushButton:checked {
                background: #2563EB;
                border-color: #2563EB;
                color: #FFFFFF;
            }
            QSplitter::handle { background: #94A3B8; width: 2px; }
            #topBar, #palettePanel, #detailPanel, #cartPanel, #previewPanel {
                background: #F8FAFC;
                border: 1px solid #94A3B8;
                border-radius: 12px;
            }
            """
        )
        self.build_ui()
        self.sync_lab_color_preview()
        self.load_initial_state()
        self.update_chart_preview()
    def build_ui(self) -> None:
        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(14, 14, 14, 14)
        root_layout.setSpacing(12)
        top_bar = QFrame()
        top_bar.setObjectName("topBar")
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(12, 10, 12, 10)
        top_layout.setSpacing(10)
        choose_materials = QPushButton("Materials")
        choose_materials.clicked.connect(self.choose_materials_dir)
        choose_library = QPushButton("Library")
        choose_library.clicked.connect(self.choose_library_dir)
        refresh_button = QPushButton("Rescan")
        refresh_button.clicked.connect(self.reload_palettes)
        import_files_button = QPushButton("Import Files")
        import_files_button.clicked.connect(self.import_material_files)
        import_folder_button = QPushButton("Import Folder")
        import_folder_button.clicked.connect(self.import_material_folder)
        paste_image_button = QPushButton("Paste Image")
        paste_image_button.clicked.connect(self.import_clipboard_image)
        self.materials_label = QLabel("Materials: not set")
        self.library_label = QLabel("Library: not set")
        self.materials_label.setStyleSheet("color: #475569; background: transparent;")
        self.library_label.setStyleSheet("color: #475569; background: transparent;")
        top_layout.addWidget(choose_materials)
        top_layout.addWidget(choose_library)
        top_layout.addWidget(refresh_button)
        top_layout.addWidget(import_files_button)
        top_layout.addWidget(import_folder_button)
        top_layout.addWidget(paste_image_button)
        top_layout.addSpacing(8)
        top_layout.addWidget(self.materials_label, 1)
        top_layout.addWidget(self.library_label, 1)
        root_layout.addWidget(top_bar)
        content_splitter = QSplitter(Qt.Horizontal)
        content_splitter.setChildrenCollapsible(False)
        palette_panel = self.build_palette_panel()
        palette_panel.setMinimumWidth(300)
        content_splitter.addWidget(palette_panel)
        work_splitter = QSplitter(Qt.Horizontal)
        work_splitter.setChildrenCollapsible(False)
        detail_column = QWidget()
        detail_column.setMinimumWidth(560)
        detail_column_layout = QVBoxLayout(detail_column)
        detail_column_layout.setContentsMargins(0, 0, 0, 0)
        detail_column_layout.setSpacing(10)
        detail_panel = self.build_detail_panel()
        preview_panel = self.build_preview_panel()
        preview_panel.setMinimumHeight(280)
        detail_column_layout.addWidget(detail_panel, 2)
        detail_column_layout.addWidget(preview_panel, 2)
        cart_panel = self.build_cart_panel()
        cart_panel.setMinimumWidth(420)
        work_splitter.addWidget(detail_column)
        work_splitter.addWidget(cart_panel)
        work_splitter.setStretchFactor(0, 3)
        work_splitter.setStretchFactor(1, 2)
        work_splitter.setSizes([860, 520])
        content_splitter.addWidget(work_splitter)
        content_splitter.setStretchFactor(0, 1)
        content_splitter.setStretchFactor(1, 4)
        content_splitter.setSizes([360, 1380])
        root_layout.addWidget(content_splitter, 1)
        self.setCentralWidget(root)
    def build_palette_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("palettePanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)
        self.drop_hint_label = QLabel("拖入文件/文件夹到窗口，或用上方 Import / Paste Image")
        self.drop_hint_label.setWordWrap(True)
        self.drop_hint_label.setStyleSheet("background: #FFFFFF; color: #475569; border: 1px dashed #94A3B8; border-radius: 10px; padding: 8px;")
        layout.addWidget(self.drop_hint_label)
        title = QLabel("Palettes")
        title.setStyleSheet("font-size: 18px; font-weight: 700; background: transparent;")
        layout.addWidget(title)

        filter_row = QHBoxLayout()
        filter_row.setSpacing(6)
        self.filter_group = QButtonGroup(self)
        self.filter_group.setExclusive(True)
        for label, key in (("All", "all"), ("Materials", "materials"), ("Library", "library"), ("Favorites", "favorites")):
            button = QPushButton(label)
            button.setCheckable(True)
            if key == "all":
                button.setChecked(True)
            button.clicked.connect(lambda _checked, value=key: self.set_source_filter(value))
            self.filter_group.addButton(button)
            filter_row.addWidget(button)
        layout.addLayout(filter_row)

        organize_row = QHBoxLayout()
        organize_row.setSpacing(6)
        organize_row.addWidget(QLabel("Sort"))
        self.sort_combo = QComboBox()
        self.sort_combo.addItems(["Folder", "Format", "Name", "Color Count"] )
        self.sort_combo.setCurrentText("Folder")
        self.sort_combo.currentTextChanged.connect(self.on_sort_or_group_changed)
        organize_row.addWidget(self.sort_combo)
        organize_row.addWidget(QLabel("Group"))
        self.group_combo = QComboBox()
        self.group_combo.addItems(["Format", "Folder", "Source", "Tags", "None"])
        self.group_combo.setCurrentText("Format")
        self.group_combo.currentTextChanged.connect(self.on_sort_or_group_changed)
        organize_row.addWidget(self.group_combo)
        layout.addLayout(organize_row)

        search_row = QHBoxLayout()
        search_row.setSpacing(6)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search name or path")
        self.search_input.textChanged.connect(self.populate_palette_tree)
        search_row.addWidget(self.search_input, 1)
        layout.addLayout(search_row)

        filter_top_row = QHBoxLayout()
        filter_top_row.setSpacing(6)
        filter_top_row.addWidget(QLabel("Count"))
        self.count_filter_combo = QComboBox()
        self.count_filter_combo.addItems(["Any", "<= 4", "5-8", "9-16", "> 16"])
        self.count_filter_combo.currentTextChanged.connect(self.populate_palette_tree)
        filter_top_row.addWidget(self.count_filter_combo)
        filter_top_row.addWidget(QLabel("Hue"))
        self.hue_filter_combo = QComboBox()
        self.hue_filter_combo.addItems(["Any", "Red", "Orange", "Yellow", "Green", "Cyan", "Blue", "Purple", "Neutral", "Mixed"] )
        self.hue_filter_combo.currentTextChanged.connect(self.populate_palette_tree)
        filter_top_row.addWidget(self.hue_filter_combo)
        layout.addLayout(filter_top_row)

        filter_bottom_row = QHBoxLayout()
        filter_bottom_row.setSpacing(6)
        filter_bottom_row.addWidget(QLabel("Type"))
        self.type_filter_combo = QComboBox()
        self.type_filter_combo.addItems(["Any", "Code Palette", "Image", "Gradient", "Document"])
        self.type_filter_combo.currentTextChanged.connect(self.populate_palette_tree)
        filter_bottom_row.addWidget(self.type_filter_combo)
        filter_bottom_row.addWidget(QLabel("Tag"))
        self.tag_filter_combo = QComboBox()
        self.tag_filter_combo.addItems(["Any"] )
        self.tag_filter_combo.currentTextChanged.connect(self.populate_palette_tree)
        filter_bottom_row.addWidget(self.tag_filter_combo)
        layout.addLayout(filter_bottom_row)

        self.palette_tree = QTreeWidget()
        self.palette_tree.setHeaderHidden(True)
        self.palette_tree.setIndentation(14)
        self.palette_tree.itemExpanded.connect(self.on_tree_item_expanded)
        self.palette_tree.itemCollapsed.connect(self.on_tree_item_collapsed)
        self.palette_tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.palette_tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.palette_tree.customContextMenuRequested.connect(self.open_palette_tree_menu)
        self.palette_tree.currentItemChanged.connect(self.on_palette_tree_current_item_changed)
        self.palette_tree.itemClicked.connect(self.on_palette_tree_clicked)
        layout.addWidget(self.palette_tree, 1)
        return panel
    def build_detail_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("detailPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)
        self.palette_title = QLabel("Palette Details")
        self.palette_title.setStyleSheet("font-size: 22px; font-weight: 700; background: transparent;")
        layout.addWidget(self.palette_title)
        self.palette_meta = QLabel("点击左侧色卡后，中间展开颜色。左键复制，右键加入右侧拼配区。")
        self.palette_meta.setWordWrap(True)
        self.palette_meta.setStyleSheet("color: #475569; background: transparent;")
        layout.addWidget(self.palette_meta)
        self.pdf_extractor_button = QPushButton("Open PDF Extractor")
        self.pdf_extractor_button.clicked.connect(self.open_current_pdf_extractor)
        self.pdf_extractor_button.hide()
        layout.addWidget(self.pdf_extractor_button)
        self.detail_splitter = QSplitter(Qt.Vertical)
        self.detail_splitter.setChildrenCollapsible(False)
        self.image_preview_label = ImagePreviewLabel()
        self.image_preview_label.setMinimumHeight(300)
        self.image_preview_label.setMinimumWidth(320)
        self.image_preview_label.setStyleSheet("background: #FFFFFF; border: 1px solid #CBD5E1; border-radius: 10px;")
        self.image_preview_label.color_picked.connect(self.on_preview_color_picked)
        self.image_preview_label.region_picked.connect(self.on_preview_region_picked)
        self.image_preview_label.hide()
        self.detail_splitter.addWidget(self.image_preview_label)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.color_container = FlowContainer()
        scroll.setWidget(self.color_container)
        self.detail_splitter.addWidget(scroll)
        self.detail_splitter.setStretchFactor(0, 2)
        self.detail_splitter.setStretchFactor(1, 3)
        self.detail_splitter.setSizes([360, 620])
        layout.addWidget(self.detail_splitter, 1)
        return panel
    def build_cart_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("cartPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)
        title = QLabel("Cart")
        title.setStyleSheet("font-size: 18px; font-weight: 700; background: transparent;")
        layout.addWidget(title)
        info = QLabel("右侧颜色加入这里。拖拽排序后保存，会按当前顺序导出。")
        info.setWordWrap(True)
        info.setStyleSheet("color: #475569; background: transparent;")
        layout.addWidget(info)
        self.selection_label = QLabel("Selected: 0")
        self.selection_label.setStyleSheet("font-weight: 700; background: transparent;")
        layout.addWidget(self.selection_label)
        self.selected_list = QListWidget()
        self.selected_list.setDragDropMode(QAbstractItemView.InternalMove)
        self.selected_list.setDefaultDropAction(Qt.MoveAction)
        self.selected_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.selected_list.model().rowsMoved.connect(self.sync_selected_colors_from_list)
        self.selected_list.itemSelectionChanged.connect(self.on_selected_cart_selection_changed)
        layout.addWidget(self.selected_list, 1)
        self.selected_preview = QLabel("No colors selected")
        self.selected_preview.setWordWrap(True)
        self.selected_preview.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.selected_preview.setStyleSheet(
            "background: #FFFFFF; color: #334155; border: 1px solid #CBD5E1; border-radius: 10px; padding: 10px;"
        )
        layout.addWidget(self.selected_preview)
        button_row = QHBoxLayout()
        remove_button = QPushButton("Remove")
        remove_button.clicked.connect(self.remove_selected_cart_item)
        clear_button = QPushButton("Clear")
        clear_button.clicked.connect(self.clear_selected_colors)
        save_button = QPushButton("Save Palette")
        save_button.clicked.connect(self.save_selected_palette)
        gradient_button = QPushButton("Export Gradient")
        gradient_button.clicked.connect(self.export_gradient_palette)
        button_row.addWidget(remove_button)
        button_row.addWidget(clear_button)
        button_row.addWidget(save_button)
        button_row.addWidget(gradient_button)
        layout.addLayout(button_row)
        lab_title = QLabel("Color Lab")
        lab_title.setStyleSheet("font-size: 16px; font-weight: 700; background: transparent;")
        lab_row = QHBoxLayout()
        self.lab_color_preview = QFrame()
        self.lab_color_preview.setFixedSize(30, 30)
        self.lab_color_preview.setStyleSheet("background: #4E74B3; border: 1px solid #64748B; border-radius: 8px;")
        lab_row.addWidget(self.lab_color_preview)
        self.lab_hex_input = QLineEdit("#4E74B3")
        self.lab_hex_input.setFixedWidth(92)
        self.lab_hex_input.editingFinished.connect(self.sync_lab_color_preview)
        lab_row.addWidget(self.lab_hex_input)
        self.lab_wheel_combo = QComboBox()
        self.lab_wheel_combo.addItems(["RGB", "RYB-like"])
        lab_row.addWidget(self.lab_wheel_combo)
        dialog_button = QPushButton("Pick")
        dialog_button.clicked.connect(self.pick_lab_color)
        lab_row.addWidget(dialog_button)
        lab_row.addStretch(1)
        layout.addLayout(lab_row)
        option_row = QHBoxLayout()
        option_row.addWidget(QLabel("Count"))
        self.lab_count_combo = QComboBox()
        self.lab_count_combo.addItems([str(value) for value in range(2, 10)])
        self.lab_count_combo.setCurrentText("5")
        option_row.addWidget(self.lab_count_combo)
        option_row.addWidget(QLabel("Tint bias"))
        self.tint_bias_combo = QComboBox()
        self.tint_bias_combo.addItems(["Neutral", "Warm", "Cool"])
        option_row.addWidget(self.tint_bias_combo)
        option_row.addWidget(QLabel("Tint mode"))
        self.tint_mode_combo = QComboBox()
        self.tint_mode_combo.addItems(["Base darkest", "Base lightest", "Base center"])
        option_row.addWidget(self.tint_mode_combo)
        option_row.addStretch(1)
        layout.addLayout(option_row)
        lab_button_row = QHBoxLayout()
        blend_button = QPushButton("Blend Mid")
        blend_button.clicked.connect(self.add_blended_lab_colors)
        similar_button = QPushButton("Similar")
        similar_button.clicked.connect(self.add_similar_lab_colors)
        complement_button = QPushButton("Complement")
        complement_button.clicked.connect(self.add_complementary_lab_colors)
        diverging_button = QPushButton("Diverging")
        diverging_button.clicked.connect(self.add_diverging_lab_colors)
        tint_button = QPushButton("Tint Ramp")
        tint_button.clicked.connect(self.add_tint_lab_colors)
        lab_button_row.addWidget(blend_button)
        lab_button_row.addWidget(similar_button)
        lab_button_row.addWidget(complement_button)
        lab_button_row.addWidget(diverging_button)
        lab_button_row.addWidget(tint_button)
        layout.addLayout(lab_button_row)
        hint = QLabel("提示：右侧选中 2 个或以上颜色时，Blend Mid 和 Diverging 会插入到这些颜色之间，而不是追加到末尾。")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #64748B; background: transparent;")
        layout.addWidget(hint)
        return panel
    def build_preview_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("previewPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)
        title = QLabel("Chart Preview")
        title.setStyleSheet("font-size: 18px; font-weight: 700; background: transparent;")
        layout.addWidget(title)
        mode_row = QHBoxLayout()
        mode_row.setSpacing(6)
        mode_row.addWidget(QLabel("Mode"))
        self.preview_normal_button = QPushButton("Normal")
        self.preview_normal_button.setCheckable(True)
        self.preview_normal_button.setChecked(True)
        self.preview_normal_button.setStyleSheet("QPushButton { background: #FFFFFF; color: #0F172A; border: 1px solid #94A3B8; } QPushButton:checked { background: #DBEAFE; color: #1D4ED8; border: 1px solid #60A5FA; }")
        self.preview_normal_button.clicked.connect(lambda: self.set_preview_mode("normal"))
        self.preview_colorblind_button = QPushButton("Colorblind")
        self.preview_colorblind_button.setCheckable(True)
        self.preview_colorblind_button.setStyleSheet("QPushButton { background: #FFFFFF; color: #0F172A; border: 1px solid #94A3B8; } QPushButton:checked { background: #DBEAFE; color: #1D4ED8; border: 1px solid #60A5FA; }")
        self.preview_colorblind_button.clicked.connect(self.activate_colorblind_preview)
        self.preview_colorblind_type_combo = QComboBox()
        self.preview_colorblind_type_combo.addItems(["Protan", "Deutan", "Tritan"])
        self.preview_colorblind_type_combo.currentIndexChanged.connect(self.on_colorblind_type_changed)
        self.preview_grayscale_button = QPushButton("Grayscale")
        self.preview_grayscale_button.setCheckable(True)
        self.preview_grayscale_button.setStyleSheet("QPushButton { background: #FFFFFF; color: #0F172A; border: 1px solid #94A3B8; } QPushButton:checked { background: #DBEAFE; color: #1D4ED8; border: 1px solid #60A5FA; }")
        self.preview_grayscale_button.clicked.connect(lambda: self.set_preview_mode("grayscale"))
        mode_row.addWidget(self.preview_normal_button)
        mode_row.addWidget(self.preview_colorblind_button)
        mode_row.addWidget(self.preview_colorblind_type_combo)
        mode_row.addWidget(self.preview_grayscale_button)
        mode_row.addStretch(1)
        layout.addLayout(mode_row)
        chart_row = QHBoxLayout()
        chart_row.setSpacing(6)
        chart_row.addWidget(QLabel("Chart"))
        self.line_button = QPushButton("Line")
        self.line_button.setCheckable(True)
        self.bar_button = QPushButton("Bar")
        self.bar_button.setCheckable(True)
        self.scatter_button = QPushButton("Scatter")
        self.scatter_button.setCheckable(True)
        self.line_button.setChecked(True)
        self.line_button.clicked.connect(lambda: self.set_chart_type("line"))
        self.bar_button.clicked.connect(lambda: self.set_chart_type("bar"))
        self.scatter_button.clicked.connect(lambda: self.set_chart_type("scatter"))
        chart_row.addWidget(self.line_button)
        chart_row.addWidget(self.bar_button)
        chart_row.addWidget(self.scatter_button)
        advanced_preview_button = QPushButton("Advanced Preview")
        advanced_preview_button.clicked.connect(self.open_advanced_preview_dialog)
        chart_row.addSpacing(12)
        chart_row.addWidget(advanced_preview_button)
        chart_row.addStretch(1)
        layout.addLayout(chart_row)
        shape_row = QHBoxLayout()
        shape_row.setSpacing(6)
        shape_row.addWidget(QLabel("Point"))
        self.shape_circle_button = QPushButton("Circle")
        self.shape_square_button = QPushButton("Square")
        self.shape_triangle_button = QPushButton("Triangle")
        for button, value in ((self.shape_circle_button, "circle"), (self.shape_square_button, "square"), (self.shape_triangle_button, "triangle")):
            button.setCheckable(True)
            button.clicked.connect(lambda _checked, marker=value: self.set_marker_shape(marker))
            shape_row.addWidget(button)
        self.shape_circle_button.setChecked(True)
        shape_row.addStretch(1)
        layout.addLayout(shape_row)
        metric_row = QHBoxLayout()
        metric_row.setSpacing(6)
        metric_row.addWidget(QLabel("Series"))
        self.series_input = QLineEdit("5")
        self.series_input.setFixedWidth(40)
        self.series_input.editingFinished.connect(self.update_chart_preview)
        metric_row.addWidget(self.series_input)
        metric_row.addWidget(QLabel("Group"))
        self.group_input = QLineEdit("4")
        self.group_input.setFixedWidth(40)
        self.group_input.editingFinished.connect(self.update_chart_preview)
        metric_row.addWidget(self.group_input)
        metric_row.addWidget(QLabel("Line"))
        self.line_width_input = QLineEdit("2")
        self.line_width_input.setFixedWidth(40)
        self.line_width_input.editingFinished.connect(self.update_chart_preview)
        metric_row.addWidget(self.line_width_input)
        metric_row.addWidget(QLabel("Point"))
        self.point_size_input = QLineEdit("5")
        self.point_size_input.setFixedWidth(40)
        self.point_size_input.editingFinished.connect(self.update_chart_preview)
        metric_row.addWidget(self.point_size_input)
        metric_row.addWidget(QLabel("Alpha"))
        self.alpha_input = QLineEdit("100")
        self.alpha_input.setFixedWidth(46)
        self.alpha_input.editingFinished.connect(self.update_chart_preview)
        metric_row.addWidget(self.alpha_input)
        metric_row.addStretch(1)
        layout.addLayout(metric_row)
        hint = QLabel("提示：预览可在正常、色盲模拟、黑白之间切换。Alpha 只影响预览，不影响导出。")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #475569; background: transparent;")
        layout.addWidget(hint)
        self.chart_preview = ChartPreviewWidget()
        layout.addWidget(self.chart_preview, 1)
        return panel
    def load_initial_state(self) -> None:
        if self.config.materials_dir:
            self.materials_label.setText(f"Materials: {self.config.materials_dir}")
        if self.config.library_dir:
            self.library_label.setText(f"Library: {self.config.library_dir}")
        if self.config.materials_dir or self.config.library_dir:
            self.reload_palettes()
        if not self.config.welcome_seen:
            QTimer.singleShot(0, self.show_first_run_guide)
    def show_first_run_guide(self) -> None:
        message = (
            "\u57fa\u7840\u64cd\u4f5c\n\n"
            "1. \u5148\u9009\u62e9 Materials \u548c Library \u6587\u4ef6\u5939\u3002\n"
            "2. \u5de6\u4fa7\u6d4f\u89c8 palette\uff0c\u5de6\u952e\u67e5\u770b\uff0c\u53f3\u952e\u505a\u5bfc\u5165\u3001\u5220\u9664\u3001\u63d0\u53d6\u3002\n"
            "3. \u4e2d\u95f4\u5de6\u952e\u590d\u5236\u989c\u8272\uff0c\u53f3\u952e\u52a0\u5165\u53f3\u4fa7\u62fc\u914d\u533a\u3002\n"
            "4. \u53f3\u4fa7\u53ef\u62d6\u62fd\u6392\u5e8f\uff0c\u518d\u4fdd\u5b58\u6216\u5bfc\u51fa\u3002\n"
            "5. \u4e0b\u65b9 Preview \u53ef\u5207\u6362\u666e\u901a\u56fe\u3001\u70ed\u56fe\u3001\u7cfb\u7edf\u8fdb\u5316\u548c\u5730\u56fe\u793a\u610f\u3002\n\n"
            "PDF \u5efa\u8bae\u901a\u8fc7\u8be6\u60c5\u533a\u7684 Open PDF Extractor \u8fdb\u5165\u4e13\u95e8\u63d0\u53d6\u7a97\u53e3\u3002"
        )
        QMessageBox.information(self, "Welcome", message)
        self.config.welcome_seen = True
        self.config.save()

    def choose_materials_dir(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self, "Choose Materials Folder", self.config.materials_dir or str(self.base_dir)
        )
        if not selected:
            return
        self.config.materials_dir = selected
        self.config.save()
        self.materials_label.setText(f"Materials: {selected}")
        self.reload_palettes()

    def choose_library_dir(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self, "Choose Library Folder", self.config.library_dir or str(self.base_dir)
        )
        if not selected:
            return
        self.config.library_dir = selected
        self.config.save()
        self.library_label.setText(f"Library: {selected}")
        self.reload_palettes()

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            if hasattr(self, "drop_hint_label"):
                self.drop_hint_label.setText("松开鼠标即可导入到 Materials")
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragLeaveEvent(self, event) -> None:  # noqa: N802
        if hasattr(self, "drop_hint_label"):
            self.drop_hint_label.setText("拖入文件/文件夹到窗口，或用上方 Import / Paste Image")
        super().dragLeaveEvent(event)

    def dropEvent(self, event) -> None:  # noqa: N802
        if hasattr(self, "drop_hint_label"):
            self.drop_hint_label.setText("拖入文件/文件夹到窗口，或用上方 Import / Paste Image")
        urls = event.mimeData().urls()
        if not urls:
            super().dropEvent(event)
            return
        paths = [Path(url.toLocalFile()) for url in urls if url.isLocalFile()]
        imported = self.import_paths_to_materials(paths)
        if imported:
            event.acceptProposedAction()
            return
        super().dropEvent(event)

    def ensure_materials_dir_ready(self) -> bool:
        if self.config.materials_dir:
            return True
        QMessageBox.information(self, "Materials Folder Missing", "Choose a materials folder first.")
        return False
    def unique_target_path(self, target: Path) -> Path:
        if not target.exists():
            return target
        stem = target.stem
        suffix = target.suffix
        counter = 1
        while True:
            candidate = target.with_name(f"{stem}_{counter}{suffix}")
            if not candidate.exists():
                return candidate
            counter += 1

    def import_material_files(self) -> None:
        if not self.ensure_materials_dir_ready():
            return
        selected, _ = QFileDialog.getOpenFileNames(
            self,
            "Import Materials",
            self.config.materials_dir or str(self.base_dir),
            "Supported Files (*.ase *.gpl *.csv *.json *.pal *.pdf *.png *.jpg *.jpeg *.bmp *.webp *.tif *.tiff);;All Files (*.*)",
        )
        if not selected:
            return
        self.import_paths_to_materials([Path(value) for value in selected])

    def import_material_folder(self) -> None:
        if not self.ensure_materials_dir_ready():
            return
        selected = QFileDialog.getExistingDirectory(
            self, "Import Folder", self.config.materials_dir or str(self.base_dir)
        )
        if not selected:
            return
        self.import_paths_to_materials([Path(selected)])

    def import_clipboard_image(self) -> None:
        if not self.ensure_materials_dir_ready():
            return
        pixmap = QGuiApplication.clipboard().pixmap()
        if pixmap.isNull():
            QMessageBox.information(self, "Clipboard Empty", "Clipboard does not contain an image.")
            return
        materials_root = Path(self.config.materials_dir)
        ensure_directory(materials_root)
        target = self.unique_target_path(materials_root / "clipboard.png")
        if not pixmap.save(str(target), "PNG"):
            QMessageBox.warning(self, "Import Failed", "Could not save clipboard image.")
            return
        self.pending_select_source_path = str(target)
        self.reload_palettes()
        self.statusBar().showMessage("Imported clipboard image", 3000)
    def import_paths_to_materials(self, paths: list[Path]) -> int:
        if not self.ensure_materials_dir_ready():
            return 0
        materials_root = Path(self.config.materials_dir)
        ensure_directory(materials_root)
        imported = 0
        last_file_target: Path | None = None
        for path in paths:
            if not path.exists():
                continue
            try:
                if path.is_dir():
                    target = self.unique_target_path(materials_root / path.name)
                    shutil.copytree(path, target)
                    imported += 1
                else:
                    target = self.unique_target_path(materials_root / path.name)
                    shutil.copy2(path, target)
                    last_file_target = target
                    imported += 1
            except Exception:
                continue
        if imported:
            self.pending_select_source_path = str(last_file_target) if last_file_target is not None else None
            self.reload_palettes()
            self.statusBar().showMessage(f"Imported {imported} item(s) into materials", 3500)
        return imported

    def on_palette_tree_current_item_changed(self, current: QTreeWidgetItem, _previous: QTreeWidgetItem) -> None:
        if current is None:
            return
        data = current.data(0, Qt.UserRole)
        if isinstance(data, Palette):
            self.show_palette_details(data)

    def get_selected_palette_items(self) -> list[Palette]:
        palettes: list[Palette] = []
        for item in self.palette_tree.selectedItems():
            palette = item.data(0, Qt.UserRole)
            if isinstance(palette, Palette):
                palettes.append(palette)
        if not palettes and self.current_palette is not None:
            palettes.append(self.current_palette)
        return palettes

    def add_selected_palette_colors(self) -> None:
        palettes = self.get_selected_palette_items()
        if not palettes:
            return
        existing_hexes = {item.hex_code for item in self.selected_colors}
        added = 0
        for palette in palettes:
            for color in palette.colors:
                if color.hex_code in existing_hexes:
                    continue
                self.selected_colors.append(color)
                existing_hexes.add(color.hex_code)
                added += 1
        self.refresh_cart()
        if self.current_palette is not None:
            self.render_palette_colors(self.current_palette)
        self.statusBar().showMessage(f"Added {added} colors from {len(palettes)} palette(s)", 2500)

    def open_palette_tree_menu(self, position) -> None:
        menu = QMenu(self)
        selected = self.get_selected_palette_items()
        favorite_action = menu.addAction("Toggle Favorite")
        unfavorite_action = menu.addAction("Remove Favorite")
        add_group_action = menu.addAction("Add Tag")
        remove_group_action = menu.addAction("Remove Tag")
        copy_action = menu.addAction("Copy File")
        add_colors_action = menu.addAction("Add Colors")
        rename_action = menu.addAction("Rename")
        extract_action = menu.addAction("Extract Theme")
        pdf_action = menu.addAction("Open PDF Extractor")
        delete_action = menu.addAction("Delete To Recycle Bin")
        if not selected:
            favorite_action.setEnabled(False)
            unfavorite_action.setEnabled(False)
            add_group_action.setEnabled(False)
            remove_group_action.setEnabled(False)
            copy_action.setEnabled(False)
            add_colors_action.setEnabled(False)
            rename_action.setEnabled(False)
            extract_action.setEnabled(False)
            pdf_action.setEnabled(False)
            delete_action.setEnabled(False)
        elif len(selected) > 1:
            rename_action.setEnabled(False)
            extract_action.setEnabled(False)
            pdf_action.setEnabled(False)
        else:
            if selected[0].source_format not in {"image", "grid"}:
                extract_action.setEnabled(False)
            if selected[0].source_format != "pdf":
                pdf_action.setEnabled(False)
        action = menu.exec(self.palette_tree.viewport().mapToGlobal(position))
        if action is favorite_action:
            self.toggle_selected_favorites()
        elif action is unfavorite_action:
            self.remove_selected_favorites()
        elif action is add_group_action:
            self.add_selected_to_group()
        elif action is remove_group_action:
            self.remove_selected_from_group()
        elif action is copy_action:
            self.copy_source_file()
        elif action is add_colors_action:
            self.add_selected_palette_colors()
        elif action is rename_action:
            self.rename_current_palette()
        elif action is extract_action:
            self.reextract_current_image_palette()
        elif action is pdf_action:
            self.open_current_pdf_extractor()
        elif action is delete_action:
            self.delete_selected_to_recycle_bin()
    def toggle_selected_favorites(self) -> None:
        selected = self.get_selected_palette_items()
        if not selected:
            return
        changed = 0
        for palette in selected:
            if palette.source_path is None:
                continue
            path = str(palette.source_path)
            self.config.set_favorite(path, not self.config.is_favorite(path))
            changed += 1
        if changed:
            self.config.save()
            self.refresh_tag_filter_options()
            self.populate_palette_tree()
            self.statusBar().showMessage(f"Updated favorites for {changed} palette(s)", 2500)
    def remove_selected_favorites(self) -> None:
        selected = self.get_selected_palette_items()
        if not selected:
            return
        changed = 0
        for palette in selected:
            if palette.source_path is None:
                continue
            path = str(palette.source_path)
            if self.config.is_favorite(path):
                self.config.set_favorite(path, False)
                changed += 1
        if changed:
            self.config.save()
            self.refresh_tag_filter_options()
            self.populate_palette_tree()
            self.statusBar().showMessage(f"Removed favorite from {changed} palette(s)", 2500)
    def add_selected_to_group(self) -> None:
        selected = [palette for palette in self.get_selected_palette_items() if palette.source_path is not None]
        if not selected:
            return
        existing = ", ".join(self.config.group_names())
        prompt = "Tag name:"
        if existing:
            prompt += f"\nExisting: {existing}"
        group_name, ok = QInputDialog.getText(self, "Add Tag", prompt)
        if not ok or not group_name.strip():
            return
        changed = 0
        for palette in selected:
            self.config.add_to_group(group_name.strip(), str(palette.source_path))
            changed += 1
        if changed:
            self.config.save()
            self.populate_palette_tree()
            self.refresh_tag_filter_options()
            self.statusBar().showMessage(f"Added tag {group_name.strip()} to {changed} palette(s)", 2500)
    def remove_selected_from_group(self) -> None:
        selected = [palette for palette in self.get_selected_palette_items() if palette.source_path is not None]
        if not selected:
            return
        group_names = self.config.group_names()
        if not group_names:
            QMessageBox.information(self, "No Tags", "No tags exist yet.")
            return
        group_name, ok = QInputDialog.getItem(self, "Remove Tag", "Tag:", group_names, 0, False)
        if not ok or not group_name:
            return
        changed = 0
        for palette in selected:
            self.config.remove_from_group(group_name, str(palette.source_path))
            changed += 1
        if changed:
            self.config.save()
            self.populate_palette_tree()
            self.refresh_tag_filter_options()
            self.statusBar().showMessage(f"Removed tag {group_name} from {changed} palette(s)", 2500)
    def refresh_tag_filter_options(self) -> None:
        if not hasattr(self, "tag_filter_combo"):
            return
        current = self.tag_filter_combo.currentText()
        tags = ["Any"] + self.config.group_names()
        self.tag_filter_combo.blockSignals(True)
        self.tag_filter_combo.clear()
        self.tag_filter_combo.addItems(tags)
        self.tag_filter_combo.setCurrentText(current if current in tags else "Any")
        self.tag_filter_combo.blockSignals(False)
    def set_source_filter(self, value: str) -> None:
        self.active_source_filter = value
        self.populate_palette_tree()
    def on_sort_or_group_changed(self) -> None:
        self.sort_mode = self.sort_combo.currentText().lower().replace(" ", "_")
        self.group_mode = self.group_combo.currentText().lower().replace(" ", "_")
        self.populate_palette_tree()
    def reload_palettes(self) -> None:
        self.palettes = []
        if self.config.materials_dir:
            self.palettes.extend(scan_palettes(Path(self.config.materials_dir), "materials"))
        if self.config.library_dir:
            self.palettes.extend(self.scan_library_palettes(Path(self.config.library_dir)))
        self.palettes = self.collapse_duplicate_palettes(self.palettes)
        self.refresh_tag_filter_options()
        self.populate_palette_tree()
        if self.pending_select_source_path:
            match = next(
                (
                    palette
                    for palette in self.palettes
                    if palette.source_path is not None and str(palette.source_path) == self.pending_select_source_path
                ),
                None,
            )
            self.pending_select_source_path = None
            if match is not None:
                self.select_palette_in_tree(match)
                self.show_palette_details(match)
                return
        if self.filtered_palettes:
            first_palette = self.filtered_palettes[0]
            self.select_palette_in_tree(first_palette, scroll=False)
            self.show_palette_details(first_palette)
            return
        self.current_palette = None
        self.color_container.clear()
        self.palette_title.setText("选择一个色卡")
        self.palette_meta.setText("点击左侧色卡后，中间展开颜色。左键复制，右键加入右侧拼配区。")
        if hasattr(self, "image_preview_label"):
            self.image_preview_label.clear_preview()
            self.image_preview_label.hide()
    def scan_library_palettes(self, library_dir: Path) -> list[Palette]:
        palettes: list[Palette] = []
        palettes_dir = library_dir / "palettes"
        if palettes_dir.exists():
            palettes.extend(scan_palettes(palettes_dir, "library"))
        generated_dir = library_dir / "generated"
        if generated_dir.exists():
            palettes.extend(scan_palettes(generated_dir, "library"))
        gradient_dir = library_dir / "exports" / "originlab_gradient"
        if gradient_dir.exists():
            palettes.extend(scan_palettes(gradient_dir, "library"))
        if palettes:
            return palettes
        palettes = scan_palettes(library_dir, "library")
        return [
            palette
            for palette in palettes
            if palette.source_path is not None and "exports" not in {part.lower() for part in palette.source_path.parts}
        ]
    def collapse_duplicate_palettes(self, palettes: list[Palette]) -> list[Palette]:
        priority = {"json": 4, "ase": 3, "gpl": 2, "csv": 1, "generated": 5}
        grouped: dict[tuple[str, str], Palette] = {}
        ordered: list[Palette] = []
        for palette in palettes:
            if palette.source_group != "library" or palette.source_path is None:
                ordered.append(palette)
                continue
            key = (palette.source_group, str(palette.source_path.with_suffix("")))
            existing = grouped.get(key)
            if existing is None:
                grouped[key] = palette
                ordered.append(palette)
                continue
            if priority.get(palette.source_format, 0) > priority.get(existing.source_format, 0):
                grouped[key] = palette
                index = ordered.index(existing)
                ordered[index] = palette
        return ordered
    def populate_palette_tree(self) -> None:
        current_scroll = self.palette_tree.verticalScrollBar().value() if hasattr(self, "palette_tree") else 0
        previous_palette = self.current_palette
        self.palette_tree.clear()
        palettes = self.get_visible_palettes()
        self.filtered_palettes = self.sort_palettes([palette for palette in palettes if self.palette_matches_filters(palette)])
        roots: dict[str, QTreeWidgetItem] = {}
        has_saved_tree_state = bool(self.config.tree_expanded)
        for palette in self.filtered_palettes:
            section = self.get_tree_section_label(palette)
            root = roots.get(section)
            if root is None:
                root = QTreeWidgetItem([section])
                root.setData(0, Qt.UserRole, {"node": "section", "label": section})
                root_key = self.get_tree_item_key(root)
                root.setExpanded(True if not has_saved_tree_state else self.config.is_tree_expanded(root_key))
                self.palette_tree.addTopLevelItem(root)
                roots[section] = root
            parent = self.ensure_tree_group_path(root, palette)
            item = QTreeWidgetItem([""])
            item.setData(0, Qt.UserRole, palette)
            item.setSizeHint(0, QSize(0, 74))
            parent.addChild(item)
            is_favorite = bool(palette.source_path and self.config.is_favorite(str(palette.source_path)))
            self.palette_tree.setItemWidget(item, 0, PaletteListCard(palette, is_favorite))
        if previous_palette is not None and self.select_palette_in_tree(previous_palette, scroll=False):
            return
        self.palette_tree.verticalScrollBar().setValue(current_scroll)
    def get_visible_palettes(self) -> list[Palette]:
        if self.active_source_filter == "all":
            return list(self.palettes)
        if self.active_source_filter == "favorites":
            return [palette for palette in self.palettes if palette.source_path and self.config.is_favorite(str(palette.source_path))]
        return [palette for palette in self.palettes if palette.source_group == self.active_source_filter]
    def get_tree_section_label(self, palette: Palette) -> str:
        if self.active_source_filter == "favorites":
            return "Favorites"
        if self.group_mode == "tags":
            return f"Tag: {self.get_palette_manual_group_label(palette)}"
        return palette.source_group.title()
    def ensure_tree_group_path(self, root: QTreeWidgetItem, palette: Palette) -> QTreeWidgetItem:
        parts: list[str] = []
        if self.group_mode == "folder":
            label = self.get_palette_folder_label(palette)
            parts = [part for part in label.replace("\\", "/").split("/") if part]
        elif self.group_mode == "format":
            parts = [palette.source_format.upper()]
        elif self.group_mode == "source":
            parts = [palette.source_group.title()]
        elif self.group_mode == "tags":
            parts = []
        parent = root
        for part in parts:
            match = None
            for index in range(parent.childCount()):
                child = parent.child(index)
                data = child.data(0, Qt.UserRole)
                if isinstance(data, dict) and data.get("node") == "group" and data.get("label") == part:
                    match = child
                    break
            if match is None:
                match = QTreeWidgetItem([part])
                match.setData(0, Qt.UserRole, {"node": "group", "label": part})
                match_key = self.get_tree_item_key(match, parent)
                match.setExpanded(True if not self.config.tree_expanded else self.config.is_tree_expanded(match_key))
                parent.addChild(match)
            parent = match
        return parent
    def select_palette_in_tree(self, palette: Palette, scroll: bool = True) -> bool:
        iterator: list[QTreeWidgetItem] = []
        for index in range(self.palette_tree.topLevelItemCount()):
            iterator.append(self.palette_tree.topLevelItem(index))
        while iterator:
            item = iterator.pop(0)
            data = item.data(0, Qt.UserRole)
            if isinstance(data, Palette) and data.source_path == palette.source_path and data.name == palette.name:
                self.palette_tree.setCurrentItem(item)
                if scroll:
                    self.palette_tree.scrollToItem(item)
                return True
            for child_index in range(item.childCount()):
                iterator.append(item.child(child_index))
        return False
    def on_palette_tree_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        data = item.data(0, Qt.UserRole)
        if isinstance(data, Palette):
            self.show_palette_details(data)
            return
        if item.childCount() > 0:
            item.setExpanded(not item.isExpanded())
    def get_tree_item_key(self, item: QTreeWidgetItem, parent: QTreeWidgetItem | None = None) -> str:
        labels: list[str] = []
        current = parent if parent is not None else item.parent()
        labels.append(item.text(0))
        while current is not None:
            labels.append(current.text(0))
            current = current.parent()
        labels.reverse()
        return " / ".join(labels)
    def on_tree_item_expanded(self, item: QTreeWidgetItem) -> None:
        if item.childCount() <= 0:
            return
        self.config.set_tree_expanded(self.get_tree_item_key(item), True)
        self.config.save()
    def on_tree_item_collapsed(self, item: QTreeWidgetItem) -> None:
        if item.childCount() <= 0:
            return
        self.config.set_tree_expanded(self.get_tree_item_key(item), False)
        self.config.save()
    def palette_matches_filters(self, palette: Palette) -> bool:
        search_text = self.search_input.text().strip().lower() if hasattr(self, "search_input") else ""
        if search_text:
            haystack = [palette.name.lower(), palette.source_format.lower(), palette.source_group.lower()]
            if palette.source_path is not None:
                haystack.append(str(palette.source_path).lower())
            if not any(search_text in value for value in haystack):
                return False
        count_mode = self.count_filter_combo.currentText() if hasattr(self, "count_filter_combo") else "Any"
        color_count = len(palette.colors)
        if count_mode == "<= 4" and color_count > 4:
            return False
        if count_mode == "5-8" and not (5 <= color_count <= 8):
            return False
        if count_mode == "9-16" and not (9 <= color_count <= 16):
            return False
        if count_mode == "> 16" and color_count <= 16:
            return False
        hue_mode = self.hue_filter_combo.currentText() if hasattr(self, "hue_filter_combo") else "Any"
        if hue_mode != "Any" and self.get_palette_hue_label(palette) != hue_mode:
            return False
        type_mode = self.type_filter_combo.currentText() if hasattr(self, "type_filter_combo") else "Any"
        if type_mode != "Any" and self.get_palette_type_label(palette) != type_mode:
            return False
        if self.group_mode == "tags":
            if palette.source_path is None:
                return False
            if not self.config.groups_for_path(str(palette.source_path)):
                return False
        tag_mode = self.tag_filter_combo.currentText() if hasattr(self, "tag_filter_combo") else "Any"
        if tag_mode != "Any":
            if palette.source_path is None:
                return False
            if tag_mode not in self.config.groups_for_path(str(palette.source_path)):
                return False
        return True
    def sort_palettes(self, palettes: list[Palette]) -> list[Palette]:
        if self.sort_mode == "name":
            return sorted(palettes, key=lambda palette: (palette.name.lower(), self.get_palette_folder_label(palette).lower()))
        if self.sort_mode == "format":
            return sorted(palettes, key=lambda palette: (palette.source_format.lower(), palette.name.lower()))
        if self.sort_mode == "color_count":
            return sorted(palettes, key=lambda palette: (-len(palette.colors), palette.name.lower()))
        return sorted(
            palettes,
            key=lambda palette: (
                self.get_palette_folder_label(palette).lower(),
                palette.source_format.lower(),
                palette.name.lower(),
            ),
        )
    def get_palette_group_label(self, palette: Palette) -> str:
        if self.group_mode == "none":
            return "All palettes"
        if self.group_mode == "format":
            return f"Format: {palette.source_format.upper()}"
        if self.group_mode == "source":
            return f"Source: {palette.source_group.title()}"
        if self.group_mode == "tags":
            return f"Tag: {self.get_palette_manual_group_label(palette)}"
        return f"Folder: {self.get_palette_folder_label(palette)}"
    def get_palette_folder_label(self, palette: Palette) -> str:
        if palette.source_path is None:
            return "Generated"
        root_dir = None
        if palette.source_group == "materials" and self.config.materials_dir:
            root_dir = Path(self.config.materials_dir)
        elif palette.source_group == "library" and self.config.library_dir:
            root_dir = Path(self.config.library_dir)
        if root_dir is not None:
            try:
                relative = palette.source_path.parent.relative_to(root_dir)
                return str(relative) if str(relative) != "." else root_dir.name
            except ValueError:
                pass
        parent = palette.source_path.parent
        return parent.name or str(parent)
    def get_palette_manual_group_label(self, palette: Palette) -> str:
        if palette.source_path is None:
            return ""
        groups = self.config.groups_for_path(str(palette.source_path))
        if not groups:
            return ""
        return groups[0]
    def get_palette_type_label(self, palette: Palette) -> str:
        if palette.source_format in {"image", "grid"}:
            return "Image"
        if palette.source_format == "pal":
            return "Gradient"
        if palette.source_format == "pdf":
            return "Document"
        return "Code Palette"

    def get_palette_hue_label(self, palette: Palette) -> str:
        if not palette.colors:
            return "Neutral"
        labels = {self.get_color_hue_label(color) for color in palette.colors[: min(8, len(palette.colors))]}
        if len(labels) == 1:
            return next(iter(labels))
        if len(labels) >= 3:
            return "Mixed"
        labels.discard("Neutral")
        if len(labels) == 1:
            return next(iter(labels))
        return "Mixed"
    def get_color_hue_label(self, color: ColorEntry) -> str:
        red, green, blue = color.rgb
        max_value = max(red, green, blue)
        min_value = min(red, green, blue)
        delta = max_value - min_value
        if max_value < 120 and delta < 18:
            return "Neutral"
        if delta < 20:
            return "Neutral"
        if max_value == red:
            degree = (60 * ((green - blue) / delta)) % 360
        elif max_value == green:
            degree = 60 * ((blue - red) / delta) + 120
        else:
            degree = 60 * ((red - green) / delta) + 240
        if degree < 20 or degree >= 340:
            return "Red"
        if degree < 45:
            return "Orange"
        if degree < 70:
            return "Yellow"
        if degree < 150:
            return "Green"
        if degree < 200:
            return "Cyan"
        if degree < 255:
            return "Blue"
        return "Purple"
    def show_palette_details(self, palette: Palette) -> None:
        self.current_palette = palette
        self.palette_title.setText(palette.name)
        source = str(palette.source_path) if palette.source_path else "Generated"
        if palette.source_format == "pdf":
            page_count = palette.metadata.get("page_count", "?")
            self.palette_meta.setText(
                f"{len(palette.colors)} preview colors | PDF | {page_count} pages | Source: {source}"
            )
            self.pdf_extractor_button.show()
        else:
            self.palette_meta.setText(
                f"{len(palette.colors)} colors | {palette.source_group} | Source: {source}"
            )
            self.pdf_extractor_button.hide()
        self.update_source_preview(palette)
        self.render_palette_colors(palette)

    def render_palette_colors(self, palette: Palette | None) -> None:
        self.color_container.clear()
        if palette is None:
            return
        selected_hexes = {item.hex_code for item in self.selected_colors}
        if palette.source_format in {"image", "grid", "pdf"}:
            columns = 4
            min_width = 132
        elif palette.source_format == "pal":
            columns = 4
            min_width = 132
        else:
            columns = 3
            min_width = 148
        for index, color in enumerate(palette.colors):
            widget = ClickableColorCard(color)
            widget.clicked.connect(self.on_color_card_clicked)
            widget.toggled.connect(self.toggle_selected_color)
            widget.set_selected(color.hex_code in selected_hexes)
            widget.set_base_selected(color.hex_code == self.base_color_hex)
            widget.setMinimumWidth(min_width)
            self.color_container.add_widget(widget, index, columns=columns)

    def update_source_preview(self, palette: Palette | None) -> None:
        if not hasattr(self, "image_preview_label"):
            return
        if palette is None:
            self.image_preview_label.clear_preview()
            self.image_preview_label.hide()
            return
        if palette.source_path is None:
            self.image_preview_label.clear_preview()
            self.image_preview_label.hide()
            return
        if palette.source_format == "pal":
            self.detail_splitter.setOrientation(Qt.Vertical)
            self.detail_splitter.setSizes([110, 470])
            self.image_preview_label.setMinimumHeight(120)
            self.image_preview_label.setMinimumWidth(240)
            self.image_preview_label.set_source_pixmap(
                build_gradient_pixmap([color.hex_code for color in palette.colors], 900, 64),
                False,
            )
            self.image_preview_label.show()
            return
        if palette.source_format == "pdf":
            try:
                preview_page = int(palette.metadata.get("preview_page", 1)) - 1
                pdf_image = render_pdf_page(palette.source_path, page_index=max(0, preview_page), max_edge=1100)
                pixmap = QPixmap.fromImage(pdf_image)
            except Exception:
                self.image_preview_label.clear_preview()
                self.image_preview_label.hide()
                return
            self.detail_splitter.setOrientation(Qt.Horizontal)
            self.detail_splitter.setSizes([360, 640])
            self.image_preview_label.setMinimumHeight(300)
            self.image_preview_label.setMinimumWidth(320)
            self.image_preview_label.set_source_pixmap(pixmap, False)
            self.image_preview_label.show()
            return
        if palette.source_format in {"image", "grid"}:
            pixmap = QPixmap(str(palette.source_path))
            if pixmap.isNull():
                self.image_preview_label.clear_preview()
                self.image_preview_label.hide()
                return
            self.detail_splitter.setOrientation(Qt.Horizontal)
            self.detail_splitter.setSizes([360, 640])
            self.image_preview_label.setMinimumHeight(300)
            self.image_preview_label.setMinimumWidth(320)
            self.image_preview_label.set_source_pixmap(pixmap, True)
            self.image_preview_label.show()
            return
        self.detail_splitter.setOrientation(Qt.Vertical)
        self.detail_splitter.setSizes([110, 470])
        self.image_preview_label.clear_preview()
        self.image_preview_label.hide()
    def on_preview_color_picked(self, hex_code: str) -> None:
        color = ColorEntry(name=f"Sample {len(self.selected_colors) + 1}", hex_code=hex_code)
        if not any(item.hex_code == color.hex_code for item in self.selected_colors):
            self.selected_colors.append(color)
            self.refresh_cart()
            if self.current_palette is not None:
                self.render_palette_colors(self.current_palette)
        self.copy_color_hex(color)
    def on_preview_region_picked(self, region: object) -> None:
        if self.current_palette is None or self.current_palette.source_path is None:
            return
        if self.current_palette.source_format not in {"image", "grid"}:
            return
        if not isinstance(region, tuple) or len(region) != 4:
            return
        rows, ok = QInputDialog.getInt(self, "Grid From Selection", "Rows:", 1, 1, 32, 1)
        if not ok:
            return
        cols, ok = QInputDialog.getInt(self, "Grid From Selection", "Columns:", 5, 1, 32, 1)
        if not ok:
            return
        try:
            palette = load_image_grid_palette(
                self.current_palette.source_path,
                rows=rows,
                cols=cols,
                sample_ratio=0.6,
                crop_bounds=region,
            )
        except Exception as exc:
            QMessageBox.warning(self, "Selection Grid Failed", str(exc))
            return
        palette.source_group = self.current_palette.source_group
        self.palette_title.setText(f"{palette.name} (selection)")
        self.palette_meta.setText(f"{len(palette.colors)} colors | selection grid | Source: {palette.source_path}")
        self.render_palette_colors(palette)
        self.statusBar().showMessage(f"Extracted {rows}x{cols} from selection", 3000)
    def add_current_palette_colors(self) -> None:
        if self.current_palette is None:
            return
        existing_hexes = {item.hex_code for item in self.selected_colors}
        added = 0
        for color in self.current_palette.colors:
            if color.hex_code in existing_hexes:
                continue
            self.selected_colors.append(color)
            existing_hexes.add(color.hex_code)
            added += 1
        self.refresh_cart()
        if self.current_palette is not None:
            self.render_palette_colors(self.current_palette)
        self.statusBar().showMessage(f"Added {added} colors", 2500)
    def on_color_card_clicked(self, color: ColorEntry) -> None:
        self.base_color_hex = color.hex_code
        self.lab_hex_input.setText(color.hex_code)
        self.sync_lab_color_preview()
        if self.current_palette is not None:
            self.render_palette_colors(self.current_palette)
        self.copy_color_hex(color)

    def copy_color_hex(self, color: ColorEntry) -> None:
        QGuiApplication.clipboard().setText(color.hex_code)
        self.statusBar().showMessage(f"Copied {color.hex_code}", 2500)

    def toggle_selected_color(self, color: ColorEntry, selected: bool) -> None:
        existing_hexes = {item.hex_code for item in self.selected_colors}
        if selected and color.hex_code not in existing_hexes:
            self.selected_colors.append(ColorEntry(name=color.name, hex_code=color.hex_code))
        elif not selected:
            self.selected_colors = [item for item in self.selected_colors if item.hex_code != color.hex_code]
        self.refresh_cart()
        if self.current_palette is not None:
            self.render_palette_colors(self.current_palette)

    def current_lab_hex(self) -> str:
        return normalize_hex_code(self.lab_hex_input.text())

    def generated_color_count(self) -> int:
        return int(self.lab_count_combo.currentText())

    def sync_lab_color_preview(self) -> None:
        try:
            hex_code = self.current_lab_hex()
        except ValueError:
            self.statusBar().showMessage("HEX needs 6 digits", 2500)
            return
        self.base_color_hex = hex_code
        self.lab_hex_input.setText(hex_code)
        self.lab_color_preview.setStyleSheet(
            f"background: {hex_code}; border: 1px solid #64748B; border-radius: 8px;"
        )
        if self.current_palette is not None:
            self.render_palette_colors(self.current_palette)

    def pick_lab_color(self) -> None:
        initial = QColor(self.lab_hex_input.text() or "#4E74B3")
        color = QColorDialog.getColor(initial, self, "Choose Base Color")
        if not color.isValid():
            return
        self.lab_hex_input.setText(color.name().upper())
        self.sync_lab_color_preview()

    def lab_wheel_mode(self) -> str:
        return "ryb" if self.lab_wheel_combo.currentText() == "RYB-like" else "rgb"

    def append_generated_colors(self, hex_codes: list[str], prefix: str) -> None:
        existing = {color.hex_code for color in self.selected_colors}
        added = 0
        for index, hex_code in enumerate(hex_codes, start=1):
            normalized = normalize_hex_code(hex_code)
            if normalized in existing:
                continue
            self.selected_colors.append(ColorEntry(name=f"{prefix} {index}", hex_code=normalized))
            existing.add(normalized)
            added += 1
        if added:
            self.refresh_cart()
            if self.current_palette is not None:
                self.render_palette_colors(self.current_palette)
        self.statusBar().showMessage(f"Added {added} generated colors", 2500)

    def get_selected_cart_rows(self) -> list[int]:
        return sorted({index.row() for index in self.selected_list.selectedIndexes()})

    def insert_generated_between_selected(self, prefix: str, segments: list[list[str]]) -> bool:
        rows = self.get_selected_cart_rows()
        if len(rows) < 2 or len(segments) != len(rows) - 1:
            return False
        inserted = 0
        counter = 1
        for pair_index, segment in enumerate(segments):
            insert_at = rows[pair_index] + 1 + inserted
            for hex_code in segment:
                normalized = normalize_hex_code(hex_code)
                self.selected_colors.insert(
                    insert_at,
                    ColorEntry(name=f"{prefix} {counter}", hex_code=normalized),
                )
                insert_at += 1
                inserted += 1
                counter += 1
        self.refresh_cart()
        if self.current_palette is not None:
            self.render_palette_colors(self.current_palette)
        self.statusBar().showMessage(f"Inserted {inserted} generated colors", 2500)
        return True

    def get_blend_source_colors(self) -> list[ColorEntry]:
        chosen: list[ColorEntry] = []
        for item in self.selected_list.selectedItems():
            color = item.data(Qt.UserRole)
            if isinstance(color, ColorEntry):
                chosen.append(color)
        if len(chosen) >= 2:
            return chosen
        return self.selected_colors

    def add_blended_lab_colors(self) -> None:
        rows = self.get_selected_cart_rows()
        if len(rows) >= 2:
            segments = []
            for index in range(len(rows) - 1):
                left = self.selected_colors[rows[index]]
                right = self.selected_colors[rows[index + 1]]
                colors = build_interpolated_colors([left.hex_code, right.hex_code], self.generated_color_count())
                segments.append(colors[1:-1])
            if self.insert_generated_between_selected("Blend", segments):
                return
        source_colors = self.get_blend_source_colors()
        if len(source_colors) < 2:
            self.statusBar().showMessage("Select at least two colors to blend", 2500)
            return
        colors = build_interpolated_colors(
            [color.hex_code for color in source_colors],
            self.generated_color_count(),
        )
        self.append_generated_colors(colors, "Blend")

    def add_similar_lab_colors(self) -> None:
        self.sync_lab_color_preview()
        colors = build_similar_colors(
            self.current_lab_hex(),
            self.lab_wheel_mode(),
            self.generated_color_count(),
        )
        self.append_generated_colors(colors, "Similar")

    def add_complementary_lab_colors(self) -> None:
        self.sync_lab_color_preview()
        colors = build_complementary_colors(
            self.current_lab_hex(),
            self.lab_wheel_mode(),
            self.generated_color_count(),
        )
        self.append_generated_colors(colors, "Complement")

    def add_diverging_lab_colors(self) -> None:
        rows = self.get_selected_cart_rows()
        if len(rows) >= 2:
            segments = []
            for index in range(len(rows) - 1):
                left = self.selected_colors[rows[index]]
                right = self.selected_colors[rows[index + 1]]
                colors = build_diverging_colors(left.hex_code, right.hex_code, self.generated_color_count())
                segments.append(colors[1:-1])
            if self.insert_generated_between_selected("Diverging", segments):
                return
        self.sync_lab_color_preview()
        source_colors = self.get_blend_source_colors()
        if len(source_colors) >= 2:
            start_hex = source_colors[0].hex_code
            end_hex = source_colors[-1].hex_code
        elif self.selected_colors:
            start_hex = self.current_lab_hex()
            end_hex = self.selected_colors[-1].hex_code
        else:
            self.statusBar().showMessage("Add at least one comparison color for diverging", 2500)
            return
        colors = build_diverging_colors(start_hex, end_hex, self.generated_color_count())
        self.append_generated_colors(colors, "Diverging")

    def add_tint_lab_colors(self) -> None:
        self.sync_lab_color_preview()
        bias = self.tint_bias_combo.currentText().lower()
        mode = self.tint_mode_combo.currentText()
        colors = build_tint_ramp_mode(
            self.current_lab_hex(),
            bias,
            mode,
            self.generated_color_count(),
        )
        self.append_generated_colors(colors, "Tint")
    def add_tint_lab_colors(self) -> None:
        self.sync_lab_color_preview()
        bias = self.tint_bias_combo.currentText().lower()
        mode = self.tint_mode_combo.currentText()
        colors = build_tint_ramp_mode(
            self.current_lab_hex(),
            bias,
            mode,
            self.generated_color_count(),
        )
        self.append_generated_colors(colors, "Tint")
    def refresh_cart(self) -> None:
        self.selected_list.clear()
        for color in self.selected_colors:
            item = QListWidgetItem()
            item.setSizeHint(QSize(0, 52))
            item.setData(Qt.UserRole, color)
            self.selected_list.addItem(item)
            self.selected_list.setItemWidget(item, SelectedColorWidget(color))
        self.refresh_selected_preview()
        self.update_chart_preview()

    def refresh_selected_preview(self) -> None:
        self.selection_label.setText(f"Selected: {len(self.selected_colors)}")
        if not self.selected_colors:
            self.selected_preview.setText("No colors selected")
            return
        preview = "  ".join(color.hex_code for color in self.selected_colors)
        self.selected_preview.setText(preview)

    def on_selected_cart_selection_changed(self) -> None:
        selected_items = self.selected_list.selectedItems()
        if selected_items:
            color = selected_items[0].data(Qt.UserRole)
            if isinstance(color, ColorEntry):
                self.base_color_hex = color.hex_code
                self.lab_hex_input.setText(color.hex_code)
                self.sync_lab_color_preview()
        self.update_chart_preview()
        if self.current_palette is not None:
            self.render_palette_colors(self.current_palette)

    def sync_selected_colors_from_list(self, *_args) -> None:
        colors: list[ColorEntry] = []
        for index in range(self.selected_list.count()):
            item = self.selected_list.item(index)
            color = item.data(Qt.UserRole)
            if isinstance(color, ColorEntry):
                colors.append(color)
        self.selected_colors = colors
        self.refresh_selected_preview()
        self.update_chart_preview()
    def remove_selected_cart_item(self) -> None:
        rows = sorted({index.row() for index in self.selected_list.selectedIndexes()}, reverse=True)
        if not rows:
            row = self.selected_list.currentRow()
            if row >= 0:
                rows = [row]
        if not rows:
            return
        for row in rows:
            if 0 <= row < len(self.selected_colors):
                self.selected_colors.pop(row)
        self.refresh_cart()
        if self.current_palette is not None:
            self.render_palette_colors(self.current_palette)
    def clear_selected_colors(self) -> None:
        self.selected_colors = []
        self.refresh_cart()
        if self.current_palette is not None:
            self.render_palette_colors(self.current_palette)
    def save_selected_palette(self) -> None:
        if not self.selected_colors:
            QMessageBox.information(self, "No Selection", "Select at least one color first.")
            return
        dialog = PaletteCreateDialog(self.selected_colors, self)
        if dialog.exec() != QDialog.Accepted:
            return
        palette_name = dialog.palette_name or "palette"
        target_key = dialog.target_key
        order_key = dialog.order_key
        output_key = dialog.output_key
        ordered_colors = self.build_ordered_colors(self.selected_colors, order_key)
        palette = Palette(name=palette_name, colors=ordered_colors, source_format="generated", source_group="library")
        clipboard_text = self.build_clipboard_text(target_key, palette)
        if output_key in ("clipboard", "both"):
            QGuiApplication.clipboard().setText(clipboard_text)
        if output_key in ("files", "both"):
            if not self.config.library_dir:
                QMessageBox.information(self, "Library Folder Missing", "Choose a library folder first.")
                return
            exported_path = self.export_palette_files(target_key, palette)
            if exported_path is not None:
                self.pending_select_source_path = str(exported_path)
            self.reload_palettes()
        if output_key == "clipboard":
            self.statusBar().showMessage("Copied palette to clipboard", 3000)
        elif output_key == "files":
            self.statusBar().showMessage("Exported palette files", 3000)
        else:
            self.statusBar().showMessage("Copied palette and exported files", 3000)

    def build_ordered_colors(self, colors: list[ColorEntry], order_key: str) -> list[ColorEntry]:
        ordered = list(colors)
        if order_key == "reverse":
            ordered.reverse()
        elif order_key == "light_to_dark":
            ordered.sort(key=self.color_lightness, reverse=True)
        elif order_key == "dark_to_light":
            ordered.sort(key=self.color_lightness)
        return [ColorEntry(name=color.name, hex_code=color.hex_code) for color in ordered]

    def color_lightness(self, color: ColorEntry) -> float:
        red, green, blue = color.rgb
        return 0.2126 * red + 0.7152 * green + 0.0722 * blue

    def build_clipboard_text(self, target_key: str, palette: Palette) -> str:
        hexes = [color.hex_code for color in palette.colors]
        if target_key == "all_formats":
            rows = [f"{r/255:.6f} {g/255:.6f} {b/255:.6f}" for r, g, b in (color.rgb for color in palette.colors)]
            return "\n\n".join([
                "HEX\n" + ", ".join(hexes),
                "R\n" + f"{self.make_safe_filename(palette.name)} <- c(" + ", ".join(f'\"{value}\"' for value in hexes) + ")",
                "Python\n" + f"{self.make_safe_filename(palette.name)} = [" + ", ".join(f'\"{value}\"' for value in hexes) + "]",
                "MATLAB\n" + f"{self.make_safe_filename(palette.name)} = [ ...\n    " + "; ...\n    ".join(rows) + "\n];",
            ])
        if target_key == "r":
            return f"{self.make_safe_filename(palette.name)} <- c(" + ", ".join(f'\"{value}\"' for value in hexes) + ")"
        if target_key == "python":
            return f"{self.make_safe_filename(palette.name)} = [" + ", ".join(f'\"{value}\"' for value in hexes) + "]"
        if target_key == "matlab":
            rows = [f"{r/255:.6f} {g/255:.6f} {b/255:.6f}" for r, g, b in (color.rgb for color in palette.colors)]
            return f"{self.make_safe_filename(palette.name)} = [ ...\n    " + "; ...\n    ".join(rows) + "\n];"
        if target_key == "originlab":
            return "\n".join(hexes)
        return ", ".join(hexes)

    def export_palette_files(self, target_key: str, palette: Palette) -> Path | None:
        assert self.config.library_dir
        file_stem = self.make_safe_filename(palette.name)
        library_palettes_dir = Path(self.config.library_dir) / "palettes"
        ensure_directory(library_palettes_dir)
        library_json_path = library_palettes_dir / f"{file_stem}.json"
        save_palette_json(palette, library_json_path)
        if target_key == "all_formats":
            for export_key in ("originlab", "general", "r", "python", "matlab"):
                self.export_palette_files(export_key, palette)
            return library_json_path
        exports_root = Path(self.config.library_dir) / "exports" / target_key
        ensure_directory(exports_root)
        if target_key == "general":
            save_palette_json(palette, exports_root / f"{file_stem}.json")
            save_palette_csv(palette, exports_root / f"{file_stem}.csv")
            return library_json_path
        if target_key == "originlab":
            save_palette_ase(palette, exports_root / f"{file_stem}.ase")
            save_palette_csv(palette, exports_root / f"{file_stem}.csv")
            return library_json_path
        content = self.build_clipboard_text(target_key, palette)
        extension = {"r": ".R", "python": ".py", "matlab": ".m"}[target_key]
        (exports_root / f"{file_stem}{extension}").write_text(content, encoding="utf-8")
        return library_json_path

    def export_gradient_palette(self) -> None:
        if not self.selected_colors:
            QMessageBox.information(self, "No Selection", "Select at least one color first.")
            return
        if not self.config.library_dir:
            QMessageBox.information(self, "Library Folder Missing", "Choose a library folder first.")
            return
        default_name = self.make_safe_filename(self.current_palette.name if self.current_palette else "gradient")
        name, ok = QInputDialog.getText(self, "Export Gradient", "Gradient name:", text=default_name)
        if not ok or not name.strip():
            return
        steps, ok = QInputDialog.getInt(self, "Export Gradient", "Steps:", 256, 8, 1024, 8)
        if not ok:
            return
        palette = Palette(
            name=name.strip(),
            colors=[ColorEntry(name=color.name, hex_code=color.hex_code) for color in self.selected_colors],
            source_format="generated",
            source_group="library",
        )
        output_dir = Path(self.config.library_dir) / "exports" / "originlab_gradient"
        ensure_directory(output_dir)
        save_originlab_pal(palette, output_dir / f"{self.make_safe_filename(name.strip())}.pal", steps=steps)
        self.reload_palettes()
        self.statusBar().showMessage("Exported OriginLab gradient", 4000)

    def reextract_current_image_palette(self) -> None:
        if self.current_palette is None or self.current_palette.source_path is None:
            QMessageBox.information(self, "Unavailable", "Select an image palette first.")
            return
        if self.current_palette.source_format not in {"image", "grid"}:
            QMessageBox.information(self, "Unavailable", "This action is only for image materials.")
            return
        count, ok = QInputDialog.getInt(
            self,
            "Reextract Image Colors",
            "Color count:",
            value=max(3, len(self.current_palette.colors)),
            minValue=1,
            maxValue=24,
            step=1,
        )
        if not ok:
            return
        try:
            palette = load_palette(self.current_palette.source_path, color_count=count)
        except Exception as exc:
            QMessageBox.warning(self, "Image Extraction Failed", str(exc))
            return
        palette.source_group = self.current_palette.source_group
        self.replace_palette_in_views(palette)
        self.statusBar().showMessage(f"Reextracted {len(palette.colors)} colors", 3000)

    def open_current_pdf_extractor(self) -> None:
        if self.current_palette is None or self.current_palette.source_path is None:
            QMessageBox.information(self, "Unavailable", "Select a PDF material first.")
            return
        if self.current_palette.source_format != "pdf":
            QMessageBox.information(self, "Unavailable", "This action is only for PDF materials.")
            return
        if not self.ensure_materials_dir_ready():
            return
        try:
            dialog = PdfExtractDialog(self.current_palette.source_path, Path(self.config.materials_dir), self)
        except Exception as exc:
            QMessageBox.warning(self, "PDF Extractor Unavailable", str(exc))
            return
        dialog.exec()
        if dialog.saved_paths:
            self.pending_select_source_path = str(dialog.saved_paths[-1])
            self.reload_palettes()
            self.statusBar().showMessage(f"Saved {len(dialog.saved_paths)} PDF palette(s) into materials", 3500)

    def replace_palette_in_views(self, palette: Palette) -> None:
        self.current_palette = palette
        replaced = False
        for index, existing in enumerate(self.palettes):
            if existing.source_path == palette.source_path:
                self.palettes[index] = palette
                replaced = True
                break
        if not replaced:
            self.palettes.append(palette)
        for index, existing in enumerate(self.filtered_palettes):
            if existing.source_path == palette.source_path:
                self.filtered_palettes[index] = palette
                break
        self.populate_palette_tree()
        self.select_palette_in_tree(palette)
        self.show_palette_details(palette)

    def detect_current_image_grid(self) -> None:
        if self.current_palette is None or self.current_palette.source_path is None:
            QMessageBox.information(self, "Unavailable", "Select an image palette first.")
            return
        if self.current_palette.source_format not in {"image", "grid"}:
            QMessageBox.information(self, "Unavailable", "This action is only for image materials.")
            return
        rows, ok = QInputDialog.getInt(self, "Detect Swatch Grid", "Rows:", 1, 1, 32, 1)
        if not ok:
            return
        cols, ok = QInputDialog.getInt(self, "Detect Swatch Grid", "Columns:", 9, 1, 32, 1)
        if not ok:
            return
        try:
            palette = load_image_grid_palette(self.current_palette.source_path, rows=rows, cols=cols, sample_ratio=0.6)
        except Exception as exc:
            QMessageBox.warning(self, "Grid Detection Failed", str(exc))
            return
        palette.source_group = self.current_palette.source_group
        self.replace_palette_in_views(palette)
        self.statusBar().showMessage(f"Detected grid {rows}x{cols}", 3000)
    def rename_current_palette(self) -> None:
        if self.current_palette is None or self.current_palette.source_path is None:
            QMessageBox.information(self, "Unavailable", "Select a palette with a source file first.")
            return
        old_path = self.current_palette.source_path
        text, ok = QInputDialog.getText(self, "Rename Palette", "New palette name:", text=self.current_palette.name)
        if not ok or not text.strip():
            return
        new_name = text.strip()
        new_path = old_path.with_name(f"{self.make_safe_filename(new_name)}{old_path.suffix}")
        if new_path.exists() and new_path != old_path:
            QMessageBox.warning(self, "Rename Failed", "A file with that name already exists.")
            return
        try:
            old_path.rename(new_path)
        except OSError as exc:
            QMessageBox.warning(self, "Rename Failed", str(exc))
            return
        self.statusBar().showMessage(f"Renamed to {new_path.name}", 3000)
        self.reload_palettes()
    def toggle_current_favorite(self) -> None:
        if self.current_palette is None or self.current_palette.source_path is None:
            QMessageBox.information(self, "Unavailable", "Select a palette with a source file first.")
            return
        path = str(self.current_palette.source_path)
        new_state = not self.config.is_favorite(path)
        self.config.set_favorite(path, new_state)
        self.config.save()
        self.populate_palette_tree()
        self.statusBar().showMessage("Favorite updated", 2000)
    def recycle_path(self, path: Path) -> bool:
        escaped = str(path).replace("'", "''")
        if path.is_dir():
            command = (
                "Add-Type -AssemblyName Microsoft.VisualBasic; "
                f"[Microsoft.VisualBasic.FileIO.FileSystem]::DeleteDirectory('{escaped}', 'OnlyErrorDialogs', 'SendToRecycleBin')"
            )
        else:
            command = (
                "Add-Type -AssemblyName Microsoft.VisualBasic; "
                f"[Microsoft.VisualBasic.FileIO.FileSystem]::DeleteFile('{escaped}', 'OnlyErrorDialogs', 'SendToRecycleBin')"
            )
        result = subprocess.run(["powershell", "-NoProfile", "-Command", command], capture_output=True, text=True)
        return result.returncode == 0
    def remove_path_from_config(self, path: str) -> None:
        if self.config.is_favorite(path):
            self.config.set_favorite(path, False)
        for group_name in self.config.group_names():
            self.config.remove_from_group(group_name, path)

    def cleanup_empty_parent_dirs(self, deleted_path: Path) -> None:
        roots: list[Path] = []
        if self.config.materials_dir:
            roots.append(Path(self.config.materials_dir).resolve())
        if self.config.library_dir:
            roots.append(Path(self.config.library_dir).resolve())
        if not roots:
            return
        start_dir = deleted_path if deleted_path.is_dir() else deleted_path.parent
        try:
            current = start_dir.resolve()
        except Exception:
            current = start_dir
        while True:
            matching_root = None
            for root in roots:
                try:
                    current.relative_to(root)
                    matching_root = root
                    break
                except Exception:
                    continue
            if matching_root is None or current == matching_root:
                break
            try:
                if current.exists() and not any(current.iterdir()):
                    current.rmdir()
                    current = current.parent
                    continue
            except Exception:
                pass
            break
    def delete_selected_to_recycle_bin(self) -> None:
        selected = [palette for palette in self.get_selected_palette_items() if palette.source_path is not None]
        if not selected:
            return
        unique_paths: list[Path] = []
        seen: set[str] = set()
        for palette in selected:
            assert palette.source_path is not None
            path_value = str(palette.source_path)
            if path_value in seen:
                continue
            seen.add(path_value)
            unique_paths.append(palette.source_path)
        answer = QMessageBox.question(self, "Delete", f"Move {len(unique_paths)} item(s) to Recycle Bin?")
        if answer != QMessageBox.Yes:
            return
        deleted = 0
        failed: list[str] = []
        for path in unique_paths:
            if not path.exists():
                self.remove_path_from_config(str(path))
                self.cleanup_empty_parent_dirs(path)
                deleted += 1
                continue
            if self.recycle_path(path):
                self.remove_path_from_config(str(path))
                self.cleanup_empty_parent_dirs(path)
                deleted += 1
            else:
                failed.append(path.name)
        if deleted:
            self.config.save()
            self.reload_palettes()
            self.current_palette = None
            self.palette_title.setText("Select a palette")
            self.palette_meta.setText("Choose one from the left to preview.")
            self.update_source_preview(None)
            self.render_palette_colors(None)
            self.statusBar().showMessage(f"Moved {deleted} item(s) to Recycle Bin", 3000)
        if failed:
            QMessageBox.warning(
                self,
                "Delete Failed",
                "Could not move these item(s) to Recycle Bin:\n" + "\n".join(failed[:10]),
            )
    def copy_source_file(self) -> None:
        selected = [palette for palette in self.get_selected_palette_items() if palette.source_path is not None]
        if not selected:
            QMessageBox.information(self, "Unavailable", "Select a palette with a source file first.")
            return
        mime_data = QMimeData()
        mime_data.setUrls([QUrl.fromLocalFile(str(palette.source_path)) for palette in selected])
        mime_data.setText("\n".join(str(palette.source_path) for palette in selected))
        QGuiApplication.clipboard().setMimeData(mime_data)
        self.statusBar().showMessage(f"Copied {len(selected)} source file reference(s)", 2500)

    def set_chart_type(self, chart_type: str) -> None:
        self.chart_type = chart_type
        self.line_button.setChecked(chart_type == "line")
        self.bar_button.setChecked(chart_type == "bar")
        self.scatter_button.setChecked(chart_type == "scatter")
        self.update_chart_preview()

    def get_cart_hex_colors(self) -> list[str]:
        colors: list[str] = []
        if hasattr(self, "selected_list"):
            for index in range(self.selected_list.count()):
                item = self.selected_list.item(index)
                data = item.data(Qt.UserRole) if item is not None else None
                if isinstance(data, ColorEntry):
                    colors.append(data.hex_code)
        if not colors:
            colors = [color.hex_code for color in self.selected_colors]
        normalized: list[str] = []
        for value in colors:
            try:
                normalized.append(normalize_hex_code(str(value)))
            except ValueError:
                continue
        return normalized

    def collect_preview_state(self, chart_type: str | None = None) -> dict[str, object]:
        highlighted_indices = {index.row() for index in self.selected_list.selectedIndexes()}
        return {
            "colors": self.get_cart_hex_colors(),
            "chart_type": chart_type or self.chart_type,
            "series_count": self.read_int(self.series_input.text() if hasattr(self, "series_input") else "5", 5, 1, 8),
            "group_count": self.read_int(self.group_input.text() if hasattr(self, "group_input") else "4", 4, 2, 12),
            "line_width": self.read_int(self.line_width_input.text() if hasattr(self, "line_width_input") else "2", 2, 1, 8),
            "point_size": self.read_int(self.point_size_input.text() if hasattr(self, "point_size_input") else "5", 5, 2, 16),
            "marker_shape": self.marker_shape,
            "alpha": self.read_int(self.alpha_input.text() if hasattr(self, "alpha_input") else "100", 100, 10, 100),
            "preview_mode": self.preview_mode,
            "highlighted_indices": highlighted_indices,
        }

    def open_advanced_preview_dialog(self) -> None:
        state = self.collect_preview_state(chart_type="heatmap")
        if not state["colors"]:
            QMessageBox.information(self, "Cart Empty", "Add colors to the Cart first. Advanced Preview uses the Cart order directly.")
            return
        dialog = AdvancedPreviewDialog(state, self)
        dialog.exec()

    def activate_colorblind_preview(self) -> None:
        mapping = {0: "colorblind_protan", 1: "colorblind_deutan", 2: "colorblind_tritan"}
        self.set_preview_mode(mapping.get(self.preview_colorblind_type_combo.currentIndex(), "colorblind_deutan"))

    def on_colorblind_type_changed(self, _index: int) -> None:
        if self.preview_mode.startswith("colorblind"):
            self.activate_colorblind_preview()


    def set_preview_mode(self, preview_mode: str) -> None:
        self.preview_mode = preview_mode
        self.preview_normal_button.setChecked(preview_mode == "normal")
        self.preview_colorblind_button.setChecked(preview_mode.startswith("colorblind"))
        self.preview_grayscale_button.setChecked(preview_mode == "grayscale")
        self.update_chart_preview()

    def update_chart_preview(self) -> None:
        state = self.collect_preview_state()
        self.chart_preview.set_preview_state(
            list(state["colors"]),
            str(state["chart_type"]),
            int(state["series_count"]),
            int(state["group_count"]),
            int(state["line_width"]),
            int(state["point_size"]),
            str(state["marker_shape"]),
            int(state["alpha"]),
            str(state["preview_mode"]),
            set(state["highlighted_indices"]),
        )

    def set_marker_shape(self, marker_shape: str) -> None:
        self.marker_shape = marker_shape
        self.shape_circle_button.setChecked(marker_shape == "circle")
        self.shape_square_button.setChecked(marker_shape == "square")
        self.shape_triangle_button.setChecked(marker_shape == "triangle")
        self.update_chart_preview()
    def read_int(self, text: str, fallback: int, minimum: int, maximum: int) -> int:
        try:
            value = int(text)
        except ValueError:
            value = fallback
        return max(minimum, min(maximum, value))
    def make_safe_filename(self, value: str) -> str:
        safe = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in value.strip())
        return safe or "palette"











    def closeEvent(self, event) -> None:  # noqa: N802
        self.hide()
        super().closeEvent(event)
        app = QApplication.instance()
        if app is not None:
            app.closeAllWindows()
            app.quit()





