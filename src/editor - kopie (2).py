# -*- coding: utf-8 -*-
import os
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinterdnd2 import DND_FILES, TkinterDnD
from PIL import Image, ImageTk
import lxml.etree as ET
import io
import subprocess
from pathlib import Path
import tempfile
import base64
import sys

# --- Cesta k projektu ---
if len(sys.argv) < 2:
    print("Nebyla předána cesta k projektu.")
    sys.exit(1)

PROJECT_PATH = Path(sys.argv[1])
OUTPUT_FOLDER = PROJECT_PATH / "vystup" / "vystup_svg"

if not OUTPUT_FOLDER.exists():
    print(f"Složka se SVG soubory neexistuje: {OUTPUT_FOLDER}")
    sys.exit(1)

# --- Najdi správnou cestu k Inkscapu ---
if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys.executable).parent
else:
    BASE_DIR = Path(__file__).parent

INKSCAPE_PATH = BASE_DIR / "inkscape_portable/App/Inkscape/bin/inkscape.exe"
if not INKSCAPE_PATH.exists():
    INKSCAPE_PATH = BASE_DIR / "inkscape_portable/InkscapePortable.exe"
if not INKSCAPE_PATH.exists():
    raise FileNotFoundError(f"Inkscape nebyl nalezen: {INKSCAPE_PATH}")

NS = {
    'svg': "http://www.w3.org/2000/svg",
    'inkscape': "http://www.inkscape.org/namespaces/inkscape",
    'xlink': "http://www.w3.org/1999/xlink"
}

INKSCAPE_LOCK = threading.Lock()

# --- Pomocné funkce ---
def svg_to_png_bytes(svg_path, dpi=150):
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

def svg_to_png_bytes_threadsafe(svg_path, dpi=150):
    with INKSCAPE_LOCK:
        return svg_to_png_bytes(svg_path, dpi)

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


# --- Hlavní aplikace ---
class SVGEditor(TkinterDnD.Tk):
    def __init__(self):
        super().__init__()
        self.title("SVG Editor s PNG/JPG vkládáním")
        self.geometry("1300x850")

        # seznam SVG souborů (rekurzivně)
        self.svg_files = [p for p in OUTPUT_FOLDER.rglob("*.svg")]
        self.current_index = 0
        self.current_tree_item = None

        self.svg_cache = {}
        self.stop_preloader = threading.Event()
        self.preloader_thread = threading.Thread(target=self.preload_loop, daemon=True)
        self.preloader_thread.start()

        self.setup_ui()

        if self.svg_files:
            self.load_svg(0)

        self.protocol("WM_DELETE_WINDOW", self.on_close)

    # --- UI ---
    def setup_ui(self):
        main_frame = tk.Frame(self)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # --- levý panel (strom + hledání) ---
        left_frame = tk.Frame(main_frame, width=300)
        left_frame.pack(side=tk.LEFT, fill=tk.Y)

        lbl = tk.Label(left_frame, text="🔍 Hledat soubor:")
        lbl.pack(pady=(10, 2))

        self.filter_var = tk.StringVar()
        self.filter_entry = tk.Entry(left_frame, textvariable=self.filter_var)
        self.filter_entry.pack(fill=tk.X, padx=10)
        self.filter_var.trace_add("write", lambda *args: self.update_tree())

        self.tree = ttk.Treeview(left_frame)
        self.tree.pack(expand=True, fill=tk.BOTH, padx=5, pady=5)
        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)
        self.tree.tag_configure("selected_item", font=("Segoe UI", 10, "bold"))

        # --- plátno ---
        self.canvas = tk.Canvas(main_frame, bg="white")
        self.canvas.pack(side=tk.LEFT, expand=True, fill=tk.BOTH)
        self.canvas.bind("<ButtonPress-1>", self.start_drag)
        self.canvas.bind("<B1-Motion>", self.do_drag)
        self.canvas.bind("<MouseWheel>", self.on_mouse_wheel)
        self.canvas.drop_target_register(DND_FILES)
        self.canvas.dnd_bind('<<Drop>>', self.drop_file)

        # --- pravý panel ---
        right_frame = tk.Frame(main_frame, width=150)
        right_frame.pack(side=tk.RIGHT, fill=tk.Y)

        self.add_png_btn = tk.Button(right_frame, text="Přidat PNG/JPG", command=self.add_png)
        self.add_png_btn.pack(pady=10)

        self.save_btn = tk.Button(right_frame, text="Uložit SVG", command=self.save_svg)
        self.save_btn.pack(pady=10)

        self.open_inkscape_btn = tk.Button(right_frame, text="Otevřít v Inkscape", command=self.open_in_inkscape)
        self.open_inkscape_btn.pack(side=tk.BOTTOM, pady=10)

        self.update_tree()

    # --- naplnění stromu ---
    def update_tree(self):
        self.tree.delete(*self.tree.get_children())
        filter_text = self.filter_var.get().lower()
        categories = {}

        for f in self.svg_files:
            try:
                rel_path = f.relative_to(OUTPUT_FOLDER)
            except ValueError:
                continue
            parts = rel_path.parts
            if len(parts) < 2:
                continue
            cat, file = parts[0], parts[-1]
            if filter_text in file.lower():
                categories.setdefault(cat, []).append((file, f))

        for cat, files in sorted(categories.items()):
            cat_id = self.tree.insert("", "end", text=cat, open=True)
            for file, full_path in sorted(files):
                self.tree.insert(cat_id, "end", text=file, values=[str(full_path)])

    # --- výběr souboru ---
    def on_tree_select(self, event):
        selected = self.tree.selection()
        if not selected:
            return
        item_id = selected[0]
        parent_id = self.tree.parent(item_id)
        if parent_id == "":
            return  # klik na kategorii, ne soubor

        # odstraníme tučnost z předchozí položky
        if self.current_tree_item and self.tree.exists(self.current_tree_item):
            self.tree.item(self.current_tree_item, tags=())

        # zvýrazníme aktuální
        self.tree.item(item_id, tags=("selected_item",))
        self.current_tree_item = item_id

        fpath_str = self.tree.item(item_id)["values"][0]
        svg_path = Path(fpath_str)
        if svg_path.exists():
            self.load_svg_by_path(svg_path)

    # ---------------- Navigace ----------------
    def prev_svg(self, event=None):
        self.current_index = (self.current_index - 1) % len(self.svg_files)
        self.load_svg(self.current_index)

    def next_svg(self, event=None):
        self.current_index = (self.current_index + 1) % len(self.svg_files)
        self.load_svg(self.current_index)

    # ---------------- SVG práce ----------------
    def load_svg(self, index):
        self.current_index = index
        self.load_svg_by_path(self.svg_files[index])

    def load_svg_by_path(self, path):
        self.current_svg_path = path
        self.canvas.delete("all")
        self.canvas.create_text(self.canvas.winfo_width()//2, self.canvas.winfo_height()//2,
                                text="Načítám SVG...", font=("Arial", 20), fill="gray")

        def load_thread():
            try:
                if path in self.svg_cache:
                    img = self.svg_cache[path]
                else:
                    png_data = svg_to_png_bytes_threadsafe(path)
                    img = Image.open(io.BytesIO(png_data))
                    self.svg_cache[path] = img
                self.img = img
                self.after(0, self.center_display_svg)
                parser = ET.XMLParser(huge_tree=True)
                self.tree_xml = ET.parse(path, parser=parser)
                self.root = self.tree_xml.getroot()
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Chyba", str(e)))
        threading.Thread(target=load_thread, daemon=True).start()

    def center_display_svg(self):
        self.update_idletasks()
        cw, ch = self.canvas.winfo_width(), self.canvas.winfo_height()
        margin = 20
        scale = min((cw - 2*margin)/self.img.width, (ch - 2*margin)/self.img.height, 1)
        w, h = int(self.img.width*scale), int(self.img.height*scale)
        ox, oy = (cw-w)//2, (ch-h)//2
        self.canvas_offset = (ox, oy)
        self.canvas_scale = scale
        display_img = self.img.resize((w, h), Image.Resampling.LANCZOS)
        self.svg_tk_img = ImageTk.PhotoImage(display_img)
        self.canvas.delete("all")
        self.canvas.create_image(ox, oy, anchor="nw", image=self.svg_tk_img)

    # ---------------- Obrázky ----------------
    def start_drag(self, event):
        self.drag_data["x"], self.drag_data["y"] = event.x, event.y

    def do_drag(self, event):
        if hasattr(self, "canvas_image_id"):
            dx, dy = event.x - self.drag_data["x"], event.y - self.drag_data["y"]
            self.canvas.move(self.canvas_image_id, dx, dy)
            if hasattr(self, "canvas_box_id"):
                self.canvas.move(self.canvas_box_id, dx, dy)
            self.drag_data["x"], self.drag_data["y"] = event.x, event.y
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
        if img_path is not None:
            img = Image.open(img_path)
            self.original_img = img
        img = self.original_img
        self.image_size = img.size
        self.image_pos = (50, 50)
        self.tk_img = ImageTk.PhotoImage(img)
        for attr in ("canvas_image_id", "canvas_box_id"):
            if hasattr(self, attr):
                self.canvas.delete(getattr(self, attr))
        self.canvas_image_id = self.canvas.create_image(
            self.image_pos[0], self.image_pos[1], anchor="nw", image=self.tk_img
        )
        self.canvas_box_id = self.canvas.create_rectangle(
            self.image_pos[0], self.image_pos[1],
            self.image_pos[0]+self.image_size[0], self.image_pos[1]+self.image_size[1],
            outline="red", width=2
        )

    def drop_file(self, event):
        files = self.tk.splitlist(event.data)
        for f in files:
            if f.lower().endswith((".png", ".jpg", ".jpeg")):
                self.load_dropped_image(f)
                break

    def add_png(self):
        img_path = filedialog.askopenfilename(filetypes=[("Obrázky", "*.png;*.jpg;*.jpeg")])
        if img_path:
            self.load_dropped_image(img_path)

    def open_in_inkscape(self):
        if not hasattr(self, "current_svg_path") or not self.current_svg_path.exists():
            messagebox.showerror("Chyba", "Žádný SVG soubor k otevření")
            return
        try:
            subprocess.Popen([str(INKSCAPE_PATH), str(self.current_svg_path)])
        except Exception as e:
            messagebox.showerror("Chyba", f"Nepodařilo se otevřít Inkscape: {e}")

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
                replace_image_in_svg(self.tree_xml, tmp_path, (rel_x, rel_y), (rel_w, rel_h))
            self.tree_xml.write(self.current_svg_path)
            messagebox.showinfo("Hotovo", f"SVG uložen: {self.current_svg_path}")
            self.original_img = None
            for attr in ("canvas_image_id", "canvas_box_id"):
                 if hasattr(self, attr):
                    self.canvas.delete(getattr(self, attr))
                    delattr(self, attr)
            
            self.svg_cache.pop(self.current_svg_path, None)
            self.load_svg_by_path(self.current_svg_path)
        except Exception as e:
            messagebox.showerror("Chyba", str(e))

    def preload_loop(self):
        while not self.stop_preloader.is_set():
            if not self.svg_files:
                time.sleep(1)
                continue
            current = getattr(self, "current_index", 0)
            indices = [(current + i) % len(self.svg_files) for i in range(-3, 6)]
            for idx in indices:
                if self.stop_preloader.is_set():
                    return
                path = self.svg_files[idx]
                if path not in self.svg_cache:
                    try:
                        if INKSCAPE_LOCK.locked():
                            time.sleep(0.5)
                            continue
                        png_data = svg_to_png_bytes_threadsafe(path)
                        img = Image.open(io.BytesIO(png_data))
                        self.svg_cache[path] = img
                    except Exception:
                        pass
            time.sleep(3)

    def on_close(self):
        self.stop_preloader.set()
        self.destroy()


if __name__ == "__main__":
    app = SVGEditor()
    app.mainloop()

