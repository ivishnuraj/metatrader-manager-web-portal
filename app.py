import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import subprocess
import threading
import queue
import os
import sys
import json
import webbrowser

BASE_DIR = os.path.dirname(sys.executable)
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")

ENDPOINTS = [
    ("Health Check", "/health"),
    ("Login", "/auth/login"),
    ("Current User", "/auth/me"),
    ("Positions", "/positions"),
    ("Trade", "/trade"),
    ("Account", "/account"),
    ("Plugins", "/v1/plugins"),
    ("Groups", "/v1/groups"),
]


class MT5ServiceManager:
    def __init__(self, root):
        self.root = root
        self.root.title("Metatrader 5 API Service")
        self.root.geometry("950x650")

        self.process = None
        self.log_queue = queue.Queue()

        self.load_config()
        self.build_ui()
        self.update_logs()

    def load_config(self):
        self.config = {
            "port": 14315
        }

        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r") as f:
                    self.config.update(json.load(f))
            except:
                pass

    def save_config(self):
        self.config["port"] = int(self.port_var.get())

        with open(CONFIG_FILE, "w") as f:
            json.dump(self.config, f, indent=2)

    def build_ui(self):
        # Header
        header_frame = ttk.Frame(self.root)
        header_frame.pack(fill="x", padx=20, pady=15)

        title = ttk.Label(
            header_frame,
            text="Metatrader 5 API Service",
            font=("Segoe UI", 24, "bold")
        )
        title.pack(anchor="w")

        subtitle = ttk.Label(
            header_frame,
            text="Developer: Vishnu Raj <synamatics@gmail.com>\nVersion 1.0",
            font=("Segoe UI", 10)
        )
        subtitle.pack(anchor="w")

        # Config Frame
        config_frame = ttk.LabelFrame(
            self.root,
            text="Configuration"
        )
        config_frame.pack(fill="x", padx=20, pady=10)

        ttk.Label(
            config_frame,
            text="API Port:"
        ).grid(row=0, column=0, padx=10, pady=10)

        self.port_var = tk.StringVar(
            value=str(self.config["port"])
        )

        self.port_entry = ttk.Entry(
            config_frame,
            textvariable=self.port_var,
            width=10
        )
        self.port_entry.grid(row=0, column=1)

        save_btn = ttk.Button(
            config_frame,
            text="Save Config",
            command=self.save_config
        )
        save_btn.grid(row=0, column=2, padx=10)

        # Status
        status_frame = ttk.Frame(self.root)
        status_frame.pack(fill="x", padx=20)

        ttk.Label(
            status_frame,
            text="Status:",
            font=("Segoe UI", 11, "bold")
        ).pack(side="left")

        self.status_label = ttk.Label(
            status_frame,
            text="Stopped",
            foreground="red"
        )
        self.status_label.pack(side="left", padx=10)

        # Buttons
        button_frame = ttk.Frame(self.root)
        button_frame.pack(fill="x", padx=20, pady=15)

        ttk.Button(
            button_frame,
            text="Start",
            command=self.start_process
        ).pack(side="left", padx=5)

        ttk.Button(
            button_frame,
            text="Stop",
            command=self.stop_process
        ).pack(side="left", padx=5)

        ttk.Button(
            button_frame,
            text="Restart",
            command=self.restart_process
        ).pack(side="left", padx=5)

        ttk.Button(
            button_frame,
            text="Clear Logs",
            command=self.clear_logs
        ).pack(side="left", padx=5)

        # Main Layout
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill="both", expand=True, padx=20, pady=10)

        # Endpoints
        endpoints_frame = ttk.LabelFrame(
            main_frame,
            text="API Endpoints"
        )
        endpoints_frame.pack(side="left", fill="y", padx=(0, 10))

        self.endpoint_list = tk.Listbox(
            endpoints_frame,
            width=45,
            height=25
        )
        self.endpoint_list.pack(fill="both", expand=True, padx=10, pady=10)

        self.populate_endpoints()

        self.endpoint_list.bind(
            "<Double-Button-1>",
            self.open_endpoint
        )

        # Logs
        logs_frame = ttk.LabelFrame(
            main_frame,
            text="Logs"
        )
        logs_frame.pack(side="right", fill="both", expand=True)

        self.log_box = scrolledtext.ScrolledText(
            logs_frame,
            bg="#111111",
            fg="#00ff88",
            insertbackground="white",
            font=("Consolas", 10)
        )
        self.log_box.pack(fill="both", expand=True)

    def populate_endpoints(self):
        self.endpoint_list.delete(0, tk.END)

        port = self.port_var.get()

        for name, endpoint in ENDPOINTS:
            url = f"http://127.0.0.1:{port}{endpoint}"
            self.endpoint_list.insert(
                tk.END,
                f"{name} → {url}"
            )

    def open_endpoint(self, event):
        selection = self.endpoint_list.curselection()

        if not selection:
            return

        item = self.endpoint_list.get(selection[0])

        if "→" in item:
            url = item.split("→")[1].strip()
            webbrowser.open(url)

    def start_process(self):
        if self.process and self.process.poll() is None:
            messagebox.showinfo(
                "Running",
                "Service already running"
            )
            return

        try:
            self.save_config()

            base_dir = os.path.dirname(sys.executable)

            worker_exe = os.path.join(
                base_dir,
                "main",
                "main.exe"
            )

            if not os.path.exists(worker_exe):
                messagebox.showerror(
                    "Error",
                    f"main.exe not found:\n{worker_exe}"
                )
                return

            env = os.environ.copy()
            env["API_PORT"] = self.port_var.get()

            self.process = subprocess.Popen(
                [worker_exe],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.PIPE,
                text=True,
                bufsize=1,
                creationflags=subprocess.CREATE_NO_WINDOW,
                env=env
            )

            self.status_label.config(
                text=f"Running on port {self.port_var.get()}",
                foreground="green"
            )

            self.write_log(
                f"[INFO] Service started on port {self.port_var.get()}"
            )

            threading.Thread(
                target=self.read_logs,
                daemon=True
            ).start()

        except Exception as e:
            messagebox.showerror(
                "Error",
                str(e)
            )

    def stop_process(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()

            self.status_label.config(
                text="Stopped",
                foreground="red"
            )

            self.write_log("[INFO] Service stopped")

    def restart_process(self):
        self.stop_process()
        self.root.after(1000, self.start_process)

    def read_logs(self):
        try:
            for line in self.process.stdout:
                self.log_queue.put(line)
        except Exception as e:
            self.log_queue.put(f"[ERROR] {e}\n")

    def update_logs(self):
        while not self.log_queue.empty():
            line = self.log_queue.get()

            self.log_box.insert(tk.END, line)
            self.log_box.see(tk.END)

        self.root.after(100, self.update_logs)

    def write_log(self, text):
        self.log_box.insert(tk.END, text + "\n")
        self.log_box.see(tk.END)

    def clear_logs(self):
        self.log_box.delete("1.0", tk.END)


if __name__ == "__main__":
    root = tk.Tk()

    style = ttk.Style()
    style.theme_use("clam")

    app = MT5ServiceManager(root)

    root.mainloop()