# -*- coding: utf-8 -*-
import os
import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk
import lxml.etree as ET
import io
import subprocess
from pathlib import Path
import tempfile

OUTPUT_FOLDER = "vystup"
os.makedirs(OUTPUT_FOLDER, exist_ok=True)  # automaticky vytvoří složku pokud neexistuje
INKSCAPE_PATH = Path("inkscape_portable/InkscapePortable.exe")  # přibalovaný portable Inkscape

NS = {
    'svg': "http://www.w3.org/2000/svg",
    'inkscape': "http://www.inkscape.org/namespaces/inkscape",
    'xlink': "http://www.w3.org/1999/xlink"
}

def svg_to_png_bytes(svg_path, dpi=150):
    """Převede SVG na PNG přes Inkscape CLI do paměti (Windows kompatibilní)."""
    if not INKSCAPE_PATH.exists():
        raise FileNotFoundError(f"Inkscape nebyl n
        raise FileNotFoundError(f"SVG soubor neexistuje: {svg_path}")

    with tempfile.NamedTemporaryFile(suffix=".png") as tmp:
        subprocess.run([
            str(INKSCAPE_PATH),
            str(svg_path),
            "--export-type=png",
            f"--export-filename={tmp.name}",
            "--export-dpi", str(dpi)
        ], check=True)
        tmp.seek(0)
        return tmp.read()

class SVGEditor(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("SVG Editor s PNG vkládáním")
        self.geometry("1200x800")

        self.svg_files = [f for f in os.listdir(OUTPUT_FOLDER) if f.endswith(".svg")]
        self.current_index = 0

        self.setup_ui()
        if self.svg_files:
            self.load_svg(self.current_index)

    def setup_ui(self):
        self.listbox = tk.Listbox(self, width=30)
        self.listbox.pack(side=tk.LEFT, fill=tk.Y)
        for f in self.svg_files:
            self.listbox.insert(tk.END, f)
        self.listbox.bind("<<ListboxSelect>>", self.on_list_select)

        self.canvas = tk.Canvas(self, bg="white")
        self.canvas.pack(side=tk.LEFT, expand=True, fill=tk.BOTH)

        self.right_frame = tk.Frame(self)
        self.right_frame.pack(side=tk.RIGHT, fill=tk.Y)

        self.add_png_btn = tk.Button(self.right_frame, text="Přidat PNG", command=self.add_png)
        self.add_png_btn.pack(pady=10)

        self.save_btn = tk.Button(self.right_frame, text="Uložit SVG", command=self.save_svg)
        self.save_btn.pack(pady=10)

        self.bind("<Left>", self.prev_svg)
        self.bind("<Right>", self.next_svg)

    def load_svg(self, index):
        if not self.svg_files:
            return
        self.current_index = index
        self.current_svg_path = os.path.abspath(os.path.join(OUTPUT_FOLDER, self.svg_files[index]))

        if not os.path.exists(self.current_svg_path):
            messagebox.showerror("Chyba", f"SVG soubor neexistuje: {self.current_svg_path}")
            return

        # Převod SVG do PNG pro náhled přes Inkscape
        try:
            png_data = svg_to_png_bytes(self.current_svg_path)
            self.img = Image.open(io.BytesIO(png_data))
            self.tk_img = ImageTk.PhotoImage(self.img)
        except Exception as e:
            messagebox.showerror("Chyba", f"Nepodařilo se načíst SVG: {e}")
            return

        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor="nw", image=self.tk_img)

        self.tree = ET.parse(self.current_svg_path)
        self.root = self.tree.getroot()

    def on_list_select(self, event):
        selection = event.widget.curselection()
        if selection:
            self.load_svg(selection[0])

    def prev_svg(self, event=None):
        self.current_index = (self.current_index - 1) % len(self.svg_files)
        self.load_svg(self.current_index)

    def next_svg(self, event=None):
        self.current_index = (self.current_index + 1) % len(self.svg_files)
        self.load_svg(self.current_index)

    def add_png(self):
        png_path = filedialog.askopenfilename(filetypes=[("PNG files", "*.png")])
        if not png_path:
            return

        img = Image.open(png_path)
        width, height = img.size

        mask = self.root.find('.//svg:mask[@inkscape:label="maska"]', NS)
        if mask is None:
            messagebox.showerror("Chyba", "Maska s label 'maska' nebyla nalezena!")
            return

        image_el = ET.Element("{http://www.w3.org/2000/svg}image", nsmap=self.root.nsmap)
        image_el.set("{http://www.w3.org/1999/xlink}href", png_path)
        image_el.set("x", "0")
        image_el.set("y", "0")
        image_el.set("width", str(width))
        image_el.set("height", str(height))
        image_el.set("mask", f"url(#{mask.get('id')})")

        self.root.append(image_el)

        # Aktualizace náhledu přes Inkscape
        temp_path = os.path.abspath(os.path.join(OUTPUT_FOLDER, "_preview_temp.svg"))
        try:
            self.tree.write(temp_path)
        except Exception as e:
            messagebox.showerror("Chyba", f"Nepodařilo se uložit dočasný SVG: {e}")
            return

        try:
            png_data = svg_to_png_bytes(temp_path)
            self.img = Image.open(io.BytesIO(png_data))
            self.tk_img = ImageTk.PhotoImage(self.img)
            self.canvas.delete("all")
            self.canvas.create_image(0, 0, anchor="nw", image=self.tk_img)
        except Exception as e:
            messagebox.showerror("Chyba", f"Nepodařilo se načíst náhled: {e}")
            return

        messagebox.showinfo("Info", "PNG bylo vloženo do SVG s maskou!")

    def save_svg(self):
        try:
            self.tree.write(self.current_svg_path)
            messagebox.showinfo("Info", f"SVG uložen: {self.current_svg_path}")
        except Exception as e:
            messagebox.showerror("Chyba", f"Nepodařilo se uložit SVG: {e}")

if __name__ == "__main__":
    app = SVGEditor()
    app.mainloop()

