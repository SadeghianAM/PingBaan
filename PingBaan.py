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

# تنظیم لاگ‌گیری
logging.basicConfig(filename='pingbaan.log', level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

SITES_FILE = "sites.json"
SETTINGS_FILE = "settings.json"
DEFAULT_SITES = ["google.com", "cloudflare.com", "github.com", "soft98.ir"]
DEFAULT_SETTINGS = {
    "language": "en"
}

# تنظیمات چندزبانه
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
        "start_ping": "Start Ping",  # کلید جدید
        "stopped": "Stopped"  # کلید جدید
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
        "start_ping": "شروع پینگ",  # کلید جدید
        "stopped": "متوقف شده"  # کلید جدید
    }
}

def load_sites():
    try:
        with open(SITES_FILE, "r") as f:
            sites = json.load(f)
            for default_site in DEFAULT_SITES:
                if default_site not in sites:
                    sites.append(default_site)
            return sites
    except Exception as e:
        logging.error(f"Failed to load sites: {str(e)}")
        return DEFAULT_SITES.copy()

def save_sites(sites):
    try:
        for default_site in DEFAULT_SITES:
            if default_site not in sites:
                sites.append(default_site)
        with open(SITES_FILE, "w") as f:
            json.dump(sites, f)
    except Exception as e:
        logging.error(f"Failed to save sites: {str(e)}")

def load_settings():
    try:
        with open(SETTINGS_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return DEFAULT_SETTINGS.copy()

def save_settings(settings):
    try:
        with open(SETTINGS_FILE, "w") as f:
            json.dump(settings, f)
    except Exception as e:
        logging.error(f"Failed to save settings: {str(e)}")

def create_icon_image(status="green"):
    image = Image.new("RGB", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    color = {"green": "green", "red": "red", "orange": "orange"}.get(status, "green")
    draw.ellipse((8, 8, 56, 56), fill=color)
    return image

def check_internet():
    try:
        requests.get("http://www.google.com", timeout=2)
        return True
    except:
        return False

class PingBaanApp:
    def __init__(self, root):
        self.root = root
        self.settings = load_settings()
        self.language = self.settings.get("language", "en")
        self.texts = LANGUAGES[self.language]
        self.root.title(self.texts["title"])
        self.style = ttkb.Style(theme="flatly")
        self.sites = load_sites()
        self.site_frames = {}
        self.timeout_tracker = {site: 0 for site in self.sites}
        self.timeout_notification_sent = {site: False for site in self.sites}
        self.previous_ping = {site: None for site in self.sites}
        self.ping_history = {site: deque(maxlen=10) for site in self.sites}  # تاریخچه 10 پینگ آخر
        self.internet_notification_sent = False
        self.tray_icon = None
        self.tray_thread = None
        self.running = True
        self.pinging = True  # وضعیت پینگ (شروع/توقف)

        # تعریف استایل‌های سفارشی برای رنگ‌های مختلف
        self.style.configure("Success.TLabel", foreground="green")
        self.style.configure("Danger.TLabel", foreground="red")
        self.style.configure("Warning.TLabel", foreground="orange")
        self.style.configure("Increasing.TLabel", foreground="red")
        self.style.configure("Decreasing.TLabel", foreground="green")

        self.frame = ttk.Frame(self.root, padding=10)
        self.frame.pack(fill="both", expand=True)

        self.add_widgets()
        self.start_pinging()

        self.root.protocol("WM_DELETE_WINDOW", self.hide_to_tray)

    def add_widgets(self):
        # فریم ورودی سایت
        self.input_frame = ttk.Frame(self.frame)
        self.input_frame.pack(fill="x", pady=5)

        self.site_label = ttk.Label(self.input_frame, text=self.texts["site_label"])
        self.site_label.pack(side="left")
        self.entry = ttk.Entry(self.input_frame, width=30)
        self.entry.pack(side="left", padx=5)
        self.add_button = ttk.Button(self.input_frame, text=self.texts["add_site"], command=self.add_site, bootstyle=PRIMARY)
        self.add_button.pack(side="left", padx=5)

        # دکمه توقف/شروع پینگ
        self.toggle_button = ttk.Button(self.input_frame, text=self.texts["toggle_ping"], command=self.toggle_pinging, bootstyle=WARNING)
        self.toggle_button.pack(side="left", padx=5)

        # فریم تنظیمات
        self.settings_frame = ttk.Labelframe(self.frame, text=self.texts["settings"], padding=5)
        self.settings_frame.pack(fill="x", pady=5)

        self.language_label = ttk.Label(self.settings_frame, text=self.texts["language_label"])
        self.language_label.grid(row=0, column=0, padx=5, pady=2)

        # فریم برای دکمه‌های رادیویی
        self.language_frame = ttk.Frame(self.settings_frame)
        self.language_frame.grid(row=0, column=1, padx=5, pady=2)
        self.language_var = tk.StringVar(value=self.language)
        ttk.Radiobutton(self.language_frame, text="English", value="en", variable=self.language_var, command=self.change_language).pack(side="left", padx=5)
        ttk.Radiobutton(self.language_frame, text="فارسی", value="fa", variable=self.language_var, command=self.change_language).pack(side="left", padx=5)

        # فریم وضعیت
        self.status_frame = ttk.Frame(self.frame)
        self.status_frame.pack(fill="both", expand=True, pady=10)

        for site in self.sites:
            self.add_site_row(site)

    def add_site_row(self, site):
        row_frame = ttk.Frame(self.status_frame)
        row_frame.pack(anchor="w", fill="x", pady=2)

        result_label = ttk.Label(row_frame, text=f"{site}: Checking...", anchor="w", width=35, font=("Consolas", 10))
        result_label.pack(side="left")

        trend_label = ttk.Label(row_frame, text="", width=2, font=("Consolas", 10))
        trend_label.pack(side="left")

        avg_label = ttk.Label(row_frame, text="", width=10, font=("Consolas", 10))
        avg_label.pack(side="left")

        # فقط برای سایت‌های غیرپیش‌فرض دکمه حذف اضافه می‌شود
        if site not in DEFAULT_SITES:
            delete_button = ttk.Button(row_frame, text="❌", command=lambda s=site: self.delete_site(s), bootstyle=DANGER)
            delete_button.pack(side="right")

        self.site_frames[site] = (row_frame, result_label, trend_label, avg_label)
        if site not in self.timeout_tracker:
            self.timeout_tracker[site] = 0
            self.timeout_notification_sent[site] = False
            self.previous_ping[site] = None
            self.ping_history[site] = deque(maxlen=10)

    def add_site(self):
        site = self.entry.get().strip().lower()
        if not validators.domain(site) and not validators.url(site):
            messagebox.showerror("Error", self.texts["invalid_site"])
            return
        if site in self.sites:
            messagebox.showerror("Error", self.texts["invalid_site"])
            return
        self.sites.append(site)
        save_sites(self.sites)
        self.add_site_row(site)
        self.entry.delete(0, tk.END)

    def delete_site(self, site):
        if site in self.sites and site not in DEFAULT_SITES:
            self.sites.remove(site)
            save_sites(self.sites)
            frame, result_label, trend_label, avg_label = self.site_frames.pop(site)
            self.timeout_tracker.pop(site, None)
            self.timeout_notification_sent.pop(site, None)
            self.previous_ping.pop(site, None)
            self.ping_history.pop(site, None)
            frame.destroy()

    def update_ui_language(self):
        # به‌روزرسانی عنوان پنجره
        self.root.title(self.texts["title"])

        # به‌روزرسانی فریم ورودی
        self.site_label.configure(text=self.texts["site_label"])
        self.add_button.configure(text=self.texts["add_site"])
        self.toggle_button.configure(text=self.texts["toggle_ping"] if self.pinging else self.texts["start_ping"])

        # به‌روزرسانی فریم تنظیمات
        self.settings_frame.configure(text=self.texts["settings"])
        self.language_label.configure(text=self.texts["language_label"])

        # به‌روزرسانی System Tray
        if self.tray_icon:
            self.tray_icon.stop()
            self.tray_icon = None
            self.hide_to_tray()

    def change_language(self):
        try:
            new_language = self.language_var.get()
            self.settings = {"language": new_language}
            save_settings(self.settings)
            self.language = new_language
            self.texts = LANGUAGES[self.language]
            self.update_ui_language()
            messagebox.showinfo("Info", self.texts["settings_saved"])
        except Exception as e:
            logging.error(f"Failed to change language: {str(e)}")
            messagebox.showerror("Error", f"Invalid settings: {str(e)}")

    def toggle_pinging(self):
        self.pinging = not self.pinging
        self.toggle_button.configure(
            text=self.texts["toggle_ping"] if self.pinging else self.texts["start_ping"],
            bootstyle=WARNING if self.pinging else SUCCESS
        )
        if not self.pinging:
            for site in self.sites:
                if site in self.site_frames:
                    result_label, trend_label, avg_label = self.site_frames[site][1:4]
                    result_label.configure(text=f"{site}: {self.texts['stopped']}", style="Warning.TLabel")
                    trend_label.configure(text="", style="Warning.TLabel")
                    avg_label.configure(text="", style="Warning.TLabel")

    def ping_site(self, site):
        try:
            delay = ping(site, timeout=2)
            if delay is None:
                return site, "❌ Timeout", "Danger.TLabel", None
            return site, f"✅ {round(delay * 1000)} ms", "Success.TLabel", round(delay * 1000)
        except Exception as e:
            logging.error(f"Ping failed for {site}: {str(e)}")
            return site, f"⚠️ Error: {str(e)}", "Warning.TLabel", None

    def start_pinging(self):
        def loop():
            while self.running:
                if not self.pinging:
                    time.sleep(1)
                    continue

                if not check_internet():
                    if not self.internet_notification_sent:
                        notification.notify(
                            title=self.texts["title"],
                            message=self.texts["no_internet"],
                            app_icon=None,
                            timeout=5
                        )
                        self.internet_notification_sent = True
                    for site in self.sites:
                        if site in self.site_frames:
                            result_label, trend_label, avg_label = self.site_frames[site][1:4]
                            result_label.configure(text=f"{site}: ❌ No Internet", style="Danger.TLabel")
                            trend_label.configure(text="", style="Danger.TLabel")
                            avg_label.configure(text="", style="Danger.TLabel")
                            self.timeout_tracker[site] = 0
                            self.timeout_notification_sent[site] = False
                            self.previous_ping[site] = None
                            self.ping_history[site].clear()
                    time.sleep(1)
                    continue

                self.internet_notification_sent = False

                online_count = 0
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    futures = {executor.submit(self.ping_site, site): site for site in self.sites}
                    for future in concurrent.futures.as_completed(futures):
                        site, result, style, ping_ms = future.result()
                        if site in self.site_frames:
                            result_label, trend_label, avg_label = self.site_frames[site][1:4]
                            result_label.configure(text=f"{site}: {result}", style=style)
                            # مقایسه پینگ با پینگ قبلی
                            if ping_ms is not None and self.previous_ping[site] is not None:
                                if ping_ms > self.previous_ping[site]:
                                    trend_label.configure(text="↑", style="Increasing.TLabel")
                                elif ping_ms < self.previous_ping[site]:
                                    trend_label.configure(text="↓", style="Decreasing.TLabel")
                                else:
                                    trend_label.configure(text="", style=style)
                            else:
                                trend_label.configure(text="", style=style)

                            # به‌روزرسانی تاریخچه و میانگین پینگ
                            if ping_ms is not None:
                                self.ping_history[site].append(ping_ms)
                                avg_ping = sum(self.ping_history[site]) / len(self.ping_history[site]) if self.ping_history[site] else 0
                                avg_label.configure(text=f"Avg: {round(avg_ping)} ms", style=style)
                            else:
                                avg_label.configure(text="", style=style)

                        # مدیریت تایم‌اوت‌ها
                        if "❌ Timeout" in result:
                            self.timeout_tracker[site] += 1
                            if self.timeout_tracker[site] >= 10 and not self.timeout_notification_sent[site]:
                                notification.notify(
                                    title=self.texts["title"],
                                    message=self.texts["timeout_alert"].format(site=site),
                                    app_icon=None,
                                    timeout=5
                                )
                                self.timeout_notification_sent[site] = True
                        else:
                            self.timeout_tracker[site] = 0
                            self.timeout_notification_sent[site] = False

                        self.previous_ping[site] = ping_ms

                        if "✅" in result:
                            online_count += 1

                # به‌روزرسانی آیکون System Tray
                tray_status = "green" if online_count == len(self.sites) else "red" if online_count == 0 else "orange"
                if self.tray_icon:
                    self.tray_icon.icon = create_icon_image(tray_status)
                    self.tray_icon.title = f"{self.texts['title']} - {online_count}/{len(self.sites)} Online"

                time.sleep(1)

        thread = threading.Thread(target=loop, daemon=True)
        thread.start()

    def hide_to_tray(self):
        self.root.withdraw()
        if self.tray_icon is None:
            image = create_icon_image()
            menu = pystray.Menu(
                pystray.MenuItem(self.texts["tray_show"], self.show_window, default=True),
                pystray.MenuItem(self.texts["tray_exit"], self.exit_app)
            )
            self.tray_icon = pystray.Icon(self.texts["title"], image, self.texts["title"], menu)
            self.tray_thread = threading.Thread(target=self.tray_icon.run, daemon=True)
            self.tray_thread.start()

    def show_window(self, icon=None, item=None):
        self.root.deiconify()
        if self.tray_icon:
            self.tray_icon.stop()
            self.tray_icon = None

    def exit_app(self, icon=None, item=None):
        self.running = False
        if self.tray_icon:
            self.tray_icon.stop()
        self.root.destroy()
        sys.exit()

if __name__ == "__main__":
    root = ttkb.Window(themename="flatly")
    app = PingBaanApp(root)
    root.mainloop()
