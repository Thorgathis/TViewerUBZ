import sys
import zipfile
import os
import tempfile
from typing import List, Dict

from PyQt6.QtWidgets import (
    QApplication, QWidget, QListWidget, QLabel, QPushButton, QHBoxLayout,
    QVBoxLayout, QFileDialog, QMessageBox, QListWidgetItem, QScrollArea, QFrame
)
from PyQt6.QtGui import QPixmap, QPainter, QDragEnterEvent, QDropEvent
from PyQt6.QtCore import Qt
from PyQt6.QtSvg import QSvgRenderer

class UBZDocument:
    def __init__(self, path: str):
        self.path = path
        self.zip = zipfile.ZipFile(path, 'r')
        self.files: Dict[str, bytes] = {zi.filename: self.zip.read(zi) for zi in self.zip.infolist()}
        self.zip.close()
        self.page_files = self._find_page_svgs()

    def _find_page_svgs(self) -> List[str]:
        svgs = [name for name in self.files.keys() if name.lower().endswith(".svg")]
        svgs = [s for s in svgs if 'thumb' not in s.lower() and 'thumbnail' not in s.lower()]
        svgs.sort()
        return svgs

    def get_svg_bytes(self, name: str) -> bytes:
        return self.files[name]

    def delete_pages(self, indices: List[int]):
        indices = sorted(indices, reverse=True)
        for i in indices:
            if 0 <= i < len(self.page_files):
                name = self.page_files.pop(i)
                if name in self.files:
                    del self.files[name]

    def save(self, out_path: str, overwrite: bool = False):
        with zipfile.ZipFile(out_path, 'w', compression=zipfile.ZIP_DEFLATED) as z:
            for name in self.page_files:
                z.writestr(name, self.files[name])
            for name, data in self.files.items():
                if name in self.page_files:
                    continue
                z.writestr(name, data)
        if overwrite:
            os.replace(out_path, self.path)


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('UBZ TViewer')
        self.resize(1200, 800)

        self.doc: UBZDocument = None
        self.current_scale = 1.0

        self.setAcceptDrops(True)

        self.list = QListWidget()
        self.list.setMinimumWidth(260)
        self.list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.list.currentRowChanged.connect(self.on_page_selected)

        zoom_in_btn = QPushButton('Zoom +')
        zoom_in_btn.clicked.connect(lambda: self.adjust_zoom(1.25))
        zoom_out_btn = QPushButton('Zoom -')
        zoom_out_btn.clicked.connect(lambda: self.adjust_zoom(0.8))
        fit_btn = QPushButton('Fit')
        fit_btn.clicked.connect(self.fit_to_window)

        prev_btn = QPushButton('◀ Prev')
        prev_btn.clicked.connect(self.prev_page)
        next_btn = QPushButton('Next ▶')
        next_btn.clicked.connect(self.next_page)
        del_btn = QPushButton('Delete')
        del_btn.clicked.connect(self.delete_selected)

        open_btn = QPushButton('Open')
        open_btn.clicked.connect(self.open_file)
        save_btn = QPushButton('Save As')
        save_btn.clicked.connect(self.save_as)
        overwrite_btn = QPushButton('Overwrite')
        overwrite_btn.clicked.connect(self.save_overwrite)

        def make_row(buttons):
            layout = QHBoxLayout()
            for b in buttons:
                layout.addWidget(b)
            frame = QFrame()
            frame.setLayout(layout)
            return frame

        row1 = make_row([zoom_in_btn, zoom_out_btn, fit_btn])
        row2 = make_row([prev_btn, next_btn, del_btn])
        row3 = make_row([open_btn, save_btn, overwrite_btn])

        left_layout = QVBoxLayout()
        left_layout.addWidget(self.list, 1)
        left_layout.addWidget(row1)
        left_layout.addWidget(row2)
        left_layout.addWidget(row3)

        self.preview_label = QLabel('Preview')
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setScaledContents(False)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setWidget(self.preview_label)

        main_layout = QHBoxLayout()
        main_layout.addLayout(left_layout, 0)
        main_layout.addWidget(self.scroll, 1)
        self.setLayout(main_layout)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.toLocalFile().lower().endswith(".ubz"):
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event: QDropEvent):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith(".ubz"):
                self.load_file(path)
                break

    def load_file(self, path: str):
        try:
            self.doc = UBZDocument(path)
        except Exception as e:
            QMessageBox.critical(self, 'Error', f'Failed to open file: {e}')
            return
        self.current_scale = 1.0
        self.populate_page_list()

    def open_file(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Open UBZ file', '', 'UBZ Files (*.ubz);;All files (*)')
        if path:
            self.load_file(path)

    def populate_page_list(self):
        self.list.clear()
        if not self.doc:
            return
        for i, svgname in enumerate(self.doc.page_files):
            item = QListWidgetItem(f'{i+1}: {os.path.basename(svgname)}')
            self.list.addItem(item)
        if self.list.count() > 0:
            self.list.setCurrentRow(0)

    def on_page_selected(self, idx: int):
        if idx < 0 or not self.doc:
            self.preview_label.setText('Preview')
            return
        svgname = self.doc.page_files[idx]
        try:
            svg_bytes = self.doc.get_svg_bytes(svgname)
            pix = self._pixmap_from_svg_bytes(svg_bytes)
            if pix:
                w = int(pix.width() * self.current_scale)
                h = int(pix.height() * self.current_scale)
                scaled = pix.scaled(w, h, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                self.preview_label.setPixmap(scaled)
                self.preview_label.resize(scaled.size())
            else:
                self.preview_label.setText('Cannot render SVG (missing QtSvg)')
        except Exception as e:
            self.preview_label.setText(f'Error rendering: {e}')

    def delete_selected(self):
        if not self.doc:
            return
        rows = sorted([r.row() for r in self.list.selectedIndexes()])
        if not rows:
            return
        confirm = QMessageBox.question(self, 'Confirm', f'Delete {len(rows)} selected page(s)?')
        if confirm != QMessageBox.StandardButton.Yes:
            return
        self.doc.delete_pages(rows)
        self.populate_page_list()

    def save_as(self):
        if not self.doc:
            return
        outpath, _ = QFileDialog.getSaveFileName(self, 'Save UBZ As', os.path.splitext(self.doc.path)[0] + '_modified.ubz', 'UBZ Files (*.ubz);;All files (*)')
        if not outpath:
            return
        try:
            self.doc.save(outpath, overwrite=False)
            QMessageBox.information(self, 'Saved', f'Saved to {outpath}')
        except Exception as e:
            QMessageBox.critical(self, 'Error', f'Failed to save file: {e}')

    def save_overwrite(self):
        if not self.doc:
            return
        confirm = QMessageBox.question(self, 'Confirm Overwrite', f'Overwrite the original file: {self.doc.path}?')
        if confirm != QMessageBox.StandardButton.Yes:
            return
        try:
            fd, tmp = tempfile.mkstemp(suffix='.ubz')
            os.close(fd)
            self.doc.save(tmp, overwrite=False)
            os.replace(tmp, self.doc.path)
            QMessageBox.information(self, 'Saved', f'Overwrote original file: {self.doc.path}')
        except Exception as e:
            QMessageBox.critical(self, 'Error', f'Failed to overwrite file: {e}')

    def _pixmap_from_svg_bytes(self, data: bytes) -> QPixmap:
        if QSvgRenderer is None:
            return None
        renderer = QSvgRenderer(data)
        svg_size = renderer.defaultSize()
        if not svg_size.isValid():
            svg_size.setWidth(800)
            svg_size.setHeight(600)
        pix = QPixmap(svg_size)
        pix.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pix)
        renderer.render(painter)
        painter.end()
        return pix

    def adjust_zoom(self, factor: float):
        self.current_scale *= factor
        self.on_page_selected(self.list.currentRow())

    def fit_to_window(self):
        if not self.doc or self.list.currentRow() < 0:
            return
        svgname = self.doc.page_files[self.list.currentRow()]
        svg_bytes = self.doc.get_svg_bytes(svgname)
        pix = self._pixmap_from_svg_bytes(svg_bytes)
        if not pix:
            return
        area_size = self.scroll.viewport().size()
        scaled = pix.scaled(area_size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self.preview_label.setPixmap(scaled)
        self.preview_label.resize(scaled.size())

    def prev_page(self):
        row = self.list.currentRow()
        if row > 0:
            self.list.setCurrentRow(row - 1)

    def next_page(self):
        row = self.list.currentRow()
        if row < self.list.count() - 1:
            self.list.setCurrentRow(row + 1)


if __name__ == '__main__':
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())
