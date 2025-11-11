# -*- coding: utf-8 -*-
import pandas as pd
import math
import unicodedata
from pathlib import Path
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from PyPDF2 import PdfReader, PdfWriter

# --- Nastavení ---
EXCEL_FILE = Path("karty.xlsx")
PNG_ROOT   = Path("vystup_png")
OUTPUT_PDF = Path("karty_tisk.pdf")
FINAL_PDF  = Path("karty_tisk_oboustranne.pdf")

CARD_W_MM, CARD_H_MM = 63.5, 88.9
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

def find_rarity_dir(vzacnost: str) -> Path:
    vz = vzacnost.strip().lower()
    for d in PNG_ROOT.iterdir():
        if d.is_dir() and d.name.lower() == vz:
            return d
    return None

def create_print_pdf():
    """Vytvoří PDF s lícovými stranami karet."""
    df = pd.read_excel(EXCEL_FILE)
    df = df.sort_values(["Vzacnost", "Nazev"])
    c = canvas.Canvas(str(OUTPUT_PDF), pagesize=A4)

    for vzacnost, group in df.groupby("Vzacnost"):
        placed = 0
        rar_dir = find_rarity_dir(vzacnost)
        if not rar_dir:
            print(f"⚠️ Podadresar pro vzácnost '{vzacnost}' nenalezen.")
            continue

        for _, row in group.iterrows():
            nazev_raw = row.get("Nazev", "")
            nazev = str(nazev_raw).strip()
            pocet = row.get("Pocet", 1)
            try:
                pocet = int(pocet) if not math.isnan(pocet) else 1
            except:
                pocet = 1

            png_file = rar_dir / f"{clean_filename(nazev)}.png"
            if not png_file.exists():
                print(f"⚠️ Chybí PNG pro kartu: {png_file}")
                continue

            for _ in range(pocet):
                if placed and placed % PER_PAGE == 0:
                    c.showPage()
                    placed = 0

                col = placed % COLS
                row_i = placed // COLS

                x = mm2pt(MARGIN_MM + col * (CARD_W_MM + GAP_MM))
                y = PAGE_H - mm2pt(MARGIN_MM + (row_i + 1) * CARD_H_MM + row_i * GAP_MM)

                c.drawImage(str(png_file), x, y,
                            width=CARD_W, height=CARD_H,
                            preserveAspectRatio=True, anchor="sw")
                placed += 1

        c.showPage()  # nová strana po dokončení vzácnosti

    c.save()
    print(f"✅ Lícové PDF vytvořeno: {OUTPUT_PDF}")

def create_backed_pdf():
    """Za každou stránku líců vloží rub odpovídající vzácnosti stránky."""
    df = pd.read_excel(EXCEL_FILE)
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
        print(f"⚠️ Počet stránek a vzácností nesedí, použiji minimum")
        rarity_pages = rarity_pages[:len(reader.pages)]

    for i, page in enumerate(reader.pages):
        vzacnost = rarity_pages[i]
        writer.add_page(page)  # líc

        back_pdf = Path(f"{vzacnost}.pdf")
        if back_pdf.exists():
            back_reader = PdfReader(back_pdf)
            writer.add_page(back_reader.pages[0])  # rub
        else:
            print(f"⚠️ Rubový PDF pro '{vzacnost}' nenalezen, pokračuji bez něj.")

    with open(FINAL_PDF, "wb") as f:
        writer.write(f)

    print(f"✅ Oboustranné PDF vytvořeno: {FINAL_PDF}")

if __name__ == "__main__":
    create_print_pdf()    # vytvoří lícové PDF
    create_backed_pdf()   # vloží ruby za každou stránku

