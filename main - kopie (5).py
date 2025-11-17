# -*- coding: utf-8 -*-
import tkinter as tk
import locale # Import pro zjištění systémového kódování
from tkinter import ttk
from tkinter import messagebox, simpledialog, filedialog
import subprocess
import threading
import time
from datetime import datetime
import os
import json
import shutil
import sys
from pathlib import Path

# ---------------- Constants ----------------
PROJECTS_DIR = Path("projekty")
SRC_DIR = Path("src")

# Ensure base directories exist
for path in [SRC_DIR, PROJECTS_DIR]: # SRC_DIR je již definováno, není třeba znovu
    path.mkdir(exist_ok=True)

DEFAULT_CONFIG = {
    "generator": {"RozmerKarty": "63.5x88.9mm"},
    "editor": {"alpha": "0.8", "PopisekKdeJeMaska":"OBRAZEK"},
    "zdroje": {"excel": "", "sablona": ""}
}

BUTTON_ORDER = ["Generator", "Editor", "Prevod", "Tisk"]

# ---------------- Load scripts from src folder ----------------
SCRIPTS = {}
for py_file in SRC_DIR.glob("*.py"):
    if py_file.name == "__init__.py":
        continue
    SCRIPTS[py_file.stem.lower()] = str(py_file)

# ---------------- Pomocné okno pro výběr projektu ----------------
def select_project_window(root):
    PROJECTS_DIR.mkdir(exist_ok=True)
    projects = [d.name for d in PROJECTS_DIR.iterdir() if d.is_dir()]

    selected_project = tk.StringVar(value="")

    def create_project(choice):
        project_path = PROJECTS_DIR / choice
        (project_path / "data").mkdir(parents=True, exist_ok=True)
        (project_path / "vystup").mkdir(exist_ok=True)
        config_path = project_path / "config.json"
        if not config_path.exists():
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(DEFAULT_CONFIG, f, indent=4, ensure_ascii=False)
        selected_project.set(choice)

    def on_select():
        sel = lb.curselection()
        if sel:
            choice = lb.get(sel[0])
            if choice == "<Nový projekt>":
                choice = simpledialog.askstring("Nový projekt", "Zadejte název nového projektu:", parent=top)
                if not choice:
                    messagebox.showerror("Chyba", "Projekt nebyl zadán.")
                    return
            create_project(choice)
            top.destroy()

    top = tk.Toplevel(root)
    top.title("Výběr projektu")
    top.geometry("300x300")
    tk.Label(top, text="Vyberte projekt nebo vytvořte nový:", font=("Arial", 10)).pack(pady=10)

    lb = tk.Listbox(top, width=30, height=10)
    lb.pack(padx=10, pady=5)

    for proj in projects:
        lb.insert(tk.END, proj)
    lb.insert(tk.END, "<Nový projekt>")

    tk.Button(top, text="Vybrat", command=on_select).pack(pady=10)
    root.wait_window(top)

    return selected_project.get()

# ---------------- Main GUI ----------------
class ScriptGUI:
    def __init__(self, root, current_project):
        self.root = root
        self.root.title("Nástroj pro tvorbu karet")
        self.current_project = current_project
        self._display_to_stem = {}

        # Frames
        top_frame = tk.Frame(root)
        top_frame.pack(side=tk.TOP, fill=tk.X, padx=10, pady=10)

        console_frame = tk.Frame(root)
        console_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Source and Settings buttons
        tk.Button(top_frame, text="Zdroje", command=self.open_source_window, bg="#e0e0e0", width=10).pack(side=tk.RIGHT, padx=10)
        tk.Button(top_frame, text="Nastavení", command=self.open_settings_window, bg="#e0e0e0", width=10).pack(side=tk.RIGHT)

        self.buttons = {}
        self.time_labels = {}
        self.running_times = {}
        self.is_script_running = False

        # Add buttons exactly according to BUTTON_ORDER
        self._add_all_buttons(top_frame)

        # Console
        self.console = tk.Text(console_frame, wrap=tk.WORD, height=20, width=60, state='disabled')
        scrollbar = ttk.Scrollbar(console_frame, orient="vertical", command=self.console.yview)
        self.console.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.console.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.console.tag_configure("bold_time", font=("Arial", 10, "bold"))

        # Status bar
        self.status_bar = tk.Label(root, text=f"Aktuální projekt: {self.current_project}", bd=1, relief=tk.SUNKEN, anchor=tk.W, font=("Arial", 10, "italic"))
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)

    # ---------------- Add a single script button ----------------
    def _add_script_button(self, parent, display_name, stem):
        frame = tk.Frame(parent)
        frame.pack(side=tk.LEFT, padx=8)
        btn = tk.Button(frame, text=display_name, width=12, command=lambda n=stem: self.confirm_and_run(n))
        btn.pack(side=tk.TOP)
        self.buttons[stem] = btn
        self._display_to_stem[display_name] = stem

    # ---------------- Add all buttons in the correct order ----------------
    def _add_all_buttons(self, parent):
        """
        Adds buttons in the order specified by BUTTON_ORDER.
        If a script is missing, its button is not created.
        """
        for display_name in BUTTON_ORDER:
            stem = display_name.lower()
            if stem in SCRIPTS:
                self._add_script_button(parent, display_name, stem)

    # ---------------- Source selection window ----------------
    def open_source_window(self):
        top = tk.Toplevel(self.root)
        top.title("Zdroje projektu")
        top.geometry("400x250")
        top.transient(self.root)
        top.grab_set()
        top.focus_force()
        top.lift()

        project_path = PROJECTS_DIR / self.current_project
        data_path = project_path / "data"
        config_path = project_path / "config.json"

        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)

        excel_var = tk.StringVar(value=config["zdroje"].get("excel", ""))
        sablona_var = tk.StringVar(value=config["zdroje"].get("sablona", ""))

        def select_excel():
            file = filedialog.askopenfilename(title="Vyberte Excel soubor", filetypes=[("Excel files", "*.xlsx")], parent=top)
            if file:
                excel_var.set(file)

        def select_sablona():
            file = filedialog.askopenfilename(title="Vyberte šablonu", filetypes=[("Svg files", "*.svg*")], parent=top)
            if file:
                sablona_var.set(file)

        def save_sources():
            excel_path = Path(excel_var.get())
            sablona_path = Path(sablona_var.get())

            if not excel_path.is_file() and config["zdroje"].get("excel"):
                excel_path = data_path / config["zdroje"]["excel"]
            if not sablona_path.is_file() and config["zdroje"].get("sablona"):
                sablona_path = data_path / config["zdroje"]["sablona"]

            if not excel_path.is_file() or not sablona_path.is_file():
                messagebox.showerror("Chyba", "Jeden nebo oba vybrané soubory neexistují.", parent=top)
                return

            try:
                data_path.mkdir(exist_ok=True)
                excel_target = data_path / excel_path.name
                sablona_target = data_path / sablona_path.name
                if excel_path.resolve() != excel_target.resolve():
                    shutil.copy2(excel_path, excel_target)
                if sablona_path.resolve() != sablona_target.resolve():
                    shutil.copy2(sablona_path, sablona_target)

                config["zdroje"]["excel"] = excel_target.name
                config["zdroje"]["sablona"] = sablona_target.name

                with open(config_path, "w", encoding="utf-8") as f:
                    json.dump(config, f, indent=4, ensure_ascii=False)

                messagebox.showinfo("Hotovo", "Zdroje byly úspěšně uloženy.", parent=top)
                top.destroy()
            except Exception as e:
                messagebox.showerror("Chyba", f"Nepodařilo se uložit soubory: {e}", parent=top)

        tk.Label(top, text="Vyberte soubory pro tento projekt:", font=("Arial", 11, "bold")).pack(pady=10)
        frm1 = tk.Frame(top); frm1.pack(pady=5, fill=tk.X, padx=10)
        tk.Label(frm1, text="Excel soubor:").pack(side=tk.LEFT)
        tk.Entry(frm1, textvariable=excel_var, width=30).pack(side=tk.LEFT, padx=5)
        tk.Button(frm1, text="Vybrat", command=select_excel).pack(side=tk.LEFT)

        frm2 = tk.Frame(top); frm2.pack(pady=5, fill=tk.X, padx=10)
        tk.Label(frm2, text="Šablona:").pack(side=tk.LEFT)
        tk.Entry(frm2, textvariable=sablona_var, width=30).pack(side=tk.LEFT, padx=14)
        tk.Button(frm2, text="Vybrat", command=select_sablona).pack(side=tk.LEFT)

        tk.Button(top, text="Uložit", command=save_sources, bg="#a0e0a0").pack(pady=20)

    # ---------------- Settings window ----------------
    def open_settings_window(self):
        top = tk.Toplevel(self.root)
        top.title("Nastavení projektu")
        top.geometry("400x400")
        top.transient(self.root)
        top.grab_set()
        top.focus_force()

        project_path = PROJECTS_DIR / self.current_project
        config_path = project_path / "config.json"
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)

        entries = {}
        frame = tk.Frame(top)
        frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        def add_field(section, key, value):
            frm = tk.Frame(frame)
            frm.pack(fill=tk.X, pady=3)
            tk.Label(frm, text=f"{section}.{key}:").pack(side=tk.LEFT)
            var = tk.StringVar(value=value)
            tk.Entry(frm, textvariable=var, width=25).pack(side=tk.RIGHT)
            entries[(section, key)] = var

        for section in config:
            if section == "zdroje":
                continue
            for key, value in config[section].items():
                if key == "alpha": # Skryjeme pole pro průhlednost v GUI
                    continue
                add_field(section, key, value)

        def save_config():
            for (section, key), var in entries.items():
                val = var.get()
                if val.lower() in ["true", "false"]:
                    val = val.lower() == "true"
                elif val.isdigit():
                    val = int(val)
                config[section][key] = val
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=4, ensure_ascii=False)
            messagebox.showinfo("Hotovo", "Nastavení uloženo.", parent=top)
            top.destroy()

        tk.Button(top, text="Uložit změny", command=save_config, bg="#a0e0a0").pack(pady=20)

    def _set_buttons_state(self, state):
        """Enable or disable all script buttons."""
        for btn in self.buttons.values():
            btn.config(state=state)

    # ---------------- Script execution ----------------
    def confirm_and_run(self, name):
        if self.is_script_running:
            messagebox.showwarning("Zaneprázdněn", "Jiný skript právě běží. Počkejte na jeho dokončení.")
            return

        # Kontrola, zda jsou vyplněny zdroje
        project_path = PROJECTS_DIR / self.current_project
        config_path = project_path / "config.json"
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
            zdroje = config.get("zdroje", {})
            if not zdroje.get("excel") or not zdroje.get("sablona"):
                messagebox.showerror("Chybějící zdroje", "Nejdříve musíte nastavit zdroje projektu.")
                return
        except (FileNotFoundError, json.JSONDecodeError) as e:
            messagebox.showerror("Chyba konfigurace", f"Nepodařilo se načíst konfigurační soubor: {e}")
            return

        if messagebox.askyesno("Potvrzení", f"Opravdu spustit {name.capitalize()}?"):
            self.run_script(name)

    def run_script(self, name):
        self.is_script_running = True
        self._set_buttons_state('disabled')
        self.running_times[name] = time.time()
        if name not in self.time_labels:
            time_label = tk.Label(self.buttons[name].master, text="00:00:00", font=("Arial", 10))
            time_label.pack(side=tk.TOP, pady=2)
            self.time_labels[name] = time_label

        self._write_console(f"[{datetime.now().strftime('%H:%M:%S')}] {name.capitalize()} spuštěn", bold_time=True)
        threading.Thread(target=self._execute_script, args=(name,), daemon=True).start()
        self._update_time_label(name)

    def _execute_script(self, name):
        script = SCRIPTS[name]
        project_path = PROJECTS_DIR / self.current_project
        try:
            process = subprocess.Popen(
                [sys.executable, script, str(project_path)], # Argumenty pro proces
                stdout=subprocess.PIPE, # Zachytáváme standardní výstup
                stderr=subprocess.STDOUT, # Zachytáváme i chybový výstup
                text=True, # Dekódujeme výstup jako text
                encoding=locale.getpreferredencoding(False), # Použijeme preferované kódování systému
                errors='replace' # Případné chyby v kódování nahradíme
            )
            for line in process.stdout:
                self._write_console(f"\t {line.strip()}")
            process.wait()
        except Exception as e:
            self._write_console(f"\t Chyba při spuštění: {e}")
        finally:
            self.is_script_running = False
            start_time = self.running_times.pop(name, time.time())
            elapsed = time.time() - start_time
            if name in self.time_labels:
                self.time_labels[name].destroy()
                del self.time_labels[name]
            self._write_console(f"{name.capitalize()} dokončen, běžel {elapsed:.2f} s")
            self._write_console("")
            self._set_buttons_state('normal')

    def _update_time_label(self, name):
        if name not in self.running_times or name not in self.time_labels:
            return
        elapsed = int(time.time() - self.running_times[name])
        hrs, rem = divmod(elapsed, 3600)
        mins, secs = divmod(rem, 60)
        self.time_labels[name].config(text=f"{hrs:02}:{mins:02}:{secs:02}")
        self.root.after(1000, lambda: self._update_time_label(name))

    def _write_console(self, text, bold_time=False):
        self.console.configure(state='normal')
        if bold_time and text.startswith("["):
            closing_bracket = text.find("]") + 1
            self.console.insert(tk.END, text[:closing_bracket], "bold_time")
            self.console.insert(tk.END, text[closing_bracket:] + "\n")
        else:
            self.console.insert(tk.END, f"{text}\n")
        self.console.see(tk.END)
        self.console.configure(state='disabled')

# ---------------- Application entry point ----------------
if __name__ == "__main__":
    root = tk.Tk()
    root.withdraw()
    project_name = select_project_window(root)
    if not project_name:
        messagebox.showerror("Chyba", "Nebyl vybrán žádný projekt.")
    else:
        root.deiconify()
        app = ScriptGUI(root, project_name)
        root.geometry("850x450")
        root.mainloop()
