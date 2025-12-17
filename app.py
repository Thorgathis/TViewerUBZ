import sys
import zipfile
import os
import tempfile
from typing import List, Dict

from PyQt6.QtWidgets import (
    QApplication, QWidget, QListWidget, QLabel, QPushButton, QHBoxLayout,
    QVBoxLayout, QFileDialog, QMessageBox, QListWidgetItem, QScrollArea, QFrame,
    QInputDialog, QProgressDialog
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

    @staticmethod
    def create_from_folder(folder_path: str, output_path: str) -> 'UBZDocument':
        """Create a UBZ document from a folder containing SVG files"""
        files_dict = {}
        svg_files = []
        
        # Walk through the folder and collect all SVG files
        for root, dirs, files in os.walk(folder_path):
            for file in files:
                if file.lower().endswith('.svg'):
                    full_path = os.path.join(root, file)
                    # Create relative path from folder_path
                    rel_path = os.path.relpath(full_path, folder_path)
                    # Normalize path separators for zip
                    rel_path = rel_path.replace('\\', '/')
                    
                    with open(full_path, 'rb') as f:
                        files_dict[rel_path] = f.read()
                    
                    if 'thumb' not in file.lower() and 'thumbnail' not in file.lower():
                        svg_files.append(rel_path)
        
        svg_files.sort()
        
        # Create the UBZ file
        with zipfile.ZipFile(output_path, 'w', compression=zipfile.ZIP_DEFLATED) as z:
            for rel_path, data in files_dict.items():
                z.writestr(rel_path, data)
        
        # Return a UBZDocument instance
        return UBZDocument(output_path)


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
        open_folder_btn = QPushButton('Import Folder')
        open_folder_btn.clicked.connect(self.import_folder)
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
        row3 = make_row([open_btn, open_folder_btn])
        row4 = make_row([save_btn, overwrite_btn])

        left_layout = QVBoxLayout()
        left_layout.addWidget(self.list, 1)
        left_layout.addWidget(row1)
        left_layout.addWidget(row2)
        left_layout.addWidget(row3)
        left_layout.addWidget(row4)

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
                path = url.toLocalFile()
                if path.lower().endswith(".ubz") or os.path.isdir(path):
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event: QDropEvent):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith(".ubz"):
                self.load_file(path)
                break
            elif os.path.isdir(path):
                # Handle folder drop - convert to UBZ
                self._convert_dropped_folder(path)
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

    def import_folder(self):
        """Import a folder containing presentations and convert them to UBZ"""
        folder_path = QFileDialog.getExistingDirectory(self, 'Select Folder with Presentations')
        if not folder_path:
            return
        
        # Find all subdirectories that contain SVG files
        presentation_folders = []
        for root, dirs, files in os.walk(folder_path):
            svg_files = [f for f in files if f.lower().endswith('.svg')]
            if svg_files:
                presentation_folders.append(root)
        
        if not presentation_folders:
            QMessageBox.warning(self, 'No Presentations', 'No folders with SVG files found.')
            return
        
        # Ask where to save converted UBZ files
        output_dir = QFileDialog.getExistingDirectory(self, 'Select Output Directory for UBZ Files', folder_path)
        if not output_dir:
            return
        
        # Create progress dialog
        progress = QProgressDialog('Converting presentations to UBZ...', 'Cancel', 0, len(presentation_folders), self)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        
        converted_count = 0
        for i, pres_folder in enumerate(presentation_folders):
            if progress.wasCanceled():
                break
            
            # Generate output filename from folder name
            folder_name = os.path.basename(pres_folder)
            if not folder_name:  # Root folder
                folder_name = os.path.basename(os.path.dirname(pres_folder))
            
            # Create a unique output path
            output_filename = folder_name + '.ubz'
            output_path = os.path.join(output_dir, output_filename)
            
            # Handle duplicate names
            counter = 1
            while os.path.exists(output_path):
                output_filename = f'{folder_name}_{counter}.ubz'
                output_path = os.path.join(output_dir, output_filename)
                counter += 1
            
            try:
                UBZDocument.create_from_folder(pres_folder, output_path)
                converted_count += 1
            except Exception as e:
                QMessageBox.warning(self, 'Conversion Error', f'Failed to convert {pres_folder}: {e}')
            
            progress.setValue(i + 1)
        
        progress.close()
        
        if converted_count > 0:
            msg = f'Successfully converted {converted_count} presentation(s) to UBZ format.'
            QMessageBox.information(self, 'Import Complete', msg)
            
            # Ask if user wants to open one of the converted files
            reply = QMessageBox.question(self, 'Open File', 'Do you want to open one of the converted files?')
            if reply == QMessageBox.StandardButton.Yes:
                path, _ = QFileDialog.getOpenFileName(self, 'Open UBZ file', output_dir, 'UBZ Files (*.ubz);;All files (*)')
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

    def _convert_dropped_folder(self, folder_path: str):
        """Convert a dropped folder to UBZ"""
        # Check if folder contains SVG files
        has_svgs = False
        for root, dirs, files in os.walk(folder_path):
            if any(f.lower().endswith('.svg') for f in files):
                has_svgs = True
                break
        
        if not has_svgs:
            QMessageBox.warning(self, 'No SVG Files', 'The dropped folder does not contain any SVG files.')
            return
        
        # Generate output filename
        folder_name = os.path.basename(folder_path)
        parent_dir = os.path.dirname(folder_path)
        output_filename = folder_name + '.ubz'
        output_path = os.path.join(parent_dir, output_filename)
        
        # Handle duplicate names
        counter = 1
        while os.path.exists(output_path):
            output_filename = f'{folder_name}_{counter}.ubz'
            output_path = os.path.join(parent_dir, output_filename)
            counter += 1
        
        try:
            self.doc = UBZDocument.create_from_folder(folder_path, output_path)
            self.current_scale = 1.0
            self.populate_page_list()
            QMessageBox.information(self, 'Conversion Complete', f'Folder converted to: {output_path}')
        except Exception as e:
            QMessageBox.critical(self, 'Conversion Error', f'Failed to convert folder: {e}')


if __name__ == '__main__':
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())
