import os
import queue
import threading
import webbrowser
import tkinter as tk
from tkinter import messagebox

import requests

APP_TITLE = "Omni Launcher"
# Local testing: http://127.0.0.1:5000   |   Deployed: https://your-site.example.com
API_BASE_URL = "http://127.0.0.1:5000"

# ---------------------------------------------------------------------------
# EDIT THIS LIST: what shows up as buttons after login.
#   ("Button name", "url",  "https://example.com")           -> opens in browser
#   ("Button name", "file", r"C:\Path\To\Program.exe")       -> starts a program / opens a file or folder
# ---------------------------------------------------------------------------
LAUNCH_ITEMS = [
    ("Join our Discord", "url", "https://discord.gg/Bj52zeber"),
    ("how to fish", "url", "steam://rungameid/4001890"),
    ("cs2", "url", "steam://rungameid/730"),
    ("sos ops", "url", "steam://rungameid/2475460"),
]

# ------------------------------------------------------------------ theme
BG = "#000000"
PANEL = "#080a0e"
FIELD = "#0d1017"
BORDER = "#1a1f2b"
ACCENT = "#1e00ff"
ACCENT_HOVER = "#4a33ff"
TEXT = "#edf2ff"
MUTED = "#7d8aa6"
DIM = "#4b5568"
CARD = "#0d1017"
CARD_HOVER = "#151a26"
GOOD = "#4ade80"
BAD = "#ff6b6b"
FONT = "Segoe UI"

ICONS = {"url": "\u2197", "file": "\u25B6"}  # arrow for links, play for programs


class FlatButton(tk.Label):
    """A flat button with hover colours (tk.Button can't do this well on Windows)."""

    def __init__(self, parent, text, command, bg=ACCENT, hover=ACCENT_HOVER, fg="white",
                 font=(FONT, 10, "bold"), pady=11, **kw):
        super().__init__(parent, text=text, bg=bg, fg=fg, font=font, pady=pady, cursor="hand2", **kw)
        self._bg, self._hover, self._command = bg, hover, command
        self.disabled = False
        self.bind("<Enter>", lambda _e: not self.disabled and self.config(bg=self._hover))
        self.bind("<Leave>", lambda _e: not self.disabled and self.config(bg=self._bg))
        self.bind("<ButtonRelease-1>", self._click)

    def _click(self, _event):
        if not self.disabled:
            self._command()

    def set_disabled(self, value, text=None):
        self.disabled = value
        self.config(cursor="arrow" if value else "hand2", bg=DIM if value else self._bg)
        if text:
            self.config(text=text)


class Client:
    def __init__(self, root):
        self.root = root
        root.title(APP_TITLE)
        w, h = 460, 620
        x = (root.winfo_screenwidth() - w) // 2
        y = (root.winfo_screenheight() - h) // 3
        root.geometry(f"{w}x{h}+{x}+{y}")
        root.configure(bg=BG)
        root.resizable(False, False)
        self.mode = "login"
        self.fields = {}
        self.username = ""
        self.busy = False
        self.results = queue.Queue()
        self.draw()

    def clear(self):
        for widget in self.root.winfo_children():
            widget.destroy()

    def header(self, subtitle):
        tk.Label(self.root, text="\u25C6", font=(FONT, 16), fg=ACCENT, bg=BG).pack(pady=(30, 0))
        tk.Label(self.root, text=APP_TITLE, font=(FONT, 26, "bold"), fg=TEXT, bg=BG).pack(pady=(0, 2))
        tk.Label(self.root, text=subtitle, font=(FONT, 10), fg=MUTED, bg=BG).pack(pady=(0, 22))

    def card(self, **pack):
        """A dark panel with a thin border and an accent line on top."""
        outer = tk.Frame(self.root, bg=BORDER, padx=1, pady=1)
        outer.pack(fill="x", padx=32, **pack)
        tk.Frame(outer, bg=ACCENT, height=2).pack(fill="x")
        inner = tk.Frame(outer, bg=PANEL, padx=26, pady=22)
        inner.pack(fill="x")
        return inner

    # ------------------------------------------------------------------ login / register
    def draw(self):
        self.clear()
        registering = self.mode == "register"
        self.header("Create your account" if registering else "Sign in to continue")

        form = self.card()
        self.fields = {}
        names = [("username", "USERNAME"), ("password", "PASSWORD")]
        if registering:
            names.append(("license_key", "REGISTRATION KEY"))

        for key, label in names:
            tk.Label(form, text=label, font=(FONT, 8, "bold"), fg=MUTED, bg=PANEL, anchor="w").pack(fill="x", pady=(10, 4))
            row = tk.Frame(form, bg=FIELD, highlightthickness=1, highlightbackground=BORDER, highlightcolor=ACCENT)
            row.pack(fill="x")
            entry = tk.Entry(row, show="\u2022" if key == "password" else "", bg=FIELD, fg=TEXT,
                             insertbackground=TEXT, relief="flat", font=(FONT, 11), bd=0)
            entry.pack(side="left", fill="x", expand=True, ipady=9, padx=(10, 0))
            entry.bind("<Return>", lambda _e: self.submit())
            entry.bind("<FocusIn>", lambda _e, r=row: r.config(highlightbackground=ACCENT))
            entry.bind("<FocusOut>", lambda _e, r=row: r.config(highlightbackground=BORDER))
            if key == "password":
                toggle = tk.Label(row, text="SHOW", font=(FONT, 8, "bold"), fg=MUTED, bg=FIELD, cursor="hand2", padx=10)
                toggle.pack(side="right")
                toggle.bind("<Button-1>", lambda _e, en=entry, t=toggle: self.toggle_password(en, t))
            self.fields[key] = entry

        # inline status message (replaces most pop-ups)
        self.status = tk.Label(form, text="", font=(FONT, 9), fg=BAD, bg=PANEL, wraplength=340, justify="left", anchor="w")
        self.status.pack(fill="x", pady=(14, 0))

        self.submit_btn = FlatButton(form, "Create account" if registering else "Log in", self.submit)
        self.submit_btn.pack(fill="x", pady=(10, 0))

        link = tk.Label(self.root, cursor="hand2", font=(FONT, 9), fg="#8f85ff", bg=BG,
                        text="Already have an account?  Log in" if registering else "Need an account?  Register")
        link.pack(pady=18)
        link.bind("<Button-1>", lambda _e: self.toggle())
        link.bind("<Enter>", lambda _e: link.config(fg="white"))
        link.bind("<Leave>", lambda _e: link.config(fg="#8f85ff"))

        tk.Label(self.root, text="protected with KeyPortal", font=(FONT, 8), fg=DIM, bg=BG).pack(side="bottom", pady=14)
        self.fields["username"].focus_set()

    def toggle_password(self, entry, label):
        hidden = entry.cget("show") != ""
        entry.config(show="" if hidden else "\u2022")
        label.config(text="HIDE" if hidden else "SHOW")

    def toggle(self):
        if self.busy:
            return
        self.mode = "login" if self.mode == "register" else "register"
        self.draw()

    def say(self, text, good=False):
        try:
            self.status.config(text=text, fg=GOOD if good else BAD)
        except tk.TclError:
            pass

    # ------------------------------------------------------------------ talking to the server
    def submit(self):
        if self.busy:
            return
        username = self.fields["username"].get().strip()
        password = self.fields["password"].get()
        if not API_BASE_URL.startswith(("http://", "https://")) or "your-domain.example" in API_BASE_URL:
            messagebox.showerror("Setup required", "Edit API_BASE_URL in desktop_client.pyw to your server address.")
            return
        if not username or not password:
            self.say("Enter your username and password.")
            return
        payload = {"username": username, "password": password}
        if self.mode == "register":
            key = self.fields["license_key"].get().strip()
            if not key:
                self.say("Enter your registration key.")
                return
            payload["license_key"] = key

        endpoint = "/api/register" if self.mode == "register" else "/api/login"
        self.busy = True
        self.submit_btn.set_disabled(True, "Please wait...")
        self.say("")
        threading.Thread(target=self.worker, args=(endpoint, payload, username), daemon=True).start()
        self.root.after(80, self.poll)

    def worker(self, endpoint, payload, username):
        """Runs in a background thread so the window never freezes."""
        try:
            response = requests.post(API_BASE_URL.rstrip("/") + endpoint, json=payload, timeout=15)
            data = response.json()
            self.results.put(("ok" if response.ok else "error", data, username))
        except requests.RequestException:
            self.results.put(("error", {"error": "Could not reach the server. Check the URL and your connection."}, username))
        except ValueError:
            self.results.put(("error", {"error": "The server sent an unexpected response."}, username))

    def poll(self):
        try:
            outcome, data, username = self.results.get_nowait()
        except queue.Empty:
            self.root.after(80, self.poll)
            return
        self.busy = False
        if outcome == "ok":
            if self.mode == "register":
                self.mode = "login"
                self.draw()
                self.say(data.get("message", "Account created. You can now log in."), good=True)
            else:
                self.username = data.get("username", username)
                self.show_main()
        else:
            try:
                self.submit_btn.set_disabled(False, "Create account" if self.mode == "register" else "Log in")
            except tk.TclError:
                pass
            self.say(data.get("error", "Request failed."))

    # ------------------------------------------------------------------ main window (after login)
    def show_main(self):
        self.clear()

        # avatar circle with the user's first letter
        avatar = tk.Canvas(self.root, width=72, height=72, bg=BG, highlightthickness=0)
        avatar.pack(pady=(34, 8))
        avatar.create_oval(2, 2, 70, 70, fill=ACCENT, outline=ACCENT_HOVER, width=2)
        avatar.create_text(36, 36, text=(self.username[:1] or "?").upper(), fill="white", font=(FONT, 26, "bold"))

        tk.Label(self.root, text=self.username, font=(FONT, 18, "bold"), fg=TEXT, bg=BG).pack()
        status = tk.Frame(self.root, bg=BG)
        status.pack(pady=(4, 22))
        tk.Label(status, text="\u25CF", font=(FONT, 8), fg=GOOD, bg=BG).pack(side="left")
        tk.Label(status, text=" Signed in", font=(FONT, 9), fg=MUTED, bg=BG).pack(side="left")

        tk.Label(self.root, text="LAUNCH", font=(FONT, 8, "bold"), fg=MUTED, bg=BG, anchor="w").pack(fill="x", padx=34, pady=(0, 6))

        if not LAUNCH_ITEMS:
            tk.Label(self.root, text="Nothing here yet.\nEdit LAUNCH_ITEMS in the code.", fg=DIM, bg=BG,
                     font=(FONT, 10)).pack(pady=20)
        for name, kind, target in LAUNCH_ITEMS:
            self.launch_card(name, kind, target)

        footer = tk.Label(self.root, text="Log out", cursor="hand2", font=(FONT, 9), fg="#8f85ff", bg=BG)
        footer.pack(side="bottom", pady=(0, 18))
        footer.bind("<Button-1>", lambda _e: self.logout())
        footer.bind("<Enter>", lambda _e: footer.config(fg="white"))
        footer.bind("<Leave>", lambda _e: footer.config(fg="#8f85ff"))
        tk.Label(self.root, text="protected with KeyPortal", font=(FONT, 8), fg=DIM, bg=BG).pack(side="bottom", pady=(0, 6))

    def launch_card(self, name, kind, target):
        outer = tk.Frame(self.root, bg=BORDER, padx=1, pady=1, cursor="hand2")
        outer.pack(fill="x", padx=32, pady=4)
        card = tk.Frame(outer, bg=CARD, padx=16, pady=12, cursor="hand2")
        card.pack(fill="x")
        icon = tk.Label(card, text=ICONS.get(kind, "\u25B6"), font=(FONT, 11), fg=ACCENT_HOVER, bg=CARD, width=2)
        icon.pack(side="left")
        label = tk.Label(card, text=name, font=(FONT, 11), fg=TEXT, bg=CARD, anchor="w")
        label.pack(side="left", fill="x", expand=True, padx=(6, 0))
        arrow = tk.Label(card, text="\u203A", font=(FONT, 16), fg=DIM, bg=CARD)
        arrow.pack(side="right")

        parts = (card, icon, label, arrow)

        def enter(_e):
            outer.config(bg=ACCENT)
            for p in parts:
                p.config(bg=CARD_HOVER)
            arrow.config(fg="white")

        def leave(_e):
            outer.config(bg=BORDER)
            for p in parts:
                p.config(bg=CARD)
            arrow.config(fg=DIM)

        for widget in (outer, *parts):
            widget.bind("<Enter>", enter)
            widget.bind("<Leave>", leave)
            widget.bind("<Button-1>", lambda _e, k=kind, t=target: self.launch(k, t))

    def launch(self, kind, target):
        try:
            if kind == "url":
                webbrowser.open(target)
            elif kind == "file":
                os.startfile(target)  # Windows only
            else:
                messagebox.showerror(APP_TITLE, f"Unknown launch type: {kind}")
        except Exception as exc:
            messagebox.showerror("Could not launch", f"{target}\n\n{exc}")

    def logout(self):
        self.username = ""
        self.mode = "login"
        self.draw()


if __name__ == "__main__":
    root = tk.Tk()
    Client(root)
    root.mainloop()
