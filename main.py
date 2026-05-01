import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

import cv2
import numpy as np
from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QDragEnterEvent, QDropEvent, QImage, QPixmap
from PySide6.QtPrintSupport import QPrinterInfo
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

APP_NAME = "SAIN DTF Print Engine"
LOG_FILE = "error.log"


@dataclass
class ProcessedLayers:
    white_layer: Image.Image
    color_layer: Image.Image
    preview: Image.Image
    mirrored_print_ready: Image.Image


class ImageProcessor:
    @staticmethod
    def process(
        src: Image.Image,
        choke_px: int,
        white_density: int,
        expand: bool,
        feather: bool,
        mirror: bool,
        shirt_rgb: tuple[int, int, int],
    ) -> ProcessedLayers:
        rgba = src.convert("RGBA")
        arr = np.array(rgba)
        alpha = arr[:, :, 3]

        kernel_size = max(1, choke_px * 2 + 1)
        kernel = np.ones((kernel_size, kernel_size), np.uint8)

        white_mask = alpha.copy()
        white_mask = cv2.erode(white_mask, kernel, iterations=1)

        if expand:
            expand_kernel = np.ones((3, 3), np.uint8)
            white_mask = cv2.dilate(white_mask, expand_kernel, iterations=1)

        if feather:
            white_mask = cv2.GaussianBlur(white_mask, (5, 5), 0)

        density_scale = max(0, min(white_density, 100)) / 100.0
        white_alpha = np.clip((white_mask.astype(np.float32) * density_scale), 0, 255).astype(np.uint8)

        white_rgba = np.zeros_like(arr)
        white_rgba[:, :, :3] = 255
        white_rgba[:, :, 3] = white_alpha
        white_layer = Image.fromarray(white_rgba, "RGBA")

        color_layer = rgba.copy()
        if mirror:
            white_layer = white_layer.transpose(Image.FLIP_LEFT_RIGHT)
            color_layer = color_layer.transpose(Image.FLIP_LEFT_RIGHT)

        mirrored_print_ready = Image.alpha_composite(white_layer, color_layer)

        preview = ImageProcessor._shirt_preview(color_layer, shirt_rgb)
        return ProcessedLayers(
            white_layer=white_layer,
            color_layer=color_layer,
            preview=preview,
            mirrored_print_ready=mirrored_print_ready,
        )

    @staticmethod
    def _shirt_preview(color_layer: Image.Image, shirt_rgb: tuple[int, int, int]) -> Image.Image:
        w, h = color_layer.size
        shirt = Image.new("RGBA", (w, h), shirt_rgb + (255,))
        return Image.alpha_composite(shirt, color_layer)


class DropLabel(QLabel):
    def __init__(self, callback):
        super().__init__("Drag and drop PNG here\n(or click Open PNG)")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setAcceptDrops(True)
        self.setFrameStyle(QFrame.Shape.StyledPanel | QFrame.Shadow.Sunken)
        self.callback = callback

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        urls = event.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            if path.lower().endswith(".png"):
                self.callback(path)


class MainWindow(QMainWindow):
    SHIRT_COLORS: Dict[str, tuple[int, int, int]] = {
        "white": (255, 255, 255),
        "black": (25, 25, 25),
        "red": (180, 30, 30),
        "blue": (35, 80, 180),
        "gray": (130, 130, 130),
    }

    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1100, 700)
        self.src_image: Optional[Image.Image] = None
        self.processed: Optional[ProcessedLayers] = None
        self.src_path: Optional[Path] = None
        self._build_ui()
        self.refresh_printer_list()

    def _build_ui(self):
        central = QWidget()
        layout = QHBoxLayout(central)

        controls = QVBoxLayout()
        self.drop = DropLabel(self.load_png)
        controls.addWidget(self.drop)

        open_btn = QPushButton("Open PNG")
        open_btn.clicked.connect(self.open_file_dialog)
        controls.addWidget(open_btn)

        form_box = QGroupBox("Processing")
        form = QFormLayout(form_box)

        self.choke = QSlider(Qt.Orientation.Horizontal)
        self.choke.setRange(0, 10)
        self.choke.setValue(2)
        form.addRow("White choke (px)", self.choke)

        self.density = QSlider(Qt.Orientation.Horizontal)
        self.density.setRange(0, 100)
        self.density.setValue(100)
        form.addRow("White density %", self.density)

        self.expand = QCheckBox("Expand/spread")
        self.feather = QCheckBox("Feather edge")
        self.mirror = QCheckBox("Mirror image")
        self.mirror.setChecked(True)
        form.addRow(self.expand)
        form.addRow(self.feather)
        form.addRow(self.mirror)

        self.shirt_color = QComboBox()
        self.shirt_color.addItems(self.SHIRT_COLORS.keys())
        self.shirt_color.setCurrentText("black")
        form.addRow("Shirt preview color", self.shirt_color)

        controls.addWidget(form_box)

        run_btn = QPushButton("Process Preview")
        run_btn.clicked.connect(self.process_preview)
        controls.addWidget(run_btn)

        export_btn = QPushButton("One-click Export Folder")
        export_btn.clicked.connect(self.export_layers)
        controls.addWidget(export_btn)

        print_box = QGroupBox("Phase 2 Print Pipeline")
        print_layout = QFormLayout(print_box)
        self.printers = QComboBox()
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh_printer_list)
        print_layout.addRow("Detected printers", self.printers)
        print_layout.addRow(refresh)

        send_btn = QPushButton("Send print-ready PNG to printer")
        send_btn.clicked.connect(self.send_to_printer)
        print_layout.addRow(send_btn)
        controls.addWidget(print_box)
        controls.addStretch()

        self.preview_label = QLabel("Preview")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumWidth(600)
        self.preview_label.setFrameStyle(QFrame.Shape.Box)

        layout.addLayout(controls, 1)
        layout.addWidget(self.preview_label, 2)

        self.setCentralWidget(central)

        menu = self.menuBar().addMenu("File")
        open_action = QAction("Open PNG", self)
        open_action.triggered.connect(self.open_file_dialog)
        menu.addAction(open_action)

    def open_file_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open PNG", "", "PNG Files (*.png)")
        if path:
            self.load_png(path)

    def load_png(self, path: str):
        try:
            image = Image.open(path)
            if image.mode not in ["RGBA", "LA"]:
                image = image.convert("RGBA")
            self.src_image = image
            self.src_path = Path(path)
            self.drop.setText(f"Loaded: {Path(path).name}")
            self.process_preview()
        except Exception as exc:
            logging.exception("Failed loading PNG")
            QMessageBox.critical(self, "Load error", str(exc))

    def process_preview(self):
        if not self.src_image:
            QMessageBox.information(self, APP_NAME, "Load a PNG first.")
            return
        try:
            self.processed = ImageProcessor.process(
                src=self.src_image,
                choke_px=self.choke.value(),
                white_density=self.density.value(),
                expand=self.expand.isChecked(),
                feather=self.feather.isChecked(),
                mirror=self.mirror.isChecked(),
                shirt_rgb=self.SHIRT_COLORS[self.shirt_color.currentText()],
            )
            self._update_preview(self.processed.preview)
        except Exception as exc:
            logging.exception("Processing failed")
            QMessageBox.critical(self, "Processing error", str(exc))

    def _update_preview(self, img: Image.Image):
        rgb = img.convert("RGB")
        arr = np.array(rgb)
        h, w, ch = arr.shape
        qimg = QImage(arr.data, w, h, w * ch, QImage.Format.Format_RGB888)
        pix = QPixmap.fromImage(qimg)
        self.preview_label.setPixmap(pix.scaled(
            self.preview_label.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
        ))

    def export_layers(self):
        if not self.processed:
            self.process_preview()
        if not self.processed:
            return

        base_dir = QFileDialog.getExistingDirectory(self, "Select export folder")
        if not base_dir:
            return

        stem = self.src_path.stem if self.src_path else "design"
        out_dir = Path(base_dir) / f"{stem}_export"
        out_dir.mkdir(parents=True, exist_ok=True)

        self.processed.white_layer.save(out_dir / "white_layer.png")
        self.processed.color_layer.save(out_dir / "color_layer.png")
        self.processed.preview.save(out_dir / "preview.png")
        self.processed.mirrored_print_ready.save(out_dir / "mirrored_print_ready.png")

        QMessageBox.information(self, APP_NAME, f"Exported:\n{out_dir}")

    def refresh_printer_list(self):
        self.printers.clear()
        printers = [p.printerName() for p in QPrinterInfo.availablePrinters()]
        et = [p for p in printers if "ET-8550" in p.upper()]
        ordered = et + [p for p in printers if p not in et]
        if not ordered:
            self.printers.addItem("No printers found")
        else:
            self.printers.addItems(ordered)

    def send_to_printer(self):
        if not self.processed:
            QMessageBox.information(self, APP_NAME, "Process an image first.")
            return
        printer = self.printers.currentText()
        if not printer or printer == "No printers found":
            QMessageBox.warning(self, APP_NAME, "No printer available.")
            return

        tmp = Path.cwd() / "_temp_print_ready.png"
        self.processed.mirrored_print_ready.save(tmp)

        try:
            if os.name == "nt":
                import win32api

                win32api.ShellExecute(0, "printto", str(tmp), f'"{printer}"', ".", 0)
                QMessageBox.information(self, APP_NAME, f"Sent to printer: {printer}")
            else:
                QMessageBox.warning(
                    self,
                    APP_NAME,
                    "Print handoff is Windows-only. File was saved as _temp_print_ready.png",
                )
        except Exception as exc:
            logging.exception("Printing failed")
            QMessageBox.critical(self, "Print error", str(exc))


def configure_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.FileHandler(LOG_FILE, encoding="utf-8"), logging.StreamHandler(sys.stdout)],
    )


def main():
    configure_logging()
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
