# -*- coding: utf-8 -*-
import tkinter as tk
from tkinter import messagebox, scrolledtext
import subprocess
import threading

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

        # Hlavní rámce
        top_frame = tk.Frame(root)
        top_frame.pack(side=tk.TOP, fill=tk.X, padx=10, pady=10)

        console_frame = tk.Frame(root)
        console_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Slovníky pro indikátory a tlačítka
        self.indicators = {}
        self.buttons = {}
        self.blink_states = {}

        # Tlačítka a indikátory
        for name in SCRIPTS.keys():
            btn_frame = tk.Frame(top_frame)
            btn_frame.pack(side=tk.LEFT, padx=8)

            btn = tk.Button(btn_frame, text=name, width=12, command=lambda n=name: self.confirm_and_run(n))
            btn.pack(side=tk.TOP)
            self.buttons[name] = btn

            indicator = tk.Label(btn_frame, text="⚪", font=("Arial", 14), fg="gray")
            indicator.pack(side=tk.TOP, pady=2)
            self.indicators[name] = indicator

        # Konzole napravo
        self.console = scrolledtext.ScrolledText(console_frame, wrap=tk.WORD, height=20, width=60, state='disabled')
        self.console.pack(fill=tk.BOTH, expand=True)

    def confirm_and_run(self, name):
        """Zobrazí potvrzení a spustí skript."""
        if messagebox.askyesno("Potvrzení", f"Opravdu spustit {name}?"):
            self.run_script(name)

    def run_script(self, name):
        """Spustí skript v samostatném vlákně."""
        script = SCRIPTS[name]
        btn = self.buttons[name]
        btn.config(state='disabled')  # Deaktivace tlačítka
        threading.Thread(target=self._execute_script, args=(name, script), daemon=True).start()

    def _execute_script(self, name, script):
        """Spustí skript a vypisuje jeho výstup do konzole."""
        self._start_blinking(name)
        try:
            process = subprocess.Popen(
                ["python", script],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True
            )
            for line in process.stdout:
                self._write_console(f"{name}: {line.strip()}\n")
            process.wait()
            self._write_console(f"{name}: --- Skript dokončen ---\n")
        except Exception as e:
            self._write_console(f"{name}: Chyba při spuštění: {e}\n")
        finally:
            self._stop_blinking(name)
            self._enable_button(name)

    def _write_console(self, text):
        """Bezpečný zápis do konzole."""
        self.console.configure(state='normal')
        self.console.insert(tk.END, text)
        self.console.see(tk.END)
        self.console.configure(state='disabled')

    def _start_blinking(self, name):
        """Spustí blikání indikátoru."""
        self.blink_states[name] = True
        self._blink(name)

    def _stop_blinking(self, name):
        """Zastaví blikání a obnoví indikátor."""
        self.blink_states[name] = False
        self.indicators[name].config(text="⚪", fg="gray")

    def _blink(self, name):
        """Změní barvu indikátoru v cyklu."""
        if not self.blink_states.get(name):
            return
        label = self.indicators[name]
        current_color = label.cget("fg")
        new_color = "orange" if current_color == "gray" else "gray"
        label.config(text="●", fg=new_color)
        self.root.after(500, lambda: self._blink(name))

    def _enable_button(self, name):
        """Znovu aktivuje tlačítko po dokončení skriptu."""
        self.buttons[name].config(state='normal')


if __name__ == "__main__":
    root = tk.Tk()
    app = ScriptGUI(root)
    root.geometry("700x400")
    root.mainloop()

