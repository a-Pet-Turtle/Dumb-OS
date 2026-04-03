'''
DUI - Dumb User Interface
A TI-86 iShell inspired terminal file manager for Dumb OS.
Part of the StarShot Studios suite.
'''

import os
import sys
import stat
import shutil
import socket
import subprocess
from datetime import datetime

try:
    from reader.rescape import *
except ImportError:
    R=B=DM=IT=UL=BL=""
    GREEN=LGREEN=CYAN=LCYAN=YELLOW=LYELLOW=WHITE=LWHITE=""
    RED=LRED=BLUE=LBLUE=MAGENTA=LMAGENTA=""
    BG_BLACK=BG_BLUE=BG_CYAN=BG_GREEN=BG_RED=BG_WHITE=""
    BG_LBLUE=BG_LGREEN=BG_LCYAN=BG_LRED=BG_LWHITE=""
    CLEAR_SCREEN=HOME=HIDE_CURSOR=SHOW_CURSOR=""
    def pos(r,c): return f"\033[{r};{c}H"
    def style(*a): return "".join(a)

import tty
import termios

# ── Constants ──────────────────────────────────────────────────────────────────

VERSION     = "2.0"
PINNED_FILE = os.path.expanduser("~/.dui_pins")
TABS_FILE   = os.path.expanduser("~/.dui_tabs")

DEFAULT_TABS = [
    {"label": "DWNLODS", "path": os.path.expanduser("~/Downloads")},
    {"label": "DOCS",    "path": os.path.expanduser("~/Documents")},
    {"label": "MEDIA",   "path": os.path.expanduser("~/Pictures")},
    {"label": "OTHER",   "path": os.path.expanduser("~")},
]

# ── Actions per file type ──────────────────────────────────────────────────────

IMAGE_EXTS = {".png",".jpg",".jpeg",".gif",".webp",".avif",".bmp",
              ".tiff",".tif",".ico",".heic",".heif"}

def get_actions(fpath):
    if os.path.isdir(fpath):
        return ["Open", "Rename", "Delete", "Pin"]
    ext = os.path.splitext(fpath)[1].lower()
    if ext == ".py":
        return ["Execute", "Open with Nano", "Rename", "Delete", "Pin"]
    elif ext == ".sh":
        return ["Execute", "Open with Nano", "Rename", "Delete", "Pin"]
    elif ext in IMAGE_EXTS:
        return ["View Image", "Open with Nano", "Rename", "Delete", "Pin"]
    else:
        return ["Open with Nano", "Rename", "Delete", "Pin"]

# ── Raw keypress ───────────────────────────────────────────────────────────────

def getch():
    fd  = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
        if ch == '\x1b':
            ch2 = sys.stdin.read(1)
            if ch2 == '[':
                ch3 = sys.stdin.read(1)
                if ch3 in ('1','2','3','4','5','6','7','8','9'):
                    ch4 = sys.stdin.read(1)
                    return ch + ch2 + ch3 + ch4
                return ch + ch2 + ch3
            return ch + ch2
        return ch
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)

# ── Pins & tabs ────────────────────────────────────────────────────────────────

def load_pins():
    try:
        with open(PINNED_FILE) as f:
            return [l.strip() for l in f if l.strip() and os.path.exists(l.strip())]
    except:
        return []

def save_pins(pins):
    try:
        with open(PINNED_FILE, "w") as f:
            f.write("\n".join(pins))
    except:
        pass

def load_tabs():
    try:
        tabs = []
        with open(TABS_FILE) as f:
            for line in f:
                parts = line.strip().split("|", 1)
                if len(parts) == 2:
                    tabs.append({"label": parts[0].strip(), "path": parts[1].strip()})
        return tabs if tabs else DEFAULT_TABS
    except:
        return DEFAULT_TABS

# ── File helpers ───────────────────────────────────────────────────────────────

def file_type(path):
    if os.path.isdir(path): return "DIR"
    ext   = os.path.splitext(path)[1].lower()
    types = {
        ".py":"PYTHON",".sh":"SHELL",".txt":"TEXT",".md":"MARKDOWN",
        ".json":"JSON",".html":"HTML",".png":"IMAGE",".jpg":"IMAGE",
        ".gif":"IMAGE",".jpeg":"IMAGE",".mp3":"AUDIO",".wav":"AUDIO",
        ".mp4":"VIDEO",".pdf":"PDF",".zip":"ARCHIVE",".tar":"ARCHIVE",
        ".pkl":"PICKLE",".csv":"CSV",
    }
    return types.get(ext, "FILE")

def file_size(path):
    try:
        s = os.path.getsize(path)
        if s < 1024:      return f"{s}B"
        elif s < 1024**2: return f"{s//1024}KB"
        elif s < 1024**3: return f"{s//1024**2}MB"
        else:             return f"{s//1024**3}GB"
    except:
        return "?"

def file_color(path):
    if os.path.isdir(path): return LCYAN
    t = file_type(path)
    if t == "PYTHON":       return LGREEN
    if t == "SHELL":        return LYELLOW
    if t in ("IMAGE","VIDEO"): return LMAGENTA
    if t == "AUDIO":        return LBLUE
    if t == "HTML":         return LRED
    if t == "PICKLE":       return YELLOW
    return LWHITE

def list_dir(path):
    try:
        e = os.listdir(path)
        e.sort(key=lambda x: (not os.path.isdir(os.path.join(path,x)), x.lower()))
        return e
    except PermissionError:
        return ["[Permission Denied]"]
    except:
        return []

def get_ncols(cols):
    pw = cols - 28
    if pw >= 120: return 3
    if pw >= 70:  return 2
    return 1

# ── Statusbar ──────────────────────────────────────────────────────────────────

def draw_statusbar(cols, rows):
    try:
        bat = open("/sys/class/power_supply/BAT0/capacity").read().strip()
        bat_str = f"BAT:{bat}%"
    except:
        bat_str = ""
    try:
        host = socket.gethostname()
    except:
        host = "unknown"
    time_str = datetime.now().strftime("%H:%M")
    try:
        wifi = subprocess.run(["iwgetid","-r"],capture_output=True,text=True).stdout.strip()
    except:
        wifi = ""
    left  = f" DUI v{VERSION}  {host}"
    right = "  ".join(p for p in [wifi,bat_str,time_str] if p) + " "
    gap   = cols - len(left) - len(right)
    bar   = f"{BG_BLUE}{LWHITE}{B}{left}{' '*max(0,gap)}{right}{R}"
    print(f"\0337{pos(rows,1)}{bar}\0338", end="", flush=True)

# ── Folder tab bar ─────────────────────────────────────────────────────────────

def draw_tabbar(all_labels, active_tab, tab_scroll, cols):
    total = len(all_labels)
    max_w = cols - 2

    # Auto-scroll so active tab is always visible
    if active_tab < tab_scroll:
        tab_scroll = active_tab
    else:
        x = 0
        last_visible = tab_scroll
        for i in range(tab_scroll, total):
            tw = len(all_labels[i]) + 4
            if x + tw > max_w: break
            last_visible = i
            x += tw
        if active_tab > last_visible:
            while active_tab > last_visible and tab_scroll < total - 1:
                tab_scroll += 1
                x = 0
                last_visible = tab_scroll
                for i in range(tab_scroll, total):
                    tw = len(all_labels[i]) + 4
                    if x + tw > max_w: break
                    last_visible = i
                    x += tw

    visible = []
    x = 0
    for i in range(tab_scroll, total):
        lbl = all_labels[i]
        tw  = len(lbl) + 4
        if x + tw > max_w: break
        visible.append((i, lbl, x, tw))
        x += tw

    # Two rows: top row has ▀ blocks for raised effect, bottom row has labels
    row1 = ""  # raise indicators
    row2 = ""  # labels
    px   = 0
    for (i, lbl, tx, tw) in visible:
        active = (i == active_tab)
        pad_l  = "  "
        pad_r  = " " * (tw - len(lbl) - 2)
        if active:
            # Active: colored ▀ blocks on top row, highlighted label on bottom
            row1 += f"{BG_BLACK}{LCYAN}{'▄'*tw}{R}"
            row2 += f"{BG_LCYAN}{BLACK}{B}{pad_l}{lbl}{pad_r}{R}"
        else:
            # Inactive: dark top, dim label
            row1 += f"{BG_BLACK}{' '*tw}{R}"
            row2 += f"{BG_BLACK}{DM}{pad_l}{lbl}{pad_r}{R}"
        px += tw

    fill  = " " * max(0, cols - px)
    row1 += f"{BG_BLACK}{fill}{R}"
    row2 += f"{BG_BLACK}{fill}{R}"

    if tab_scroll > 0:
        row2 = f"{BG_BLACK}{LYELLOW}◀{R}" + row2[4:]
    if len(visible) < total - tab_scroll:
        row2 = row2[:-1] + f"{BG_BLACK}{LYELLOW}▶{R}"

    print(pos(1,1) + row1, end="")
    print(pos(2,1) + row2, end="", flush=True)
    return [v[0] for v in visible], tab_scroll

# ── File grid ──────────────────────────────────────────────────────────────────

def draw_files(entries, selected, path, cols, rows, scroll, ncols):
    panel_w = cols - 28
    panel_h = rows - 4
    col_w   = max(1, panel_w // ncols)

    for row in range(panel_h):
        print(pos(row+3, 1), end="")
        line = ""
        for col in range(ncols):
            idx   = (scroll * ncols) + (row * ncols) + col
            if idx < len(entries):
                entry  = entries[idx]
                fpath  = os.path.join(path, entry) if path else entry
                is_dir = os.path.isdir(fpath)
                color  = file_color(fpath)
                prefix = "▶ " if is_dir else "  "
                name   = (prefix + entry)[:col_w-1].ljust(col_w-1)
                if idx == selected:
                    line += f"{BG_LBLUE}{BLACK}{B}{name}{R}"
                else:
                    line += f"{color}{name}{R}"
            else:
                line += " " * (col_w - 1)
        print(line, end="")

# ── Status panel ───────────────────────────────────────────────────────────────

def draw_status_panel(entries, selected, path, cols, rows):
    px      = cols - 27
    panel_h = rows - 4
    for row in range(panel_h):
        print(f"{pos(row+3,px)}{DM}│{R}", end="")
    if not entries or selected >= len(entries):
        return
    entry = entries[selected]
    fpath = os.path.join(path, entry) if path else entry
    color = file_color(fpath)
    try:
        mdate = datetime.fromtimestamp(os.path.getmtime(fpath)).strftime("%Y-%m-%d")
    except:
        mdate = "unknown"
    try:
        mode = oct(stat.S_IMODE(os.stat(fpath).st_mode))[-3:]
    except:
        mode = "???"
    info = [
        ("NAME", entry[:22]),
        ("TYPE", file_type(fpath)),
        ("SIZE", file_size(fpath)),
        ("DATE", mdate),
        ("PERM", mode),
    ]
    row = 3
    print(f"{pos(row,px+2)}{B}{LCYAN}── INFO ──{R}", end=""); row+=1
    for label, value in info:
        if row >= rows-1: break
        print(f"{pos(row,px+2)}{DM}{label}{R}", end=""); row+=1
        print(f"{pos(row,px+2)}{color}{value[:22]}{R}", end=""); row+=1
    row+=1
    if row < rows-1:
        print(f"{pos(row,px+2)}{DM}── {selected+1}/{len(entries)} ──{R}", end="")

# ── Context menu ───────────────────────────────────────────────────────────────

def draw_context_menu(fpath, menu_sel, cols, rows):
    actions = get_actions(fpath)
    name    = os.path.basename(fpath)
    mw      = 26
    mx      = cols - mw - 2
    my      = 3
    print(f"{pos(my,mx)}{BG_LCYAN}{BLACK}{B} {name[:mw-2].ljust(mw-2)} {R}", end="")
    print(f"{pos(my+1,mx)}{BG_LCYAN}{BLACK}{'─'*mw}{R}", end="")
    for i, action in enumerate(actions):
        label = f" {action[:mw-2].ljust(mw-2)} "
        if i == menu_sel:
            print(f"{pos(my+2+i,mx)}{BG_LWHITE}{BLACK}{B}{label}{R}", end="")
        else:
            print(f"{pos(my+2+i,mx)}{BG_BLACK}{LWHITE}{label}{R}", end="")
    fy = my+2+len(actions)
    print(f"{pos(fy,mx)}{BG_BLACK}{DM}{'─'*mw}{R}", end="")
    print(f"{pos(fy+1,mx)}{BG_BLACK}{DM} ↑↓:Move  Enter:Go  b:Back  {R}", end="", flush=True)
    return actions

def run_action(action, fpath, path, entries, selected, pins):
    if action == "Open" and os.path.isdir(fpath):
        return fpath, list_dir(fpath), 0, pins

    elif action == "Execute":
        print(CLEAR_SCREEN + SHOW_CURSOR)
        subprocess.run(["python3", fpath])
        input(f"\n{DM}Press Enter to return...{R}")
        print(CLEAR_SCREEN + HIDE_CURSOR)

    elif action == "Open with Nano":
        print(CLEAR_SCREEN + SHOW_CURSOR)
        subprocess.run(["nano", fpath])
        print(CLEAR_SCREEN + HIDE_CURSOR)

    elif action == "View Image":
        print(CLEAR_SCREEN + SHOW_CURSOR)
        subprocess.run(["chafa", "--symbols", "half", fpath])
        input(f"\n{DM}Press Enter to return...{R}")
        print(CLEAR_SCREEN + HIDE_CURSOR)

    elif action == "Rename":
        cols, rows = os.get_terminal_size()
        print(f"{pos(rows-1,1)}{SHOW_CURSOR}{LWHITE}New name: {R}", end="", flush=True)
        new_name = input("").strip()
        print(HIDE_CURSOR, end="", flush=True)
        if new_name:
            try:
                os.rename(fpath, os.path.join(path, new_name))
                entries  = list_dir(path)
            except:
                pass

    elif action == "Delete":
        cols, rows = os.get_terminal_size()
        print(f"{pos(rows-1,1)}{LRED}Delete '{os.path.basename(fpath)}'? (y/n){R}", end="", flush=True)
        if getch() == 'y':
            try:
                shutil.rmtree(fpath) if os.path.isdir(fpath) else os.remove(fpath)
                entries  = list_dir(path)
                selected = min(selected, max(0, len(entries)-1))
            except:
                pass

    elif action == "Pin":
        if fpath not in pins:
            pins.append(fpath)
            save_pins(pins)

    return path, entries, selected, pins

# ── Settings page ─────────────────────────────────────────────────────────────

def draw_settings(tabs, settings_sel, cols, rows):
    print(pos(3,1) + f"{LCYAN}{B}DUI Settings{R}  {DM}Up/Down:Select  Enter:Edit  q:Back{R}", end="")
    print(pos(4,1) + f"{DM}{'─' * (cols-2)}{R}", end="")
    items = list(tabs) + [{"label": "+ Add new tab", "path": ""}]
    for i, tab in enumerate(items):
        row    = 5 + i
        is_new = (i == len(tabs))
        label  = tab["label"]
        path   = tab["path"]
        if i == settings_sel:
            if is_new:
                print(pos(row,1) + f"{BG_LGREEN}{BLACK}{B}  {label:<10}  {R}", end="")
            else:
                print(pos(row,1) + f"{BG_LBLUE}{BLACK}{B}  {label:<10}  {path[:cols-16]}{R}", end="")
        else:
            if is_new:
                print(pos(row,1) + f"  {DM}{label}{R}", end="")
            else:
                print(pos(row,1) + f"  {LGREEN}{label:<10}{R}  {LWHITE}{path[:cols-16]}{R}", end="")

def edit_tab_inline(tabs, settings_sel, cols, rows):
    is_new    = (settings_sel >= len(tabs))
    old_label = tabs[settings_sel]["label"] if not is_new else ""
    old_path  = tabs[settings_sel]["path"]  if not is_new else ""
    print(f"{pos(rows-2,1)}{SHOW_CURSOR}{LWHITE}Tab label [{old_label}]: {R}", end="", flush=True)
    new_label = input("").strip() or old_label
    print(f"{pos(rows-1,1)}{LWHITE}Directory [{old_path}]: {R}", end="", flush=True)
    new_path  = input("").strip() or old_path
    print(HIDE_CURSOR, end="", flush=True)
    if new_label and new_path:
        if is_new:
            tabs.append({"label": new_label, "path": new_path})
        else:
            tabs[settings_sel] = {"label": new_label, "path": new_path}
        try:
            with open(TABS_FILE, "w") as f:
                for tab in tabs:
                    f.write(f"{tab['label']}|{tab['path']}\n")
        except:
            pass
    return tabs

# ── Main ───────────────────────────────────────────────────────────────────────

def dui(args):
    tabs       = load_tabs()
    pins       = load_pins()

    all_labels = ["HOME"] + [t["label"] for t in tabs] + ["SETTINGS"]
    total_tabs = len(all_labels)

    active_tab   = 1
    tab_scroll   = 0
    selected     = 0
    scroll       = 0
    current_path = tabs[0]["path"] if tabs else os.path.expanduser("~")
    entries      = list_dir(current_path)

    in_menu  = False
    menu_sel = 0
    settings_sel = 0

    print(CLEAR_SCREEN + HIDE_CURSOR + HOME, end="", flush=True)

    def cur_list_path():
        if active_tab == 0:               return pins, ""
        if active_tab == total_tabs - 1:  return [], ""
        return entries, current_path

    def refresh():
        nonlocal entries, tab_scroll
        cols, rows = os.get_terminal_size()
        ncols      = get_ncols(cols)

        for r in range(1, rows+1):
            print(pos(r,1) + " "*cols, end="")

        _, tab_scroll = draw_tabbar(all_labels, active_tab, tab_scroll, cols)

        cl, cp = cur_list_path()

        if active_tab == 0:
            if not pins:
                print(pos(3,1) + f"{DM}No pins. Open a file menu and choose Pin.{R}", end="")
            else:
                draw_files(pins, selected, "", cols, rows, scroll, ncols)
                draw_status_panel(pins, selected, "", cols, rows)
        elif active_tab == total_tabs - 1:
            draw_settings(tabs, settings_sel, cols, rows)
        else:
            draw_files(entries, selected, current_path, cols, rows, scroll, ncols)
            draw_status_panel(entries, selected, current_path, cols, rows)

        if in_menu:
            cl, cp = cur_list_path()
            if cl and selected < len(cl):
                fpath = os.path.join(cp, cl[selected]) if cp else cl[selected]
                draw_context_menu(fpath, menu_sel, cols, rows)

        draw_statusbar(cols, rows)
        help_str = f"{DM} ↑↓←→:Move  Enter:Menu  b:Back  Tab:NextTab  ,.TabScroll  q:Quit {R}"
        print(pos(rows-1,1) + help_str[:cols], end="", flush=True)

    refresh()

    while True:
        cols, rows = os.get_terminal_size()
        ncols      = get_ncols(cols)
        panel_h    = rows - 4
        key        = getch()
        cl, cp     = cur_list_path()

        # ── Context menu ──
        if in_menu:
            cl, cp = cur_list_path()
            fpath  = os.path.join(cp, cl[selected]) if cp else cl[selected]
            actions = get_actions(fpath)
            if key == '\x1b[A':
                menu_sel = (menu_sel-1) % len(actions); refresh()
            elif key == '\x1b[B':
                menu_sel = (menu_sel+1) % len(actions); refresh()
            elif key in ('\r','\n'):
                action  = actions[menu_sel]
                in_menu = False
                new_path, new_entries, new_sel, pins = run_action(
                    action, fpath, cp, list(cl), selected, pins)
                if active_tab != 0 and active_tab != total_tabs-1:
                    current_path = new_path
                    entries      = new_entries
                    selected     = new_sel
                elif active_tab == 0:
                    pass  # pins updated in place
                refresh()
            elif key in ('b','B','\x1b\x1b'):
                in_menu=False; menu_sel=0; refresh()
            continue

        # ── Settings mode ──
        if active_tab == total_tabs - 1:
            settings_items = len(tabs) + 1  # tabs + "add new"
            if key == '[A':
                settings_sel = max(0, settings_sel - 1); refresh()
            elif key == '[B':
                settings_sel = min(settings_items - 1, settings_sel + 1); refresh()
            elif key in ('\r', '\n'):
                cols, rows = os.get_terminal_size()
                tabs = edit_tab_inline(tabs, settings_sel, cols, rows)
                all_labels[:] = ["HOME"] + [t["label"] for t in tabs] + ["SETTINGS"]
                total_tabs = len(all_labels)
                if settings_sel >= len(tabs):
                    settings_sel = max(0, len(tabs) - 1)
                refresh()
            elif key == 'd' and settings_sel < len(tabs):
                tabs.pop(settings_sel)
                try:
                    with open(TABS_FILE, "w") as f:
                        for tab in tabs:
                            f.write(f"{tab['label']}|{tab['path']}\n")
                except:
                    pass
                all_labels[:] = ["HOME"] + [t["label"] for t in tabs] + ["SETTINGS"]
                total_tabs = len(all_labels)
                settings_sel = max(0, min(settings_sel, len(tabs)-1))
                refresh()
            elif key == '\t':
                active_tab = (active_tab + 1) % total_tabs
                selected=0; scroll=0; menu_sel=0; settings_sel=0
                if 1 <= active_tab <= len(tabs):
                    current_path = tabs[active_tab-1]["path"]
                    if not os.path.exists(current_path):
                        os.makedirs(current_path, exist_ok=True)
                    entries = list_dir(current_path)
                refresh()
            elif key == ',':
                active_tab = (active_tab - 1) % total_tabs
                selected=0; scroll=0; menu_sel=0; settings_sel=0
                if 1 <= active_tab <= len(tabs):
                    current_path = tabs[active_tab-1]["path"]
                    if not os.path.exists(current_path):
                        os.makedirs(current_path, exist_ok=True)
                    entries = list_dir(current_path)
                refresh()
            elif key in ('.', '\t'):
                active_tab = (active_tab + 1) % total_tabs
                selected=0; scroll=0; menu_sel=0; settings_sel=0
                if 1 <= active_tab <= len(tabs):
                    current_path = tabs[active_tab-1]["path"]
                    if not os.path.exists(current_path):
                        os.makedirs(current_path, exist_ok=True)
                    entries = list_dir(current_path)
                refresh()
            elif key in ('q', 'Q', 'b', 'B'):
                active_tab = 1; refresh()
            continue

        # ── Normal mode ──
        if key in ('q','Q'):
            break
        elif key == '\x1b\x1b':
            break

        elif key == '\t':
            active_tab = (active_tab+1) % total_tabs
            selected=0; scroll=0; menu_sel=0
            if 1 <= active_tab <= len(tabs):
                current_path = tabs[active_tab-1]["path"]
                if not os.path.exists(current_path):
                    os.makedirs(current_path, exist_ok=True)
                entries = list_dir(current_path)
            if active_tab < tab_scroll:
                tab_scroll = active_tab
            refresh()

        elif key == ',':
            active_tab = (active_tab - 1) % total_tabs
            selected=0; scroll=0; menu_sel=0; settings_sel=0
            if 1 <= active_tab <= len(tabs):
                current_path = tabs[active_tab-1]["path"]
                if not os.path.exists(current_path):
                    os.makedirs(current_path, exist_ok=True)
                entries = list_dir(current_path)
            refresh()
        elif key in ('.', '\t'):
            active_tab = (active_tab + 1) % total_tabs
            selected=0; scroll=0; menu_sel=0; settings_sel=0
            if 1 <= active_tab <= len(tabs):
                current_path = tabs[active_tab-1]["path"]
                if not os.path.exists(current_path):
                    os.makedirs(current_path, exist_ok=True)
                entries = list_dir(current_path)
            refresh()

        elif key == '\x1b[A':  # UP
            if selected - ncols >= 0:
                selected -= ncols
                if selected < scroll * ncols: scroll = max(0, scroll-1)
            refresh()
        elif key == '\x1b[B':  # DOWN
            if selected + ncols < len(cl):
                selected += ncols
                if selected >= (scroll+panel_h)*ncols: scroll+=1
            refresh()
        elif key == '\x1b[D':  # LEFT
            if selected % ncols > 0:
                selected -= 1
            refresh()
        elif key == '\x1b[C':  # RIGHT
            if selected % ncols < ncols-1 and selected+1 < len(cl):
                selected += 1
            refresh()

        elif key in ('b','B'):
            if active_tab not in (0, total_tabs-1):
                parent = os.path.dirname(current_path)
                if parent != current_path:
                    current_path = parent
                    entries = list_dir(current_path)
                    selected=0; scroll=0
            refresh()

        elif key in ('\r','\n'):
            if cl and selected < len(cl):
                in_menu=True; menu_sel=0
                refresh()

    print(CLEAR_SCREEN + SHOW_CURSOR + HOME, end="", flush=True)

if __name__ == "__main__":
    dui([])