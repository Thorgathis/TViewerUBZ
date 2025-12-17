# TViewer UBZ

A PyQt6-based viewer and editor for UBZ presentation files.

## Features

- **Open UBZ Files**: View and navigate through UBZ presentation files
- **Folder Import**: Import entire folders with nested presentations and convert them to UBZ format
- **Drag & Drop**: Drag and drop both UBZ files and folders for quick access
- **Page Management**: Delete unwanted pages from presentations
- **Zoom Controls**: Zoom in, zoom out, and fit to window
- **Save Options**: Save as new file or overwrite original

## Installation

```bash
pip install -r requirements.txt
```

## Usage

```bash
python app.py
```

### Importing Folders

1. Click "Import Folder" button
2. Select a folder containing presentations (can have multiple nested folders)
3. Select output directory for converted UBZ files
4. The application will convert all folders containing SVG files to UBZ format
5. Optionally open one of the converted files to start editing

### Drag & Drop

- Drag a UBZ file to open it immediately
- Drag a folder to convert it to UBZ and open it

### Editing

- Navigate through pages using Prev/Next buttons or by clicking in the list
- Select multiple pages and delete them
- Save your changes as a new file or overwrite the original

## UBZ Format

UBZ files are ZIP archives containing SVG files representing presentation pages. The application automatically finds and organizes SVG files (excluding thumbnails) within the archive.
