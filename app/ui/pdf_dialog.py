from __future__ import annotations

import math
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.models import ColorEntry, Palette
from app.parsers import (
    load_pdf_palette,
    load_pdf_region_palette,
    pdf_page_count,
    render_pdf_page,
)
from app.storage import ensure_directory, save_palette_json


class PdfPreviewLabel(QLabel):
    color_picked = Signal(str)
    region_picked = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self._source_pixmap: QPixmap | None = None
        self._scaled_pixmap: QPixmap | None = None
        self._drag_start: QPointF | None = None
        self._drag_current: QPointF | None = None
        self._selected_rect: QRectF | None = None
        self._display_rect: QRectF | None = None
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(480, 640)
        self.setStyleSheet("background: #FFFFFF; border: 1px solid #CBD5E1; border-radius: 10px;")

    def set_source_pixmap(self, pixmap: QPixmap) -> None:
        self._source_pixmap = pixmap
        self._selected_rect = None
        self._refresh_pixmap()

    def clear_preview(self) -> None:
        self._source_pixmap = None
        self._scaled_pixmap = None
        self._drag_start = None
        self._drag_current = None
        self._selected_rect = None
        self._display_rect = None
        self.clear()

    def clear_selection(self) -> None:
        self._drag_start = None
        self._drag_current = None
        self._selected_rect = None
        self.update()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._refresh_pixmap()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() != Qt.LeftButton or self._source_pixmap is None:
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
        local_point = self._to_display_point(event.position(), clamp=True)
        if local_point is None:
            return
        self._drag_current = local_point
        self.update()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self._drag_start is None or self._source_pixmap is None:
            super().mouseReleaseEvent(event)
            return
        local_point = self._to_display_point(event.position(), clamp=True)
        if local_point is None:
            self._drag_start = None
            self._drag_current = None
            self.update()
            super().mouseReleaseEvent(event)
            return
        rect = QRectF(self._drag_start, local_point).normalized()
        if rect.width() >= 10 and rect.height() >= 10:
            self._selected_rect = rect
            image_rect = self._to_image_rect(rect)
            if image_rect is not None:
                self.region_picked.emit(image_rect)
        else:
            if self._selected_rect is not None:
                self.clear_selection()
            else:
                sample = self._sample_average_color(QRectF(local_point.x() - 2, local_point.y() - 2, 4, 4))
                if sample is not None:
                    self.color_picked.emit(sample.name().upper())
        self._drag_start = None
        self._drag_current = None
        self.update()
        super().mouseReleaseEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        if self._scaled_pixmap is not None and self._display_rect is not None:
            painter.drawPixmap(
                int(self._display_rect.left()),
                int(self._display_rect.top()),
                self._scaled_pixmap,
            )
        if self._selected_rect is not None:
            painter.setPen(QPen(QColor("#1D4ED8"), 2))
            painter.setBrush(QColor(37, 99, 235, 26))
            painter.drawRoundedRect(self._selected_rect, 6, 6)
        if self._drag_start is not None and self._drag_current is not None:
            rect = QRectF(self._drag_start, self._drag_current).normalized()
            painter.setPen(QPen(QColor("#2563EB"), 2))
            painter.setBrush(QColor(37, 99, 235, 40))
            painter.drawRoundedRect(rect, 6, 6)
        painter.end()

    def _refresh_pixmap(self) -> None:
        if self._source_pixmap is None or self._source_pixmap.isNull():
            self._scaled_pixmap = None
            self._display_rect = None
            self.clear()
            return
        content_rect = self.contentsRect()
        scaled = self._source_pixmap.scaled(content_rect.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        left = content_rect.left() + (content_rect.width() - scaled.width()) / 2
        top = content_rect.top() + (content_rect.height() - scaled.height()) / 2
        self._scaled_pixmap = scaled
        self._display_rect = QRectF(left, top, scaled.width(), scaled.height())
        self.update()

    def _to_display_point(self, position: QPointF, clamp: bool = False) -> QPointF | None:
        if self._display_rect is None:
            return None
        if clamp:
            x_value = max(self._display_rect.left(), min(self._display_rect.right(), position.x()))
            y_value = max(self._display_rect.top(), min(self._display_rect.bottom(), position.y()))
            return QPointF(x_value, y_value)
        if not self._display_rect.contains(position):
            return None
        return QPointF(position.x(), position.y())

    def _sample_average_color(self, display_rect: QRectF) -> QColor | None:
        if self._display_rect is None or self._source_pixmap is None:
            return None
        x_scale = self._source_pixmap.width() / self._display_rect.width()
        y_scale = self._source_pixmap.height() / self._display_rect.height()
        left = max(0, min(self._source_pixmap.width() - 1, int((display_rect.left() - self._display_rect.left()) * x_scale)))
        top = max(0, min(self._source_pixmap.height() - 1, int((display_rect.top() - self._display_rect.top()) * y_scale)))
        right = max(left + 1, min(self._source_pixmap.width(), int(math.ceil((display_rect.right() - self._display_rect.left()) * x_scale))))
        bottom = max(top + 1, min(self._source_pixmap.height(), int(math.ceil((display_rect.bottom() - self._display_rect.top()) * y_scale))))
        image = self._source_pixmap.toImage()
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
        if self._display_rect is None or self._source_pixmap is None:
            return None
        x_scale = self._source_pixmap.width() / self._display_rect.width()
        y_scale = self._source_pixmap.height() / self._display_rect.height()
        left = max(0, min(self._source_pixmap.width() - 1, int((display_rect.left() - self._display_rect.left()) * x_scale)))
        top = max(0, min(self._source_pixmap.height() - 1, int((display_rect.top() - self._display_rect.top()) * y_scale)))
        right = max(left + 1, min(self._source_pixmap.width(), int(math.ceil((display_rect.right() - self._display_rect.left()) * x_scale))))
        bottom = max(top + 1, min(self._source_pixmap.height(), int(math.ceil((display_rect.bottom() - self._display_rect.top()) * y_scale))))
        return left, top, right, bottom


class PreviewColorCard(QFrame):
    copy_requested = Signal(object)
    add_requested = Signal(object)
    remove_requested = Signal(object)

    def __init__(self, color: ColorEntry) -> None:
        super().__init__()
        self.color = color
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet("background: #FFFFFF; border: 1px solid #CBD5E1; border-radius: 10px;")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        swatch = QFrame()
        swatch.setFixedSize(24, 24)
        swatch.setStyleSheet(
            f"background: {color.hex_code}; border: 1px solid #64748B; border-radius: 6px;"
        )
        layout.addWidget(swatch)
        label = QLabel(f"{color.hex_code}  {color.name}")
        label.setStyleSheet("color: #0F172A;")
        layout.addWidget(label, 1)
        remove_button = QPushButton("-")
        remove_button.setFixedWidth(28)
        remove_button.clicked.connect(lambda: self.remove_requested.emit(self.color))
        layout.addWidget(remove_button)

    def contextMenuEvent(self, event) -> None:  # noqa: N802
        menu = QMenu(self)
        copy_action = menu.addAction("Copy HEX")
        add_action = menu.addAction("Add to Cart")
        remove_action = menu.addAction("Remove")
        action = menu.exec(event.globalPos())
        if action is copy_action:
            self.copy_requested.emit(self.color)
        elif action is add_action:
            self.add_requested.emit(self.color)
        elif action is remove_action:
            self.remove_requested.emit(self.color)


class PdfExtractDialog(QDialog):
    def __init__(self, pdf_path: Path, materials_dir: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.pdf_path = pdf_path
        self.materials_dir = materials_dir
        self.saved_paths: list[Path] = []
        self.current_page_index = 0
        self.current_region: tuple[int, int, int, int] | None = None
        self.current_preview_palette: Palette | None = None
        self.current_preview_suffix = "preview"
        self.page_count = pdf_page_count(pdf_path)
        self.thumbnail_limit = 48

        self.setWindowTitle(f"PDF Extractor - {pdf_path.name}")
        self.resize(1420, 900)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(12, 12, 12, 12)
        root_layout.setSpacing(10)

        top_info = QLabel(
            "????????????????????????????????????????? materials/pdf_imports?"
        )
        top_info.setWordWrap(True)
        top_info.setStyleSheet("color: #475569;")
        root_layout.addWidget(top_info)

        body = QHBoxLayout()
        body.setSpacing(10)
        root_layout.addLayout(body, 1)

        self.page_list = QListWidget()
        self.page_list.setSelectionMode(QAbstractItemView.MultiSelection)
        self.page_list.setIconSize(QSize(84, 110))
        self.page_list.setMinimumWidth(220)
        self.page_list.currentItemChanged.connect(self.on_current_page_changed)
        body.addWidget(self.page_list)

        self.preview_label = PdfPreviewLabel()
        self.preview_label.color_picked.connect(self.on_color_picked)
        self.preview_label.region_picked.connect(self.on_region_picked)
        body.addWidget(self.preview_label, 1)

        side_panel = QWidget()
        side_layout = QVBoxLayout(side_panel)
        side_layout.setContentsMargins(0, 0, 0, 0)
        side_layout.setSpacing(8)
        body.addWidget(side_panel)
        side_panel.setMinimumWidth(340)

        jump_row = QHBoxLayout()
        jump_row.addWidget(QLabel("Page"))
        self.page_jump_input = QLineEdit("1")
        self.page_jump_input.setPlaceholderText("Page")
        jump_row.addWidget(self.page_jump_input, 1)
        jump_button = QPushButton("Go")
        jump_button.clicked.connect(self.jump_to_page)
        jump_row.addWidget(jump_button)
        side_layout.addLayout(jump_row)

        count_row = QHBoxLayout()
        count_row.addWidget(QLabel("Colors"))
        self.count_combo = QComboBox()
        self.count_combo.addItems([str(value) for value in range(3, 17)])
        self.count_combo.setCurrentText("5")
        count_row.addWidget(self.count_combo, 1)
        side_layout.addLayout(count_row)

        preview_page_button = QPushButton("Preview Current Page")
        preview_page_button.clicked.connect(self.preview_current_page_palette)
        side_layout.addWidget(preview_page_button)

        preview_combined_button = QPushButton("Preview Selected Pages")
        preview_combined_button.clicked.connect(self.preview_selected_pages_palette)
        side_layout.addWidget(preview_combined_button)

        preview_region_button = QPushButton("Preview Current Region")
        preview_region_button.clicked.connect(self.preview_current_region_palette)
        side_layout.addWidget(preview_region_button)

        preview_actions = QHBoxLayout()
        add_preview_button = QPushButton("Add Preview to Cart")
        add_preview_button.clicked.connect(self.add_preview_palette_to_cart)
        clear_preview_button = QPushButton("Clear Preview")
        clear_preview_button.clicked.connect(self.clear_preview_palette)
        preview_actions.addWidget(add_preview_button)
        preview_actions.addWidget(clear_preview_button)
        side_layout.addLayout(preview_actions)

        save_button = QPushButton("Save Preview to Materials")
        save_button.clicked.connect(self.save_current_preview_palette)
        side_layout.addWidget(save_button)

        self.region_label = QLabel("Region: none")
        self.region_label.setWordWrap(True)
        self.region_label.setStyleSheet("color: #475569;")
        side_layout.addWidget(self.region_label)

        self.saved_label = QLabel("Saved: 0")
        self.saved_label.setStyleSheet("font-weight: 700;")
        side_layout.addWidget(self.saved_label)

        self.info_label = QLabel("No extraction yet.")
        self.info_label.setWordWrap(True)
        self.info_label.setStyleSheet("color: #334155;")
        side_layout.addWidget(self.info_label)

        preview_title = QLabel("Preview Palette")
        preview_title.setStyleSheet("font-weight: 700;")
        side_layout.addWidget(preview_title)

        self.preview_palette_meta = QLabel("??????????????????????????")
        self.preview_palette_meta.setWordWrap(True)
        self.preview_palette_meta.setStyleSheet("color: #475569;")
        side_layout.addWidget(self.preview_palette_meta)

        self.preview_list = QListWidget()
        self.preview_list.setSelectionMode(QAbstractItemView.MultiSelection)
        self.preview_list.setMinimumHeight(280)
        side_layout.addWidget(self.preview_list, 1)

        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        side_layout.addWidget(close_button)

        self.populate_page_list()
        if self.page_list.count():
            self.page_list.setCurrentRow(0)

    def current_color_count(self) -> int:
        return int(self.count_combo.currentText())

    def populate_page_list(self) -> None:
        for page_index in range(self.page_count):
            item = QListWidgetItem(f"Page {page_index + 1}")
            item.setData(Qt.UserRole, page_index)
            if page_index < self.thumbnail_limit:
                try:
                    image = render_pdf_page(self.pdf_path, page_index=page_index, max_edge=180)
                    item.setIcon(QIcon(QPixmap.fromImage(image)))
                except Exception:
                    pass
            self.page_list.addItem(item)

    def selected_page_indices(self) -> list[int]:
        indices = sorted(
            {
                int(item.data(Qt.UserRole))
                for item in self.page_list.selectedItems()
                if item.data(Qt.UserRole) is not None
            }
        )
        if indices:
            return indices
        current = self.page_list.currentItem()
        if current is None:
            return []
        return [int(current.data(Qt.UserRole))]

    def on_current_page_changed(self, current: QListWidgetItem, _previous: QListWidgetItem) -> None:
        if current is None:
            return
        page_index = int(current.data(Qt.UserRole))
        self.current_page_index = page_index
        if current.icon().isNull():
            try:
                thumb = render_pdf_page(self.pdf_path, page_index=page_index, max_edge=180)
                current.setIcon(QIcon(QPixmap.fromImage(thumb)))
            except Exception:
                pass
        try:
            image = render_pdf_page(self.pdf_path, page_index=page_index, max_edge=1600)
        except Exception as exc:
            QMessageBox.warning(self, "PDF Preview Failed", str(exc))
            return
        self.preview_label.set_source_pixmap(QPixmap.fromImage(image))
        self.page_jump_input.setText(str(page_index + 1))
        self.current_region = None
        self.region_label.setText("Region: none")
        self.info_label.setText(f"Viewing page {page_index + 1} / {self.page_count}")

    def jump_to_page(self) -> None:
        try:
            page_number = int(self.page_jump_input.text())
        except ValueError:
            return
        page_number = max(1, min(self.page_count, page_number))
        self.page_list.setCurrentRow(page_number - 1)
        self.page_list.scrollToItem(self.page_list.item(page_number - 1))

    def preview_colors(self) -> list[ColorEntry]:
        if self.current_preview_palette is None:
            return []
        return self.current_preview_palette.colors

    def set_preview_palette(self, palette: Palette, suffix: str) -> None:
        self.current_preview_palette = palette
        self.current_preview_suffix = suffix
        self.refresh_preview_palette_widgets()

    def append_preview_palette(self, palette: Palette, suffix: str) -> None:
        if self.current_preview_palette is None or not self.current_preview_palette.colors:
            self.set_preview_palette(palette, suffix)
            return
        existing = {color.hex_code for color in self.current_preview_palette.colors}
        added = 0
        for color in palette.colors:
            if color.hex_code in existing:
                continue
            self.current_preview_palette.colors.append(ColorEntry(name=color.name, hex_code=color.hex_code))
            existing.add(color.hex_code)
            added += 1
        if added > 0:
            self.current_preview_palette.name = f"{self.pdf_path.stem} preview mix"
            self.current_preview_suffix = "preview_mix"
        self.refresh_preview_palette_widgets()

    def refresh_preview_palette_widgets(self) -> None:
        self.preview_list.clear()
        if self.current_preview_palette is None or not self.current_preview_palette.colors:
            self.preview_palette_meta.setText("??????????????????????????")
            return
        meta_parts = [f"{len(self.current_preview_palette.colors)} colors"]
        page_value = self.current_preview_palette.metadata.get("page")
        if page_value is not None:
            meta_parts.append(f"page {page_value}")
        self.preview_palette_meta.setText(" | ".join(meta_parts))
        for color in self.current_preview_palette.colors:
            item = QListWidgetItem()
            item.setData(Qt.UserRole, color)
            item.setSizeHint(QSize(0, 52))
            self.preview_list.addItem(item)
            card = PreviewColorCard(color)
            card.copy_requested.connect(self.copy_preview_color)
            card.add_requested.connect(self.add_preview_color_to_cart)
            card.remove_requested.connect(self.remove_preview_color)
            self.preview_list.setItemWidget(item, card)

    def clear_preview_palette(self) -> None:
        self.current_preview_palette = None
        self.current_preview_suffix = "preview"
        self.refresh_preview_palette_widgets()
        self.info_label.setText("Preview cleared.")

    def on_color_picked(self, hex_code: str) -> None:
        color = ColorEntry(name=f"Picked {len(self.preview_colors()) + 1}", hex_code=hex_code)
        palette = Palette(
            name=f"{self.pdf_path.stem} picked",
            colors=[color],
            source_path=self.pdf_path,
            source_format="pdf_picked",
        )
        palette.metadata["page"] = self.current_page_index + 1
        self.append_preview_palette(palette, "picked")
        self.info_label.setText(f"Added {hex_code} to preview")

    def on_region_picked(self, region: object) -> None:
        if not isinstance(region, tuple) or len(region) != 4:
            return
        self.current_region = region
        left, top, right, bottom = region
        self.region_label.setText(f"Region: x {left}-{right}, y {top}-{bottom}")
        self.info_label.setText("Region selected. Use region preview or grid preview, then save if needed.")

    def build_combined_palette(self, pages: list[int]) -> Palette:
        count = self.current_color_count()
        colors: list[ColorEntry] = []
        seen: set[str] = set()
        for page_index in pages:
            page_palette = load_pdf_palette(self.pdf_path, color_count=count, page_index=page_index)
            for color in page_palette.colors:
                if color.hex_code in seen:
                    continue
                seen.add(color.hex_code)
                colors.append(ColorEntry(name=f"P{page_index + 1} {color.name}", hex_code=color.hex_code))
        palette = Palette(
            name=f"{self.pdf_path.stem} pages",
            colors=colors,
            source_path=self.pdf_path,
            source_format="pdf_combined",
        )
        if len(pages) == 1:
            palette.metadata["page"] = pages[0] + 1
        return palette

    def preview_current_page_palette(self) -> None:
        palette = load_pdf_palette(self.pdf_path, color_count=self.current_color_count(), page_index=self.current_page_index)
        palette.name = f"{self.pdf_path.stem} p{self.current_page_index + 1}"
        self.append_preview_palette(palette, f"p{self.current_page_index + 1:03d}")
        self.info_label.setText(f"Added page {self.current_page_index + 1} colors to preview")

    def preview_selected_pages_palette(self) -> None:
        pages = self.selected_page_indices()
        if not pages:
            QMessageBox.information(self, "No Pages Selected", "Select one or more pages first.")
            return
        palette = self.build_combined_palette(pages)
        suffix = "pages_" + "-".join(str(page + 1) for page in pages[:6])
        self.append_preview_palette(palette, suffix)
        self.info_label.setText(f"Added {len(pages)} selected page(s) to preview")

    def preview_current_region_palette(self) -> None:
        if self.current_region is None:
            QMessageBox.information(self, "No Region Selected", "Drag on the current page to select a region first.")
            return
        palette = load_pdf_region_palette(
            self.pdf_path,
            page_index=self.current_page_index,
            crop_bounds=self.current_region,
            color_count=self.current_color_count(),
        )
        palette.name = f"{self.pdf_path.stem} p{self.current_page_index + 1} region"
        self.append_preview_palette(palette, f"p{self.current_page_index + 1:03d}_region")
        self.info_label.setText("Added current region colors to preview")

    def copy_preview_color(self, color: ColorEntry) -> None:
        QGuiApplication.clipboard().setText(color.hex_code)
        self.info_label.setText(f"Copied {color.hex_code}")

    def add_preview_color_to_cart(self, color: ColorEntry) -> None:
        parent = self.parent()
        if parent is None or not hasattr(parent, "selected_colors"):
            return
        selected_colors = getattr(parent, "selected_colors")
        existing = {item.hex_code for item in selected_colors}
        if color.hex_code not in existing:
            selected_colors.append(ColorEntry(name=color.name, hex_code=color.hex_code))
            if hasattr(parent, "refresh_cart"):
                parent.refresh_cart()
            if hasattr(parent, "current_palette") and getattr(parent, "current_palette") is not None and hasattr(parent, "render_palette_colors"):
                parent.render_palette_colors(parent.current_palette)
        if hasattr(parent, "statusBar"):
            parent.statusBar().showMessage(f"Added {color.hex_code} to cart", 2500)
        self.refresh_preview_palette_widgets()
        self.info_label.setText(f"Added {color.hex_code} to main cart")

    def add_preview_palette_to_cart(self) -> None:
        if self.current_preview_palette is None or not self.current_preview_palette.colors:
            QMessageBox.information(self, "No Preview", "Preview colors first.")
            return
        parent = self.parent()
        if parent is None or not hasattr(parent, "selected_colors"):
            return
        selected_colors = getattr(parent, "selected_colors")
        existing = {item.hex_code for item in selected_colors}
        added = 0
        for color in self.current_preview_palette.colors:
            if color.hex_code in existing:
                continue
            selected_colors.append(ColorEntry(name=color.name, hex_code=color.hex_code))
            existing.add(color.hex_code)
            added += 1
        if hasattr(parent, "refresh_cart"):
            parent.refresh_cart()
        if hasattr(parent, "current_palette") and getattr(parent, "current_palette") is not None and hasattr(parent, "render_palette_colors"):
            parent.render_palette_colors(parent.current_palette)
        self.refresh_preview_palette_widgets()
        self.info_label.setText(f"Added {added} preview color(s) to main cart")

    def remove_preview_color(self, color: ColorEntry) -> None:
        if self.current_preview_palette is None:
            return
        self.current_preview_palette.colors = [item for item in self.current_preview_palette.colors if item.hex_code != color.hex_code]
        self.refresh_preview_palette_widgets()
        self.info_label.setText(f"Removed {color.hex_code} from preview")

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

    def save_palette(self, palette: Palette, stem_suffix: str) -> Path:
        target_dir = self.materials_dir / "pdf_imports" / self.pdf_path.stem
        ensure_directory(target_dir)
        target = self.unique_target_path(target_dir / f"{self.pdf_path.stem}_{stem_suffix}.json")
        save_palette_json(palette, target)
        self.saved_paths.append(target)
        self.saved_label.setText(f"Saved: {len(self.saved_paths)}")
        self.info_label.setText(f"Saved palette: {target.name}")
        return target

    def save_current_preview_palette(self) -> None:
        if self.current_preview_palette is None or not self.current_preview_palette.colors:
            QMessageBox.information(self, "No Preview", "Preview a page, region, grid, or picked colors first.")
            return
        self.save_palette(self.current_preview_palette, self.current_preview_suffix)
