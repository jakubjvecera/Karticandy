# -*- coding: utf-8 -*-
import os
from pathlib import Path
import tempfile
import base64
import subprocess
import io
from PIL import Image, ImageTk
import lxml.etree as ET
from tkinter import filedialog, messagebox
from tkinterdnd2 import DND_FILES, TkinterDnD
import tkinter as tk

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

def replace_images_in_svg(tree, images_info):
    root = tree.getroot()
    group = root.find('.//svg:g[@inkscape:label="OBRAZEK"]', NS)
    if group is None:
        raise ValueError("Skupina s label 'OBRAZEK' nebyla nalezena")

    # odstraníme všechny existující <image>
    for img_el in group.findall('.//svg:image', NS):
        group.remove(img_el)

    for info in images_info:
        img_el = ET.SubElement(group, "{http://www.w3.org/2000/svg}image")
        img_data = Path(info['path']).read_bytes()
        mime = "image/jpeg" if info['path'].lower().endswith((".jpg", ".jpeg")) else "image/png"
        b64_data = base64.b64encode(img_data).decode("utf-8")
        img_el.set("{http://www.w3.org/1999/xlink}href", f"data:{mime};base64,{b64_data}")
        img_el.set("x", str(info['pos'][0]))
        img_el.set("y", str(info['pos'][1]))
        img_el.set("width", str(info['size'][0]))
        img_el.set("height", str(info['size'][1]))

class SVGEditor(TkinterDnD.Tk):
    def __init__(self):
        super().__init__()
        self.title("SVG Editor s PNG/JPG vkládáním")
        self.geometry("1200x800")

        self.svg_files = [f for f in os.listdir(OUTPUT_FOLDER) if f.endswith(".svg")]
        self.current_index = 0

        self.drag_data = {"x": 0, "y": 0}
        self.images = []  # [{'img', 'tk', 'pos', 'size', 'canvas_id', 'path'}]
        self.undo_stack = []
        self.redo_stack = []

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

        # Drag & drop
        self.canvas.drop_target_register(DND_FILES)
        self.canvas.dnd_bind('<<Drop>>', self.on_drop)

        self.right_frame = tk.Frame(self)
        self.right_frame.pack(side=tk.RIGHT, fill=tk.Y)

        self.add_png_btn = tk.Button(self.right_frame, text="Přidat PNG/JPG", command=self.add_png)
        self.add_png_btn.pack(pady=10)

        self.undo_btn = tk.Button(self.right_frame, text="Undo", command=self.undo)
        self.undo_btn.pack(pady=5)
        self.redo_btn = tk.Button(self.right_frame, text="Redo", command=self.redo)
        self.redo_btn.pack(pady=5)

        self.save_btn = tk.Button(self.right_frame, text="Uložit SVG", command=self.save_svg)
        self.save_btn.pack(pady=10)

        self.zoom_in_btn = tk.Button(self.right_frame, text="Zvětšit", command=lambda: self.resize_selected(1.1))
        self.zoom_in_btn.pack(pady=5)
        self.zoom_out_btn = tk.Button(self.right_frame, text="Zmenšit", command=lambda: self.resize_selected(0.9))
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
            self.svg_tk_img = ImageTk.PhotoImage(self.img)
        except Exception as e:
            messagebox.showerror("Chyba", f"Nepodařilo se načíst SVG: {e}")
            return

        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor="nw", image=self.svg_tk_img)

        self.tree = ET.parse(self.current_svg_path)
        self.root = self.tree.getroot()
        self.images.clear()

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
        self.selected = None
        for img in reversed(self.images):
            x, y = img['pos']
            w, h = img['size']
            if x <= event.x <= x + w and y <= event.y <= y + h:
                self.selected = img
                break
        if self.selected:
            self.draw_border(self.selected)

    def do_drag(self, event):
        if not self.selected:
            return
        dx = event.x - self.drag_data["x"]
        dy = event.y - self.drag_data["y"]
        self.canvas.move(self.selected['canvas_id'], dx, dy)
        self.selected['pos'] = (self.selected['pos'][0] + dx, self.selected['pos'][1] + dy)
        self.drag_data["x"] = event.x
        self.drag_data["y"] = event.y
        self.draw_border(self.selected)

    def resize_selected(self, scale_factor):
        if not hasattr(self, 'selected') or self.selected is None:
            return
        img_obj = self.selected['img']
        w, h = self.selected['size']
        ratio = w / h
        new_w = w * scale_factor
        new_h = new_w / ratio
        self.selected['size'] = (new_w, new_h)
        img_resized = img_obj.resize((int(new_w), int(new_h)), Image.Resampling.LANCZOS)
        self.selected['tk'] = ImageTk.PhotoImage(img_resized)
        self.canvas.itemconfig(self.selected['canvas_id'], image=self.selected['tk'])
        self.draw_border(self.selected)

    def draw_border(self, img_dict):
        if hasattr(self, 'border_id'):
            self.canvas.delete(self.border_id)
        x, y = img_dict['pos']
        w, h = img_dict['size']
        self.border_id = self.canvas.create_rectangle(x, y, x + w, y + h, outline="red", width=2, dash=(4,2))

    # --- Přidání obrázků ---
    def add_png(self):
        img_path = filedialog.askopenfilename(filetypes=[("Obrázky", "*.png;*.jpg;*.jpeg")])
        if img_path:
            self.add_image_to_canvas(img_path)

    def on_drop(self, event):
        files = self.tk.splitlist(event.data)
        for f in files:
            if f.lower().endswith((".png",".jpg",".jpeg")):
                self.add_image_to_canvas(f)

    def add_image_to_canvas(self, img_path):
        try:
            img = Image.open(img_path)
            tk_img = ImageTk.PhotoImage(img)
            canvas_id = self.canvas.create_image(50, 50, anchor="nw", image=tk_img)
            self.images.append({'img': img, 'tk': tk_img, 'pos': (50,50), 'size': img.size, 'canvas_id': canvas_id, 'path': img_path})
            self.selected = self.images[-1]
            self.push_undo()
            self.draw_border(self.selected)
        except Exception as e:
            messagebox.showerror("Chyba", f"Nepodařilo se načíst obrázek: {e}")

    # --- Undo / Redo ---
    def push_undo(self):
        snapshot = [(img['path'], img['pos'], img['size']) for img in self.images]
        self.undo_stack.append(snapshot)
        self.redo_stack.clear()

    def undo(self):
        if not self.undo_stack:
            return
        self.redo_stack.append([(img['path'], img['pos'], img['size']) for img in self.images])
        snapshot = self.undo_stack.pop()
        self.restore_snapshot(snapshot)

    def redo(self):
        if not self.redo_stack:
            return
        self.undo_stack.append([(img['path'], img['pos'], img['size']) for img in self.images])
        snapshot = self.redo_stack.pop()
        self.restore_snapshot(snapshot)

    def restore_snapshot(self, snapshot):
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor="nw", image=self.svg_tk_img)
        self.images.clear()
        for path, pos, size in snapshot:
            img = Image.open(path)
            tk_img = ImageTk.PhotoImage(img.resize((int(size[0]), int(size[1])), Image.Resampling.LANCZOS))
            canvas_id = self.canvas.create_image(pos[0], pos[1], anchor="nw", image=tk_img)
            self.images.append({'img': img, 'tk': tk_img, 'pos': pos, 'size': size, 'canvas_id': canvas_id, 'path': path})
        if self.images:
            self.selected = self.images[-1]
            self.draw_border(self.selected)

    # --- Uložení SVG ---
    def save_svg(self):
        if not self.images:
            messagebox.showerror("Chyba", "Nejdříve vložte obrázky")
            return
        try:
            svg_width = parse_svg_length(self.root.get("width")) or self.img.width
            svg_height = parse_svg_length(self.root.get("height")) or self.img.height

            images_info = []
            for img in self.images:
                rel_x = img['pos'][0] / self.img.width * svg_width
                rel_y = img['pos'][1] / self.img.height * svg_height
                rel_w = img['size'][0] / self.img.width * svg_width
                rel_h = img['size'][1] / self.img.height * svg_height
                images_info.append({'path': img['path'], 'pos': (rel_x, rel_y), 'size': (rel_w, rel_h)})

            with tempfile.TemporaryDirectory() as tmpdir:
                for i, img_dict in enumerate(self.images):
                    tmp_path = os.path.join(tmpdir, f"image{i}.png")
                    img_dict['img'].save(tmp_path)
                    images_info[i]['path'] = tmp_path

                replace_images_in_svg(self.tree, images_info)

            self.tree.write(self.current_svg_path)
            messagebox.showinfo("Hotovo", f"SVG uložen: {self.current_svg_path}")
        except Exception as e:
            messagebox.showerror("Chyba", str(e))

if __name__ == "__main__":
    app = SVGEditor()
    app.mainloop()

