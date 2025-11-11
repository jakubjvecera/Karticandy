# -*- coding: utf-8 -*-
import tkinter as tk
from tkinter import messagebox, simpledialog, filedialog
import subprocess
import threading
import time
from datetime import datetime
import os
import json
import shutil

SCRIPTS = {
    "Generátor": "generator.py",
    "Editor": "editor.py",
    "Převod": "prevod.py",
    "Tisk": "tisk.py"
}

PROJECTS_DIR = "projekty"  # Hlavní složka pro všechny projekty
DEFAULT_CONFIG = {
    "generator": {"rozměr_karty": "63x88mm", "barvy": "RGB"},
    "editor": {"font": "Arial", "velikost": 12},
    "prevod": {"formát": "PNG"},
    "tisk": {"printer": "HP_LaserJet", "duplex": True},
    "zdroje": {"excel": "", "sablona": ""}
}


# ---------------- Pomocné okno pro výběr projektu ----------------
def select_project_window(root):
    """Zobrazí okno pro výběr nebo vytvoření projektu a vrátí jeho název."""
    os.makedirs(PROJECTS_DIR, exist_ok=True)
    projects = [d for d in os.listdir(PROJECTS_DIR) if os.path.isdir(os.path.join(PROJECTS_DIR, d))]

    selected_project = tk.StringVar(value="")

    def create_project(choice):
        project_path = os.path.join(PROJECTS_DIR, choice)
        os.makedirs(project_path, exist_ok=True)
        os.makedirs(os.path.join(project_path, "data"), exist_ok=True)
        os.makedirs(os.path.join(project_path, "výstupy"), exist_ok=True)
        config_path = os.path.join(project_path, "config.json")
        if not os.path.isfile(config_path):
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(DEFAULT_CONFIG, f, indent=4)
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


# ---------------- Hlavní GUI ----------------
class ScriptGUI:
    def __init__(self, root, current_project):
        self.root = root
        self.root.title("Správce Skriptů")
        self.current_project = current_project

        # Rámečky
        top_frame = tk.Frame(root)
        top_frame.pack(side=tk.TOP, fill=tk.X, padx=10, pady=10)

        console_frame = tk.Frame(root)
        console_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Tlačítko "Zdroje" vpravo nahoře
        source_btn = tk.Button(top_frame, text="Zdroje", command=self.open_source_window, bg="#e0e0e0", width=10)
        source_btn.pack(side=tk.RIGHT, padx=10)

        # Slovníky pro tlačítka, časové štítky a startovní časy
        self.buttons = {}
        self.time_labels = {}
        self.running_times = {}

        # Tlačítka skriptů
        for name in SCRIPTS.keys():
            btn_frame = tk.Frame(top_frame)
            btn_frame.pack(side=tk.LEFT, padx=8)

            btn = tk.Button(btn_frame, text=name, width=12, command=lambda n=name: self.confirm_and_run(n))
            btn.pack(side=tk.TOP)
            self.buttons[name] = btn

        # Konzole
        self.console = tk.Text(console_frame, wrap=tk.WORD, height=20, width=60, state='disabled')
        self.console.pack(fill=tk.BOTH, expand=True)
        self.console.tag_configure("bold_time", font=("Arial", 10, "bold"))

        # Zobrazíme aktuální projekt
        self.project_label = tk.Label(root, text=f"Aktuální projekt: {self.current_project}", font=("Arial", 10, "italic"))
        self.project_label.pack(side=tk.BOTTOM, pady=5)

    # ---------------- Okno pro výběr zdrojů ----------------
    def open_source_window(self):
        """Umožní uživateli vybrat Excel a šablonu, které se uloží do data/."""
        top = tk.Toplevel(self.root)
        top.title("Zdroje projektu")
        top.geometry("400x250")

        # Zajistí, že okno zůstane nad hlavním
        top.transient(self.root)
        top.grab_set()
        top.focus_force()
        top.lift()

        project_path = os.path.join(PROJECTS_DIR, self.current_project)
        data_path = os.path.join(project_path, "data")
        config_path = os.path.join(project_path, "config.json")

        # Načteme config a doplníme klíč "zdroje", pokud chybí
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)

        if "zdroje" not in config:
            config["zdroje"] = {"excel": "", "sablona": ""}
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=4)

        excel_var = tk.StringVar(value=config["zdroje"].get("excel", ""))
        sablona_var = tk.StringVar(value=config["zdroje"].get("sablona", ""))

        def select_excel():
            file = filedialog.askopenfilename(
                title="Vyberte Excel soubor",
                filetypes=[("Excel files", "*.xlsx")],
                parent=top
            )
            if file:
                excel_var.set(file)

        def select_sablona():
            file = filedialog.askopenfilename(
                title="Vyberte šablonu",
                filetypes=[("Svg files", "*.svg*")],
                parent=top
            )
            if file:
                sablona_var.set(file)

        def save_sources():
            excel_src = excel_var.get()
            sablona_src = sablona_var.get()
            if not excel_src or not sablona_src:
                messagebox.showerror("Chyba", "Musíte vybrat oba soubory!", parent=top)
                return

            try:
                excel_dst = os.path.join(data_path, os.path.basename(excel_src))
                sablona_dst = os.path.join(data_path, os.path.basename(sablona_src))
                shutil.copy2(excel_src, excel_dst)
                shutil.copy2(sablona_src, sablona_dst)

                config["zdroje"]["excel"] = os.path.basename(excel_src)
                config["zdroje"]["sablona"] = os.path.basename(sablona_src)

                with open(config_path, "w", encoding="utf-8") as f:
                    json.dump(config, f, indent=4)

                messagebox.showinfo("Hotovo", "Zdroje byly úspěšně uloženy do projektu.", parent=top)
                top.destroy()
            except Exception as e:
                messagebox.showerror("Chyba", f"Nepodařilo se uložit soubory: {e}", parent=top)

        # UI layout
        tk.Label(top, text="Vyberte soubory pro tento projekt:", font=("Arial", 11, "bold")).pack(pady=10)

        frm1 = tk.Frame(top)
        frm1.pack(pady=5, fill=tk.X, padx=10)
        tk.Label(frm1, text="Excel soubor:").pack(side=tk.LEFT)
        tk.Entry(frm1, textvariable=excel_var, width=30).pack(side=tk.LEFT, padx=5)
        tk.Button(frm1, text="Vybrat", command=select_excel).pack(side=tk.LEFT)

        frm2 = tk.Frame(top)
        frm2.pack(pady=5, fill=tk.X, padx=10)
        tk.Label(frm2, text="Šablona:").pack(side=tk.LEFT)
        tk.Entry(frm2, textvariable=sablona_var, width=30).pack(side=tk.LEFT, padx=14)
        tk.Button(frm2, text="Vybrat", command=select_sablona).pack(side=tk.LEFT)

        tk.Button(top, text="Uložit", command=save_sources, bg="#a0e0a0").pack(pady=20)

    # ---------------- Script Execution ----------------
    def confirm_and_run(self, name):
        if messagebox.askyesno("Potvrzení", f"Opravdu spustit {name}?"):
            self.run_script(name)

    def run_script(self, name):
        self.buttons[name].config(state='disabled')
        self.running_times[name] = time.time()

        if name not in self.time_labels:
            time_label = tk.Label(self.buttons[name].master, text="00:00:00", font=("Arial", 10))
            time_label.pack(side=tk.TOP, pady=2)
            self.time_labels[name] = time_label

        self._write_console(f"[{datetime.now().strftime('%H:%M:%S')}] {name} spuštěn", bold_time=True)
        threading.Thread(target=self._execute_script, args=(name,), daemon=True).start()
        self._update_time_label(name)

    def _execute_script(self, name):
        script = SCRIPTS[name]
        project_path = os.path.join(PROJECTS_DIR, self.current_project)
        try:
            process = subprocess.Popen(
                ["python", script, project_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True
            )
            for line in process.stdout:
                line = line.strip()
                self._write_console(f"[{datetime.now().strftime('%H:%M:%S')}] {name}: {line}", bold_time=True)
            process.wait()
        except Exception as e:
            self._write_console(f"[{datetime.now().strftime('%H:%M:%S')}] {name}: Chyba při spuštění: {e}", bold_time=True)
        finally:
            start_time = self.running_times.pop(name, time.time())
            elapsed = time.time() - start_time
            if name in self.time_labels:
                self.time_labels[name].destroy()
                del self.time_labels[name]

            self._write_console(f"[{datetime.now().strftime('%H:%M:%S')}] {name} dokončen, běžel {elapsed:.2f} s", bold_time=True)
            self._write_console("")
            self.buttons[name].config(state='normal')

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
            self.console.insert(tk.END, text + "\n")
        self.console.see(tk.END)
        self.console.configure(state='disabled')


# ---------------- Spouštění aplikace ----------------
if __name__ == "__main__":
    root = tk.Tk()
    root.withdraw()  # skryjeme hlavní okno při výběru projektu

    project_name = select_project_window(root)
    if not project_name:
        messagebox.showerror("Chyba", "Nebyl vybrán žádný projekt.")
    else:
        root.deiconify()  # zobrazíme hlavní GUI až teď
        app = ScriptGUI(root, project_name)
        root.geometry("800x400")
        root.mainloop()

