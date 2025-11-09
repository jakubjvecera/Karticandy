# -*- coding: utf-8 -*-
import pandas as pd
from pathlib import Path
import xml.etree.ElementTree as ET
import unicodedata

# Funkce pro odstranìní diakritiky
def odstranit_diakritiku(text):
    return ''.join(
        c for c in unicodedata.normalize('NFKD', str(text))
        if not unicodedata.combining(c)
    )

# Naèti data z Excelu
try:
    df = pd.read_excel("karty.xlsx")
except UnicodeDecodeError as e:
    print(f"Chyba pri nacitani souboru: {e}")
    print("Zkuste ulozit soubor 'karty.xlsx' v kodovani UTF-8.")
    exit(1)
except Exception as e:
    print(f"Neocekavana chyba: {e}")
    exit(1)

# Namespace pro SVG
namespaces = {'svg': 'http://www.w3.org/2000/svg'}

# Zpracuj každou kartu
for index, row in df.iterrows():
    # Ovìø klíèové sloupce
    if "Vzacnost" not in row or pd.isna(row["Vzacnost"]):
        print(f"??  Karta na radku {index+2} nema vyplnenou vzacnost")
        continue
    if "Nazev" not in row or pd.isna(row["Nazev"]):
        print(f"??  Karta na radku {index+2} nema vyplneny nazev,")
        continue

    # Získej vzácnost a pøiprav cestu k šablonì
    vzacnost = odstranit_diakritiku(row["Vzacnost"]).lower().strip()
    sablona_path = f"sablona_{vzacnost}.svg"

    # Zkontroluj, že šablona existuje
    if not Path(sablona_path).exists():
        print(f"? Chybi sablona pro '{vzacnost}': {sablona_path}")
        continue

    # Naèti šablonu
    try:
        tree = ET.parse(sablona_path)
        root = tree.getroot()
    except ET.ParseError as e:
        print(f"? Chyba pri nacitani sablony {sablona_path}: {e}")
        continue

    # Pro každý sloupec nahraï text v SVG podle id
    for col in df.columns:
        element = root.find(f".//svg:*[@id='{col}']", namespaces)
        if element is not None:
            hodnota = row[col]
            if pd.isna(hodnota):
                hodnota = ""
            elif isinstance(hodnota, float) and hodnota.is_integer():
                hodnota = int(hodnota)
            element.text = str(hodnota)
        # nepoužité sloupce prostì ignoruj

    # Vytvoø výstupní cestu: vystup/<vzacnost>/<nazev_karty>.svg
    nazev_karty = odstranit_diakritiku(row["Nazev"]).strip().replace(" ", "_")
    slozka = Path("vystup") / vzacnost
    slozka.mkdir(parents=True, exist_ok=True)
    vystup_soubor = slozka / f"{nazev_karty}.svg"

    # Ulož výstupní soubor
    try:
        tree.write(vystup_soubor, encoding="utf-8", xml_declaration=True)
    except UnicodeEncodeError as e:
        print(f"? Chyba pri ukladani souboru {vystup_soubor}: {e}")
        continue

print("? Hotovo!")


