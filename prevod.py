# -*- coding: utf-8 -*-
import subprocess
from pathlib import Path

INKSCAPE_PATH = Path("inkscape_portable/InkscapePortable.exe")  # cesta k portable Inkscape

# Cesta k adresáři s SVG soubory
svg_slozka = Path("vystup")
vystup_zaklad = Path("vystup_png")
vystup_zaklad.mkdir(exist_ok=True)

# Rekurzivně projdeme všechny SVG soubory
for svg_soubor in svg_slozka.rglob("*.svg"):
    rel_path = svg_soubor.relative_to(svg_slozka).with_suffix(".png")
    vystup_png = vystup_zaklad / rel_path
    vystup_png.parent.mkdir(parents=True, exist_ok=True)

    try:
        subprocess.run([
            str(INKSCAPE_PATH),
            str(svg_soubor),
            "--export-type=png",
            f"--export-filename={vystup_png}",
            "--export-dpi=300"
        ], check=True)
        print(f"Převod hotov: {svg_soubor} -> {vystup_png}")
    except subprocess.CalledProcessError as e:
        print(f"Chyba při převodu {svg_soubor}: {e}")

print("Hotovo!")
