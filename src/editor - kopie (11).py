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
import shutil
from pathlib import Path
import base64

# ---------------- cesta k projektu ----------------
if len(sys.argv) < 2:
    print("Nebyla předána cesta k projektu.")
    sys.exit(1)

PROJECT_PATH = Path(sys.argv[1])
OUTPUT_FOLDER = PROJECT_PATH / "vystup" / "vystup_svg"
DATA_FOLDER = PROJECT_PATH / "data"
EDITED_SVG_FOLDER = PROJECT_PATH / "vystup" / "vystup_editedsvg"
INKSCAPE_EDIT_FOLDER = DATA_FOLDER / "editorinkscape"
INKSCAPE_WATCH_STATE_FILE = DATA_FOLDER / "inkscape_watch.json"
DATA_FOLDER.mkdir(parents=True, exist_ok=True)
EDITED_SVG_FOLDER.mkdir(parents=True, exist_ok=True)
INKSCAPE_EDIT_FOLDER.mkdir(parents=True, exist_ok=True)


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
        self.loading_path = None
        self.svg_cache = {}
        self.root = None
        self.tree_xml = None

        # marked files (red)
        self.marked_files_path = DATA_FOLDER / "marked_files.json"
        self.marked_files = set()
        if self.marked_files_path.exists():
            try:
                with open(self.marked_files_path, "r", encoding="utf-8") as f:
                    self.marked_files = set(Path(p) for p in json.load(f))
            except Exception:
                self.marked_files = set()

        # canvas images
        self.original_img = None            # PIL image (plná kvalita)
        self.tk_img = None                  # aktuální PhotoImage zobrazený v canvasu
        self.svg_tk_img = None              # náhled SVG
        self.image_pos = (0, 0)
        self.image_size = (0, 0)            # velikost v pixelech na canvasu (floaty OK)
        self.canvas_offset = (0, 0)
        self.canvas_scale = 1.0
        self.drag_data = {"x": 0, "y": 0}

        # opacity
        self.opacity_var = tk.DoubleVar(value=1.0)

        # Načtení poslední hodnoty opacity z configu
        config_path = PROJECT_PATH / "config.json"
        if config_path.exists():
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    config_data = json.load(f)
                last_alpha = config_data.get("editor", {}).get("alpha")
                if last_alpha is not None:
                    self.opacity_var.set(float(last_alpha))
            except (json.JSONDecodeError, ValueError, TypeError):
                # Pokud je soubor poškozený nebo hodnota neplatná, použije se výchozí 1.0
                pass


        # debounce id pro ukládání alpha do configu
        self._alpha_save_after_id = None

        # preloader a signál pro ukončení vláken
        self.stop_preloader = threading.Event()
        self.preloader_thread = threading.Thread(target=self.preload_loop, daemon=True)
        self.preloader_thread.start()

        # Sledování souboru v Inkscape
        self.inkscape_watch_file = None
        if INKSCAPE_WATCH_STATE_FILE.exists():
            try:
                with open(INKSCAPE_WATCH_STATE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    # Obnovíme Path objekty
                    data["original_path"] = Path(data["original_path"])
                    data["edit_path"] = Path(data["edit_path"])
                    self.inkscape_watch_file = data
            except Exception:
                INKSCAPE_WATCH_STATE_FILE.unlink(missing_ok=True)
        self.inkscape_watch_thread = threading.Thread(target=self.watch_inkscape_file_loop, daemon=True)
        self.inkscape_watch_thread.start()

        # UI
        self.setup_ui()

        if self.svg_files:
            self.load_svg(0)

        # šipky pro navigaci
        self.bind("<Left>", self.prev_svg)
        self.bind("<Right>", self.next_svg)

        # klávesové zkratky
        for key in ["x", "X"]:
            self.bind(key, lambda e: self.toggle_mark_file())  # označit/odznačit
        for key in ["s", "S", "<Return>"]:
            self.bind(key, lambda e: self.save_svg())  # uložit SVG
        for key in ["v", "V"]:
            self.bind(key, lambda e: self.add_png())   # vložit PNG/JPG
        for key in ["i", "I"]:
            self.bind(key, lambda e: self.open_in_inkscape()) # otevřít v Inkscape

        self.protocol("WM_DELETE_WINDOW", self.on_close)

    # ---------------- UI ----------------
    def setup_ui(self):
        main_frame = tk.Frame(self)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # levý panel
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
        self.tree.tag_configure("marked_file", foreground="red")
        self.tree.tag_configure("inkscape_edit_file", foreground="purple", font=("Segoe UI", 10, "bold"))
        self.tree.tag_configure("active_file", background="#cce5ff", font=("Segoe UI", 10, "bold"))

        self.saved_count_label = tk.Label(left_frame, text="")
        self.saved_count_label.pack(pady=(0, 10))

        # canvas
        self.canvas = tk.Canvas(main_frame, bg="white")
        self.canvas.pack(side=tk.LEFT, expand=True, fill=tk.BOTH)
        self.canvas.bind("<ButtonPress-1>", self.start_drag)
        self.canvas.bind("<B1-Motion>", self.do_drag)
        self.canvas.bind("<MouseWheel>", self.on_mouse_wheel)
        self.canvas.bind("<Button-4>", self.on_mouse_wheel)
        self.canvas.bind("<Button-5>", self.on_mouse_wheel)
        self.canvas.drop_target_register(DND_FILES)
        self.canvas.dnd_bind('<<Drop>>', self.drop_file)

        # pravý panel
        right_frame = tk.Frame(main_frame, width=160)
        right_frame.pack(side=tk.RIGHT, fill=tk.Y)

        self.add_png_btn = tk.Button(right_frame, text="Přidat PNG/JPG", command=self.add_png)
        self.add_png_btn.pack(pady=10)

        self.save_btn = tk.Button(right_frame, text="Uložit SVG", command=self.save_svg)
        self.save_btn.pack(pady=10)

        self.mark_btn = tk.Button(right_frame, text="Označit", command=self.toggle_mark_file)
        self.mark_btn.pack(pady=10)

        tk.Label(right_frame, text="Průhlednost:").pack(pady=(10,0))
        # slider teď volá update_image_opacity s write_config=True (uloží změnu do configu, debounce)
        self.opacity_slider = tk.Scale(
            right_frame, from_=0.2, to=1, resolution=0.01,
            orient=tk.HORIZONTAL, variable=self.opacity_var,
            command=lambda v: self.update_image_opacity(v, write_config=True)
        )
        self.opacity_slider.pack(fill=tk.X, padx=5)

        self.open_inkscape_btn = tk.Button(right_frame, text="Otevřít v Inkscape", command=self.open_in_inkscape)
        self.open_inkscape_btn.pack(side=tk.BOTTOM, pady=10)

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
            has_marked_in_cat = any(full_path in self.marked_files for _, full_path in files)
            for file, full_path in sorted(files):
                tags = []
                rel_path = full_path.relative_to(OUTPUT_FOLDER)
                inkscape_edit_path = INKSCAPE_EDIT_FOLDER / rel_path
                edited_path = EDITED_SVG_FOLDER / rel_path
                # Priorita barev: červená > fialová > zelená
                if full_path in self.marked_files:
                    tags.append("marked_file")
                elif inkscape_edit_path.exists():
                    tags.append("inkscape_edit_file")
                elif edited_path.exists():
                    tags.append("saved_file")

                if self.current_svg_path == full_path:
                    tags.append("active_file")
                self.tree.insert(cat_id, "end", text=file, values=[str(full_path)], tags=tuple(tags))
            if has_marked_in_cat:
                self.tree.item(cat_id, tags=("marked_file",))

        # Spočítáme "uložené" soubory podle existence v EDITED_SVG_FOLDER
        saved_count = sum(1 for f in self.svg_files if (EDITED_SVG_FOLDER / f.relative_to(OUTPUT_FOLDER)).exists())
        total = len(self.svg_files)
        self.saved_count_label.config(text=f"Uloženo: {saved_count} / {total}")

    def toggle_mark_file(self):
        if not hasattr(self, "current_svg_path") or self.current_svg_path is None:
            return
        path = self.current_svg_path
        if path in self.marked_files:
            self.marked_files.remove(path)
        else:
            self.marked_files.add(path)
        try:
            with open(self.marked_files_path, "w", encoding="utf-8") as f:
                json.dump([str(p) for p in self.marked_files], f, ensure_ascii=False, indent=2)
        except Exception:
            pass
        # Aktualizujeme strom a text tlačítka
        self.update_tree()
        self.update_mark_button_text()

    def update_mark_button_text(self):
        is_marked = self.current_svg_path and self.current_svg_path in self.marked_files
        self.mark_btn.config(text="Odznačit" if is_marked else "Označit")

    def on_tree_select(self, event):
        selected = self.tree.selection()
        if not selected:
            return
        item_id = selected[0]
        parent_id = self.tree.parent(item_id)
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

    # ---------------- načítání SVG ----------------
    def load_svg(self, index):
        self.current_index = index
        self.load_svg_by_path(self.svg_files[index])

    def load_svg_by_path(self, path: Path):
        self.loading_path = path
        self.current_svg_path = path
        if path in self.svg_files:
            self.current_index = self.svg_files.index(path)

        # Aktualizujeme text tlačítka pro označení
        self.update_mark_button_text()

        self.canvas.delete("all")
        self.canvas.create_text(self.canvas.winfo_width() // 2, self.canvas.winfo_height() // 2,
                                text="Načítám SVG...", font=("Arial", 20), fill="gray")

        def load_thread():
            try:
                # Prioritně zkusíme načíst upravený soubor
                edited_path = EDITED_SVG_FOLDER / path.relative_to(OUTPUT_FOLDER)
                load_path = edited_path if edited_path.exists() else path

                if load_path in self.svg_cache:
                    img = self.svg_cache[load_path]
                else:
                    png_data = svg_to_png_bytes_threadsafe(load_path)
                    img = Image.open(io.BytesIO(png_data)).convert("RGBA")
                    self.svg_cache[load_path] = img

                if self.loading_path != path:
                    return
                self.img = img
                parser = ET.XMLParser(huge_tree=True)
                self.tree_xml = ET.parse(path, parser=parser)
                self.root = self.tree_xml.getroot()
                self.after(0, self.center_display_svg)
                self.after(0, lambda: self.highlight_active_tree_item(path))
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Chyba při načítání SVG", str(e)))

        threading.Thread(target=load_thread, daemon=True).start()

    def center_display_svg(self):
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
        if getattr(self, "original_img", None) is not None:
            # při načtení SVG jen aplikuj existující vložený obrázek (neukládej config)
            self.load_dropped_image(None)

    def highlight_active_tree_item(self, path: Path):
        for cat in self.tree.get_children():
            for sub in self.tree.get_children(cat):
                tags = [t for t in self.tree.item(sub, "tags") if t != "active_file"]
                self.tree.item(sub, tags=tuple(tags))
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
        self.update_tree()

    # ---------------- obrázky ----------------
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
        """
        Rychlé interaktivní zvětšení/zmenšení vloženého obrázku.
        Provádí pouze jeden rychlý resize (BILINEAR) a aplikaci opacity.
        NEVOLÁ ukládání configu.
        """
        if getattr(self, "original_img", None) is None or not hasattr(self, "canvas_image_id"):
            return

        # získej delta (Windows/macOS/Linux)
        delta = 0
        if hasattr(event, "delta"):
            delta = event.delta
        else:
            # Button-4 / Button-5 (X11)
            num = getattr(event, "num", None)
            if num == 4:
                delta = 120
            elif num == 5:
                delta = -120

        # jemnější krok podle hodnoty delta
        if abs(delta) >= 240:
            step = 1.2 if delta > 0 else 0.8
        elif abs(delta) >= 120:
            step = 1.1 if delta > 0 else 0.9
        else:
            step = 1.05 if delta > 0 else 0.95

        new_w = max(1, self.image_size[0] * step)
        new_h = max(1, self.image_size[1] * step)
        self.image_size = (new_w, new_h)

        # rychlý resample pro interaktivitu (BILINEAR)
        img = self.original_img
        if img.mode != "RGBA":
            img = img.convert("RGBA")
        img_resized = img.resize((max(1, int(new_w)), max(1, int(new_h))), Image.Resampling.BILINEAR)

        # aplikuj aktuální opacity (bez dalšího resamplu)
        try:
            opacity = max(0.2, float(self.opacity_var.get()))
        except Exception:
            opacity = 1.0
        alpha = img_resized.split()[3].point(lambda p: int(p * opacity))
        img_resized.putalpha(alpha)

        self.tk_img = ImageTk.PhotoImage(img_resized)
        self.canvas.itemconfig(self.canvas_image_id, image=self.tk_img)

        # přesun/rámeček
        if hasattr(self, "canvas_box_id"):
            self.canvas.coords(
                self.canvas_box_id,
                int(self.image_pos[0]), int(self.image_pos[1]),
                int(self.image_pos[0] + self.image_size[0]), int(self.image_pos[1] + self.image_size[1])
            )

        # NEUkládej config zde (wheel změny nevyžadují zápis)
        # pokud chceš, aby se po dokončení zoomu prováděl kvalitnější resample, můžeš zde zavolat
        # např. self._finalize_interactive_resize() - ale není nutné.

    def load_dropped_image(self, img_path=None):
        if img_path is not None:
            img = Image.open(img_path).convert("RGBA")
            self.original_img = img
        img = self.original_img
        if img is None:
            return
        self.image_size = img.size
        self.image_pos = (self.canvas_offset[0] + 50, self.canvas_offset[1] + 50)
        self.tk_img = ImageTk.PhotoImage(img)
        for attr in ("canvas_image_id", "canvas_box_id"):
            if hasattr(self, attr):
                try:
                    self.canvas.delete(getattr(self, attr))
                except Exception:
                    pass
                try:
                    delattr(self, attr)
                except Exception:
                    pass
        self.canvas_image_id = self.canvas.create_image(
            self.image_pos[0], self.image_pos[1], anchor="nw", image=self.tk_img
        )
        self.canvas_box_id = self.canvas.create_rectangle(
            int(self.image_pos[0]), int(self.image_pos[1]),
            int(self.image_pos[0]+self.image_size[0]), int(self.image_pos[1]+self.image_size[1]),
            outline="red", width=2
        )
        # aplikovat průhlednost (neukládat config)
        self.update_image_opacity(self.opacity_var.get(), write_config=False)

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

    # ---------------- opacity ----------------
    def update_image_opacity(self, value, write_config=False):
        """
        Přepočítá a zobrazí obraz podle opacity.
        Pokud write_config==True, provede debounced uložení do config.json (pouze slider).
        """
        if getattr(self, "original_img", None) is None or not hasattr(self, "canvas_image_id"):
            return
        try:
            opacity = max(0.2, float(value))  # min 0.2
        except Exception:
            opacity = 1.0
        self.opacity_var.set(opacity)

        # resize once podle self.image_size (pouze jednou)
        img = self.original_img.copy()
        if img.mode != "RGBA":
            img = img.convert("RGBA")
        w = max(1, int(self.image_size[0]))
        h = max(1, int(self.image_size[1]))
        # kvalitní resize pro stabilní zobrazení - BILINEAR pro interaktivitu
        img = img.resize((w, h), Image.Resampling.BILINEAR)
        alpha = img.split()[3].point(lambda p: int(p * opacity))
        img.putalpha(alpha)
        self.tk_img = ImageTk.PhotoImage(img)
        self.canvas.itemconfig(self.canvas_image_id, image=self.tk_img)

        # aktualizace rámečku
        if hasattr(self, "canvas_box_id"):
            self.canvas.coords(
                self.canvas_box_id,
                int(self.image_pos[0]), int(self.image_pos[1]),
                int(self.image_pos[0] + self.image_size[0]), int(self.image_pos[1] + self.image_size[1])
            )

        # pokud má volání uložet config (slider), použij debounce
        if write_config:
            if self._alpha_save_after_id is not None:
                try:
                    self.after_cancel(self._alpha_save_after_id)
                except Exception:
                    pass
            # po 300 ms od poslední změny zapíš config
            self._alpha_save_after_id = self.after(300, self._save_alpha_to_config)

    def _save_alpha_to_config(self):
        config_path = PROJECT_PATH / "config.json"
        config_data = {}
        if config_path.exists():
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    config_data = json.load(f)
            except Exception:
                config_data = {}
        if "editor" not in config_data:
            config_data["editor"] = {}
        config_data["editor"]["alpha"] = float(self.opacity_var.get())
        try:
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(config_data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
        # clear debounce id
        self._alpha_save_after_id = None

    # ---------------- Inkscape ----------------
    def open_in_inkscape(self):
        if not hasattr(self, "current_svg_path") or not self.current_svg_path.exists():
            messagebox.showerror("Chyba", "Žádný SVG soubor k otevření")
            return

        # Zjistíme, kterou verzi souboru otevřít (upravenou, nebo originál)
        original_path = self.current_svg_path
        rel_path = original_path.relative_to(OUTPUT_FOLDER)
        edited_path = EDITED_SVG_FOLDER / rel_path
        source_path = edited_path if edited_path.exists() else original_path

        # Cílová cesta v dočasné složce
        inkscape_dest_path = INKSCAPE_EDIT_FOLDER / rel_path

        if self.inkscape_watch_file and self.inkscape_watch_file["edit_path"].exists():
             messagebox.showwarning("Pozor", "Už je editován jiný soubor. Nejdříve ho uložte v Inkscape.")
             return

        try:
            # Vytvoříme adresáře a zkopírujeme soubor
            inkscape_dest_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, inkscape_dest_path)
 
            # Uložíme si informace pro sledování
            watch_info = {
                "original_path": original_path,
                "edit_path": inkscape_dest_path,
                "mtime": inkscape_dest_path.stat().st_mtime
            }
            self.inkscape_watch_file = watch_info

            # Uložíme stav do JSON souboru pro případ restartu
            with open(INKSCAPE_WATCH_STATE_FILE, "w", encoding="utf-8") as f:
                # Uložíme cesty jako stringy
                save_data = watch_info.copy()
                save_data["original_path"] = str(save_data["original_path"])
                save_data["edit_path"] = str(save_data["edit_path"])
                json.dump(save_data, f, indent=2)

            # Spustíme Inkscape
            subprocess.Popen([str(INKSCAPE_PATH), str(inkscape_dest_path)])
            self.update_tree()
        except Exception as e:
            messagebox.showerror("Chyba", f"Nepodařilo se otevřít Inkscape: {e}")

    def watch_inkscape_file_loop(self):
        while not self.stop_preloader.is_set():
            if self.inkscape_watch_file:
                path = self.inkscape_watch_file["edit_path"]
                if path.exists():
                    try:
                        current_mtime = path.stat().st_mtime
                        if current_mtime > self.inkscape_watch_file["mtime"]:
                            # Soubor se změnil!
                            self.after(0, self.handle_inkscape_save)
                    except FileNotFoundError:
                        # Soubor byl mezitím smazán
                        self.inkscape_watch_file = None
                        INKSCAPE_WATCH_STATE_FILE.unlink(missing_ok=True)
                        self.after(0, self.update_tree)
                else:
                    # Soubor už neexistuje
                    self.inkscape_watch_file = None
                    INKSCAPE_WATCH_STATE_FILE.unlink(missing_ok=True)
                    self.after(0, self.update_tree)
            time.sleep(1)

    # ---------------- uložení SVG (z editoru) ----------------
    def save_svg(self):
        if getattr(self, "original_img", None) is None:
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

            # Uložíme do nové složky
            save_path = EDITED_SVG_FOLDER / self.current_svg_path.relative_to(OUTPUT_FOLDER)
            save_path.parent.mkdir(parents=True, exist_ok=True)
            self.tree_xml.write(save_path, encoding="utf-8", xml_declaration=True)

            messagebox.showinfo("Hotovo", f"SVG uložen: {self.current_svg_path}")
            self.original_img = None
            for attr in ("canvas_image_id", "canvas_box_id"):
                if hasattr(self, attr):
                    try:
                        self.canvas.delete(getattr(self, attr))
                    except Exception:
                        pass
                    try:
                        delattr(self, attr)
                    except Exception:
                        pass
            # Vyčistíme cache pro oba možné soubory (původní i upravený)
            self.svg_cache.pop(save_path, None)
            self.svg_cache.pop(self.current_svg_path, None)

            self.load_svg_by_path(self.current_svg_path)
        except Exception as e:
            messagebox.showerror("Chyba při ukládání", str(e))

    def handle_inkscape_save(self):
        if not self.inkscape_watch_file:
            return

        watch_info = self.inkscape_watch_file
        self.inkscape_watch_file = None # Zabráníme dvojímu zpracování

        source_path = watch_info["edit_path"]
        original_path = watch_info["original_path"]
        rel_path = original_path.relative_to(OUTPUT_FOLDER)
        dest_path = EDITED_SVG_FOLDER / rel_path

        try:
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(source_path, dest_path) # Přesuneme soubor

            # Vyčistíme cache, aby se náhled načetl znovu
            self.svg_cache.pop(dest_path, None)
            self.svg_cache.pop(original_path, None)

            # Pokud je to aktuálně zobrazený soubor, načteme ho znovu
            if self.current_svg_path == original_path:
                self.load_svg_by_path(original_path)
        except Exception as e:
            messagebox.showerror("Chyba", f"Nepodařilo se zpracovat uložený soubor z Inkscape: {e}")
        finally:
            self.update_tree()
            # Vyčistíme soubor se stavem
            INKSCAPE_WATCH_STATE_FILE.unlink(missing_ok=True)

    # ---------------- preloader ----------------
    def preload_loop(self):
        while not self.stop_preloader.is_set():
            if not self.svg_files:
                time.sleep(1)
                continue
            current = getattr(self, "current_index", 0)
            indices = [(current - i) % len(self.svg_files) for i in range(3,0,-1)] + \
                        [(current + i) % len(self.svg_files) for i in range(0,6)]
            for idx in indices:
                if self.stop_preloader.is_set():
                    return
                original_path = self.svg_files[idx]
                edited_path = EDITED_SVG_FOLDER / original_path.relative_to(OUTPUT_FOLDER)
                load_path = edited_path if edited_path.exists() else original_path
    
                if load_path not in self.svg_cache:
                    try:
                        if INKSCAPE_LOCK.locked():
                            time.sleep(0.1)
                            continue
                        png_data = svg_to_png_bytes_threadsafe(load_path)
                        img = Image.open(io.BytesIO(png_data)).convert("RGBA")
                        self.svg_cache[load_path] = img
                    except Exception:
                        pass
            time.sleep(1)
    
    # ---------------- ukončení ----------------
    def on_close(self):
        self.stop_preloader.set()
        # cancel pending alpha save
        if self._alpha_save_after_id is not None:
            try:
                self.after_cancel(self._alpha_save_after_id)
            except Exception:
                pass
        self.destroy()

# ---------------- spustit ----------------
if __name__ == "__main__":
    app = SVGEditor()
    app.mainloop()