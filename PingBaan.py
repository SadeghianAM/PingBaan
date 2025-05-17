import tkinter as tk
from tkinter import messagebox, ttk
import ttkbootstrap as ttkb
from ttkbootstrap.constants import *
import threading
import json
import time
from ping3 import ping
import validators
from PIL import Image, ImageDraw
import pystray
import sys
from plyer import notification
import concurrent.futures
import logging
import requests
import os
from collections import deque
import unittest

# Logging configuration
logging.basicConfig(filename='pingbaan.log', level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

SITES_FILE = "sites.json"
SETTINGS_FILE = "settings.json"
DEFAULT_SITES = ["google.com", "cloudflare.com", "github.com", "soft98.ir"]
DEFAULT_SETTINGS = {"language": "en"}

LANGUAGES = {
    "en": {
        "title": "PingBaan",
        "add_site": "Add Site",
        "site_label": "Enter site address:",
        "settings": "Settings",
        "language_label": "Language:",
        "no_internet": "No internet connection detected.",
        "invalid_site": "Invalid or duplicate site address.",
        "settings_saved": "Settings saved successfully.",
        "tray_show": "Show PingBaan",
        "tray_exit": "Exit",
        "timeout_alert": "Site {site} has been timing out for over 10 seconds.",
        "toggle_ping": "Stop Ping",
        "start_ping": "Start Ping",
        "stopped": "Stopped"
    },
    "fa": {
        "title": "پینگ‌بان",
        "add_site": "افزودن سایت",
        "site_label": "آدرس سایت را وارد کنید:",
        "settings": "تنظیمات",
        "language_label": "زبان:",
        "no_internet": "اتصال به اینترنت وجود ندارد.",
        "invalid_site": "آدرس سایت نامعتبر یا تکراری است.",
        "settings_saved": "تنظیمات با موفقیت ذخیره شد.",
        "tray_show": "نمایش پینگ‌بان",
        "tray_exit": "خروج",
        "timeout_alert": "سایت {site} بیش از ۱۰ ثانیه تایم‌اوت شده است.",
        "toggle_ping": "توقف پینگ",
        "start_ping": "شروع پینگ",
        "stopped": "شده متوقف"
    }
}

# Utility functions

def load_json(path, default):
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except Exception:
        return default.copy()


def save_json(path, data):
    try:
        with open(path, 'w') as f:
            json.dump(data, f)
    except Exception as e:
        logging.error(f"Failed to save {path}: {e}")


def load_sites():
    sites = load_json(SITES_FILE, DEFAULT_SITES)
    return list(set(sites) | set(DEFAULT_SITES))


def save_sites(sites):
    unique = set(sites) | set(DEFAULT_SITES)
    save_json(SITES_FILE, list(unique))


def load_settings():
    return load_json(SETTINGS_FILE, DEFAULT_SETTINGS)


def save_settings(settings):
    save_json(SETTINGS_FILE, settings)


def create_icon_images():
    images = {}
    for status, color in [('green','green'), ('red','red'), ('orange','orange')]:
        img = Image.new('RGB', (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.ellipse((8,8,56,56), fill=color)
        images[status] = img
    return images


def check_internet():
    try:
        requests.get('http://www.google.com', timeout=2)
        return True
    except requests.RequestException:
        return False


class PingManager:
    def __init__(self, sites):
        self.sites = list(sites)
        self.timeout_tracker = {s: 0 for s in self.sites}
        self.timeout_notified = {s: False for s in self.sites}
        self.previous = {s: None for s in self.sites}
        self.history = {s: deque(maxlen=10) for s in self.sites}

    def ping_site(self, site):
        try:
            delay = ping(site, timeout=2)
            if delay is None:
                return site, None, 'timeout'
            ms = round(delay * 1000)
            return site, ms, 'success'
        except Exception as e:
            logging.error(f"Ping error for {site}: {e}")
            return site, None, 'error'


class PingBaanApp:
    def __init__(self, root):
        self.root = root
        self.settings = load_settings()
        self.lang = self.settings.get('language', 'en')
        self.texts = LANGUAGES[self.lang]
        self.root.title(self.texts['title'])
        self.style = ttkb.Style(theme='flatly')
        # Custom label styles for coloured output
        self.style.configure("Success.TLabel", foreground="green")
        self.style.configure("Danger.TLabel", foreground="red")
        self.style.configure("Warning.TLabel", foreground="orange")
        self.style.configure("Increasing.TLabel", foreground="red")
        self.style.configure("Decreasing.TLabel", foreground="green")
        self.sites = load_sites()
        self.manager = PingManager(self.sites)
        self.icon_images = create_icon_images()
        self.stop_event = threading.Event()
        self.pinging = True
        self.internet_notified = False
        self.tray_icon = None
        self.site_frames = {}

        self.setup_ui()
        self.start_loop()
        self.root.protocol('WM_DELETE_WINDOW', self.hide_to_tray)

    def setup_ui(self):
        frame = ttk.Frame(self.root, padding=10)
        frame.pack(fill='both', expand=True)

        # Input frame
        input_frame = ttk.Frame(frame)
        input_frame.pack(fill='x', pady=5)
        self.entry_label = ttk.Label(input_frame, text=self.texts['site_label'])
        self.entry_label.pack(side='left')
        self.entry = ttk.Entry(input_frame, width=30)
        self.entry.pack(side='left', padx=5)
        self.add_btn = ttk.Button(input_frame, text=self.texts['add_site'], command=self.add_site, bootstyle=PRIMARY)
        self.add_btn.pack(side='left', padx=5)
        self.toggle_btn = ttk.Button(input_frame, text=self.texts['toggle_ping'], command=self.toggle_pinging, bootstyle=WARNING)
        self.toggle_btn.pack(side='left', padx=5)

        # Settings
        self.settings_frame = ttk.Labelframe(frame, text=self.texts['settings'], padding=5)
        self.settings_frame.pack(fill='x', pady=5)
        self.language_label = ttk.Label(self.settings_frame, text=self.texts['language_label'])
        self.language_label.grid(row=0, column=0, padx=5)
        self.lang_var = tk.StringVar(value=self.lang)
        lang_frame = ttk.Frame(self.settings_frame)
        lang_frame.grid(row=0, column=1, padx=5)
        ttk.Radiobutton(lang_frame, text='English', value='en', variable=self.lang_var, command=self.change_language).pack(side='left', padx=5)
        ttk.Radiobutton(lang_frame, text='فارسی', value='fa', variable=self.lang_var, command=self.change_language).pack(side='left', padx=5)

        # Status
        status_frame = ttk.Frame(frame)
        status_frame.pack(fill='both', expand=True, pady=10)
        for site in self.sites:
            self.add_site_row(status_frame, site)

    def add_site_row(self, container, site):
        row = ttk.Frame(container)
        row.pack(anchor='w', fill='x', pady=2)
        lbl = ttk.Label(row, text=f"{site}: Checking...", width=35, font=('Consolas',10))
        lbl.pack(side='left')
        trend = ttk.Label(row, text='', width=2, font=('Consolas',10))
        trend.pack(side='left')
        avg = ttk.Label(row, text='', width=10, font=('Consolas',10))
        avg.pack(side='left')
        if site not in DEFAULT_SITES:
            ttk.Button(row, text='❌', command=lambda s=site: self.delete_site(s), bootstyle=DANGER).pack(side='right')
        self.site_frames[site] = (lbl, trend, avg)

    def add_site(self):
        site = self.entry.get().strip().lower()
        if not validators.domain(site) and not validators.url(site) or site in self.sites:
            messagebox.showerror('Error', self.texts['invalid_site'])
            return
        self.sites.append(site)
        save_sites(self.sites)
        self.manager = PingManager(self.sites)
        self.add_site_row(self.root.children['!frame'].children['!frame2'], site)  # adjust ref as needed
        self.entry.delete(0, tk.END)

    def delete_site(self, site):
        if site in self.sites and site not in DEFAULT_SITES:
            self.sites.remove(site)
            save_sites(self.sites)
            self.manager = PingManager(self.sites)
            lbl, trend, avg = self.site_frames.pop(site)
            lbl.master.destroy()

    def change_language(self):
        new_lang = self.lang_var.get()
        self.settings['language'] = new_lang
        save_settings(self.settings)
        self.lang = new_lang
        self.texts = LANGUAGES[self.lang]
        self.update_ui_language()
        messagebox.showinfo('Info', self.texts['settings_saved'])('Info', self.texts['settings_saved'])
        self.root.title(self.texts['title'])

    def update_ui_language(self):
        # Update all static text for current language
        self.root.title(self.texts['title'])
        self.entry_label.configure(text=self.texts['site_label'])
        self.add_btn.configure(text=self.texts['add_site'])
        self.toggle_btn.configure(text=self.texts['toggle_ping'] if self.pinging else self.texts['start_ping'])
        self.settings_frame.configure(text=self.texts['settings'])
        self.language_label.configure(text=self.texts['language_label'])

    def toggle_pinging(self):
        self.pinging = not self.pinging
        text = self.texts['toggle_ping'] if self.pinging else self.texts['start_ping']
        style = WARNING if self.pinging else SUCCESS
        self.toggle_btn.configure(text=text, bootstyle=style)
        if not self.pinging:
            for site, (lbl, trend, avg) in self.site_frames.items():
                lbl.configure(text=f"{site}: {self.texts['stopped']}")
                trend.configure(text='')
                avg.configure(text='')

    def notify_internet_down(self):
        if not self.internet_notified:
            notification.notify(title=self.texts['title'], message=self.texts['no_internet'], timeout=5)
            self.internet_notified = True
            for site, (lbl, trend, avg) in self.site_frames.items():
                lbl.configure(text=f"{site}: ❌ No Internet")
                trend.configure(text='')
                avg.configure(text='')

    def start_loop(self):
        def loop():
            while not self.stop_event.is_set():
                if not self.pinging:
                    if self.stop_event.wait(1): break
                    continue
                if not check_internet():
                    self.notify_internet_down()
                    if self.stop_event.wait(1): break
                    continue
                self.internet_notified = False
                self.perform_pings()
                if self.stop_event.wait(1): break
        threading.Thread(target=loop, daemon=True).start()

    def perform_pings(self):
        with concurrent.futures.ThreadPoolExecutor() as ex:
            futures = {ex.submit(self.manager.ping_site, s): s for s in self.sites}
            online = 0
            for fut in concurrent.futures.as_completed(futures):
                site, ms, status = fut.result()
                lbl, trend, avg = self.site_frames.get(site, (None,None,None))
                style = 'Success.TLabel' if status == 'success' else 'Danger.TLabel' if status == 'timeout' else 'Warning.TLabel'
                if lbl:
                    result_text = f"✅ {ms} ms" if status == 'success' else '❌ Timeout' if status == 'timeout' else '⚠️ Error'
                    lbl.configure(text=f"{site}: {result_text}", style=style)
                    if status == 'success':
                        if self.manager.previous[site] is not None:
                            trend.configure(
                            text='↑' if ms>self.manager.previous[site] else '↓' if ms<self.manager.previous[site] else '',
                            style='Increasing.TLabel' if ms>self.manager.previous[site] else 'Decreasing.TLabel' if ms<self.manager.previous[site] else 'Success.TLabel'
                        )
                        self.manager.history[site].append(ms)
                        avg_ping = round(sum(self.manager.history[site])/len(self.manager.history[site]))
                        avg.configure(text=f"Avg: {avg_ping} ms", style=style)
                        online += 1
                    else:
                        trend.configure(text='')
                        avg.configure(text='', style=style)
                # handle timeouts
                if status == 'timeout':
                    self.manager.timeout_tracker[site] += 1
                    if self.manager.timeout_tracker[site] >= 10 and not self.manager.timeout_notified[site]:
                        notification.notify(title=self.texts['title'], message=self.texts['timeout_alert'].format(site=site), timeout=5)
                        self.manager.timeout_notified[site] = True
                else:
                    self.manager.timeout_tracker[site] = 0
                    self.manager.timeout_notified[site] = False
                self.manager.previous[site] = ms
        # update tray icon
        if self.tray_icon:
            total = len(self.sites)
            status = 'green' if online==total else 'red' if online==0 else 'orange'
            self.tray_icon.icon = self.icon_images[status]
            self.tray_icon.title = f"{self.texts['title']} - {online}/{total} Online"

    def hide_to_tray(self):
        self.root.withdraw()
        if not self.tray_icon:
            menu = pystray.Menu(
                pystray.MenuItem(self.texts['tray_show'], self.show_window),
                pystray.MenuItem(self.texts['tray_exit'], self.exit_app)
            )
            self.tray_icon = pystray.Icon(self.texts['title'], self.icon_images['green'], self.texts['title'], menu)
            threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def show_window(self, icon=None, item=None):
        self.root.deiconify()
        if self.tray_icon:
            self.tray_icon.stop()
            self.tray_icon = None

    def exit_app(self, icon=None, item=None):
        self.stop_event.set()
        if self.tray_icon:
            self.tray_icon.stop()
        self.root.destroy()
        sys.exit()


# Unit tests
class TestPingBaan(unittest.TestCase):
    def test_check_internet(self):
        self.assertIsInstance(check_internet(), bool)

    def test_ping_site(self):
        mgr = PingManager(['example.com'])
        site, ms, status = mgr.ping_site('example.com')
        self.assertEqual(site, 'example.com')
        self.assertIn(status, ['success', 'timeout', 'error'])


if __name__ == '__main__':
    if 'test' in sys.argv:
        unittest.main(argv=['first-arg-is-ignored'], exit=False)
    else:
        root = ttkb.Window(themename='flatly')
        app = PingBaanApp(root)
        root.mainloop()
