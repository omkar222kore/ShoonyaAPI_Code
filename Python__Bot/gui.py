# =========================
# FULL PORTABLE GUI.py
# =========================

import tkinter as tk
from tkinter import scrolledtext, messagebox
import subprocess
import threading
import os
import requests
import time
import webbrowser
import sys

# BASE PATH
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# NGROK PATH
ngrok_path = os.path.join(
    BASE_DIR,
    "ngrok.exe"
)

# NGROK CONFIG PATH (ngrok.yml sits next to gui.py)
ngrok_config_path = os.path.join(
    BASE_DIR,
    "ngrok.yml"
)

process = None
ngrok_process = None


def read_output(pipe):

    global process

    while True:

        line = pipe.readline()

        if not line:
            break

        # LIVE PNL UPDATE
        if "TOTAL_PNL:" in line:

            try:

                pnl = line.split("TOTAL_PNL:")[1].strip()

                pnl_float = float(pnl)

                root.after(
                    0,
                    pnl_var.set,
                    pnl
                )

                # CHANGE COLOR BASED ON PNL
                if pnl_float >= 0:

                    root.after(
                        0,
                        pnl_value.config,
                        {"fg": "lime"}
                    )

                else:

                    root.after(
                        0,
                        pnl_value.config,
                        {"fg": "red"}
                    )

            except:
                pass

        root.after(
            0,
            output_box.insert,
            tk.END,
            line
        )

        root.after(
            0,
            output_box.see,
            tk.END
        )

    root.after(
        0,
        status_label.config,
        {"text": "Bot Stopped", "fg": "red"}
    )

    process = None


def clear_output():

    output_box.delete(1.0, tk.END)


def copy_webhook():

    webhook = webhook_entry.get()

    if webhook:

        root.clipboard_clear()

        root.clipboard_append(webhook)

        messagebox.showinfo(
            "Copied",
            "Webhook URL copied!"
        )


def start_ngrok():

    global ngrok_process

    try:

        if ngrok_process is not None:

            output_box.insert(
                tk.END,
                "\nNgrok already running\n"
            )

            output_box.see(tk.END)

            return None

        output_box.insert(
            tk.END,
            "\nStarting ngrok (3 tunnels: 5000, 5001, 5002)...\n"
        )

        output_box.see(tk.END)

        # START ALL 3 TUNNELS USING ngrok.yml
        ngrok_process = subprocess.Popen(
            [
                ngrok_path,
                "start",
                "--all",
                "--config",
                ngrok_config_path
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        time.sleep(5)

        if ngrok_process.poll() is not None:

            error_output = ngrok_process.stderr.read()

            output_box.insert(
                tk.END,
                f"\nNGROK FAILED:\n{error_output}\n"
            )

            output_box.see(tk.END)

            ngrok_process = None

            return None

        # WAIT FOR TUNNELS TO BE READY
        tunnels = []

        for _ in range(20):

            try:

                response = requests.get(
                    "http://127.0.0.1:4040/api/tunnels"
                )

                tunnels = response.json().get(
                    "tunnels",
                    []
                )

                if len(tunnels) >= 3:
                    break

            except:
                pass

            time.sleep(1)

        if not tunnels:

            output_box.insert(
                tk.END,
                "\nNGROK ERROR: No tunnels created after waiting\n"
            )

            output_box.see(tk.END)

            return None

        # SHOW ALL TUNNEL URLs IN OUTPUT
        output_box.insert(
            tk.END,
            "\n--- ACTIVE NGROK TUNNELS ---\n"
        )

        public_url_5000 = None

        for tunnel in tunnels:

            addr = tunnel.get("config", {}).get("addr", "")
            url = tunnel["public_url"]

            output_box.insert(
                tk.END,
                f"  {addr}  →  {url}\n"
            )

            # GRAB PORT 5000 URL FOR MAIN BOT WEBHOOK
            if ":5000" in addr:
                public_url_5000 = url

        output_box.insert(
            tk.END,
            "----------------------------\n\n"
        )

        output_box.see(tk.END)

        # FALLBACK: USE FIRST TUNNEL IF 5000 NOT FOUND
        if not public_url_5000 and tunnels:
            public_url_5000 = tunnels[0]["public_url"]

        if not public_url_5000:

            output_box.insert(
                tk.END,
                "\nNGROK ERROR: Could not find port 5000 tunnel\n"
            )

            output_box.see(tk.END)

            return None

        webhook_url = f"{public_url_5000}/webhook"

        output_box.insert(
            tk.END,
            f"MAIN WEBHOOK (port 5000):\n{webhook_url}\n\n"
        )

        # SET WEBHOOK ENTRY TO PORT 5000 URL
        webhook_entry.delete(0, tk.END)

        webhook_entry.insert(0, webhook_url)

        # AUTO COPY
        root.clipboard_clear()

        root.clipboard_append(webhook_url)

        output_box.see(tk.END)

        # OPEN NGROK DASHBOARD
        webbrowser.open("http://127.0.0.1:4040")

        return webhook_url

    except Exception as e:

        output_box.insert(
            tk.END,
            f"\nNGROK ERROR:\n{e}\n"
        )

        output_box.see(tk.END)

        return None


def start_bot():

    global process

    if process is not None:

        messagebox.showinfo(
            "Info",
            "Bot already running"
        )

        return

    token = token_entry.get().strip()

    if not token:

        messagebox.showerror(
            "Error",
            "Please enter SuperToken"
        )

        return

    trading_cap = cap_entry.get().strip()

    if not trading_cap.isdigit():

        messagebox.showerror(
            "Error",
            "Trading capital must be numeric"
        )

        return

    env = os.environ.copy()

    env["SUPER_TOKEN"] = token
    env["TRADING_CAP_PER_STOCK"] = trading_cap

    webhook_url = start_ngrok()

    if not webhook_url:

        messagebox.showerror(
            "Ngrok Error",
            "Failed to start ngrok tunnels"
        )

        return

    try:

        process = subprocess.Popen(
            [
                os.path.join(
                    BASE_DIR,
                    "BuySell_updated.exe"
                )
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True,
            env=env,
            cwd=BASE_DIR
        )

        threading.Thread(
            target=read_output,
            args=(process.stdout,),
            daemon=True
        ).start()

        status_label.config(
            text="Bot Running",
            fg="green"
        )

    except Exception as e:

        messagebox.showerror(
            "Error",
            str(e)
        )


def stop_bot():

    global process
    global ngrok_process

    try:

        if process:

            process.terminate()

            process = None

        if ngrok_process:

            ngrok_process.terminate()

            ngrok_process = None

        webhook_entry.delete(0, tk.END)

        status_label.config(
            text="Bot Stopped",
            fg="red"
        )

        pnl_var.set("0.00")

        output_box.insert(
            tk.END,
            "\nBot Stopped\n"
        )

        output_box.see(tk.END)

    except Exception as e:

        output_box.insert(
            tk.END,
            f"\nSTOP ERROR:\n{e}\n"
        )

        output_box.see(tk.END)


# =========================
# GUI
# =========================

root = tk.Tk()

pnl_var = tk.StringVar()
pnl_var.set("0.00")

root.title("Shoonya Trading Bot")

root.geometry("750x820")

root.resizable(False, False)

# TITLE
title = tk.Label(
    root,
    text="Shoonya Algo Trading Bot",
    font=("Arial", 22, "bold")
)

title.pack(pady=15)

# TOKEN LABEL
token_label = tk.Label(
    root,
    text="Enter SuperToken",
    font=("Arial", 11)
)

token_label.pack()

# TOKEN FRAME
token_frame = tk.Frame(root)

token_frame.pack(pady=10)

# TOKEN ENTRY
token_entry = tk.Entry(
    token_frame,
    width=60,
    show="*",
    font=("Arial", 10)
)

token_entry.pack(side=tk.LEFT)

show_token = False


def toggle_token():

    global show_token

    show_token = not show_token

    if show_token:

        token_entry.config(show="")

        toggle_btn.config(text="Hide")

    else:

        token_entry.config(show="*")

        toggle_btn.config(text="Show")


# SHOW/HIDE BUTTON
toggle_btn = tk.Button(
    token_frame,
    text="Show",
    command=toggle_token
)

toggle_btn.pack(side=tk.LEFT, padx=5)

# =========================
# TRADING CAPITAL
# =========================

cap_label = tk.Label(
    root,
    text="Trading Capital Per Stock",
    font=("Arial", 11)
)

cap_label.pack(pady=(10, 0))

cap_entry = tk.Entry(
    root,
    width=20,
    font=("Arial", 11),
    justify="center"
)

cap_entry.pack(pady=5)

cap_entry.insert(0, "1000")

# START BUTTON
start_button = tk.Button(
    root,
    text="START BOT",
    command=start_bot,
    bg="green",
    fg="white",
    width=20,
    height=2,
    font=("Arial", 10, "bold")
)

start_button.pack(pady=5)

# STOP BUTTON
stop_button = tk.Button(
    root,
    text="STOP BOT",
    command=stop_bot,
    bg="red",
    fg="white",
    width=20,
    height=2,
    font=("Arial", 10, "bold")
)

stop_button.pack(pady=5)

# CLEAR BUTTON
clear_button = tk.Button(
    root,
    text="CLEAR OUTPUT",
    command=clear_output,
    bg="blue",
    fg="white",
    width=20,
    height=2,
    font=("Arial", 10, "bold")
)

clear_button.pack(pady=5)

# WEBHOOK LABEL
webhook_label = tk.Label(
    root,
    text="Webhook URL (Port 5000 - Main Bot)",
    font=("Arial", 11, "bold")
)

webhook_label.pack(pady=(10, 2))

# WEBHOOK FRAME
webhook_frame = tk.Frame(root)

webhook_frame.pack(pady=5)

# WEBHOOK ENTRY
webhook_entry = tk.Entry(
    webhook_frame,
    width=70,
    font=("Arial", 10)
)

webhook_entry.pack(side=tk.LEFT, padx=5)

# COPY BUTTON
copy_button = tk.Button(
    webhook_frame,
    text="COPY",
    command=copy_webhook,
    bg="orange",
    fg="black",
    width=10,
    font=("Arial", 9, "bold")
)

copy_button.pack(side=tk.LEFT)

# STATUS LABEL
status_label = tk.Label(
    root,
    text="Bot Stopped",
    fg="red",
    font=("Arial", 14, "bold")
)

status_label.pack(pady=10)

# =========================
# TOTAL PNL
# =========================

pnl_frame = tk.Frame(root)

pnl_frame.pack(pady=5)

pnl_title = tk.Label(
    pnl_frame,
    text="TOTAL PnL : ",
    font=("Arial", 14, "bold")
)

pnl_title.pack(side=tk.LEFT)

pnl_value = tk.Label(
    pnl_frame,
    textvariable=pnl_var,
    font=("Arial", 14, "bold"),
    fg="cyan"
)

pnl_value.pack(side=tk.LEFT)

# OUTPUT TERMINAL
output_box = scrolledtext.ScrolledText(
    root,
    width=90,
    height=22,
    bg="black",
    fg="lime",
    font=("Consolas", 10)
)

output_box.pack(padx=10, pady=10)

root.mainloop()
