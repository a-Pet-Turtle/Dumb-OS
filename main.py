version = "1.27"

import intro
from reader.rescape import *
import os
import getpass
import subprocess
import sys
import platform
import socket
from datetime import datetime
import shlex
import readline
import atexit
from surf import surf
from netdog import netdog
from dui import dui
from dumbbot import DumbBot, build_seed, render, try_math, MODEL_F
import numpy as np

try:
    intro.run_sequence_reveal(intro.stages)
except KeyboardInterrupt:
    os.system("clear")

if platform.system() == "Windows":
    print(f"{style(RED, BL)}DISCLAIMER:{R} SOME FEATURES MAY NOT WORK ON WINDOWS")

os.chdir(os.path.expanduser("~"))

# ── History ────────────────────────────────────────────────────────────────────

HISTORY_FILE = os.path.expanduser("~/.dos_history")

try:
    readline.read_history_file(HISTORY_FILE)
except FileNotFoundError:
    pass

atexit.register(readline.write_history_file, HISTORY_FILE)

# ── DumbBot setup ──────────────────────────────────────────────────────────────

import random as _random
_db_model = DumbBot()
_db_model.known_name = getpass.getuser()
_db_last_reply = ""

if os.path.exists(MODEL_F):
    try:
        _db_model.load(MODEL_F)
    except Exception as e:
        print(f"{LRED}DumbBot: Failed to load model: {e}{R}")
else:
    print(f"{LRED}DumbBot: No model found at {MODEL_F}{R}")
    print(f"{DM}Place your trained dumbbot_model.pkl there to enable db.{R}")

# ── Commands ───────────────────────────────────────────────────────────────────

def shell_credits(args):
    print(f"           {BL}- -{R} Dumb OS Project {BL}- -{R}")
    print(f"Main Programmer        - {GREEN}a_Pet_Turtle{R}")
    print(f"Claude                 - {GREEN}Initial Shell, Netdog UI, DUI conversion, & Corpus Data{R}")
    print(f"Gemini                 - {GREEN}Converted cmatrix to Python intro{R}")
    print(f"Chris Allegretta       - {GREEN}Original cmatrix code{R}")
    print(f"Microsoft/Tim Paterson - {GREEN}DOS Logo{R}")
    print(f"asciiart.eu            - {GREEN}ASCII Art Conversion of DOS Logo{R}")
    print(f"Aaron Curtis           - {GREEN}iShell Inspiration (DUI){R}")
    print(f"Jonah Cohen            - {GREEN}iShell Inspiration (DUI){R}")
    print(f"Debian                 - {GREEN}This DOS thing is built on it{R}")
    print(f"\n{DM}A StarShot Studios Production{R}\n")
    print("What is Dumb OS?")
    print("The name is a play on words combining both the Dumbbot integration,")
    print("and Microsoft's DOS (Disk OS)")
    print("DOS is pretty much a glorified shell, but with simple chatbot")
    print("integration and other built in features.\n")

def cmd_img(args):
    if not args:
        print(f"{LRED}Usage: img <filename or url>{R}")
        return
    target = args[0]

    if target.startswith("http://") or target.startswith("https://"):
        try:
            import urllib.request
            tmp = "/tmp/dos_img_tmp"
            urllib.request.urlretrieve(target, tmp)
            subprocess.run(["chafa", tmp])
        except Exception as e:
            print(f"{LRED}DOS: img: {e}{R}")
    else:
        subprocess.run(["chafa", target])

def shell_help(args):
    print(f"\n{B}DOS Help{R}  {DM}v{version}{R}")
    print(f"{DM}{'─' * 40}{R}")
    for name, (fn, desc) in COMMANDS.items():
        print(f"  {LGREEN}{name:<12}{R} {desc}")
    print(f"  {LGREEN}cd{R}           Changes directory")
    print(f"  {LGREEN}ls{R}           List files in current directory")
    print(f"  {LGREEN}clear{R}        Clear the terminal")
    print(f"{DM}{'─' * 40}{R}\n")

def cmd_db(args):
    global _db_last_reply
    if not args:
        print(f"{LRED}Usage: db <message>{R}")
        return
    query = " ".join(args)

    # Math check
    math_ans = try_math(query)
    if math_ans:
        print(f"{LCYAN}DumbBot:{R} {math_ans}")
        return

    seed_ctx, detected_name = build_seed(query, _db_last_reply, _db_model)

    if detected_name:
        _db_model.known_name = detected_name

    temp = _random.uniform(0.78, 0.95)
    raw, ctxs, ids = _db_model.generate(
        seed_ctx, max_len=_random.randint(6, 16), temp=temp
    )
    response = render(raw, _db_model.known_name, _db_model)
    _db_last_reply = raw

    print(f"{LCYAN}DumbBot:{R} {response}")

# ── Taskbar ───────────────────────────────────────────────────────────────────

def set_scroll_region():
    lines = os.get_terminal_size().lines
    print(f"\033[2;{lines}r", end="", flush=True)

def reset_scroll_region():
    print(f"\033[r", end="", flush=True)

def taskbar():
    cols = os.get_terminal_size().columns
    try:
        battery = open("/sys/class/power_supply/BAT0/capacity").read().strip()
        battery_str = f"Battery {battery}%  "
    except:
        battery_str = ""
    time_str = datetime.now().strftime("%H:%M")
    left   = "Dumb OS"
    middle = "StarShot Studios"
    right  = f"{battery_str}{time_str}"
    padding   = cols - len(left) - len(middle) - len(right)
    left_pad  = padding // 2
    right_pad = padding - left_pad
    bar = f"{BG_BLUE}{LWHITE}{B}{left}{' ' * left_pad}{middle}{' ' * right_pad}{right}{R}"
    print(f"\0337{pos(1,1)}{bar}\0338", end="", flush=True)

# ── Command Registry ───────────────────────────────────────────────────────────

COMMANDS = {
    "help":    (shell_help,    "Shows a list of built-in commands"),
    "credits": (shell_credits, "Shows credits for who worked on the project"),
    "img":     (cmd_img,       "Displays an image from a file or URL"),
    "surf":    (surf,          "Displays a webpage in terminal"),
    "netdog":  (netdog,        "LAN chat — no internet required"),
    "dui":     (dui,           "Launches the Dumb User Interface Mode"),
    "db":      (cmd_db,        "Talk to DumbBot"),
}

# ── Parser ─────────────────────────────────────────────────────────────────────

def parse(command):
    try:
        parts = shlex.split(command)
    except ValueError:
        print(f"DOS: parse error: mismatched quotes")
        return

    name = parts[0].lower()
    args = parts[1:]

    if name in COMMANDS:
        fn, _ = COMMANDS[name]
        fn(args)
        return

    if name == "cd":
        target = args[0] if args else os.path.expanduser("~")
        try:
            os.chdir(target)
        except FileNotFoundError:
            print(f"DOS: cd: {target}: No such file or directory")
        except PermissionError:
            print(f"DOS: cd: {target}: Permission denied")
        return

    try:
        subprocess.run(command, shell=True, cwd=os.getcwd())
    except KeyboardInterrupt:
        print()
    except Exception as e:
        print(f"DOS: error: {e}")

# ── Shell ──────────────────────────────────────────────────────────────────────

def run_shell():
    user = getpass.getuser()
    hostname = socket.gethostname()
    set_scroll_region()
    print()
    print()
    print(f"{BG_LRED} +---------------+ {R}")
    print(f"{BG_LRED} |{R}{style(BLACK, BG_LCYAN)}  Type 'help'  {R}{BG_LRED}| {R}")
    print(f"{BG_LRED} |{R}{style(BLACK, BG_LCYAN)}  for a list   {R}{BG_LRED}| {R}")
    print(f"{BG_LRED} |{R}{style(BLACK, BG_LCYAN)}  of built in  {R}{BG_LRED}| {R}")
    print(f"{BG_LRED} |{R}{style(BLACK, BG_LCYAN)}   commands    {R}{BG_LRED}| {R}")
    print(f"{BG_LRED} +---------------+ {R}")
    try:
        while True:
            taskbar()
            cwd = os.getcwd()
            prompt = f"\n{RED}{user}{R}@{BLUE}{hostname}{R}: {cwd}$ "

            try:
                command = input(prompt).strip()
            except (EOFError, KeyboardInterrupt):
                print(f"\n{LRED}Use 'exit' to quit DOS.{R}")
                continue

            if not command:
                continue

            if command in ("exit", "quit"):
                os.system("clear")
                sys.exit(0)

            parse(command)
            taskbar()
    finally:
        reset_scroll_region()
        print(SHOW_CURSOR)

if __name__ == "__main__":
    os.system("clear")
    run_shell()
