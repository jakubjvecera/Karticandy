# -*- coding: utf-8 -*-
import os
import sys
import io
import json
import time
import threading
import tempfile
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinterdnd2 import DND_FILES, TkinterDnD
from PIL import Image, ImageTk
import lxml.etree as ET
import subprocess
from pathlib import Path
import base64

# ---------------- cesta k projektu ----------------
if len(sys.argv) < 2:
    print("Nebyla předána cesta k projektu.")
    sys.exit(1)

PROJECT_PATH = Path(sys.argv[1])
OUTPUT_FOLDER = PROJECT_PATH / "vystup" / "vystup_svg"
DATA_FOLDER = PROJECT_PATH / "data"
DATA_FOLDER.mkdir(parents=True, exist_ok=True)

if not OUTPUT_FOLDER.exists():
    print(f"Složka se SVG soubory neexistuje: {OUTPUT_FOLDER}")
    sys.exit(1)

# --- Najdi Inkscape (portable) ---
if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys.executable).parent
else:
    BASE_DIR = Path(__file__).parent

INKSCAPE_PATH = BASE_DIR / "inkscape_portable/App/Inkscape/bin/inkscape.exe"
if not INKSCAPE_PATH.exists():
    INKSCAPE_PATH = BASE_DIR / "inkscape_portable/InkscapePortable.exe"
if not INKSCAPE_PATH.exists():
    raise FileNotFoundError(f"Inkscape nebyl nalezen: {INKSCAPE_PATH}")

# --- namespaces ---
NS = {
    'svg': "http://www.w3.org/2000/svg",
    'inkscape': "http://www.inkscape.org/namespaces/inkscape",
    'xlink': "http://www.w3.org/1999/xlink"
}

# --- lock pro Inkscape (jedno volání najednou) ---
INKSCAPE_LOCK = threading.Lock()

# ---------------- pomocné funkce ----------------
def svg_to_png_bytes(svg_path, dpi=150):
    """Spustí Inkscape pro export SVG->PNG a vrátí bytes."""
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        subprocess.run([
            str(INKSCAPE_PATH),
            str(svg_path),
            "--export-type=png",
            f"--export-filename={tmp_path}",
            "--export-dpi", str(dpi)
        ], check=True)
        with open(tmp_path, "rb") as f:
            return f.read()
    finally:
        try:
            os.remove(tmp_path)
        except Exception:
            pass

def svg_to_png_bytes_threadsafe(svg_path, dpi=150):
    """Wrapper, který zajišťuje, že Inkscape volá ve zámku."""
    with INKSCAPE_LOCK:
        return svg_to_png_bytes(svg_path, dpi)

def parse_svg_length(value):
    if value is None:
        return 0.0
    for unit in ["mm", "cm", "in", "pt", "pc", "px"]:
        if value.endswith(unit):
            value = value.replace(unit, "")
            break
    try:
        return float(value)
    except Exception:
        return 0.0

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

# ---------------- hlavní aplikace ----------------
class SVGEditor(TkinterDnD.Tk):
    def __init__(self):
        super().__init__()
        self.title("SVG Editor s PNG/JPG vkládáním")
        self.geometry("1300x850")

        # seznam svg
        self.svg_files = sorted([p for p in OUTPUT_FOLDER.rglob("*.svg")])
        self.current_index = 0
        self.current_svg_path = None
        self.loading_path = None  # cesta která se právě načítá (prevence race)
        self.svg_cache = {}  # Path -> PIL.Image
        self.root = None
        self.tree_xml = None

        # saved files (persistentní)
        self.saved_files_path = DATA_FOLDER / "saved_files.json"
        self.saved_files = set()
        if self.saved_files_path.exists():
            try:
                with open(self.saved_files_path, "r", encoding="utf-8") as f:
                    self.saved_files = set(Path(p) for p in json.load(f))
            except Exception:
                self.saved_files = set()

        # stav pro vkládání obrázků na plátně
        self.original_img = None
        self.tk_img = None
        self.svg_tk_img = None
        self.image_pos = (0, 0)
        self.image_size = (0, 0)
        self.canvas_offset = (0, 0)
        self.canvas_scale = 1.0
        self.drag_data = {"x": 0, "y": 0}

        # preloader thread
        self.stop_preloader = threading.Event()
        self.preloader_thread = threading.Thread(target=self.preload_loop, daemon=True)
        self.preloader_thread.start()

        # UI
        self.setup_ui()

        # pokud jsou soubory, načti první
        if self.svg_files:
            self.load_svg(0)

        # klávesy
        self.bind("<Left>", self.prev_svg)
        self.bind("<Right>", self.next_svg)
        # windows mousewheel vs linux differences handled in binding
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    # ---------------- UI ----------------
    def setup_ui(self):
        main_frame = tk.Frame(self)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # --- levý panel
        left_frame = tk.Frame(main_frame, width=320)
        left_frame.pack(side=tk.LEFT, fill=tk.Y)

        tk.Label(left_frame, text="🔍 Hledat soubor:").pack(pady=(10, 2))
        self.filter_var = tk.StringVar()
        self.filter_entry = tk.Entry(left_frame, textvariable=self.filter_var)
        self.filter_entry.pack(fill=tk.X, padx=10)
        self.filter_var.trace_add("write", lambda *args: self.update_tree())

        self.tree = ttk.Treeview(left_frame)
        self.tree.pack(expand=True, fill=tk.BOTH, padx=5, pady=5)
        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)
        self.tree.tag_configure("selected_item", font=("Segoe UI", 10, "bold"))
        self.tree.tag_configure("saved_file", foreground="green")
        self.tree.tag_configure("active_file", background="#cce5ff", font=("Segoe UI", 10, "bold"))

        self.saved_count_label = tk.Label(left_frame, text="")
        self.saved_count_label.pack(pady=(0, 10))

        # --- canvas
        self.canvas = tk.Canvas(main_frame, bg="white")
        self.canvas.pack(side=tk.LEFT, expand=True, fill=tk.BOTH)
        self.canvas.bind("<ButtonPress-1>", self.start_drag)
        self.canvas.bind("<B1-Motion>", self.do_drag)
        # mouse wheel binding cross-platform
        self.canvas.bind("<MouseWheel>", self.on_mouse_wheel)      # Windows / Mac
        self.canvas.bind("<Button-4>", self.on_mouse_wheel)        # Linux up
        self.canvas.bind("<Button-5>", self.on_mouse_wheel)        # Linux down
        # DnD
        self.canvas.drop_target_register(DND_FILES)
        self.canvas.dnd_bind('<<Drop>>', self.drop_file)

        # --- pravý panel
        right_frame = tk.Frame(main_frame, width=160)
        right_frame.pack(side=tk.RIGHT, fill=tk.Y)

        self.add_png_btn = tk.Button(right_frame, text="Přidat PNG/JPG", command=self.add_png)
        self.add_png_btn.pack(pady=10)

        self.save_btn = tk.Button(right_frame, text="Uložit SVG", command=self.save_svg)
        self.save_btn.pack(pady=10)

        self.open_inkscape_btn = tk.Button(right_frame, text="Otevřít v Inkscape", command=self.open_in_inkscape)
        self.open_inkscape_btn.pack(side=tk.BOTTOM, pady=10)

        # naplnit strom
        self.update_tree()

    # ---------------- strom ----------------
    def update_tree(self):
        self.tree.delete(*self.tree.get_children())
        filter_text = self.filter_var.get().lower()
        categories = {}

        for f in self.svg_files:
            try:
                rel_path = f.relative_to(OUTPUT_FOLDER)
            except Exception:
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
                tags = []
                if full_path in self.saved_files:
                    tags.append("saved_file")
                if self.current_svg_path == full_path:
                    tags.append("active_file")
                self.tree.insert(cat_id, "end", text=file, values=[str(full_path)], tags=tuple(tags))

        saved = len(self.saved_files)
        total = len(self.svg_files)
        self.saved_count_label.config(text=f"Uloženo: {saved} / {total}")

    def on_tree_select(self, event):
        selected = self.tree.selection()
        if not selected:
            return
        item_id = selected[0]
        parent_id = self.tree.parent(item_id)
        # klik přímo na kategorii
        if parent_id == "":
            return
        fpath_str = self.tree.item(item_id)["values"][0]
        svg_path = Path(fpath_str)
        if svg_path.exists():
            self.load_svg_by_path(svg_path)

    # ---------------- navigace ----------------
    def prev_svg(self, event=None):
        if not self.svg_files:
            return
        self.current_index = (self.current_index - 1) % len(self.svg_files)
        self.load_svg(self.current_index)

    def next_svg(self, event=None):
        if not self.svg_files:
            return
        self.current_index = (self.current_index + 1) % len(self.svg_files)
        self.load_svg(self.current_index)

    # ---------------- načítání SVG (s prevencí race) ----------------
    def load_svg(self, index):
        self.current_index = index
        self.load_svg_by_path(self.svg_files[index])

    def load_svg_by_path(self, path: Path):
        # nastavíme, co chceme načíst - slouží jako "token" pro race-prevent
        self.loading_path = path
        self.current_svg_path = path
        if path in self.svg_files:
            self.current_index = self.svg_files.index(path)

        # vizuální info
        self.canvas.delete("all")
        self.canvas.create_text(self.canvas.winfo_width() // 2, self.canvas.winfo_height() // 2,
                                text="Načítám SVG...", font=("Arial", 20), fill="gray")

        def load_thread():
            try:
                # pokud je v cache, rychle použít
                if path in self.svg_cache:
                    img = self.svg_cache[path]
                else:
                    png_data = svg_to_png_bytes_threadsafe(path)
                    img = Image.open(io.BytesIO(png_data)).convert("RGBA")
                    self.svg_cache[path] = img

                # jestli mezitím už uživatel chtěl něco jiného, zahodíme tento výstup
                if path != self.loading_path:
                    return

                self.img = img
                parser = ET.XMLParser(huge_tree=True)
                self.tree_xml = ET.parse(path, parser=parser)
                self.root = self.tree_xml.getroot()

                # vykreslit v hlavním vlákně a zvýraznit položku ve stromu
                self.after(0, self.center_display_svg)
                self.after(0, lambda: self.highlight_active_tree_item(path))
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Chyba při načítání SVG", str(e)))

        threading.Thread(target=load_thread, daemon=True).start()

    def center_display_svg(self):
        # zobrazit obrázek ve středu canvasu se škálováním
        self.update_idletasks()
        cw, ch = self.canvas.winfo_width(), self.canvas.winfo_height()
        if getattr(self, "img", None) is None:
            return
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
        # pokud je vložené raster obrázek, znovu ho zobrazíme
        if getattr(self, "original_img", None) is not None:
            self.load_dropped_image(None)  # znovu vykreslí vložený obrázek (použije self.original_img)

    def highlight_active_tree_item(self, path: Path):
        # odstraníme active_file tag ze všech položek
        for cat in self.tree.get_children():
            for sub in self.tree.get_children(cat):
                tags = [t for t in self.tree.item(sub, "tags") if t != "active_file"]
                self.tree.item(sub, tags=tuple(tags))

        # najdeme odpovídající položku a označíme ji + přiblížíme
        for cat in self.tree.get_children():
            for sub in self.tree.get_children(cat):
                vals = self.tree.item(sub)["values"]
                if vals and Path(vals[0]) == path:
                    tags = list(self.tree.item(sub, "tags"))
                    if "active_file" not in tags:
                        tags.append("active_file")
                    self.tree.item(sub, tags=tuple(tags))
                    self.tree.selection_set(sub)
                    self.tree.see(sub)
                    break
        # aktualizace stromu (barvy uložených apod.)
        self.update_tree()

    # ---------------- práce s vloženými obrázky (z původního kódu) ----------------
    def start_drag(self, event):
        # připravíme drag data pro posun vloženého obrázku
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
        if getattr(self, "original_img", None) is None or not hasattr(self, "canvas_image_id"):
            return
        # cross-platform delta handling
        delta = 0
        if hasattr(event, "delta"):
            delta = event.delta
        elif event.num == 4:
            delta = 120
        elif event.num == 5:
            delta = -120
        scale_factor = 1.1 if delta > 0 else 0.9
        self.image_size = (self.image_size[0]*scale_factor, self.image_size[1]*scale_factor)
        img_resized = self.original_img.resize(
            (max(1, int(self.image_size[0])), max(1, int(self.image_size[1]))),
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
        # když img_path je None, použijeme self.original_img (znovuvykreslení)
        if img_path is not None:
            img = Image.open(img_path).convert("RGBA")
            self.original_img = img
        img = self.original_img
        self.image_size = img.size
        # umístění relativní k zobrazenému SVG
        # chceme pozici v canvas (ne v SVG souřadnicích)
        self.image_pos = (self.canvas_offset[0] + 50, self.canvas_offset[1] + 50)
        self.tk_img = ImageTk.PhotoImage(img)
        # smazat předchozí položky
        for attr in ("canvas_image_id", "canvas_box_id"):
            if hasattr(self, attr):
                try:
                    self.canvas.delete(getattr(self, attr))
                except Exception:
                    pass
        # vytvoříme nové prvky na canvasu
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

    # ---------------- otevřít v Inkscape ----------------
    def open_in_inkscape(self):
        if not hasattr(self, "current_svg_path") or not self.current_svg_path or not self.current_svg_path.exists():
            messagebox.showerror("Chyba", "Žádný SVG soubor k otevření")
            return
        try:
            subprocess.Popen([str(INKSCAPE_PATH), str(self.current_svg_path)])
        except Exception as e:
            messagebox.showerror("Chyba", f"Nepodařilo se otevřít Inkscape: {e}")

    # ---------------- uložení SVG (vloží base64 image do elementu OBRAZEK) ----------------
    def save_svg(self):
        if getattr(self, "original_img", None) is None:
            messagebox.showerror("Chyba", "Nejdříve vložte obrázek")
            return
        try:
            # spočítat pozici a velikost v SVG souřadnicích
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
                # uložit do temp jako PNG (ponecháme průhlednost)
                self.original_img.save(tmp_path)
                replace_image_in_svg(self.tree_xml, tmp_path, (rel_x, rel_y), (rel_w, rel_h))

            # zapsat XML zpět do souboru
            self.tree_xml.write(self.current_svg_path)
            messagebox.showinfo("Hotovo", f"SVG uložen: {self.current_svg_path}")

            # přidat do saved_files a uložit JSON
            self.saved_files.add(self.current_svg_path)
            with open(self.saved_files_path, "w", encoding="utf-8") as f:
                json.dump([str(p) for p in self.saved_files], f, ensure_ascii=False, indent=2)

            # reset canvas image
            self.original_img = None
            for attr in ("canvas_image_id", "canvas_box_id"):
                if hasattr(self, attr):
                    try:
                        self.canvas.delete(getattr(self, attr))
                        delattr(self, attr)
                    except Exception:
                        pass

            # vyčistit cache pro tento soubor (aby se nový náhled přegeneroval)
            self.svg_cache.pop(self.current_svg_path, None)
            # znovu načíst (aktualizovat náhled)
            self.load_svg_by_path(self.current_svg_path)
        except Exception as e:
            messagebox.showerror("Chyba při ukládání SVG", str(e))

    # ---------------- preloader (priorita aktuálního a 3 vzad, 5 vpřed) ----------------
    def preload_loop(self):
        while not self.stop_preloader.is_set():
            try:
                if not self.svg_files:
                    time.sleep(1)
                    continue
                current = getattr(self, "current_index", 0)
                # bezpečnost: pokud index mimo rozsah (např. soubory se změnily), opravíme
                if current < 0 or current >= len(self.svg_files):
                    current = 0
                    self.current_index = 0

                # 1) Priorita - aktuální soubor
                current_path = self.svg_files[current]
                if current_path not in self.svg_cache:
                    try:
                        if not INKSCAPE_LOCK.locked():
                            png_data = svg_to_png_bytes_threadsafe(current_path)
                            img = Image.open(io.BytesIO(png_data)).convert("RGBA")
                            self.svg_cache[current_path] = img
                    except Exception:
                        # ignorujeme chyby u jednoho souboru
                        pass

                # 2) Okolní soubory 3 vzad, 5 vpřed (vynecháme 0 - aktuální)
                indices = [(current + i) % len(self.svg_files) for i in range(-3, 6) if i != 0]
                for idx in indices:
                    if self.stop_preloader.is_set():
                        break
                    path = self.svg_files[idx]
                    if path in self.svg_cache:
                        continue
                    try:
                        if INKSCAPE_LOCK.locked():
                            # když je Inkscape právě používán, přeskočíme tento cyklus a nezdržujeme
                            continue
                        png_data = svg_to_png_bytes_threadsafe(path)
                        img = Image.open(io.BytesIO(png_data)).convert("RGBA")
                        self.svg_cache[path] = img
                    except Exception:
                        pass

                # kratší interval (1s)
                time.sleep(1)
            except Exception:
                time.sleep(1)

    # ---------------- zavření ----------------
    def on_close(self):
        self.stop_preloader.set()
        # počkáme krátce, aby se vlákno mohlo ukončit
        time.sleep(0.05)
        self.destroy()

# ---------------- main ----------------
if __name__ == "__main__":
    app = SVGEditor()
    app.mainloop()

