# -*- coding: utf-8 -*-
import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox
from tkinterdnd2 import DND_FILES, TkinterDnD
from PIL import Image, ImageTk
import lxml.etree as ET
import io
import subprocess
from pathlib import Path
import tempfile
import base64

OUTPUT_FOLDER = "vystup"
os.makedirs(OUTPUT_FOLDER, exist_ok=True)
INKSCAPE_PATH = Path("inkscape_portable/InkscapePortable.exe")  # portable Inkscape

NS = {
    'svg': "http://www.w3.org/2000/svg",
    'inkscape': "http://www.inkscape.org/namespaces/inkscape",
    'xlink': "http://www.w3.org/1999/xlink"
}

def svg_to_png_bytes(svg_path, dpi=150):
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

def parse_svg_length(value):
    if value is None:
        return 0.0
    for unit in ["mm", "cm", "in", "pt", "pc", "px"]:
        if value.endswith(unit):
            value = value.replace(unit, "")
            break
    return float(value)

def replace_image_in_svg(tree, new_image_path, pos, size):
    root = tree.getroot()
    group = root.find('.//svg:g[@inkscape:label="OBRAZEK"]', NS)
    if group is None:
        raise ValueError("Skupina s label 'OBRAZEK' nebyla nalezena")
    image_el = group.find('.//svg:image', NS)
    if image_el is None:
        raise ValueError("Element <image> nebyl nalezen ve skupině OBRAZEK")

    img_data = Path(new_image_path).read_bytes()
    mime = "image/jpeg" if new_image_path.lower().endswith((".jpg", ".jpeg")) else "image/png"
    b64_data = base64.b64encode(img_data).decode("utf-8")

    image_el.set("{http://www.w3.org/1999/xlink}href", f"data:{mime};base64,{b64_data}")
    image_el.set("x", str(pos[0]))
    image_el.set("y", str(pos[1]))
    image_el.set("width", str(size[0]))
    image_el.set("height", str(size[1]))
    return tree

class SVGEditor(TkinterDnD.Tk):
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

        self.canvas_offset = (0, 0)
        self.canvas_scale = 1.0

        self.svg_cache = {}  # cache pro PNG

        self.setup_ui()
        if self.svg_files:
            self.load_svg(self.current_index)

    # --- UI ---
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
        self.canvas.bind("<MouseWheel>", self.on_mouse_wheel)
        self.canvas.bind("<Button-4>", self.on_mouse_wheel)
        self.canvas.bind("<Button-5>", self.on_mouse_wheel)

        self.canvas.drop_target_register(DND_FILES)
        self.canvas.dnd_bind('<<Drop>>', self.drop_file)

        self.right_frame = tk.Frame(self)
        self.right_frame.pack(side=tk.RIGHT, fill=tk.Y)

        self.add_png_btn = tk.Button(self.right_frame, text="Přidat PNG/JPG", command=self.add_png)
        self.add_png_btn.pack(pady=10)

        self.save_btn = tk.Button(self.right_frame, text="Uložit SVG", command=self.save_svg)
        self.save_btn.pack(pady=10)

        self.open_inkscape_btn = tk.Button(self.right_frame, text="Otevřít v Inkscape", command=self.open_in_inkscape)
        self.open_inkscape_btn.pack(side=tk.BOTTOM, pady=10)

        self.bind("<Left>", self.prev_svg)
        self.bind("<Right>", self.next_svg)
        self.bind_all("<Control-s>", lambda event: self.save_svg())
        self.bind_all("<Return>", lambda event: self.save_svg())

    # --- Seznam SVG ---
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

    # --- Načítání SVG ---
    def load_svg(self, index):
        self.current_index = index
        filename = self.svg_files[index]
        self.current_svg_path = os.path.abspath(os.path.join(OUTPUT_FOLDER, filename))

        # --- načtení z cache ---
        if filename in self.svg_cache:
            self.img = self.svg_cache[filename]
        else:
            try:
                png_data = svg_to_png_bytes(self.current_svg_path)
                self.img = Image.open(io.BytesIO(png_data))
                self.svg_cache[filename] = self.img
            except Exception as e:
                messagebox.showerror("Chyba", f"Nepodařilo se načíst SVG: {e}")
                return

        self.center_display_svg()

        self.tree = ET.parse(self.current_svg_path)
        self.root = self.tree.getroot()

        if self.original_img:
            self.load_dropped_image(None)

        # --- přednačítání sousedních SVG ---
        threading.Thread(target=self.preload_svg_cache, daemon=True).start()

    def preload_svg_cache(self):
        indices_to_preload = []
        for i in range(self.current_index - 3, self.current_index + 6):
            idx = i % len(self.svg_files)
            indices_to_preload.append(idx)

        for idx in indices_to_preload:
            filename = self.svg_files[idx]
            if filename not in self.svg_cache:
                path = os.path.abspath(os.path.join(OUTPUT_FOLDER, filename))
                try:
                    png_data = svg_to_png_bytes(path)
                    img = Image.open(io.BytesIO(png_data))
                    self.svg_cache[filename] = img
                except Exception:
                    pass

    # --- Zobrazení SVG ---
    def center_display_svg(self):
        self.update_idletasks()
        canvas_width = self.canvas.winfo_width()
        canvas_height = self.canvas.winfo_height()
        if canvas_width <= 1 or canvas_height <= 1:
            canvas_width = 800
            canvas_height = 600

        margin = 20
        max_w = canvas_width - 2*margin
        max_h = canvas_height - 2*margin

        scale_w = max_w / self.img.width
        scale_h = max_h / self.img.height
        scale = min(scale_w, scale_h, 1)

        display_w = max(1, int(self.img.width * scale))
        display_h = max(1, int(self.img.height * scale))

        offset_x = (canvas_width - display_w) // 2
        offset_y = (canvas_height - display_h) // 2

        self.canvas_offset = (offset_x, offset_y)
        self.canvas_scale = scale

        display_img = self.img.resize((display_w, display_h), Image.Resampling.LANCZOS)
        self.svg_tk_img = ImageTk.PhotoImage(display_img)
        self.canvas.delete("all")
        self.canvas.create_image(offset_x, offset_y, anchor="nw", image=self.svg_tk_img)

    # --- Drag & Drop PNG ---
    def start_drag(self, event):
        self.drag_data["x"] = event.x
        self.drag_data["y"] = event.y

    def do_drag(self, event):
        if hasattr(self, "canvas_image_id"):
            dx = event.x - self.drag_data["x"]
            dy = event.y - self.drag_data["y"]
            self.canvas.move(self.canvas_image_id, dx, dy)
            if hasattr(self, "canvas_box_id"):
                self.canvas.move(self.canvas_box_id, dx, dy)
            self.drag_data["x"] = event.x
            self.drag_data["y"] = event.y
            self.image_pos = (self.image_pos[0]+dx, self.image_pos[1]+dy)

    def on_mouse_wheel(self, event):
        if self.original_img is None or not hasattr(self, "canvas_image_id"):
            return
        scale_factor = 1.1 if getattr(event, "delta", 0) > 0 or getattr(event, "num", 0) == 4 else 0.9
        self.image_size = (self.image_size[0]*scale_factor, self.image_size[1]*scale_factor)
        img_resized = self.original_img.resize(
            (int(self.image_size[0]), int(self.image_size[1])),
            Image.Resampling.LANCZOS
        )
        self.tk_img = ImageTk.PhotoImage(img_resized)
        self.canvas.itemconfig(self.canvas_image_id, image=self.tk_img)

        if hasattr(self, "canvas_box_id"):
            self.canvas.coords(
                self.canvas_box_id,
                self.image_pos[0], self.image_pos[1],
                self.image_pos[0]+self.image_size[0], self.image_pos[1]+self.image_size[1]
            )

    def load_dropped_image(self, img_path=None):
        try:
            if img_path is not None:
                img = Image.open(img_path)
                self.original_img = img
            img = self.original_img
            self.image_size = img.size
            self.image_pos = (50, 50)
            self.tk_img = ImageTk.PhotoImage(img)

            if hasattr(self, "canvas_image_id"):
                self.canvas.delete(self.canvas_image_id)
            if hasattr(self, "canvas_box_id"):
                self.canvas.delete(self.canvas_box_id)

            self.canvas_image_id = self.canvas.create_image(
                self.image_pos[0], self.image_pos[1], anchor="nw", image=self.tk_img
            )
            self.canvas_box_id = self.canvas.create_rectangle(
                self.image_pos[0], self.image_pos[1],
                self.image_pos[0]+self.image_size[0], self.image_pos[1]+self.image_size[1],
                outline="red", width=2
            )
        except Exception as e:
            messagebox.showerror("Chyba", f"Nepodařilo se načíst obrázek: {e}")

    def drop_file(self, event):
        files = self.tk.splitlist(event.data)
        for f in files:
            if f.lower().endswith((".png", ".jpg", ".jpeg")):
                self.load_dropped_image(f)
                break

    def add_png(self):
        img_path = filedialog.askopenfilename(filetypes=[("Obrázky", "*.png;*.jpg;*.jpeg")])
        if not img_path:
            return
        self.load_dropped_image(img_path)

    def open_in_inkscape(self):
        if not hasattr(self, "current_svg_path") or not os.path.exists(self.current_svg_path):
            messagebox.showerror("Chyba", "Žádný SVG soubor k otevření")
            return
        if not INKSCAPE_PATH.exists():
            messagebox.showerror("Chyba", f"Inkscape nebyl nalezen: {INKSCAPE_PATH}")
            return
        try:
            subprocess.Popen([str(INKSCAPE_PATH), str(self.current_svg_path)])
        except Exception as e:
            messagebox.showerror("Chyba", f"Nepodařilo se otevřít Inkscape: {e}")

    # --- Ukládání ---
    def save_svg(self):
        if self.original_img is None:
            messagebox.showerror("Chyba", "Nejdříve vložte obrázek")
            return
        try:
            canvas_x, canvas_y = self.image_pos
            offset_x, offset_y = self.canvas_offset
            scale = self.canvas_scale

            img_x = (canvas_x - offset_x) / scale
            img_y = (canvas_y - offset_y) / scale
            img_w = self.image_size[0] / scale
            img_h = self.image_size[1] / scale

            svg_width = parse_svg_length(self.root.get("width")) or self.img.width
            svg_height = parse_svg_length(self.root.get("height")) or self.img.height

            rel_x = img_x / self.img.width * svg_width
            rel_y = img_y / self.img.height * svg_height
            rel_w = img_w / self.img.width * svg_width
            rel_h = img_h / self.img.height * svg_height

            with tempfile.TemporaryDirectory() as tmpdir:
                tmp_path = os.path.join(tmpdir, "image.png")
                self.original_img.save(tmp_path)
                replace_image_in_svg(self.tree, tmp_path, (rel_x, rel_y), (rel_w, rel_h))

            self.tree.write(self.current_svg_path)
            messagebox.showinfo("Hotovo", f"SVG uložen: {self.current_svg_path}")

            # Odstranění PNG a přechod na další SVG
            self.original_img = None
            if hasattr(self, "canvas_image_id"):
                self.canvas.delete(self.canvas_image_id)
                del self.canvas_image_id
            if hasattr(self, "canvas_box_id"):
                self.canvas.delete(self.canvas_box_id)
                del self.canvas_box_id

            self.next_svg()
        except Exception as e:
            messagebox.showerror("Chyba", str(e))


if __name__ == "__main__":
    app = SVGEditor()
    app.mainloop()

