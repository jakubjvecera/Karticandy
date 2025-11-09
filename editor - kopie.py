# -*- coding: utf-8 -*-
import os
import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk
import lxml.etree as ET
import io
import cairosvg

OUTPUT_FOLDER = "vystup"

NS = {
    'svg': "http://www.w3.org/2000/svg",
    'inkscape': "http://www.inkscape.org/namespaces/inkscape",
    'xlink': "http://www.w3.org/1999/xlink"
}

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
        # Levý panel - seznam souborů
        self.listbox = tk.Listbox(self, width=30)
        self.listbox.pack(side=tk.LEFT, fill=tk.Y)
        for f in self.svg_files:
            self.listbox.insert(tk.END, f)
        self.listbox.bind("<<ListboxSelect>>", self.on_list_select)

        # Střední panel - náhled SVG
        self.canvas = tk.Canvas(self, bg="white")
        self.canvas.pack(side=tk.LEFT, expand=True, fill=tk.BOTH)

        # Pravý panel - tlačítka
        self.right_frame = tk.Frame(self)
        self.right_frame.pack(side=tk.RIGHT, fill=tk.Y)

        self.add_png_btn = tk.Button(self.right_frame, text="Přidat PNG", command=self.add_png)
        self.add_png_btn.pack(pady=10)

        self.save_btn = tk.Button(self.right_frame, text="Uložit SVG", command=self.save_svg)
        self.save_btn.pack(pady=10)

        # Klávesové zkratky
        self.bind("<Left>", self.prev_svg)
        self.bind("<Right>", self.next_svg)

    def load_svg(self, index):
        if not self.svg_files:
            return
        self.current_index = index
        self.current_svg_path = os.path.join(OUTPUT_FOLDER, self.svg_files[index])

        # Převod SVG do PNG pro náhled
        png_data = cairosvg.svg2png(url=self.current_svg_path)
        self.img = Image.open(io.BytesIO(png_data))
        self.tk_img = ImageTk.PhotoImage(self.img)

        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor="nw", image=self.tk_img)

        # Načíst SVG XML
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

        # Načíst PNG velikost
        img = Image.open(png_path)
        width, height = img.size

        # Vložit PNG do SVG
        # Najdeme masku podle inkscape:label="maska"
        mask = self.root.find('.//svg:mask[@inkscape:label="maska"]', NS)
        if mask is None:
            messagebox.showerror("Chyba", "Maska s label 'maska' nebyla nalezena!")
            return

        # Vytvořit <image> element
        image_el = ET.Element("{http://www.w3.org/2000/svg}image", nsmap=self.root.nsmap)
        image_el.set("{http://www.w3.org/1999/xlink}href", png_path)
        image_el.set("x", "0")
        image_el.set("y", "0")
        image_el.set("width", str(width))
        image_el.set("height", str(height))
        image_el.set("mask", f"url(#{mask.get('id')})")

        # Přidat do SVG (např. jako poslední prvek)
        self.root.append(image_el)

        # Aktualizovat náhled
        temp_path = os.path.join(OUTPUT_FOLDER, "_preview_temp.svg")
        self.tree.write(temp_path)
        png_data = cairosvg.svg2png(url=temp_path)
        self.img = Image.open(io.BytesIO(png_data))
        self.tk_img = ImageTk.PhotoImage(self.img)
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor="nw", image=self.tk_img)

        messagebox.showinfo("Info", "PNG bylo vloženo do SVG s maskou!")

    def save_svg(self):
        self.tree.write(self.current_svg_path)
        messagebox.showinfo("Info", f"SVG uložen: {self.current_svg_path}")

if __name__ == "__main__":
    app = SVGEditor()
    app.mainloop()

