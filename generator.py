# -*- coding: utf-8 -*-
import pandas as pd
from pathlib import Path
import xml.etree.ElementTree as ET
import unicodedata
import re
import tkinter as tk
from tkinter import filedialog, messagebox

# ---------------- Funkce ----------------

# Odstranění diakritiky
def odstranit_diakritiku(text):
    return ''.join(
        c for c in unicodedata.normalize('NFKD', str(text))
        if not unicodedata.combining(c)
    )

# Nastavení stylu display
def set_display(elem, value):
    styl = elem.get("style", "")
    novy_styl = ";".join(
        s for s in styl.split(";") if not s.strip().startswith("display:")
    )
    elem.set("style", (novy_styl + f";display:{value}").strip(";"))

# Bezpečné hledání <g> podle více atributů
def najdi_g(root, name, namespaces):
    for attr in ["id", "inkscape:label", "sodipodi:label", "label"]:
        elem = root.find(f".//svg:g[@{attr}='{name}']", namespaces)
        if elem is not None:
            return elem
    return None

# ---------------- Výběr souboru Excel ----------------
root_tk = tk.Tk()
root_tk.withdraw()  # skryje hlavní okno

soubor_xlsx = filedialog.askopenfilename(
    title="Vyberte Excel soubor s kartami",
    filetypes=[("Excel soubory", "*.xlsx")]
)

if not soubor_xlsx:
    messagebox.showerror("Chyba", "Nebyl vybrán žádný soubor.")
    exit(1)

# Načtení dat z Excelu
try:
    df = pd.read_excel(soubor_xlsx)
except Exception as e:
    messagebox.showerror("Chyba", f"Chyba při načítání souboru: {e}")
    exit(1)

# ---------------- SVG nastavení ----------------
namespaces = {
    'svg': 'http://www.w3.org/2000/svg',
    'inkscape': 'http://www.inkscape.org/namespaces/inkscape',
    'sodipodi': 'http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd'
}

# Výstupní složka
slozka = Path("vystup")
slozka.mkdir(parents=True, exist_ok=True)

# ---------------- Zpracování karet ----------------
for index, row in df.iterrows():
    if "Vzacnost" not in row or pd.isna(row["Vzacnost"]):
        print(f"Karta na řádku {index+2} nemá vyplněnou vzácnost.")
        continue
    if "Nazev" not in row or pd.isna(row["Nazev"]):
        print(f"Karta na řádku {index+2} nemá vyplněný název.")
        continue
    if "Kategorie" not in row or pd.isna(row["Nazev"]):
        print(f"Karta na řádku {index+2} nemá vyplněnou kategorii.")
        continue

    # Načti šablonu
    sablona_path = "sablona_Bezna.svg"
    if not Path(sablona_path).exists():
        print(f"Chybí šablona: {sablona_path}")
        continue

    try:
        tree = ET.parse(sablona_path)
        root = tree.getroot()
    except ET.ParseError as e:
        print(f"Chyba při načítání šablony {sablona_path}: {e}")
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
    if kategorie_root is not None and "Kategorie" in df.columns and not pd.isna(row["Kategorie"]):
        aktualni_kategorie = str(row["Kategorie"]).strip()
        # Skryj všechny podskupiny
        for podskupina in kategorie_root.findall(".//svg:g", namespaces):
            set_display(podskupina, "none")
        # Najdi cílovou kategorii
        cilova = najdi_g(kategorie_root, aktualni_kategorie, namespaces)
        if cilova is not None:
            set_display(cilova, "inline")
            for vnoreny in cilova.findall(".//svg:g", namespaces):
                set_display(vnoreny, "inline")
        else:
            print(f"️Kategorie '{aktualni_kategorie}' nebyla nalezena v šabloně")

    # --- Vzácnost ---
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
                print(f"Vzacnost '{aktualni_vzacnost}' nebyla nalezena v šabloně")

    # Uložení výstupu
    nazev_karty = odstranit_diakritiku(row["Nazev"]).strip().replace(" ", "_")
    nazev_karty = re.sub(r'[^A-Za-z0-9_-]', '_', nazev_karty)
    vystup_soubor = slozka / f"{nazev_karty}.svg"

    try:
        tree = ET.ElementTree(root)
        tree.write(vystup_soubor, encoding="utf-8", xml_declaration=True, method="xml")
    except Exception as e:
        print(f"Chyba při ukládání souboru {vystup_soubor}: {e}")
        continue

print("Hotovo!")

