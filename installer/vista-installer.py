#!/usr/bin/env python3
"""
Vista Linux TUI Installer
─────────────────────────
A full curses-based installer that partitions a real disk, bootstraps
Debian Sid, installs the chosen desktop (GNOME or KDE Plasma OLED),
installs Vista, and configures GRUB.

Must be run as root.
"""

import curses
import os
import subprocess
import sys
import time
import shutil
import crypt
import textwrap

# ═══════════════════════════════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════════════════════════════

VISTA_ASCII = r"""
   ####*************###*#*+=-:..:
 ******+++===+++++***#####**+=+
 +++===----:------=-=++***#####
 =-----==+*********++====+*####
 --==++**=--:.........:::-+****
 ++**+=:.:.  ..:.    .:   :=**#
 **+-:-+**:..#@#. ... -+-  .:=*
 +=:-*@@@*.::=*:   .: :%%=.  :=
 ++*%@@@@*.::     .::.:%@*--+**
 ***##%%@#..-:....::. =@%*=*@@@
 *##****%%=..:::::...*@%##%@@@@
 *####*****+=-:::::-*#**%%@@@@@
 *#####******+++++==+=#%%%@@@@@
 ##############******#%@@@@@@@@
"""


KEYBOARD_LAYOUTS = [
    ("us",     "English (US)"),
    ("gb",     "English (UK)"),
    ("es",     "Spanish"),
    ("fr",     "French"),
    ("de",     "German"),
    ("it",     "Italian"),
    ("pt",     "Portuguese"),
    ("br",     "Portuguese (Brazil)"),
    ("ru",     "Russian"),
    ("jp",     "Japanese"),
    ("kr",     "Korean"),
    ("latam",  "Latin American"),
]

TIMEZONES = [
    "America/New_York", "America/Chicago", "America/Denver",
    "America/Los_Angeles", "America/Sao_Paulo", "America/Argentina/Buenos_Aires",
    "America/Mexico_City", "Europe/London", "Europe/Madrid", "Europe/Paris",
    "Europe/Berlin", "Europe/Rome", "Europe/Moscow", "Asia/Tokyo",
    "Asia/Shanghai", "Asia/Kolkata", "Asia/Seoul", "Australia/Sydney",
    "Pacific/Auckland", "UTC",
]

DESKTOPS = [
    ("gnome", "GNOME",
     "GNOME desktop with Dash to Dock extension.\n"
     "Modern, clean, touch-friendly. Dark theme enabled by default."),
    ("kde",   "KDE Plasma — OLED Pure Black",
     "KDE Plasma with a custom pure-black OLED theme.\n"
     "True #000000 blacks everywhere. Great for OLED screens.\n"
     "Includes Latte-style bottom panel."),
]


# ═══════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════

def run(cmd, check=True, capture=True):
    """Run a shell command, return (returncode, stdout)."""
    r = subprocess.run(
        cmd, shell=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.STDOUT if capture else None,
    )
    out = r.stdout.decode(errors="replace") if capture and r.stdout else ""
    if check and r.returncode != 0:
        raise RuntimeError(f"Command failed: {cmd}\n{out}")
    return r.returncode, out


def get_disks():
    """Return list of (device, size, model) from lsblk."""
    _, raw = run("lsblk -d -n -o NAME,SIZE,MODEL -e 7,11", check=False)
    disks = []
    for line in raw.strip().splitlines():
        parts = line.split(None, 2)
        if len(parts) >= 2:
            name = parts[0]
            size = parts[1]
            model = parts[2] if len(parts) > 2 else ""
            disks.append((f"/dev/{name}", size, model.strip()))
    return disks


def is_efi():
    return os.path.isdir("/sys/firmware/efi")


# ═══════════════════════════════════════════════════════════════════
# Curses UI helpers
# ═══════════════════════════════════════════════════════════════════

# Colour pair indices
CP_NORMAL   = 1   # white on blue
CP_HEADER   = 2   # black on cyan
CP_WARN     = 3   # red on blue
CP_OK       = 4   # green on blue
CP_HILITE   = 5   # black on white (selection highlight)
CP_DIM      = 6   # cyan on blue
CP_PROGRESS = 7   # black on green
CP_ACCENT   = 8   # magenta on blue


def init_colors():
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(CP_NORMAL,   curses.COLOR_WHITE,   curses.COLOR_BLUE)
    curses.init_pair(CP_HEADER,   curses.COLOR_BLACK,   curses.COLOR_CYAN)
    curses.init_pair(CP_WARN,     curses.COLOR_RED,     curses.COLOR_BLUE)
    curses.init_pair(CP_OK,       curses.COLOR_GREEN,   curses.COLOR_BLUE)
    curses.init_pair(CP_HILITE,   curses.COLOR_BLACK,   curses.COLOR_WHITE)
    curses.init_pair(CP_DIM,      curses.COLOR_CYAN,    curses.COLOR_BLUE)
    curses.init_pair(CP_PROGRESS, curses.COLOR_BLACK,   curses.COLOR_GREEN)
    curses.init_pair(CP_ACCENT,   curses.COLOR_MAGENTA, curses.COLOR_BLUE)


def draw_box(win, y, x, h, w, attr=0):
    """Draw a box with Unicode box-drawing characters."""
    try:
        win.addstr(y,         x, "╔" + "═" * (w - 2) + "╗", attr)
        for row in range(y + 1, y + h - 1):
            win.addstr(row,   x, "║",         attr)
            win.addstr(row,   x + w - 1, "║", attr)
        win.addstr(y + h - 1, x, "╚" + "═" * (w - 2) + "╝", attr)
    except curses.error:
        pass


def center(win, y, text, attr=0):
    _, w = win.getmaxyx()
    x = max(0, (w - len(text)) // 2)
    try:
        win.addstr(y, x, text, attr)
    except curses.error:
        pass


def safe_addstr(win, y, x, text, attr=0):
    h, w = win.getmaxyx()
    if 0 <= y < h and 0 <= x < w:
        try:
            win.addstr(y, x, text[:w - x], attr)
        except curses.error:
            pass


def draw_header(win, title):
    win.erase()
    h, w = win.getmaxyx()
    win.bkgd(" ", curses.color_pair(CP_NORMAL))
    # header bar
    safe_addstr(win, 0, 0, " " * w, curses.color_pair(CP_HEADER))
    label = f" ⬢ VISTA LINUX INSTALLER — {title} "
    safe_addstr(win, 0, max(0, (w - len(label)) // 2), label,
                curses.color_pair(CP_HEADER) | curses.A_BOLD)
    # separator
    safe_addstr(win, 1, 0, "─" * w, curses.color_pair(CP_DIM))


def draw_footer(win, text="[Enter] Next  [Esc] Back  [Q] Quit"):
    h, w = win.getmaxyx()
    safe_addstr(win, h - 1, 0, " " * (w - 1), curses.color_pair(CP_HEADER))
    safe_addstr(win, h - 1, 2, text, curses.color_pair(CP_HEADER))


def draw_progress(win, y, pct, label=""):
    h, w = win.getmaxyx()
    bar_w = max(10, w - 22)
    filled = int(pct / 100 * bar_w)
    bar = "█" * filled + "░" * (bar_w - filled)
    safe_addstr(win, y, 4, f"[{bar}] {pct:3d}%",
                curses.color_pair(CP_OK) | curses.A_BOLD)
    if label:
        safe_addstr(win, y + 1, 4, label.ljust(w - 8), curses.color_pair(CP_DIM))


def menu_select(win, y_start, items, sel=0, label_fn=str):
    """Let user pick from a list.  Returns index, -1 for escape, -2 for quit."""
    h, w = win.getmaxyx()
    max_visible = h - y_start - 3

    while True:
        top = max(0, min(sel - max_visible // 2, len(items) - max_visible))

        for i in range(min(len(items), max_visible)):
            idx = top + i
            if idx >= len(items):
                break
            txt = label_fn(items[idx])
            if len(txt) > w - 10:
                txt = txt[: w - 13] + "…"
            attr = curses.color_pair(CP_HILITE) | curses.A_BOLD if idx == sel \
                else curses.color_pair(CP_NORMAL)
            prefix = " ▸ " if idx == sel else "   "
            safe_addstr(win, y_start + i, 3, f"{prefix}{txt}".ljust(w - 6), attr)

        # scroll indicators
        if top > 0:
            safe_addstr(win, y_start - 1, w - 4, " ▲ ", curses.color_pair(CP_DIM))
        if top + max_visible < len(items):
            safe_addstr(win, y_start + max_visible, w - 4, " ▼ ",
                        curses.color_pair(CP_DIM))

        win.refresh()
        c = win.getch()
        if c == curses.KEY_UP and sel > 0:
            sel -= 1
        elif c == curses.KEY_DOWN and sel < len(items) - 1:
            sel += 1
        elif c == curses.KEY_PPAGE:
            sel = max(0, sel - max_visible)
        elif c == curses.KEY_NPAGE:
            sel = min(len(items) - 1, sel + max_visible)
        elif c == ord("\n"):
            return sel
        elif c == 27:
            return -1
        elif c in (ord("q"), ord("Q")):
            return -2


def text_input(win, y, x, prompt, default="", secret=False, max_len=40):
    """Simple single-line text input.  Returns string or None for escape."""
    safe_addstr(win, y, x, prompt, curses.color_pair(CP_OK) | curses.A_BOLD)
    px = x + len(prompt) + 1
    buf = list(default)
    curses.curs_set(1)
    while True:
        shown = "*" * len(buf) if secret else "".join(buf)
        safe_addstr(win, y, px, shown.ljust(max_len),
                    curses.color_pair(CP_NORMAL) | curses.A_UNDERLINE)
        try:
            win.move(y, px + len(buf))
        except curses.error:
            pass
        win.refresh()
        c = win.getch()
        if c == ord("\n"):
            curses.curs_set(0)
            return "".join(buf)
        elif c == 27:
            curses.curs_set(0)
            return None
        elif c in (curses.KEY_BACKSPACE, 127, 8):
            if buf:
                buf.pop()
        elif 32 <= c <= 126 and len(buf) < max_len:
            buf.append(chr(c))


# ═══════════════════════════════════════════════════════════════════
# Installer class
# ═══════════════════════════════════════════════════════════════════

class VistaInstaller:
    def __init__(self, stdscr):
        self.scr = stdscr
        curses.curs_set(0)
        init_colors()
        self.scr.bkgd(" ", curses.color_pair(CP_NORMAL))
        self.scr.keypad(True)

        self.cfg = {
            "keyboard":  "us",
            "timezone":  "America/New_York",
            "disk":      "",
            "disk_info": "",
            "hostname":  "vista",
            "username":  "vista",
            "password":  "",
            "efi":       is_efi(),
            "desktop":   "gnome",       # "gnome" or "kde"
        }

    # ── navigation ────────────────────────────────────────────────
    def run(self):
        screens = [
            self.screen_welcome,
            self.screen_keyboard,
            self.screen_timezone,
            self.screen_desktop,
            self.screen_disk,
            self.screen_partitioning,
            self.screen_user,
            self.screen_summary,
            self.screen_install,
            self.screen_done,
        ]
        idx = 0
        while 0 <= idx < len(screens):
            result = screens[idx]()
            if result == "next":
                idx += 1
            elif result == "back":
                idx = max(0, idx - 1)
            elif result == "quit":
                return

    # ══════════════════════════════════════════════════════════════
    # SCREENS
    # ══════════════════════════════════════════════════════════════

    # ── 1. Welcome ────────────────────────────────────────────────
    def screen_welcome(self):
        draw_header(self.scr, "Welcome")
        h, w = self.scr.getmaxyx()
        for i, line in enumerate(VISTA_ASCII.strip().splitlines()):
            center(self.scr, 3 + i, line,
                   curses.color_pair(CP_OK) | curses.A_BOLD)

        center(self.scr, 10, "Welcome to the Vista Linux Installer",
               curses.color_pair(CP_NORMAL) | curses.A_BOLD)
        center(self.scr, 12, "A Debian Sid rolling release powered by the Vista package manager.")
        center(self.scr, 13, "Choose GNOME or KDE Plasma OLED as your desktop.")

        boot_mode = "EFI" if self.cfg["efi"] else "Legacy BIOS"
        center(self.scr, 15, f"Boot mode detected: {boot_mode}",
               curses.color_pair(CP_DIM))

        draw_footer(self.scr, "[Enter] Start  [Q] Quit")
        self.scr.refresh()

        while True:
            c = self.scr.getch()
            if c == ord("\n"):
                return "next"
            if c in (ord("q"), ord("Q")):
                return "quit"

    # ── 2. Keyboard ───────────────────────────────────────────────
    def screen_keyboard(self):
        draw_header(self.scr, "Keyboard Layout")
        safe_addstr(self.scr, 3, 4, "Select your keyboard layout:",
                    curses.color_pair(CP_NORMAL) | curses.A_BOLD)
        draw_footer(self.scr)

        sel = menu_select(self.scr, 5, KEYBOARD_LAYOUTS,
                          label_fn=lambda t: f"{t[0]:8s}  {t[1]}")
        if sel == -1:
            return "back"
        if sel == -2:
            return "quit"
        self.cfg["keyboard"] = KEYBOARD_LAYOUTS[sel][0]
        return "next"

    # ── 3. Timezone ───────────────────────────────────────────────
    def screen_timezone(self):
        draw_header(self.scr, "Timezone")
        safe_addstr(self.scr, 3, 4, "Select your timezone:",
                    curses.color_pair(CP_NORMAL) | curses.A_BOLD)
        draw_footer(self.scr)

        sel = menu_select(self.scr, 5, TIMEZONES)
        if sel == -1:
            return "back"
        if sel == -2:
            return "quit"
        self.cfg["timezone"] = TIMEZONES[sel]
        return "next"

    # ── 4. Desktop Environment ────────────────────────────────────
    def screen_desktop(self):
        draw_header(self.scr, "Desktop Environment")
        h, w = self.scr.getmaxyx()
        safe_addstr(self.scr, 3, 4, "Choose your desktop environment:",
                    curses.color_pair(CP_NORMAL) | curses.A_BOLD)

        sel = 0
        while True:
            for i, (de_id, de_name, de_desc) in enumerate(DESKTOPS):
                y_pos = 5 + i * 6

                if i == sel:
                    attr_name = curses.color_pair(CP_HILITE) | curses.A_BOLD
                    attr_box  = curses.color_pair(CP_HILITE)
                    attr_desc = curses.color_pair(CP_HILITE)
                    pointer   = " ▸ "
                else:
                    attr_name = curses.color_pair(CP_NORMAL) | curses.A_BOLD
                    attr_box  = curses.color_pair(CP_DIM)
                    attr_desc = curses.color_pair(CP_DIM)
                    pointer   = "   "

                box_w = min(w - 6, 68)
                draw_box(self.scr, y_pos, 3, 5, box_w, attr_box)
                safe_addstr(self.scr, y_pos, 5,
                            f"{pointer}{de_name} ", attr_name)
                # description lines
                for j, dline in enumerate(de_desc.splitlines()):
                    safe_addstr(self.scr, y_pos + 1 + j, 6,
                                dline[:box_w - 6], attr_desc)

            draw_footer(self.scr)
            self.scr.refresh()

            c = self.scr.getch()
            if c == curses.KEY_UP and sel > 0:
                sel -= 1
            elif c == curses.KEY_DOWN and sel < len(DESKTOPS) - 1:
                sel += 1
            elif c == ord("\n"):
                self.cfg["desktop"] = DESKTOPS[sel][0]
                return "next"
            elif c == 27:
                return "back"
            elif c in (ord("q"), ord("Q")):
                return "quit"

    # ── 5. Disk selection ─────────────────────────────────────────
    def screen_disk(self):
        draw_header(self.scr, "Select Disk")

        disks = get_disks()
        if not disks:
            center(self.scr, 6, "No disks found!",
                   curses.color_pair(CP_WARN) | curses.A_BOLD)
            draw_footer(self.scr, "[Esc] Back")
            self.scr.refresh()
            while self.scr.getch() != 27:
                pass
            return "back"

        safe_addstr(self.scr, 3, 4, "Select the disk to install Vista Linux on:",
                    curses.color_pair(CP_NORMAL) | curses.A_BOLD)
        safe_addstr(self.scr, 4, 4,
                    "⚠  WARNING: The selected disk will be COMPLETELY ERASED!",
                    curses.color_pair(CP_WARN) | curses.A_BOLD)
        draw_footer(self.scr)

        sel = menu_select(self.scr, 6, disks,
                          label_fn=lambda d: f"{d[0]:12s}  {d[1]:>8s}  {d[2]}")
        if sel == -1:
            return "back"
        if sel == -2:
            return "quit"
        self.cfg["disk"] = disks[sel][0]
        self.cfg["disk_info"] = f"{disks[sel][0]} ({disks[sel][1]})"
        return "next"

    # ── 6. Partitioning scheme ────────────────────────────────────
    def screen_partitioning(self):
        draw_header(self.scr, "Partition Scheme")
        h, w = self.scr.getmaxyx()

        disk = self.cfg["disk"]
        efi = self.cfg["efi"]

        safe_addstr(self.scr, 3, 4, f"Disk: {self.cfg['disk_info']}",
                    curses.color_pair(CP_OK) | curses.A_BOLD)
        safe_addstr(self.scr, 5, 4,
                    "The following partition layout will be created:",
                    curses.color_pair(CP_NORMAL))

        if efi:
            layout = [
                ("EFI System Partition", "512 MB",  "FAT32",  f"{disk}1 → /boot/efi"),
                ("Swap",                 "4 GB",    "swap",   f"{disk}2"),
                ("Root",                 "Rest",    "ext4",   f"{disk}3 → /"),
            ]
        else:
            layout = [
                ("BIOS Boot",  "1 MB",   "—",     f"{disk}1"),
                ("Swap",       "4 GB",   "swap",  f"{disk}2"),
                ("Root",       "Rest",   "ext4",  f"{disk}3 → /"),
            ]

        safe_addstr(self.scr, 7, 6,
                    f"{'Partition':<26s} {'Size':<10s} {'Type':<8s} {'Device'}",
                    curses.color_pair(CP_DIM))
        safe_addstr(self.scr, 8, 6, "─" * 64, curses.color_pair(CP_DIM))
        for i, (part, size, ptype, dev) in enumerate(layout):
            safe_addstr(self.scr, 9 + i, 6,
                        f"{part:<26s} {size:<10s} {ptype:<8s} {dev}")

        draw_footer(self.scr, "[Enter] Accept  [Esc] Back")
        self.scr.refresh()

        while True:
            c = self.scr.getch()
            if c == ord("\n"):
                return "next"
            if c == 27:
                return "back"

    # ── 7. User setup ─────────────────────────────────────────────
    def screen_user(self):
        while True:
            draw_header(self.scr, "User Setup")
            safe_addstr(self.scr, 3, 4, "Create your user account:",
                        curses.color_pair(CP_NORMAL) | curses.A_BOLD)

            hostname = text_input(self.scr, 5, 4, "Hostname:",
                                  self.cfg["hostname"])
            if hostname is None:
                return "back"
            self.cfg["hostname"] = hostname or self.cfg["hostname"]

            username = text_input(self.scr, 7, 4, "Username:",
                                  self.cfg["username"])
            if username is None:
                return "back"
            self.cfg["username"] = username or self.cfg["username"]

            password = text_input(self.scr, 9, 4, "Password:", secret=True)
            if password is None:
                return "back"
            if not password:
                safe_addstr(self.scr, 11, 4, "Password cannot be empty!",
                            curses.color_pair(CP_WARN) | curses.A_BOLD)
                self.scr.refresh()
                time.sleep(1.5)
                continue

            confirm = text_input(self.scr, 11, 4, "Confirm :", secret=True)
            if confirm is None:
                return "back"
            if password != confirm:
                safe_addstr(self.scr, 13, 4, "Passwords do not match!",
                            curses.color_pair(CP_WARN) | curses.A_BOLD)
                self.scr.refresh()
                time.sleep(1.5)
                continue

            self.cfg["password"] = password
            return "next"

    # ── 8. Summary ────────────────────────────────────────────────
    def screen_summary(self):
        draw_header(self.scr, "Summary")
        h, w = self.scr.getmaxyx()

        de_label = "GNOME + Dash to Dock" if self.cfg["desktop"] == "gnome" \
            else "KDE Plasma — OLED Pure Black"

        draw_box(self.scr, 3, 2, 14, min(w - 4, 72), curses.color_pair(CP_DIM))

        items = [
            ("Keyboard",  self.cfg["keyboard"]),
            ("Timezone",  self.cfg["timezone"]),
            ("Desktop",   de_label),
            ("Disk",      self.cfg["disk_info"]),
            ("Boot mode", "EFI" if self.cfg["efi"] else "Legacy BIOS"),
            ("Hostname",  self.cfg["hostname"]),
            ("Username",  self.cfg["username"]),
            ("Password",  "••••••"),
            ("Pkg mgr",   "Vista (apt backend)"),
        ]

        for i, (k, v) in enumerate(items):
            safe_addstr(self.scr, 4 + i, 5, f"{k + ':':<14s}",
                        curses.color_pair(CP_DIM))
            safe_addstr(self.scr, 4 + i, 19, v,
                        curses.color_pair(CP_OK) | curses.A_BOLD)

        center(self.scr, 18,
               "⚠  THIS WILL ERASE ALL DATA ON THE SELECTED DISK ⚠",
               curses.color_pair(CP_WARN) | curses.A_BOLD | curses.A_BLINK)

        draw_footer(self.scr, "[Enter] BEGIN INSTALLATION  [Esc] Go Back")
        self.scr.refresh()

        while True:
            c = self.scr.getch()
            if c == ord("\n"):
                return "next"
            if c == 27:
                return "back"

    # ── 9. Installation ───────────────────────────────────────────
    def screen_install(self):
        draw_header(self.scr, "Installing")
        self.scr.refresh()

        de_label = "GNOME + Dash to Dock" if self.cfg["desktop"] == "gnome" \
            else "KDE Plasma OLED"

        steps = [
            ("Wiping partition table",              5, self._step_wipe),
            ("Creating partitions",                10, self._step_partition),
            ("Formatting partitions",              18, self._step_format),
            ("Mounting filesystems",               22, self._step_mount),
            ("Bootstrapping Debian Sid",           48, self._step_debootstrap),
            ("Configuring base system",            55, self._step_configure_base),
            ("Installing kernel & base packages",  65, self._step_packages),
            ("Installing Vista package manager",   70, self._step_vista),
            ("Replacing apt with Vista wrapper",   73, self._step_replace_apt),
            (f"Installing {de_label}",             88, self._step_desktop),
            (f"Configuring {de_label}",            92, self._step_configure_desktop),
            ("Installing bootloader (GRUB)",       96, self._step_grub),
            ("Finalising",                        100, self._step_finalise),
        ]

        for label, pct, fn in steps:
            draw_progress(self.scr, 5, pct, label)
            self.scr.refresh()
            try:
                fn()
            except Exception as e:
                safe_addstr(self.scr, 10, 4, f"ERROR: {e}",
                            curses.color_pair(CP_WARN) | curses.A_BOLD)
                safe_addstr(self.scr, 12, 4,
                            "Check /tmp/vista-install.log for details.",
                            curses.color_pair(CP_DIM))
                draw_footer(self.scr, "[Enter] Abort to shell")
                self.scr.refresh()
                while self.scr.getch() != ord("\n"):
                    pass
                return "quit"

        draw_progress(self.scr, 5, 100, "Installation complete!")
        safe_addstr(self.scr, 9, 4, "✔ Vista Linux has been installed successfully!",
                    curses.color_pair(CP_OK) | curses.A_BOLD)
        draw_footer(self.scr, "[Enter] Continue")
        self.scr.refresh()
        while self.scr.getch() != ord("\n"):
            pass
        return "next"

    # ── 10. Done ──────────────────────────────────────────────────
    def screen_done(self):
        draw_header(self.scr, "Complete!")
        for i, line in enumerate(VISTA_ASCII.strip().splitlines()):
            center(self.scr, 3 + i, line,
                   curses.color_pair(CP_OK) | curses.A_BOLD)

        center(self.scr, 10, "Vista Linux has been installed!",
               curses.color_pair(CP_NORMAL) | curses.A_BOLD)
        center(self.scr, 12, "Remove the installation media and reboot.")
        center(self.scr, 13, "Login with your user account and enjoy!")

        de = self.cfg["desktop"]
        if de == "gnome":
            center(self.scr, 15, "Desktop: GNOME with Dash to Dock",
                   curses.color_pair(CP_DIM))
        else:
            center(self.scr, 15, "Desktop: KDE Plasma — Pure Black OLED",
                   curses.color_pair(CP_DIM))

        draw_footer(self.scr, "[R] Reboot Now  [Esc] Exit to Live Shell")
        self.scr.refresh()

        while True:
            c = self.scr.getch()
            if c in (ord("r"), ord("R")):
                curses.endwin()
                os.system("umount -R /mnt 2>/dev/null; reboot")
                return "quit"
            if c == 27:
                return "quit"

    # ══════════════════════════════════════════════════════════════
    # INSTALLATION STEP IMPLEMENTATIONS
    # ══════════════════════════════════════════════════════════════

    def _part(self, n):
        """Return partition device, e.g. /dev/sda1 or /dev/nvme0n1p1."""
        disk = self.cfg["disk"]
        if "nvme" in disk or "mmcblk" in disk:
            return f"{disk}p{n}"
        return f"{disk}{n}"

    def _step_wipe(self):
        disk = self.cfg["disk"]
        run(f"wipefs -af {disk}")
        run(f"sgdisk --zap-all {disk}", check=False)

    def _step_partition(self):
        disk = self.cfg["disk"]
        if self.cfg["efi"]:
            run(f"parted -s {disk} mklabel gpt")
            run(f"parted -s {disk} mkpart ESP fat32 1MiB 513MiB")
            run(f"parted -s {disk} set 1 esp on")
            run(f"parted -s {disk} mkpart swap linux-swap 513MiB 4609MiB")
            run(f"parted -s {disk} mkpart root ext4 4609MiB 100%")
        else:
            run(f"parted -s {disk} mklabel msdos")
            run(f"parted -s {disk} mkpart primary ext4 1MiB 2MiB")
            run(f"parted -s {disk} set 1 bios_grub on")
            run(f"parted -s {disk} mkpart primary linux-swap 2MiB 4098MiB")
            run(f"parted -s {disk} mkpart primary ext4 4098MiB 100%")
        time.sleep(1)
        run("partprobe", check=False)
        time.sleep(1)

    def _step_format(self):
        if self.cfg["efi"]:
            run(f"mkfs.fat -F32 {self._part(1)}")
        run(f"mkswap {self._part(2)}")
        run(f"mkfs.ext4 -F {self._part(3)}")

    def _step_mount(self):
        run(f"mount {self._part(3)} /mnt")
        if self.cfg["efi"]:
            run("mkdir -p /mnt/boot/efi")
            run(f"mount {self._part(1)} /mnt/boot/efi")
        run(f"swapon {self._part(2)}", check=False)

    def _step_debootstrap(self):
        run("debootstrap --variant=minbase sid /mnt http://deb.debian.org/debian")

    def _step_configure_base(self):
        hostname = self.cfg["hostname"]
        username = self.cfg["username"]
        password = self.cfg["password"]
        keyboard = self.cfg["keyboard"]
        timezone = self.cfg["timezone"]

        # hostname
        with open("/mnt/etc/hostname", "w") as f:
            f.write(hostname + "\n")
        with open("/mnt/etc/hosts", "w") as f:
            f.write(f"127.0.0.1  localhost\n127.0.1.1  {hostname}\n")

        # fstab
        root_uuid = run(f"blkid -s UUID -o value {self._part(3)}")[1].strip()
        swap_uuid = run(f"blkid -s UUID -o value {self._part(2)}")[1].strip()
        fstab = f"UUID={root_uuid}  /  ext4  errors=remount-ro  0  1\n"
        fstab += f"UUID={swap_uuid}  none  swap  sw  0  0\n"
        if self.cfg["efi"]:
            efi_uuid = run(f"blkid -s UUID -o value {self._part(1)}")[1].strip()
            fstab += f"UUID={efi_uuid}  /boot/efi  vfat  umask=0077  0  1\n"
        with open("/mnt/etc/fstab", "w") as f:
            f.write(fstab)

        # timezone
        run(f"ln -sf /usr/share/zoneinfo/{timezone} /mnt/etc/localtime")

        # locale
        with open("/mnt/etc/locale.gen", "w") as f:
            f.write("en_US.UTF-8 UTF-8\n")

        # keyboard
        os.makedirs("/mnt/etc/default", exist_ok=True)
        with open("/mnt/etc/default/keyboard", "w") as f:
            f.write(textwrap.dedent(f"""\
                XKBMODEL="pc105"
                XKBLAYOUT="{keyboard}"
                XKBVARIANT=""
                XKBOPTIONS=""
                BACKSPACE="guess"
            """))

        # sources.list
        with open("/mnt/etc/apt/sources.list", "w") as f:
            f.write("deb http://deb.debian.org/debian sid main contrib non-free non-free-firmware\n")

        # branding
        if os.path.exists("/usr/share/vista/vista-ascii.txt"):
            os.makedirs("/mnt/usr/share/vista", exist_ok=True)
            shutil.copy("/usr/share/vista/vista-ascii.txt",
                        "/mnt/usr/share/vista/")
        for bfile in ("os-release", "issue", "motd"):
            src = f"/etc/{bfile}"
            if os.path.exists(src):
                shutil.copy(src, f"/mnt/etc/{bfile}")

        # user account
        hashed = crypt.crypt(password, crypt.mksalt(crypt.METHOD_SHA512))
        self._chroot(f"useradd -m -G sudo -s /bin/bash {username}")
        self._chroot(f"usermod -p '{hashed}' {username}")

        # skel bashrc
        skel_src = "/etc/skel/.bashrc"
        if os.path.exists(skel_src):
            shutil.copy(skel_src, f"/mnt/home/{username}/.bashrc")
            run(f"chroot /mnt chown {username}:{username} /home/{username}/.bashrc")

    def _step_packages(self):
        self._bind_mount()
        self._chroot("apt-get update")
        self._chroot(
            "DEBIAN_FRONTEND=noninteractive apt-get install -y "
            "linux-image-amd64 linux-headers-amd64 firmware-linux firmware-linux-nonfree "
            "firmware-misc-nonfree broadcom-sta-dkms dkms locales console-setup sudo "
            "network-manager iproute2 iputils-ping curl wget git nano vim "
            "python3 dconf-cli uuid-runtime ca-certificates "
            "build-essential pkg-config libssl-dev mesa-utils nvidia-detect tlp macfanctld"
        )
        self._chroot("locale-gen")
        self._chroot("systemctl enable tlp 2>/dev/null || true")

    def _step_vista(self):
        self._chroot(
            "bash -c '"
            "export RUSTUP_HOME=/tmp/rustup CARGO_HOME=/tmp/cargo && "
            "curl --proto =https --tlsv1.2 -sSf https://sh.rustup.rs | "
            "sh -s -- -y --profile minimal && "
            "source /tmp/cargo/env && "
            "cd /tmp && git clone https://github.com/whyfle/vista.git && "
            "cd vista && cargo build --release && "
            "cp target/release/vista /usr/local/bin/vista && "
            "chmod +x /usr/local/bin/vista && "
            "cd / && rm -rf /tmp/vista /tmp/rustup /tmp/cargo"
            "'"
        )
        os.makedirs("/mnt/etc/vista", exist_ok=True)
        with open("/mnt/etc/vista/config.toml", "w") as f:
            f.write('[vista]\nbackend = "apt"\ncolors = true\n')

    def _step_replace_apt(self):
        for name, real in [("apt", "apt.real"), ("apt-get", "apt-get.real")]:
            src = f"/mnt/usr/bin/{name}"
            if os.path.isfile(src) and not os.path.islink(src):
                os.rename(src, f"/mnt/usr/bin/{real}")
            wrapper = textwrap.dedent(f"""\
                #!/bin/bash
                echo -e "\\033[1;35m╔══════════════════════════════════════════════════════════════╗\\033[0m"
                echo -e "\\033[1;35m║  Vista Linux uses \\033[1;32mvista\\033[1;35m as its package manager.              ║\\033[0m"
                echo -e "\\033[1;35m╚══════════════════════════════════════════════════════════════╝\\033[0m"
                echo ""
                echo -e "  Try:  \\033[1;32mvista install <package>\\033[0m"
                echo ""
                read -p "Run the original {name} command anyway? [y/N] " -n 1 -r
                echo
                if [[ \\$REPLY =~ ^[Yy]$ ]]; then
                    exec /usr/bin/{real} "$@"
                else
                    exit 0
                fi
            """)
            with open(src, "w") as f:
                f.write(wrapper)
            os.chmod(src, 0o755)

    # ── Desktop: install ──────────────────────────────────────────

    def _step_desktop(self):
        if self.cfg["desktop"] == "gnome":
            self._install_gnome()
        else:
            self._install_kde()

    def _install_gnome(self):
        self._chroot(
            "DEBIAN_FRONTEND=noninteractive apt-get.real install -y "
            "gnome-core gdm3 gnome-shell-extension-dash-to-dock "
            "gnome-terminal nautilus gnome-tweaks"
        )
        self._chroot("systemctl enable gdm3")

    def _install_kde(self):
        self._chroot(
            "DEBIAN_FRONTEND=noninteractive apt-get.real install -y "
            "kde-plasma-desktop sddm plasma-workspace plasma-nm "
            "konsole dolphin kate ark plasma-systemmonitor "
            "breeze-icon-theme breeze-cursor-theme breeze-gtk-theme "
            "sddm-theme-breeze kde-spectacle "
            "xdg-desktop-portal-kde "
            "pipewire pipewire-audio wireplumber"
        )
        self._chroot("systemctl enable sddm")

    # ── Desktop: configure ────────────────────────────────────────

    def _step_configure_desktop(self):
        if self.cfg["desktop"] == "gnome":
            self._configure_gnome()
        else:
            self._configure_kde()

    def _configure_gnome(self):
        """Set up GNOME with Dash to Dock and dark theme."""
        # dconf profile
        os.makedirs("/mnt/etc/dconf/profile", exist_ok=True)
        with open("/mnt/etc/dconf/profile/user", "w") as f:
            f.write("user-db:user\nsystem-db:local\n")

        os.makedirs("/mnt/etc/dconf/db/local.d", exist_ok=True)
        with open("/mnt/etc/dconf/db/local.d/00-vista", "w") as f:
            f.write(textwrap.dedent("""\
                [org/gnome/desktop/interface]
                color-scheme='prefer-dark'
                gtk-theme='Adwaita-dark'
                clock-show-weekday=true
                font-antialiasing='rgba'

                [org/gnome/desktop/wm/preferences]
                button-layout='appmenu:minimize,maximize,close'

                [org/gnome/shell]
                enabled-extensions=['dash-to-dock@micxgx.gmail.com']
                favorite-apps=['org.gnome.Terminal.desktop', 'org.gnome.Nautilus.desktop', 'firefox-esr.desktop']

                [org/gnome/shell/extensions/dash-to-dock]
                dock-position='BOTTOM'
                dash-max-icon-size=48
                extend-height=false
                dock-fixed=true
                transparency-mode='DYNAMIC'
                custom-theme-shrink=true
                show-trash=false
                show-mounts=false
                apply-custom-theme=true
                running-indicator-style='DOTS'

                [org/gnome/desktop/peripherals/touchpad]
                tap-to-click=true
                natural-scroll=true

                [org/gnome/settings-daemon/plugins/power]
                sleep-inactive-ac-type='nothing'

                [org/gnome/terminal/legacy]
                theme-variant='dark'
            """))

        # Lock Dash to Dock extension so it stays enabled
        os.makedirs("/mnt/etc/dconf/db/local.d/locks", exist_ok=True)
        with open("/mnt/etc/dconf/db/local.d/locks/vista", "w") as f:
            f.write("/org/gnome/shell/enabled-extensions\n")

        # GDM dark
        os.makedirs("/mnt/etc/dconf/db/gdm.d", exist_ok=True)
        with open("/mnt/etc/dconf/db/gdm.d/00-vista", "w") as f:
            f.write(textwrap.dedent("""\
                [org/gnome/desktop/interface]
                color-scheme='prefer-dark'
                gtk-theme='Adwaita-dark'
                [org/gnome/login-screen]
                banner-message-enable=true
                banner-message-text='Welcome to Vista Linux'
            """))
        with open("/mnt/etc/dconf/profile/gdm", "w") as f:
            f.write("user-db:user\nsystem-db:gdm\nfile-db:/usr/share/gdm/greeter-dconf-defaults\n")

        self._chroot("dconf update")

    def _configure_kde(self):
        """Set up KDE Plasma with a pure-black OLED theme."""
        username = self.cfg["username"]
        home = f"/mnt/home/{username}"

        # ── Vista OLED Black colour scheme ────────────────────────
        colors_dir = f"{home}/.local/share/color-schemes"
        os.makedirs(colors_dir, exist_ok=True)
        with open(f"{colors_dir}/VistaOLED.colors", "w") as f:
            f.write(textwrap.dedent("""\
                [ColorEffects:Disabled]
                Color=56,56,56
                ColorAmount=0
                ColorEffect=0
                ContrastAmount=0.65
                ContrastEffect=1
                IntensityAmount=0.1
                IntensityEffect=2

                [ColorEffects:Inactive]
                ChangeSelectionColor=true
                Color=112,111,110
                ColorAmount=0.025
                ColorEffect=2
                ContrastAmount=0.1
                ContrastEffect=2
                Enable=false
                IntensityAmount=0
                IntensityEffect=0

                [Colors:Button]
                BackgroundAlternate=0,0,0
                BackgroundNormal=10,10,10
                DecorationFocus=61,174,233
                DecorationHover=61,174,233
                ForegroundActive=61,174,233
                ForegroundInactive=160,160,160
                ForegroundLink=29,153,243
                ForegroundNegative=218,68,83
                ForegroundNeutral=246,116,0
                ForegroundNormal=225,225,225
                ForegroundPositive=39,174,96
                ForegroundVisited=155,89,182

                [Colors:Complementary]
                BackgroundAlternate=0,0,0
                BackgroundNormal=0,0,0
                DecorationFocus=61,174,233
                DecorationHover=61,174,233
                ForegroundActive=61,174,233
                ForegroundInactive=160,160,160
                ForegroundLink=29,153,243
                ForegroundNegative=218,68,83
                ForegroundNeutral=246,116,0
                ForegroundNormal=225,225,225
                ForegroundPositive=39,174,96
                ForegroundVisited=155,89,182

                [Colors:Header]
                BackgroundAlternate=0,0,0
                BackgroundNormal=0,0,0
                DecorationFocus=61,174,233
                DecorationHover=61,174,233
                ForegroundActive=61,174,233
                ForegroundInactive=160,160,160
                ForegroundLink=29,153,243
                ForegroundNegative=218,68,83
                ForegroundNeutral=246,116,0
                ForegroundNormal=225,225,225
                ForegroundPositive=39,174,96
                ForegroundVisited=155,89,182

                [Colors:Selection]
                BackgroundAlternate=29,153,243
                BackgroundNormal=61,174,233
                DecorationFocus=61,174,233
                DecorationHover=61,174,233
                ForegroundActive=255,255,255
                ForegroundInactive=255,255,255
                ForegroundLink=253,188,75
                ForegroundNegative=176,55,69
                ForegroundNeutral=198,92,0
                ForegroundNormal=255,255,255
                ForegroundPositive=23,104,57
                ForegroundVisited=155,89,182

                [Colors:Tooltip]
                BackgroundAlternate=0,0,0
                BackgroundNormal=5,5,5
                DecorationFocus=61,174,233
                DecorationHover=61,174,233
                ForegroundActive=61,174,233
                ForegroundInactive=160,160,160
                ForegroundLink=29,153,243
                ForegroundNegative=218,68,83
                ForegroundNeutral=246,116,0
                ForegroundNormal=225,225,225
                ForegroundPositive=39,174,96
                ForegroundVisited=155,89,182

                [Colors:View]
                BackgroundAlternate=0,0,0
                BackgroundNormal=0,0,0
                DecorationFocus=61,174,233
                DecorationHover=61,174,233
                ForegroundActive=61,174,233
                ForegroundInactive=160,160,160
                ForegroundLink=29,153,243
                ForegroundNegative=218,68,83
                ForegroundNeutral=246,116,0
                ForegroundNormal=225,225,225
                ForegroundPositive=39,174,96
                ForegroundVisited=155,89,182

                [Colors:Window]
                BackgroundAlternate=0,0,0
                BackgroundNormal=0,0,0
                DecorationFocus=61,174,233
                DecorationHover=61,174,233
                ForegroundActive=61,174,233
                ForegroundInactive=160,160,160
                ForegroundLink=29,153,243
                ForegroundNegative=218,68,83
                ForegroundNeutral=246,116,0
                ForegroundNormal=225,225,225
                ForegroundPositive=39,174,96
                ForegroundVisited=155,89,182

                [General]
                ColorScheme=VistaOLED
                Name=Vista OLED Black
                shadeSortColumn=true

                [KDE]
                contrast=4

                [WM]
                activeBackground=0,0,0
                activeBlend=255,255,255
                activeForeground=225,225,225
                inactiveBackground=0,0,0
                inactiveBlend=75,71,67
                inactiveForeground=160,160,160
            """))

        # ── kdeglobals — global Plasma settings ───────────────────
        kde_cfg = f"{home}/.config"
        os.makedirs(kde_cfg, exist_ok=True)

        with open(f"{kde_cfg}/kdeglobals", "w") as f:
            f.write(textwrap.dedent("""\
                [General]
                ColorScheme=VistaOLED
                Name=Vista OLED Black
                TerminalApplication=konsole
                TerminalService=org.kde.konsole.desktop
                XftAntialias=true
                XftHintStyle=hintslight
                XftSubPixel=rgb
                fixed=Hack,10,-1,5,400,0,0,0,0,0,0,0,0,0,0,1

                [Icons]
                Theme=breeze-dark

                [KDE]
                AnimationDurationFactor=0.5
                LookAndFeelPackage=org.kde.breezedark.desktop
                SingleClick=false
                contrast=4
                widgetStyle=Breeze
            """))

        # ── Plasma shell (panel + desktop) ────────────────────────
        with open(f"{kde_cfg}/plasmashellrc", "w") as f:
            f.write(textwrap.dedent("""\
                [PlasmaViews][Panel 2]
                floating=1
                panelOpacity=2

                [PlasmaViews][Panel 2][Defaults]
                thickness=44

                [PlasmaViews][Panel 2][Horizontal1920]
                thickness=44
            """))

        # Panel configuration — bottom panel like a dock
        with open(f"{kde_cfg}/plasma-org.kde.plasma.desktop-appletsrc", "w") as f:
            f.write(textwrap.dedent("""\
                [ActionPlugins][0]
                MidButton;NoModifier=org.kde.paste
                RightButton;NoModifier=org.kde.contextmenu

                [Containments][1]
                activityId=
                formfactor=0
                immutability=1
                lastScreen=0
                location=0
                plugin=org.kde.desktopcontainment
                wallpaperplugin=org.kde.image

                [Containments][1][Wallpaper][org.kde.image][General]
                Color=0,0,0
                FillMode=0
                SlidePaths=/usr/share/wallpapers/

                [Containments][2]
                activityId=
                formfactor=2
                immutability=1
                lastScreen=0
                location=4
                plugin=org.kde.panel

                [Containments][2][General]
                AppletOrder=3;4;5;6

                [Containments][2][Applets][3]
                immutability=1
                plugin=org.kde.plasma.kickoff

                [Containments][2][Applets][4]
                immutability=1
                plugin=org.kde.plasma.icontasks

                [Containments][2][Applets][4][Configuration][General]
                launchers=preferred://filemanager,preferred://browser,applications:org.kde.konsole.desktop

                [Containments][2][Applets][5]
                immutability=1
                plugin=org.kde.plasma.systemtray

                [Containments][2][Applets][6]
                immutability=1
                plugin=org.kde.plasma.digitalclock

                [Containments][2][Applets][6][Configuration][Appearance]
                use24hFormat=2

                [ScreenMapping]
                itemsOnDisabledScreens=
            """))

        # ── KWin — window manager tweaks ──────────────────────────
        with open(f"{kde_cfg}/kwinrc", "w") as f:
            f.write(textwrap.dedent("""\
                [Compositing]
                AnimationSpeed=3
                Backend=OpenGL
                GLCore=true
                LatencyPolicy=Low

                [Desktops]
                Number=2
                Rows=1

                [Effect-overview]
                BorderActivate=9

                [org.kde.kdecoration2]
                BorderSize=None
                BorderSizeAuto=false
                ButtonsOnLeft=
                ButtonsOnRight=IAX
                library=org.kde.breeze
                theme=Breeze
            """))

        # ── Konsole OLED profile ──────────────────────────────────
        konsole_dir = f"{home}/.local/share/konsole"
        os.makedirs(konsole_dir, exist_ok=True)

        with open(f"{konsole_dir}/VistaOLED.profile", "w") as f:
            f.write(textwrap.dedent("""\
                [Appearance]
                ColorScheme=VistaOLED
                Font=Hack,11,-1,5,400,0,0,0,0,0,0,0,0,0,0,1

                [General]
                Command=/bin/bash
                Name=Vista OLED
                Parent=FALLBACK/

                [Scrolling]
                HistoryMode=2
                ScrollBarPosition=2
            """))

        # Konsole color scheme — pure black background
        with open(f"{konsole_dir}/VistaOLED.colorscheme", "w") as f:
            f.write(textwrap.dedent("""\
                [Background]
                Color=0,0,0

                [BackgroundFaint]
                Color=0,0,0

                [BackgroundIntense]
                Color=0,0,0

                [Color0]
                Color=0,0,0

                [Color0Faint]
                Color=24,24,24

                [Color0Intense]
                Color=104,104,104

                [Color1]
                Color=218,68,83

                [Color1Faint]
                Color=120,37,45

                [Color1Intense]
                Color=255,84,100

                [Color2]
                Color=39,174,96

                [Color2Faint]
                Color=21,94,52

                [Color2Intense]
                Color=50,220,120

                [Color3]
                Color=246,116,0

                [Color3Faint]
                Color=133,62,0

                [Color3Intense]
                Color=255,150,40

                [Color4]
                Color=29,153,243

                [Color4Faint]
                Color=16,82,131

                [Color4Intense]
                Color=61,174,233

                [Color5]
                Color=155,89,182

                [Color5Faint]
                Color=84,48,98

                [Color5Intense]
                Color=185,109,212

                [Color6]
                Color=26,188,156

                [Color6Faint]
                Color=14,102,84

                [Color6Intense]
                Color=40,220,185

                [Color7]
                Color=225,225,225

                [Color7Faint]
                Color=160,160,160

                [Color7Intense]
                Color=255,255,255

                [Foreground]
                Color=225,225,225

                [ForegroundFaint]
                Color=160,160,160

                [ForegroundIntense]
                Color=255,255,255

                [General]
                Anchor=0.5,0.5
                Blur=false
                ColorRandomization=false
                Description=Vista OLED Black
                FillStyle=Tile
                Opacity=1
                Wallpaper=
                WallpaperFlipType=NoFlip
                WallpaperOpacity=1
            """))

        # Set VistaOLED as default Konsole profile
        with open(f"{kde_cfg}/konsolerc", "w") as f:
            f.write(textwrap.dedent("""\
                [Desktop Entry]
                DefaultProfile=VistaOLED.profile

                [General]
                ConfigVersion=1

                [MainWindow]
                MenuBar=Disabled
                ToolBarsMovable=Disabled
            """))

        # ── SDDM theme (dark) ────────────────────────────────────
        os.makedirs("/mnt/etc/sddm.conf.d", exist_ok=True)
        with open("/mnt/etc/sddm.conf.d/vista.conf", "w") as f:
            f.write(textwrap.dedent("""\
                [Theme]
                Current=breeze

                [General]
                InputMethod=

                [Users]
                MaximumUid=60513
                MinimumUid=1000
            """))

        # ── GTK dark for KDE ──────────────────────────────────────
        gtk3_dir = f"{home}/.config/gtk-3.0"
        os.makedirs(gtk3_dir, exist_ok=True)
        with open(f"{gtk3_dir}/settings.ini", "w") as f:
            f.write(textwrap.dedent("""\
                [Settings]
                gtk-application-prefer-dark-theme=true
                gtk-theme-name=Breeze-Dark
                gtk-icon-theme-name=breeze-dark
                gtk-cursor-theme-name=breeze_cursors
                gtk-font-name=Noto Sans 10
            """))

        gtk4_dir = f"{home}/.config/gtk-4.0"
        os.makedirs(gtk4_dir, exist_ok=True)
        with open(f"{gtk4_dir}/settings.ini", "w") as f:
            f.write(textwrap.dedent("""\
                [Settings]
                gtk-application-prefer-dark-theme=true
                gtk-theme-name=Breeze-Dark
                gtk-icon-theme-name=breeze-dark
                gtk-cursor-theme-name=breeze_cursors
                gtk-font-name=Noto Sans 10
            """))

        # ── Fix ownership ─────────────────────────────────────────
        self._chroot(
            f"chown -R {username}:{username} /home/{username}/.config "
            f"/home/{username}/.local"
        )

    # ── Bootloader ────────────────────────────────────────────────

    def _step_grub(self):
        if self.cfg["efi"]:
            self._chroot(
                "DEBIAN_FRONTEND=noninteractive apt-get.real install -y "
                "grub-efi-amd64 efibootmgr"
            )
            self._chroot(
                "grub-install --target=x86_64-efi "
                "--efi-directory=/boot/efi --bootloader-id=vista --recheck"
            )
        else:
            self._chroot(
                "DEBIAN_FRONTEND=noninteractive apt-get.real install -y "
                "grub-pc"
            )
            self._chroot(f"grub-install --target=i386-pc {self.cfg['disk']}")

        grub_default = "/mnt/etc/default/grub"
        if os.path.exists(grub_default):
            with open(grub_default, "r") as f:
                grub = f.read()
            grub = grub.replace(
                'GRUB_DISTRIBUTOR=`lsb_release -i -s 2> /dev/null || echo Debian`',
                'GRUB_DISTRIBUTOR="Vista Linux"')
            if "GRUB_CMDLINE_LINUX_DEFAULT" in grub:
                grub = grub.replace(
                    'GRUB_CMDLINE_LINUX_DEFAULT="quiet"',
                    'GRUB_CMDLINE_LINUX_DEFAULT="quiet splash plymouth.ignore-serial-consoles vt.handoff=7"'
                )
            if "GRUB_BACKGROUND" not in grub:
                grub += '\nGRUB_BACKGROUND="/boot/grub/grub-splash.png"\n'
            with open(grub_default, "w") as f:
                f.write(grub)

        # Install plymouth packages and theme on installed system
        self._chroot("DEBIAN_FRONTEND=noninteractive apt-get.real install -y plymouth plymouth-themes")
        plymouth_target = "/mnt/usr/share/plymouth/themes/vista-logo"
        os.makedirs(plymouth_target, exist_ok=True)
        if os.path.exists("/usr/share/vista/plymouth"):
            for item in os.listdir("/usr/share/vista/plymouth"):
                s = os.path.join("/usr/share/vista/plymouth", item)
                d = os.path.join(plymouth_target, item)
                if os.path.isfile(s):
                    shutil.copy(s, d)
        
        # Copy GRUB splash
        os.makedirs("/mnt/boot/grub", exist_ok=True)
        if os.path.exists("/boot/grub/grub-splash.png"):
            shutil.copy("/boot/grub/grub-splash.png", "/mnt/boot/grub/grub-splash.png")

        self._chroot("plymouth-set-default-theme vista-logo || true")
        self._chroot("update-initramfs -u || true")
        self._chroot("update-grub")

    def _step_finalise(self):
        src = "/usr/local/bin/vista-installer"
        if os.path.exists(src):
            shutil.copy(src, "/mnt/usr/local/bin/vista-installer")
            os.chmod("/mnt/usr/local/bin/vista-installer", 0o755)

        # Copy custom neofetch / vista-fetch to target
        fetch_src = "/usr/local/bin/neofetch"
        if os.path.exists(fetch_src):
            shutil.copy(fetch_src, "/mnt/usr/local/bin/neofetch")
            os.chmod("/mnt/usr/local/bin/neofetch", 0o755)
            run("ln -sf neofetch /mnt/usr/local/bin/vista-fetch", check=False)

        # Copy prime-run and vista-gpu-setup
        for gpu_tool in ["prime-run", "vista-gpu-setup"]:
            p = f"/usr/local/bin/{gpu_tool}"
            if os.path.exists(p):
                shutil.copy(p, f"/mnt{p}")
                os.chmod(f"/mnt{p}", 0o755)

        # Auto-configure iMac 2009 fan control if Apple hardware
        self._chroot("/usr/local/bin/vista-gpu-setup || true")

        self._unbind_mount()
        if self.cfg["efi"]:
            run("umount /mnt/boot/efi", check=False)
        run("swapoff -a", check=False)
        run("umount -R /mnt", check=False)

    # ── chroot helpers ────────────────────────────────────────────

    def _bind_mount(self):
        for d in ("dev", "dev/pts", "proc", "sys", "run"):
            os.makedirs(f"/mnt/{d}", exist_ok=True)
        run("mount --bind /dev /mnt/dev")
        run("mount --bind /dev/pts /mnt/dev/pts")
        run("mount -t proc proc /mnt/proc")
        run("mount -t sysfs sysfs /mnt/sys")
        if self.cfg["efi"] and os.path.isdir("/sys/firmware/efi/efivars"):
            run("mount --bind /sys/firmware/efi/efivars "
                "/mnt/sys/firmware/efi/efivars", check=False)
        run("mount --bind /run /mnt/run")
        shutil.copy("/etc/resolv.conf", "/mnt/etc/resolv.conf")

    def _unbind_mount(self):
        for d in reversed(["run", "sys/firmware/efi/efivars",
                           "sys", "proc", "dev/pts", "dev"]):
            run(f"umount /mnt/{d}", check=False)

    def _chroot(self, cmd):
        run(f"chroot /mnt /bin/bash -c '{cmd}'")


# ═══════════════════════════════════════════════════════════════════
# Entry point
# ═══════════════════════════════════════════════════════════════════

def main():
    if os.geteuid() != 0:
        print("\033[1;31mError: vista-installer must be run as root.\033[0m")
        print("Try:  sudo vista-installer")
        sys.exit(1)
    curses.wrapper(lambda stdscr: VistaInstaller(stdscr).run())


if __name__ == "__main__":
    main()
