# -*- coding: utf-8 -*-
import pandas as pd
from pathlib import Path
import xml.etree.ElementTree as ET
import unicodedata
import re

# Funkce pro odstraneni diakritiky
def odstranit_diakritiku(text):
    return ''.join(
        c for c in unicodedata.normalize('NFKD', str(text))
        if not unicodedata.combining(c)
    )

# Funkce pro nastaveni display stylu
def set_display(elem, value):
    styl = elem.get("style", "")
    novy_styl = ";".join(
        s for s in styl.split(";") if not s.strip().startswith("display:")
    )
    elem.set("style", (novy_styl + f";display:{value}").strip(";"))

# Funkce pro bezpeèné hledání <g> podle více atributù
def najdi_g(root, name, namespaces):
    for attr in ["id", "inkscape:label", "sodipodi:label", "label"]:
        elem = root.find(f".//svg:g[@{attr}='{name}']", namespaces)
        if elem is not None:
            return elem
    return None

# Nacti data z Excelu
try:
    df = pd.read_excel("karty.xlsx")
except Exception as e:
    print(f"Chyba pri nacitani souboru: {e}")
    exit(1)

# Namespace pro SVG
namespaces = {
    'svg': 'http://www.w3.org/2000/svg',
    'inkscape': 'http://www.inkscape.org/namespaces/inkscape',
    'sodipodi': 'http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd'
}

# Vystupni slozka
slozka = Path("vystup")
slozka.mkdir(parents=True, exist_ok=True)

# Zpracuj kazdou kartu z Excelu
for index, row in df.iterrows():
    if "Vzacnost" not in row or pd.isna(row["Vzacnost"]):
        print(f"Karta na radku {index+2} nema vyplnenou vzacnost")
        continue
    if "Nazev" not in row or pd.isna(row["Nazev"]):
        print(f"Karta na radku {index+2} nema vyplneny nazev")
        continue

    # Nacti univerzalni sablonu
    sablona_path = "sablona_Bezna.svg"
    if not Path(sablona_path).exists():
        print(f"Chybi sablona: {sablona_path}")
        continue

    try:
        tree = ET.parse(sablona_path)
        root = tree.getroot()
    except ET.ParseError as e:
        print(f"Chyba pri nacitani sablony {sablona_path}: {e}")
        continue

    # Nahrazeni placeholderu podle nazvu sloupcu
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

    # --- Kategorie root ---
    kategorie_root = najdi_g(root, "Kategorie", namespaces)
    if kategorie_root is not None and "Kategorie" in df.columns and not pd.isna(row["Kategorie"]):
        aktualni_kategorie = str(row["Kategorie"]).strip()

        # Skryj vsechny podskupiny
        for podskupina in kategorie_root.findall(".//svg:g", namespaces):
            set_display(podskupina, "none")

        # Najdi cilovou kategorii
        cilova = najdi_g(kategorie_root, aktualni_kategorie, namespaces)
        if cilova is not None:
            set_display(cilova, "inline")
            for vnoreny in cilova.findall(".//svg:g", namespaces):
                set_display(vnoreny, "inline")
        else:
            print(f"?Kategorie '{aktualni_kategorie}' nebyla nalezena v sablone")

    # --- Vzacnost root ---
    vzacnost_skupiny = []
    for attr in ["id", "inkscape:label", "sodipodi:label", "label"]:
        vzacnost_skupiny.extend(root.findall(f".//svg:g[@{attr}='Vzacnost']", namespaces))

    if "Vzacnost" in df.columns and not pd.isna(row["Vzacnost"]):
        aktualni_vzacnost = odstranit_diakritiku(row["Vzacnost"]).lower().strip()

        for vzacnost_root in vzacnost_skupiny:
            for podskupina in vzacnost_root.findall(".//svg:g", namespaces):
                set_display(podskupina, "none")

            cilova = najdi_g(vzacnost_root, aktualni_vzacnost, namespaces)
            if cilova is not None:
                set_display(cilova, "inline")
            else:
                print(f"Vzacnost '{aktualni_vzacnost}' nebyla nalezena v sablone")

    # Ulozeni vystupu
    nazev_karty = odstranit_diakritiku(row["Nazev"]).strip().replace(" ", "_")
    nazev_karty = re.sub(r'[^A-Za-z0-9_-]', '_', nazev_karty)
    vystup_soubor = slozka / f"{nazev_karty}.svg"

    try:
        tree = ET.ElementTree(root)
        tree.write(vystup_soubor, encoding="utf-8", xml_declaration=True, method="xml")
    except Exception as e:
        print(f"Chyba pri ukladani souboru {vystup_soubor}: {e}")
        continue

print("Hotovo!")
