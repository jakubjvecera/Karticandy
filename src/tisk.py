# -*- coding: utf-8 -*-
import pandas as pd
import math
import sys
import json
import unicodedata
from pathlib import Path
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from PyPDF2 import PdfReader, PdfWriter
import tkinter as tk
from tkinter import messagebox, filedialog
import shutil
import io

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
 
# ---------------- Cesta k projektu ----------------
if len(sys.argv) < 2:
    print("Nebyla předána cesta k projektu.")
    sys.exit(1)
 
PROJECT_PATH = Path(sys.argv[1])
SCRIPT_DIR = Path(__file__).parent
DATA_DIR = PROJECT_PATH / "data"
OUTPUT_DIR = PROJECT_PATH / "vystup"
PNG_ROOT = OUTPUT_DIR / "vystup_png"
OUTPUT_PDF = OUTPUT_DIR / "karty_pro_tisk.pdf"
FINAL_PDF = OUTPUT_DIR / "karty_pro_tisk_oboustranne.pdf"
 
config_path = PROJECT_PATH / "config.json"
if not config_path.exists():
    print(f"Chybí config soubor: {config_path}")
    sys.exit(1)
 
with open(config_path, "r", encoding="utf-8") as f:
    config = json.load(f)
 
EXCEL_FILE = DATA_DIR / config["zdroje"].get("excel", "")
 
# --- Získání rozměrů karty z configu ---
rozmer_karty_str = config.get("generator", {}).get("RozmerKarty", "63.5x88.9mm")
try:
    w_str, h_str = rozmer_karty_str.lower().replace("mm", "").split('x')
    CARD_W_MM, CARD_H_MM = float(w_str), float(h_str)
    print(f"Info: Načteny rozměry karty z konfigurace: {CARD_W_MM}x{CARD_H_MM} mm")
except (ValueError, IndexError):
    CARD_W_MM, CARD_H_MM = 63.5, 88.9
    print(f"Varování: Nepodařilo se načíst rozměry karty, použity výchozí: {CARD_W_MM}x{CARD_H_MM} mm")

MARGIN_MM = 7
GAP_MM    = 2

def mm2pt(mm_val): return mm_val * 72 / 25.4
CARD_W, CARD_H = mm2pt(CARD_W_MM), mm2pt(CARD_H_MM)
PAGE_W, PAGE_H = A4

# spočítáme, kolik karet se vejde na stránku
usable_width_mm  = (PAGE_W / mm) - 2 * MARGIN_MM
usable_height_mm = (PAGE_H / mm) - 2 * MARGIN_MM
COLS = int((usable_width_mm + GAP_MM) // (CARD_W_MM + GAP_MM))
ROWS = int((usable_height_mm + GAP_MM) // (CARD_H_MM + GAP_MM))
PER_PAGE = COLS * ROWS

def clean_filename(name: str) -> str:
    nfkd_form = unicodedata.normalize('NFKD', name)
    only_ascii = nfkd_form.encode('ASCII', 'ignore').decode('ASCII')
    return only_ascii.replace(' ', '_')

def create_print_pdf():
    """Vytvoří PDF s lícovými stranami karet."""
    if not EXCEL_FILE.exists():
        print(f"Chyba: Soubor Excelu '{EXCEL_FILE}' nebyl nalezen.")
        return

    df = pd.read_excel(str(EXCEL_FILE))
    df = df.sort_values(["Vzacnost", "Nazev"])
    c = canvas.Canvas(str(OUTPUT_PDF), pagesize=A4)

    for vzacnost, group in df.groupby("Vzacnost"):
        placed_in_group = 0
        for _, row in group.iterrows():
            nazev_raw = row.get("Nazev", "")
            nazev = str(nazev_raw).strip()
            kategorie = str(row.get("Kategorie", "")).strip()
            pocet = row.get("Pocet", 1)
            try:
                pocet = int(pocet) if not math.isnan(pocet) else 1
            except:
                pocet = 1

            clean_name = f"{clean_filename(nazev)}.png"

            # 1. Hledání v hlavní složce (upravené)
            png_file = PNG_ROOT / kategorie / clean_name
            # 2. Pokud nenalezeno, hledání v podsložce 'unedited'
            if not png_file.exists():
                png_file = PNG_ROOT / "unedited" / kategorie / clean_name

            if not png_file.exists():
                print(f"Varování: Chybí PNG pro kartu '{nazev}' v kategorii '{kategorie}'. Karta nebude v PDF.")
                continue

            for _ in range(pocet):
                if placed_in_group and placed_in_group % PER_PAGE == 0:
                    c.showPage()
                    placed_in_group = 0

                col = placed_in_group % COLS
                row_i = placed_in_group // COLS

                x = mm2pt(MARGIN_MM + col * (CARD_W_MM + GAP_MM))
                y = PAGE_H - mm2pt(MARGIN_MM + (row_i + 1) * CARD_H_MM + row_i * GAP_MM)

                c.drawImage(str(png_file), x, y,
                            width=CARD_W, height=CARD_H,
                            preserveAspectRatio=True, anchor="sw")
                placed_in_group += 1

        # Po dokončení všech karet jedné vzácnosti vždy ukončíme stránku,
        # aby další vzácnost začala na nové.
        if placed_in_group > 0:
            c.showPage()

    c.save()
    print(f"Info: Lícové PDF vytvořeno: {OUTPUT_PDF}")

def create_backed_pdf():
    """Za každou stránku líců vloží rub odpovídající vzácnosti stránky."""
    if not EXCEL_FILE.exists():
        print(f"Chyba: Soubor Excelu '{EXCEL_FILE}' nebyl nalezen.")
        return

    df = pd.read_excel(str(EXCEL_FILE))
    df = df.sort_values(["Vzacnost", "Nazev"])

    # spočítáme počet stránek pro každou vzácnost
    rarity_pages = []
    for vzacnost, group in df.groupby("Vzacnost"):
        total_cards = group["Pocet"].fillna(1).astype(int).sum()
        num_pages = math.ceil(total_cards / PER_PAGE)
        rarity_pages.extend([vzacnost] * num_pages)

    reader = PdfReader(OUTPUT_PDF)
    writer = PdfWriter()

    if len(rarity_pages) != len(reader.pages):
        print(f"Varování: Nesouhlasí počet stránek a vzácností, oříznuto na minimum.")
        rarity_pages = rarity_pages[:len(reader.pages)]

    for i, page in enumerate(reader.pages):
        vzacnost = rarity_pages[i]
        writer.add_page(page)  # líc

        back_pdf_name = f"{clean_filename(vzacnost)}.pdf"
        back_pdf = SCRIPT_DIR / back_pdf_name

        if not back_pdf.is_file():
            # Pokud rub chybí, zeptáme se uživatele, zda ho chce přidat
            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)

            user_agrees = messagebox.askyesno(
                "Chybí rubová strana",
                f"Rubový PDF pro vzácnost '{vzacnost}' nebyl nalezen.\n"
                f"Očekávaný název souboru je: '{back_pdf_name}' ve složce 'src'.\n\n"
                f"Chcete nyní vybrat soubor, který se zkopíruje pod správným názvem?",
                parent=root
            )

            if user_agrees:
                source_file = filedialog.askopenfilename(
                    title=f"Vyberte PDF soubor pro vzácnost '{vzacnost}'",
                    filetypes=[("PDF soubory", "*.pdf")],
                    parent=root
                )
                if source_file:
                    try:
                        shutil.copy2(source_file, back_pdf)
                        print(f"Info: Soubor '{Path(source_file).name}' byl zkopírován do 'src' jako '{back_pdf_name}'.")
                    except Exception as e:
                        messagebox.showerror("Chyba kopírování", f"Nepodařilo se zkopírovat soubor: {e}", parent=root)
            
            root.destroy()

        if back_pdf.is_file():
            back_reader = PdfReader(back_pdf)
            writer.add_page(back_reader.pages[0])  # rub
        else:
            print(f"Varování: Rubový PDF pro vzácnost '{vzacnost}' stále nenalezen (hledáno jako {back_pdf_name}). Stránka bude bez rubu.")

    with open(FINAL_PDF, "wb") as f:
        writer.write(f)

    print(f"Info: Oboustranné PDF vytvořeno: {FINAL_PDF}")

if __name__ == "__main__":
    create_print_pdf()    # vytvoří lícové PDF
    create_backed_pdf()   # vloží ruby za každou stránku

    # Uložení cest k vytvořeným souborům do configu
    if "tisk" not in config:
        config["tisk"] = {}

    if OUTPUT_PDF.exists():
        config["tisk"]["pdf_licove"] = str(OUTPUT_PDF.relative_to(PROJECT_PATH))
    if FINAL_PDF.exists():
        config["tisk"]["pdf_oboustranne"] = str(FINAL_PDF.relative_to(PROJECT_PATH))

    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4, ensure_ascii=False)
    print("Info: Cesty k PDF souborům uloženy do konfigurace.")
