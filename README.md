# SAIN DTF Print Engine

Windows desktop app for personal DTF workflows (Epson ET-8550 converted to DTF ink) with local-only processing.

## Features

- Drag/drop PNG with transparency.
- White underbase generated from alpha.
- White choke inward (default 2px).
- White density slider (0-100%).
- Expand/spread toggle.
- Feather edge toggle.
- Mirror toggle for transfer printing.
- Shirt color preview: white, black, red, blue, gray.
- One-click export folder with:
  - `white_layer.png`
  - `color_layer.png`
  - `preview.png`
  - `mirrored_print_ready.png`
- Phase 2 print pipeline module:
  - Detect installed printers.
  - Prioritize Epson ET-8550 in list if found.
  - Send print-ready PNG to Windows print system.
- Error logging to `error.log`.

## Project Structure

- `main.py` - full desktop app (UI + processing + printer handoff)
- `requirements.txt` - dependencies
- `start.bat` - run app on Windows
- `build_exe.bat` - build standalone EXE using PyInstaller
- `sample_output/` - output folder placeholder

## Exact Run Steps (Windows)

1. Install Python 3.10+.
2. Open Command Prompt in project folder.
3. Run:

```bat
start.bat
```

This creates `venv`, installs dependencies, and launches the app.

## Build EXE (Windows)

```bat
build_exe.bat
```

Generated executable will be in `dist/SAIN DTF Print Engine/`.

## Usage

1. Launch app.
2. Drag/drop a transparent PNG or click **Open PNG**.
3. Tune white choke/density and toggles.
4. Click **Process Preview**.
5. Click **One-click Export Folder** and choose a destination.
6. (Optional) In **Phase 2 Print Pipeline**, choose printer and click **Send print-ready PNG to printer**.

## Notes

- Local-only: no cloud calls.
- Printing handoff is Windows-only (`pywin32` path).
- Advanced white-channel RIP bridge is intentionally isolated for future module expansion.
