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
    if "Vzacnost" not in row or pd.isna(row["Vzacnost"]):
        print(f"Karta na radku {index+2} nema vyplnenou vzacnost")
        continue
    if "Nazev" not in row or pd.isna(row["Nazev"]):
        print(f"Karta na radku {index+2} nema vyplneny nazev")
        continue

    vzacnost = odstranit_diakritiku(row["Vzacnost"]).lower().strip()
    sablona_path = f"sablona_{vzacnost}.svg"

    if not Path(sablona_path).exists():
        print(f"Chybi sablona pro '{vzacnost}': {sablona_path}")
        continue

    # Nacti SVG jako text (misto ElementTree, kvuli placeholderum)
    try:
        with open(sablona_path, "r", encoding="utf-8") as f:
            svg_text = f.read()
    except Exception as e:
        print(f"Chyba pri nacitani sablony {sablona_path}: {e}")
        continue

    # Nahraz placeholdery ve formatu >Nazev< nebo >Popis<
    for col in df.columns:
        if pd.isna(row[col]):
            hodnota = ""
        elif isinstance(row[col], float) and row[col].is_integer():
            hodnota = str(int(row[col]))
        else:
            hodnota = str(row[col])

        # odstranime diakritiku z nazvu sloupce pro pripad, ze SVG ma bez hacku
        placeholder = f">{col}<"
        svg_text = svg_text.replace(placeholder, f">{hodnota}<")

    # Kategorie zustava po stare
    if "Kategorie" in df.columns and not pd.isna(row["Kategorie"]):
        try:
            tree = ET.ElementTree(ET.fromstring(svg_text))
            root = tree.getroot()
        except ET.ParseError as e:
            print(f"Chyba pri zpracovani SVG textu u {sablona_path}: {e}")
            continue

        aktualni_kategorie = str(row["Kategorie"]).strip()
        kategorie_root = (
            root.find(".//svg:g[@id='Kategorie']", namespaces)
            or root.find(".//svg:g[@inkscape:label='Kategorie']", namespaces)
        )

        if kategorie_root is not None:
            for podskupina in kategorie_root.findall(".//svg:g", namespaces):
                styl = podskupina.get("style", "")
                novy_styl = ";".join(
                    s for s in styl.split(";") if not s.strip().startswith("display:")
                )
                podskupina.set("style", (novy_styl + ";display:none").strip(";"))

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

        # Znovu uloz SVG text ze stromu (protoze kategorie meni XML)
        import io
        buffer = io.BytesIO()
        tree.write(buffer, encoding="utf-8", xml_declaration=True)
        svg_text = buffer.getvalue().decode("utf-8")

    # Uloz vystup
    nazev_karty = odstranit_diakritiku(row["Nazev"]).strip().replace(" ", "_")
    slozka = Path("vystup") / vzacnost
    slozka.mkdir(parents=True, exist_ok=True)
    vystup_soubor = slozka / f"{nazev_karty}.svg"

    try:
        with open(vystup_soubor, "w", encoding="utf-8") as f:
            f.write(svg_text)
    except UnicodeEncodeError as e:
        print(f"Chyba pri ukladani souboru {vystup_soubor}: {e}")
        continue

print("Hotovo!")
