import tkinter as tk
from tkinter import messagebox
import threading
import json
import time
from ping3 import ping
from PIL import Image, ImageDraw
import pystray
import sys

SITES_FILE = "sites.json"
DEFAULT_SITES = ["google.com", "cloudflare.com", "github.com"]


def load_sites():
    try:
        with open(SITES_FILE, "r") as f:
            return json.load(f)
    except:
        return DEFAULT_SITES.copy()


def save_sites(sites):
    with open(SITES_FILE, "w") as f:
        json.dump(sites, f)


def create_icon_image():
    # ساخت یک آیکون ساده دایره‌ای سبز برای Tray
    image = Image.new("RGB", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((8, 8, 56, 56), fill="green")
    return image


class PingBaanApp:
    def __init__(self, root):
        self.root = root
        self.root.title("PingBaan")
        self.sites = load_sites()
        self.site_frames = {}
        self.tray_icon = None
        self.tray_thread = None

        self.frame = tk.Frame(self.root)
        self.frame.pack(padx=10, pady=10)

        self.add_widgets()
        self.start_pinging()

        # هنگام بستن پنجره، به جای خروج، به Tray می‌رود
        self.root.protocol("WM_DELETE_WINDOW", self.hide_to_tray)

    def add_widgets(self):
        self.entry = tk.Entry(self.frame, width=30)
        self.entry.grid(row=0, column=0)

        self.add_button = tk.Button(self.frame, text="Add Site", command=self.add_site)
        self.add_button.grid(row=0, column=1, padx=5)

        self.status_frame = tk.Frame(self.frame)
        self.status_frame.grid(row=1, column=0, columnspan=2, pady=10)

        for site in self.sites:
            self.add_site_row(site)

    def add_site_row(self, site):
        row_frame = tk.Frame(self.status_frame)
        row_frame.pack(anchor="w", fill="x", pady=1)

        label = tk.Label(row_frame, text=f"{site}: Checking...", anchor="w", width=35, font=("Consolas", 10))
        label.pack(side="left")

        delete_button = tk.Button(row_frame, text="❌", fg="red", command=lambda s=site: self.delete_site(s))
        delete_button.pack(side="right")

        self.site_frames[site] = (row_frame, label)

    def add_site(self):
        site = self.entry.get().strip().lower()
        if site and site not in self.sites:
            self.sites.append(site)
            save_sites(self.sites)
            self.add_site_row(site)
            self.entry.delete(0, tk.END)
        else:
            messagebox.showinfo("Info", "Site is empty or already exists.")

    def delete_site(self, site):
        if site in self.sites:
            self.sites.remove(site)
            save_sites(self.sites)
            frame, _ = self.site_frames.pop(site)
            frame.destroy()

    def start_pinging(self):
        def loop():
            while True:
                for site in self.sites:
                    if site in self.site_frames:
                        label = self.site_frames[site][1]
                        try:
                            delay = ping(site, timeout=2)
                            if delay is None:
                                result = "❌ Timeout"
                                color = "red"
                            else:
                                result = f"✅ {round(delay * 1000)} ms"
                                color = "green"
                        except:
                            result = "⚠️ Error"
                            color = "orange"
                        label.config(text=f"{site}: {result}", fg=color)
                time.sleep(3)

        thread = threading.Thread(target=loop, daemon=True)
        thread.start()

    def hide_to_tray(self):
        self.root.withdraw()  # پنجره اصلی مخفی می‌شود
        if self.tray_icon is None:
            image = create_icon_image()
            menu = pystray.Menu(
                pystray.MenuItem("Show PingBaan", self.show_window),
                pystray.MenuItem("Exit", self.exit_app)
            )
            self.tray_icon = pystray.Icon("PingBaan", image, "PingBaan", menu)
            # اجرای آیکون در ترد جداگانه
            self.tray_thread = threading.Thread(target=self.tray_icon.run, daemon=True)
            self.tray_thread.start()

    def show_window(self, icon=None, item=None):
        self.root.deiconify()  # پنجره دوباره نمایش داده می‌شود
        if self.tray_icon:
            self.tray_icon.stop()
            self.tray_icon = None

    def exit_app(self, icon=None, item=None):
        if self.tray_icon:
            self.tray_icon.stop()
        self.root.destroy()
        sys.exit()


if __name__ == "__main__":
    root = tk.Tk()
    app = PingBaanApp(root)
    root.mainloop()
