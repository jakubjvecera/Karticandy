# -*- coding: utf-8 -*-
import pandas as pd
from pathlib import Path
import xml.etree.ElementTree as ET
import unicodedata

# Funkce pro odstraneni diakritiky
def odstranit_diakritiku(text):
    return ''.join(
        c for c in unicodedata.normalize('NFKD', str(text))
        if not unicodedata.combining(c)
    )

# Nacti data z Excelu
try:
    df = pd.read_excel("karty.xlsx")
except UnicodeDecodeError as e:
    print(f"Chyba pri nacitani souboru: {e}")
    print("Zkuste ulozit soubor 'karty.xlsx' v kodovani UTF-8.")
    exit(1)
except Exception as e:
    print(f"Neocekavana chyba: {e}")
    exit(1)

# Namespace pro SVG (jen SVG, inkscape se pouzije jen pokud existuje ve strukture)
namespaces = {
    'svg': 'http://www.w3.org/2000/svg',
    'inkscape': 'http://www.inkscape.org/namespaces/inkscape'
}



# Zpracuj kazdou kartu z Excelu
for index, row in df.iterrows():
    # Over klicove sloupce
    if "Vzacnost" not in row or pd.isna(row["Vzacnost"]):
        print(f"Karta na radku {index+2} nema vyplnenou vzacnost")
        continue
    if "Nazev" not in row or pd.isna(row["Nazev"]):
        print(f"Karta na radku {index+2} nema vyplneny nazev")
        continue

    # Urci vzacnost a priprav sablonu
    vzacnost = odstranit_diakritiku(row["Vzacnost"]).lower().strip()
    sablona_path = f"sablona_{vzacnost}.svg"

    if not Path(sablona_path).exists():
        print(f"Chybi sablona pro '{vzacnost}': {sablona_path}")
        continue

    # Nacti SVG sablonu
    try:
        tree = ET.parse(sablona_path)
        root = tree.getroot()
    except ET.ParseError as e:
        print(f"Chyba pri nacitani sablony {sablona_path}: {e}")
        continue

    # Nahrad texty podle id
    for col in df.columns:
        element = root.find(f".//svg:*[@id='{col}']", namespaces)
        if element is not None:
            hodnota = row[col]
            if pd.isna(hodnota):
                hodnota = ""
            elif isinstance(hodnota, float) and hodnota.is_integer():
                hodnota = int(hodnota)
            element.text = str(hodnota)

    # Kategorie
    if "Kategorie" in df.columns and not pd.isna(row["Kategorie"]):
        aktualni_kategorie = str(row["Kategorie"]).strip()

        # Pokusime se najit skupinu Kategorie (musi mit inkscape namespace pokud existuje)
        kategorie_root = (
            root.find(".//svg:g[@id='Kategorie']", namespaces)
            or root.find(".//svg:g[@inkscape:label='Kategorie']", namespaces)
        )

        if kategorie_root is not None:
            # Vsechny podskupiny skryjeme
            for podskupina in kategorie_root.findall(".//svg:g", namespaces):
                styl = podskupina.get("style", "")
                # Zachovej ostatni styly, ale prepis display
                novy_styl = ";".join(
                    s for s in styl.split(";") if not s.strip().startswith("display:")
                )
                podskupina.set("style", (novy_styl + ";display:none").strip(";"))

            # A aktualni kategorii zobrazime
            cilova = (
                kategorie_root.find(f".//svg:g[@id='{aktualni_kategorie}']", namespaces)
                or kategorie_root.find(f".//svg:g[@inkscape:label='{aktualni_kategorie}']", namespaces)
            )
            if cilova is not None:
                styl = cilova.get("style", "")
                novy_styl = ";".join(
                    s for s in styl.split(";") if not s.strip().startswith("display:")
                )
                cilova.set("style", (novy_styl + ";display:inline").strip(";"))
            else:
                print(f"Kategorie '{aktualni_kategorie}' nebyla nalezena v sablone {sablona_path}")

    # Uloz vystup
    nazev_karty = odstranit_diakritiku(row["Nazev"]).strip().replace(" ", "_")
    slozka = Path("vystup") / vzacnost
    slozka.mkdir(parents=True, exist_ok=True)
    vystup_soubor = slozka / f"{nazev_karty}.svg"

    try:
        tree.write(vystup_soubor, encoding="utf-8", xml_declaration=True)
    except UnicodeEncodeError as e:
        print(f"Chyba pri ukladani souboru {vystup_soubor}: {e}")
        continue

print("Hotovo!")

