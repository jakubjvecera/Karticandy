# -*- coding: utf-8 -*-
import subprocess
from pathlib import Path
import sys

# --- Získání cesty k projektu z argumentu ---
if len(sys.argv) < 2:
    print("Chyba: Nebyla předána cesta k projektu.")
    sys.exit(1)

PROJECT_PATH = Path(sys.argv[1])

# --- Najdi Inkscape (portable) ---
if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys.executable).parent
else:
    BASE_DIR = Path(__file__).parent

INKSCAPE_PATH = BASE_DIR / "inkscape_portable/App/Inkscape/bin/inkscape.exe"
if not INKSCAPE_PATH.exists():
    INKSCAPE_PATH = BASE_DIR / "inkscape_portable/InkscapePortable.exe"
if not INKSCAPE_PATH.exists():
    raise FileNotFoundError(f"Inkscape nebyl nalezen: {INKSCAPE_PATH}")

# --- Cesty ke složkám ---
SVG_ORIGINAL_ROOT = PROJECT_PATH / "vystup" / "vystup_svg"
SVG_EDITED_ROOT = PROJECT_PATH / "vystup" / "vystup_editedsvg"
OUTPUT_PNG_ROOT = PROJECT_PATH / "vystup" / "vystup_png"

OUTPUT_PNG_ROOT.mkdir(exist_ok=True)

# --- Kontrola chybějících souborů ---
if not SVG_ORIGINAL_ROOT.exists():
    print(f"Chyba: Zdrojová složka s originálními SVG neexistuje: {SVG_ORIGINAL_ROOT}")
    sys.exit(1)

original_files = {p.relative_to(SVG_ORIGINAL_ROOT) for p in SVG_ORIGINAL_ROOT.rglob("*.svg")}
edited_files = {p.relative_to(SVG_EDITED_ROOT) for p in SVG_EDITED_ROOT.rglob("*.svg")} if SVG_EDITED_ROOT.exists() else set()

missing_files = original_files - edited_files

if missing_files:
    print("Info: Následující soubory nebyly upraveny, použije se původní verze:")
    for f in sorted(missing_files):
        print(f" - {f}")
    print("-" * 60)

# --- Převod pouze upravených SVG souborů ---
if not edited_files:
    print(f"Info: Složka upravených karet '{SVG_EDITED_ROOT.name}' je prázdná nebo neexistuje. Budou převedeny původní verze.")
else:
    for svg_file in SVG_EDITED_ROOT.rglob("*.svg"):
        relative_path = svg_file.relative_to(SVG_EDITED_ROOT)
        output_png_path = (OUTPUT_PNG_ROOT / relative_path).with_suffix(".png")
        output_png_path.parent.mkdir(parents=True, exist_ok=True)

        print(f"Zpracovávám (upravený): {relative_path}")
        try:
            subprocess.run([str(INKSCAPE_PATH), str(svg_file), "--export-type=png", f"--export-filename={output_png_path}", "--export-dpi=300"], check=True, capture_output=True, text=True, encoding='utf-8')
        except subprocess.CalledProcessError as e:
            print(f"Chyba: Nepodařilo se převést {svg_file.name}: {e.stderr}")

# --- Převod neupravených SVG souborů (ty, které chybí v 'vystup_editedsvg') ---
if missing_files:
    print("\nInfo: Převádím neupravené (původní) soubory...")
    output_unedited_root = OUTPUT_PNG_ROOT / "unedited"
    output_unedited_root.mkdir(exist_ok=True)

    for missing_file_rel_path in sorted(missing_files):
        svg_file = SVG_ORIGINAL_ROOT / missing_file_rel_path
        output_png_path = (output_unedited_root / missing_file_rel_path).with_suffix(".png")
        output_png_path.parent.mkdir(parents=True, exist_ok=True)

        print(f"Zpracovávám (původní): {missing_file_rel_path}")
        try:
            subprocess.run([str(INKSCAPE_PATH), str(svg_file), "--export-type=png", f"--export-filename={output_png_path}", "--export-dpi=300"], check=True, capture_output=True, text=True, encoding='utf-8')
        except subprocess.CalledProcessError as e:
            print(f"Chyba: Nepodařilo se převést {svg_file.name}: {e.stderr}")

print("Hotovo!")
