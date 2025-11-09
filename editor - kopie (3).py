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
import base64

OUTPUT_FOLDER = "vystup"
os.makedirs(OUTPUT_FOLDER, exist_ok=True)
INKSCAPE_PATH = Path("inkscape_portable/InkscapePortable.exe")  # přibalovaný portable Inkscape

NS = {
    'svg': "http://www.w3.org/2000/svg",
    'inkscape': "http://www.inkscape.org/namespaces/inkscape",
    'xlink': "http://www.w3.org/1999/xlink"
}

def svg_to_png_bytes(svg_path, dpi=150):
    """Převede SVG na PNG přes Inkscape CLI do paměti (Windows kompatibilní)."""
    if not INKSCAPE_PATH.exists():
        raise FileNotFoundError(f"Inkscape nebyl nalezen: {INKSCAPE_PATH}")
    if not os.path.exists(svg_path):
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

def replace_image_in_svg(tree, new_image_path, pos, size):
    """Nahradí obrázek v <g inkscape:label="OBRAZEK"> novým obrázkem s base64 a zvolenou pozicí/velikostí."""
    root = tree.getroot()
    group = root.find('.//svg:g[@inkscape:label="OBRAZEK"]', NS)
    if group is None:
        raise ValueError("Skupina s label 'OBRAZEK' nebyla nalezena")
    image_el = group.find('.//svg:image', NS)
    if image_el is None:
        raise ValueError("Element <image> nebyl nalezen ve skupině OBRAZEK")

    # načti nový obrázek a zakóduj do base64
    img_data = Path(new_image_path).read_bytes()
    mime = "image/jpeg" if new_image_path.lower().endswith((".jpg", ".jpeg")) else "image/png"
    b64_data = base64.b64encode(img_data).decode("utf-8")

    # aktualizace atributů
    image_el.set("{http://www.w3.org/1999/xlink}href", f"data:{mime};base64,{b64_data}")
    image_el.set("x", str(pos[0]))
    image_el.set("y", str(pos[1]))
    image_el.set("width", str(size[0]))
    image_el.set("height", str(size[1]))
    return tree

class SVGEditor(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("SVG Editor s PNG/JPG vkládáním")
        self.geometry("1200x800")

        self.svg_files = [f for f in os.listdir(OUTPUT_FOLDER) if f.endswith(".svg")]
        self.current_index = 0

        self.drag_data = {"x": 0, "y": 0}
        self.image_pos = (0, 0)
        self.image_size = (0, 0)
        self.original_img = None

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
        self.canvas.bind("<ButtonPress-1>", self.start_drag)
        self.canvas.bind("<B1-Motion>", self.do_drag)

        self.right_frame = tk.Frame(self)
        self.right_frame.pack(side=tk.RIGHT, fill=tk.Y)

        self.add_png_btn = tk.Button(self.right_frame, text="Přidat PNG/JPG", command=self.add_png)
        self.add_png_btn.pack(pady=10)

        self.save_btn = tk.Button(self.right_frame, text="Uložit SVG", command=self.save_svg)
        self.save_btn.pack(pady=10)

        self.zoom_in_btn = tk.Button(self.right_frame, text="Zvětšit", command=lambda: self.resize_image(1.1))
        self.zoom_in_btn.pack(pady=5)
        self.zoom_out_btn = tk.Button(self.right_frame, text="Zmenšit", command=lambda: self.resize_image(0.9))
        self.zoom_out_btn.pack(pady=5)

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

    # --- Drag & resize ---
    def start_drag(self, event):
        self.drag_data["x"] = event.x
        self.drag_data["y"] = event.y

    def do_drag(self, event):
        if hasattr(self, "canvas_image_id"):
            dx = event.x - self.drag_data["x"]
            dy = event.y - self.drag_data["y"]
            self.canvas.move(self.canvas_image_id, dx, dy)
            self.drag_data["x"] = event.x
            self.drag_data["y"] = event.y
            self.image_pos = (self.image_pos[0] + dx, self.image_pos[1] + dy)

    def resize_image(self, scale_factor):
        if self.original_img is None or not hasattr(self, "canvas_image_id"):
            return
        self.image_size = (self.image_size[0]*scale_factor, self.image_size[1]*scale_factor)
        img_resized = self.original_img.resize(
            (int(self.image_size[0]), int(self.image_size[1])),
            Image.Resampling.LANCZOS
        )
        self.tk_img = ImageTk.PhotoImage(img_resized)
        self.canvas.itemconfig(self.canvas_image_id, image=self.tk_img)

    # --- Přidání PNG/JPG ---
    def add_png(self):
        img_path = filedialog.askopenfilename(filetypes=[("Obrázky", "*.png;*.jpg;*.jpeg")])
        if not img_path:
            return
        try:
            img = Image.open(img_path)
            self.original_img = img
            self.image_size = img.size
            self.image_pos = (50, 50)
            self.tk_img = ImageTk.PhotoImage(img)
            if hasattr(self, "canvas_image_id"):
                self.canvas.delete(self.canvas_image_id)
            self.canvas_image_id = self.canvas.create_image(
                self.image_pos[0], self.image_pos[1], anchor="nw", image=self.tk_img
            )
        except Exception as e:
            messagebox.showerror("Chyba", f"Nepodařilo se načíst obrázek: {e}")

    # --- Uložení SVG ---
    def save_svg(self):
        if self.original_img is None:
            messagebox.showerror("Chyba", "Nejdříve vložte obrázek")
            return
        img_path = filedialog.askopenfilename(filetypes=[("Obrázky", "*.png;*.jpg;*.jpeg")])
        if not img_path:
            return
        try:
            replace_image_in_svg(self.tree, img_path, self.image_pos, self.image_size)
            self.tree.write(self.current_svg_path)
            messagebox.showinfo("Hotovo", f"SVG uložen: {self.current_svg_path}")
        except Exception as e:
            messagebox.showerror("Chyba", str(e))

if __name__ == "__main__":
    app = SVGEditor()
    app.mainloop()

