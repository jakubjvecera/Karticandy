# -*- coding: utf-8 -*-
import subprocess
from pathlib import Path

# Cesta k adresáøi s SVG soubory
svg_slozka = Path("vystup")

# Pro každou složku vzácnosti (bezna, vzacna, atd.)
for vzacnost in svg_slozka.iterdir():
    if vzacnost.is_dir():
        # výstupní složka pro PNG
        vystup_slozka = Path("vystup_png") / vzacnost.name
        vystup_slozka.mkdir(parents=True, exist_ok=True)

        # všechny SVG v této složce
        for svg_soubor in vzacnost.glob("*.svg"):
            vystup_png = vystup_slozka / svg_soubor.with_suffix(".png").name

            subprocess.run([
                "inkscape",
                str(svg_soubor),
                "--export-type=png",
                f"--export-filename={vystup_png}",
                "--export-dpi=300"
            ], check=True)

            print(f"Prevedeno: {svg_soubor} -> {vystup_png}")

print("? Hotovo")



