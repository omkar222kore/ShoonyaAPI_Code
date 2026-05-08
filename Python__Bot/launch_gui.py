import tkinter as tk
from tkinter import scrolledtext, messagebox
import subprocess
import threading
import os
import requests
import time
import webbrowser

process = None
ngrok_process = None

# PYTHON PATH
venv_python = r"D:\Python__Bot\.venv\Scripts\python.exe"

# PROJECT PATH
project_path = r"D:\Python__Bot"

# NGROK PATH
ngrok_path = r"C:\ngrok\ngrok.exe"


def read_output(pipe):
    global process

    while True:

        line = pipe.readline()

        if not line:
            break

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

        # Prevent duplicate ngrok
        if ngrok_process is not None:

            output_box.insert(
                tk.END,
                "\nNgrok already running\n"
            )

            output_box.see(tk.END)

            return None

        output_box.insert(
            tk.END,
            "\nStarting ngrok...\n"
        )

        output_box.see(tk.END)

        ngrok_process = subprocess.Popen(
            [ngrok_path, "http", "5000"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        # Wait for startup
        time.sleep(5)

        # Check if ngrok crashed
        if ngrok_process.poll() is not None:

            error_output = ngrok_process.stderr.read()

            output_box.insert(
                tk.END,
                f"\nNGROK FAILED:\n{error_output}\n"
            )

            output_box.see(tk.END)

            ngrok_process = None

            return None

        # Wait for tunnel creation
        public_url = None

        for _ in range(20):

            try:

                response = requests.get(
                    "http://127.0.0.1:4040/api/tunnels"
                )

                tunnels = response.json().get(
                    "tunnels",
                    []
                )

                if tunnels:

                    public_url = tunnels[0]["public_url"]

                    break

            except:
                pass

            time.sleep(1)

        # Tunnel still not created
        if not public_url:

            output_box.insert(
                tk.END,
                "\nNGROK ERROR: Tunnel not created after waiting\n"
            )

            output_box.see(tk.END)

            return None

        webhook_url = f"{public_url}/webhook"

        output_box.insert(
            tk.END,
            f"\nWEBHOOK URL:\n{webhook_url}\n\n"
        )

        # Update webhook textbox
        webhook_entry.delete(0, tk.END)

        webhook_entry.insert(0, webhook_url)

        # Auto copy webhook
        root.clipboard_clear()

        root.clipboard_append(webhook_url)

        output_box.see(tk.END)

        # Open ngrok page
        webbrowser.open(public_url)

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

    env = os.environ.copy()

    env["SUPER_TOKEN"] = token

    # Start ngrok first
    webhook_url = start_ngrok()

    # Stop if ngrok failed
    if not webhook_url:

        messagebox.showerror(
            "Ngrok Error",
            "Failed to start ngrok tunnel"
        )

        return

    try:

        process = subprocess.Popen(
            [
                venv_python,
                os.path.join(
                    project_path,
                    "BuySell_updated.py"
                )
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
            cwd=project_path
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

        # Clear webhook textbox
        webhook_entry.delete(0, tk.END)

        status_label.config(
            text="Bot Stopped",
            fg="red"
        )

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

root.title("Shoonya Trading Bot")

root.geometry("750x700")

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
    text="Webhook URL",
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

