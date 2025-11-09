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

# Nacti data z Excelu
try:
    df = pd.read_excel("karty.xlsx")
except Exception as e:
    print(f"Chyba pri nacitani souboru: {e}")
    exit(1)

# Namespace pro SVG
namespaces = {
    'svg': 'http://www.w3.org/2000/svg',
    'inkscape': 'http://www.inkscape.org/namespaces/inkscape'
}

# Vystupni slozka
slozka = Path("vystup")
slozka.mkdir(parents=True, exist_ok=True)

# Zpracuj kazdou kartu z Excelu
for index, row in df.iterrows():
    if "Vzacnost" not in row or pd.isna(row["Vzacnost"]):
        print(f"?? Karta na radku {index+2} nema vyplnenou vzacnost")
        continue
    if "Nazev" not in row or pd.isna(row["Nazev"]):
        print(f"?? Karta na radku {index+2} nema vyplneny nazev")
        continue

    # Nacti univerzalni sablonu
    sablona_path = "sablona_Bezna.svg"
    if not Path(sablona_path).exists():
        print(f"? Chybi sablona: {sablona_path}")
        continue

    try:
        tree = ET.parse(sablona_path)
        root = tree.getroot()
    except ET.ParseError as e:
        print(f"? Chyba pri nacitani sablony {sablona_path}: {e}")
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

        # Regulární výraz pro nahrazení placeholderu >Nazev<
        svg_text = re.sub(rf">\s*{re.escape(col)}\s*<", f">{hodnota}<", svg_text)

    # Zpatky prevedeme na XML strom
    root = ET.fromstring(svg_text)

    # --- Kategorie ---
    if "Kategorie" in df.columns and not pd.isna(row["Kategorie"]):
        aktualni_kategorie = str(row["Kategorie"]).strip()

        kategorie_root = (
            root.find(".//svg:g[@id='Kategorie']", namespaces)
            or root.find(".//svg:g[@inkscape:label='Kategorie']", namespaces)
        )

        if kategorie_root is not None:
            # Skryj vsechny podskupiny
            for podskupina in kategorie_root.findall(".//svg:g", namespaces):
                styl = podskupina.get("style", "")
                novy_styl = ";".join(
                    s for s in styl.split(";") if not s.strip().startswith("display:")
                )
                podskupina.set("style", (novy_styl + ";display:none").strip(";"))

            # Najdi cilovou kategorii (id nebo label)
            cilova = (
                kategorie_root.find(f".//svg:g[@id='{aktualni_kategorie}']", namespaces)
                or kategorie_root.find(f".//svg:g[@inkscape:label='{aktualni_kategorie}']", namespaces)
            )

            if cilova is not None:
                # Zviditelni cilovou skupinu
                styl = cilova.get("style", "")
                novy_styl = ";".join(
                    s for s in styl.split(";") if not s.strip().startswith("display:")
                )
                cilova.set("style", (novy_styl + ";display:inline").strip(";"))

                # Zviditelni vsechny podskupiny
                for vnoreny in cilova.findall(".//svg:g", namespaces):
                    styl_vnoreny = vnoreny.get("style", "")
                    novy_styl_vnoreny = ";".join(
                        s for s in styl_vnoreny.split(";") if not s.strip().startswith("display:")
                    )
                    vnoreny.set("style", (novy_styl_vnoreny + ";display:inline").strip(";"))
            else:
                print(f"? Kategorie '{aktualni_kategorie}' nebyla nalezena v sablone")

    # --- Vzacnost ---
 # Najdi všechny koøenové skupiny s Vzacnost
if "Vzacnost" in df.columns and not pd.isna(row["Vzacnost"]):
    aktualni_vzacnost = odstranit_diakritiku(row["Vzacnost"]).lower().strip()

    # Najdi všechny skupiny s label Vzacnost
    vzacnost_skupiny = root.findall(".//svg:g[@id='Vzacnost']", namespaces) + \
                       root.findall(".//svg:g[@inkscape:label='Vzacnost']", namespaces)

    for vzacnost_root in vzacnost_skupiny:
        # Skryj všechny podskupiny
        for podskupina in vzacnost_root.findall(".//svg:g", namespaces):
            styl = podskupina.get("style", "")
            novy_styl = ";".join(
                s for s in styl.split(";") if not s.strip().startswith("display:")
            )
            podskupina.set("style", (novy_styl + ";display:none").strip(";"))

        # Najdi cílovou vzácnost
        cilova = (
            vzacnost_root.find(f".//svg:g[@id='{aktualni_vzacnost}']", namespaces)
            or vzacnost_root.find(f".//svg:g[@inkscape:label='{aktualni_vzacnost}']", namespaces)
        )

        if cilova is not None:
            styl = cilova.get("style", "")
            novy_styl = ";".join(
                s for s in styl.split(";") if not s.strip().startswith("display:")
            )
            cilova.set("style", (novy_styl + ";display:inline").strip(";"))
        else:
            print(f" Vzacnost '{aktualni_vzacnost}' nebyla nalezena v sablone")


    # Ulozeni vystupu
    nazev_karty = odstranit_diakritiku(row["Nazev"]).strip().replace(" ", "_")
    vystup_soubor = slozka / f"{nazev_karty}.svg"

    try:
        tree = ET.ElementTree(root)
        tree.write(vystup_soubor, encoding="utf-8", xml_declaration=True, method="xml")
    except Exception as e:
        print(f" Chyba pri ukladani souboru {vystup_soubor}: {e}")
        continue

print("? Hotovo!")

