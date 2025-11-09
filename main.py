# -*- coding: utf-8 -*-
import tkinter as tk
from tkinter import messagebox, scrolledtext
import subprocess
import threading
import time
from datetime import datetime

SCRIPTS = {
    "Generátor": "generator.py",
    "Editor": "editor.py",
    "Převod": "prevod.py",
    "Tisk": "tisk.py"
}

class ScriptGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Správce Skriptů")

        # Rámečky
        top_frame = tk.Frame(root)
        top_frame.pack(side=tk.TOP, fill=tk.X, padx=10, pady=10)

        console_frame = tk.Frame(root)
        console_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Slovníky pro tlačítka, časové štítky a startovní časy
        self.buttons = {}
        self.time_labels = {}
        self.running_times = {}

        # Tlačítka
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

    def confirm_and_run(self, name):
        if messagebox.askyesno("Potvrzení", f"Opravdu spustit {name}?"):
            self.run_script(name)

    def run_script(self, name):
        """Spustí skript a vytvoří časový štítek pod tlačítkem."""
        self.buttons[name].config(state='disabled')
        self.running_times[name] = time.time()

        # Vytvoříme časový štítek pod tlačítkem až teď
        if name not in self.time_labels:
            time_label = tk.Label(self.buttons[name].master, text="00:00:00", font=("Arial", 10))
            time_label.pack(side=tk.TOP, pady=2)
            self.time_labels[name] = time_label

        self._write_console(f"[{datetime.now().strftime('%H:%M:%S')}] {name} spuštěn", bold_time=True)
        threading.Thread(target=self._execute_script, args=(name,), daemon=True).start()
        self._update_time_label(name)

    def _execute_script(self, name):
        """Spustí skript a vypisuje jeho výstup do konzole s časem."""
        script = SCRIPTS[name]
        try:
            process = subprocess.Popen(
                ["python", script],
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
            # Skript skončil
            start_time = self.running_times.pop(name, time.time())
            elapsed = time.time() - start_time
            # Odstraníme časový štítek
            if name in self.time_labels:
                self.time_labels[name].destroy()
                del self.time_labels[name]

            self._write_console(f"[{datetime.now().strftime('%H:%M:%S')}] {name} dokončen, běžel {elapsed:.2f} s", bold_time=True)
            self._write_console("")  # prázdný řádek po dokončení
            self.buttons[name].config(state='normal')

    def _update_time_label(self, name):
        """Aktualizuje čas běhu skriptu u tlačítka."""
        if name not in self.running_times or name not in self.time_labels:
            return
        elapsed = int(time.time() - self.running_times[name])
        hrs, rem = divmod(elapsed, 3600)
        mins, secs = divmod(rem, 60)
        self.time_labels[name].config(text=f"{hrs:02}:{mins:02}:{secs:02}")
        self.root.after(1000, lambda: self._update_time_label(name))

    def _write_console(self, text, bold_time=False):
        """Zapíše text do konzole, volitelně s tučným časem."""
        self.console.configure(state='normal')
        if bold_time and text.startswith("["):
            closing_bracket = text.find("]") + 1
            self.console.insert(tk.END, text[:closing_bracket], "bold_time")
            self.console.insert(tk.END, text[closing_bracket:] + "\n")
        else:
            self.console.insert(tk.END, text + "\n")
        self.console.see(tk.END)
        self.console.configure(state='disabled')


if __name__ == "__main__":
    root = tk.Tk()
    app = ScriptGUI(root)
    root.geometry("800x400")
    root.mainloop()

