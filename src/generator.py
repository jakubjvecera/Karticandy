# -*- coding: utf-8 -*-
import pandas as pd
from pathlib import Path
import xml.etree.ElementTree as ET
import unicodedata
import re
import sys
import json

# ---------------- Funkce ----------------

def odstranit_diakritiku(text):
    return ''.join(
        c for c in unicodedata.normalize('NFKD', str(text))
        if not unicodedata.combining(c)
    )

def set_display(elem, value):
    styl = elem.get("style", "")
    novy_styl = ";".join(
        s for s in styl.split(";") if not s.strip().startswith("display:")
    )
    elem.set("style", (novy_styl + f";display:{value}").strip(";"))

def najdi_g(root, name, namespaces):
    for attr in ["id", "inkscape:label", "sodipodi:label", "label"]:
        elem = root.find(f".//svg:g[@{attr}='{name}']", namespaces)
        if elem is not None:
            return elem
    return None

# ---------------- Cesta k projektu ----------------
if len(sys.argv) < 2:
    print("Nebyla předána cesta k projektu.")
    sys.exit(1)

project_path = Path(sys.argv[1])
data_dir = project_path / "data"
output_dir = project_path / "vystup"
output_dir.mkdir(exist_ok=True)

# ---------------- Výstupní složka pro SVG ----------------
vystup_svg_dir = output_dir / "vystup_svg"
vystup_svg_dir.mkdir(exist_ok=True)

config_path = project_path / "config.json"
if not config_path.exists():
    print(f"Chybí config soubor: {config_path}")
    sys.exit(1)

with open(config_path, "r", encoding="utf-8") as f:
    config = json.load(f)

excel_file = data_dir / config["zdroje"].get("excel", "")
sablona_file = data_dir / config["zdroje"].get("sablona", "")

if not excel_file.exists():
    print(f"Excel soubor nenalezen: {excel_file}")
    sys.exit(1)

if not sablona_file.exists():
    print(f"Šablona nenalezena: {sablona_file}")
    sys.exit(1)

# ---------------- Načtení dat z Excelu ----------------
try:
    df = pd.read_excel(excel_file)
except Exception as e:
    print(f"Chyba při načítání Excelu: {e}")
    sys.exit(1)

# ---------------- SVG nastavení ----------------
namespaces = {
    'svg': 'http://www.w3.org/2000/svg',
    'inkscape': 'http://www.inkscape.org/namespaces/inkscape',
    'sodipodi': 'http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd'
}

# ---------------- Zpracování karet ----------------
for index, row in df.iterrows():
    if "Vzacnost" not in row or pd.isna(row["Vzacnost"]):
        print(f"Karta na řádku {index+2} nemá vyplněnou vzácnost.")
        continue
    if "Nazev" not in row or pd.isna(row["Nazev"]):
        print(f"Karta na řádku {index+2} nemá vyplněný název.")
        continue
    if "Kategorie" not in row or pd.isna(row["Kategorie"]):
        print(f"Karta na řádku {index+2} nemá vyplněnou kategorii.")
        continue

    # Načti šablonu
    try:
        tree = ET.parse(sablona_file)
        root = tree.getroot()
    except ET.ParseError as e:
        print(f"Chyba při načítání šablony {sablona_file}: {e}")
        continue

    # Nahrazení placeholderů podle názvů sloupců
    svg_text = ET.tostring(root, encoding="unicode")
    for col in df.columns:
        hodnota = row[col]
        if pd.isna(hodnota):
            hodnota = ""
        elif isinstance(hodnota, float) and hodnota.is_integer():
            hodnota = int(hodnota)
        hodnota = str(hodnota)

        svg_text = re.sub(rf">\s*{re.escape(col)}\s*<", f">{hodnota}<", svg_text)

    root = ET.fromstring(svg_text)

    # --- Kategorie ---
    kategorie_root = najdi_g(root, "Kategorie", namespaces)
    if kategorie_root is not None:
        aktualni_kategorie = str(row["Kategorie"]).strip()
        for podskupina in kategorie_root.findall(".//svg:g", namespaces):
            set_display(podskupina, "none")
        cilova = najdi_g(kategorie_root, aktualni_kategorie, namespaces)
        if cilova is not None:
            set_display(cilova, "inline")
            for vnoreny in cilova.findall(".//svg:g", namespaces):
                set_display(vnoreny, "inline")
        else:
            print(f"Kategorie '{aktualni_kategorie}' nebyla nalezena v šabloně")

    # --- Vzácnost ---
    vzacnost_skupiny = []
    for attr in ["id", "inkscape:label", "sodipodi:label", "label"]:
        vzacnost_skupiny.extend(root.findall(f".//svg:g[@{attr}='Vzacnost']", namespaces))

    aktualni_vzacnost = odstranit_diakritiku(row["Vzacnost"]).lower().strip()
    for vzacnost_root in vzacnost_skupiny:
        for podskupina in vzacnost_root.findall(".//svg:g", namespaces):
            set_display(podskupina, "none")
        cilova = najdi_g(vzacnost_root, aktualni_vzacnost, namespaces)
        if cilova is not None:
            set_display(cilova, "inline")
        else:
            print(f"Vzacnost '{aktualni_vzacnost}' nebyla nalezena v šabloně")

    # ---------------- Uložení výstupu do podsložky podle kategorie ----------------
    aktualni_kategorie = str(row["Kategorie"]).strip()
    cilova_slozka = vystup_svg_dir / aktualni_kategorie
    cilova_slozka.mkdir(exist_ok=True)

    nazev_karty = odstranit_diakritiku(row["Nazev"]).strip().replace(" ", "_")
    nazev_karty = re.sub(r'[^A-Za-z0-9_-]', '_', nazev_karty)
    vystup_soubor = cilova_slozka / f"{nazev_karty}.svg"

    try:
        tree = ET.ElementTree(root)
        tree.write(vystup_soubor, encoding="utf-8", xml_declaration=True, method="xml")
    except Exception as e:
        print(f"Chyba při ukládání souboru {vystup_soubor}: {e}")
        continue

print("Hotovo!")

