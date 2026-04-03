'''
NetDog Terminal
A terminal version of Netdog LAN chat for Dumb OS.
Part of the StarShot Studios suite.
Ported from netdog.py (tkinter) by Claude.
'''

import os
import socket
import threading
import struct
import base64
import json
from datetime import datetime

try:
    from reader.rescape import *
except ImportError:
    # Fallback if run outside DOS
    R=B=DM=IT=UL=BL=""
    GREEN=LGREEN=CYAN=LCYAN=YELLOW=LYELLOW=""
    RED=LRED=BLUE=LBLUE=MAGENTA=WHITE=""

# ── Config ─────────────────────────────────────────────────────────────────────

CONFIG_FILE = os.path.expanduser("~/.netdog_config.json")
SAVE_DIR    = os.path.expanduser("~/netdog_files")

def _load_config():
    try:
        with open(CONFIG_FILE) as f:
            return json.load(f)
    except:
        return {}

def _save_config(cfg):
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(cfg, f)
    except:
        pass

# ── State ──────────────────────────────────────────────────────────────────────

class _State:
    def __init__(self):
        self.running     = False
        self.mode        = None       # "host" or "join"
        self.my_name     = ""
        self.clients     = {}         # addr_str -> sock  (host only)
        self.client_names= {}         # addr_str -> name
        self.server_sock = None
        self.conn_sock   = None       # client only
        self.prompt      = ""         # reprinted after incoming messages

_s = _State()

# ── Helpers ────────────────────────────────────────────────────────────────────

def _ts():
    return datetime.now().strftime("%H:%M")

def _print_incoming(line, color=LCYAN):
    '''Print an incoming message without mangling the input prompt.'''
    print(f"\r{color}{line}{R}")
    print(_s.prompt, end="", flush=True)

def _my_ip():
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 80))
        ip = sock.getsockname()[0]
        sock.close()
        return ip
    except:
        return "unknown"

def _ensure_save_dir():
    os.makedirs(SAVE_DIR, exist_ok=True)

# ── Low-level send / recv ──────────────────────────────────────────────────────

def _send_raw(sock, data: bytes):
    sock.sendall(struct.pack(">I", len(data)) + data)

def _send_to_all(data: bytes, exclude=None):
    if _s.mode == "host":
        _broadcast(struct.pack(">I", len(data)) + data, exclude=exclude)
    else:
        _send_raw(_s.conn_sock, data)

def _recv_exactly(sock, n):
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("disconnected")
        buf += chunk
    return buf

def _broadcast(payload, exclude=None):
    dead = []
    for addr, sock in list(_s.clients.items()):
        if addr == exclude:
            continue
        try:
            sock.sendall(payload)
        except:
            dead.append(addr)
    for addr in dead:
        _drop_client(addr)

def _drop_client(addr_str):
    name = _s.client_names.get(addr_str, addr_str)
    _s.clients.pop(addr_str, None)
    _s.client_names.pop(addr_str, None)
    _print_incoming(f"● {name} left", color=DM)

# ── Receive loop ───────────────────────────────────────────────────────────────

def _recv_loop(sock, peer):
    while _s.running:
        try:
            raw_len = _recv_exactly(sock, 4)
            length  = struct.unpack(">I", raw_len)[0]
            data    = _recv_exactly(sock, length).decode(errors="replace")

            # Host name handshake
            if data.startswith("__WHOAMI__") and "<<<END>>>" in data:
                if _s.mode == "host":
                    reply = f"__HOSTINFO__{_s.my_name}\n<<<END>>>".encode()
                    try:
                        _send_raw(sock, reply)
                    except:
                        pass
                continue

            if data.startswith("__HOSTINFO__") and "<<<END>>>" in data:
                host_name = data.replace("__HOSTINFO__", "").replace("\n<<<END>>>", "").strip()
                _s.client_names[peer] = f"{host_name} {DM}(host){R}"
                _print_incoming(f"● {host_name} is hosting", color=DM)
                continue

            # Name announcement
            if data.startswith("__NAME__") and "<<<END>>>" in data:
                name = data.replace("__NAME__", "").replace("\n<<<END>>>", "").strip()
                old  = _s.client_names.get(peer, peer)
                _s.client_names[peer] = name
                _print_incoming(f"● {old} is now known as {name}", color=DM)
                if _s.mode == "host":
                    relay = f"__NAME__{name}\n<<<END>>>".encode()
                    _broadcast(struct.pack(">I", len(relay)) + relay, exclude=peer)
                continue

            # File transfer
            if data.startswith("__FILE__"):
                try:
                    _ensure_save_dir()
                    _, rest     = data.split("__FILE__", 1)
                    filename, b64data = rest.split("\n<<<SEP>>>", 1)
                    b64data     = b64data.replace("<<<END>>>", "").strip()
                    file_bytes  = base64.b64decode(b64data)
                    save_path   = os.path.join(SAVE_DIR, filename)
                    with open(save_path, "wb") as f:
                        f.write(file_bytes)
                    sender   = _s.client_names.get(peer, peer)
                    size_kb  = len(file_bytes) / 1024
                    _print_incoming(f"📎 {sender} sent {filename} ({size_kb:.1f} KB) → {save_path}", color=YELLOW)
                    if _s.mode == "host":
                        raw_relay = data.encode()
                        _broadcast(struct.pack(">I", len(raw_relay)) + raw_relay, exclude=peer)
                except Exception as e:
                    _print_incoming(f"file error: {e}", color=RED)
                continue

            # Normal message
            if "<<<END>>>" in data:
                msg = data.replace("<<<END>>>", "").strip()
                if not msg:
                    continue
                if _s.mode == "host":
                    relay = data.encode()
                    _broadcast(struct.pack(">I", len(relay)) + relay, exclude=peer)
                if ": " in msg:
                    sender, body = msg.split(": ", 1)
                else:
                    sender = _s.client_names.get(peer, peer)
                    body   = msg
                _print_incoming(f"[{_ts()}] {LCYAN}{sender}{R}: {body}")

        except Exception:
            break

    if _s.mode == "host":
        _drop_client(peer)
    else:
        _print_incoming("● disconnected from host", color=RED)
        _s.running = False

# ── Accept loop (host only) ────────────────────────────────────────────────────

def _accept_loop():
    while _s.running:
        try:
            conn, addr = _s.server_sock.accept()
            addr_str   = f"{addr[0]}:{addr[1]}"
            _s.clients[addr_str]      = conn
            _s.client_names[addr_str] = addr_str
            _print_incoming(f"● {addr_str} joined", color=DM)
            threading.Thread(target=_recv_loop, args=(conn, addr_str), daemon=True).start()
        except:
            break

# ── Startup ────────────────────────────────────────────────────────────────────

def _startup():
    print(f"\n{GREEN}{B}🐕 NetDog Terminal{R}  {DM}LAN chat — no internet required{R}")

    cfg = _load_config()

    # Rejoin prompt
    if cfg.get("last_mode"):
        last = (f"{cfg.get('last_name','?')}  •  "
                f"{'hosting' if cfg['last_mode']=='host' else cfg.get('last_host','?')}  •  "
                f"room {cfg.get('last_port','?')}")
        print(f"{DM}Last session: {last}{R}")
        rejoin = input(f"Rejoin last session? {DM}(y/n){R} ").strip().lower()
        if rejoin == "y":
            return cfg["last_mode"], cfg["last_name"], cfg.get("last_host",""), cfg["last_port"]

    # Mode
    while True:
        mode = input(f"Host or Join? {DM}(h/j){R} ").strip().lower()
        if mode in ("h", "j"):
            break
        print(f"{LRED}Please enter h or j{R}")
    mode = "host" if mode == "h" else "join"

    # Name
    while True:
        name = input("Your name: ").strip()
        if name:
            break
        print(f"{LRED}Name cannot be empty{R}")

    # Host IP (join only)
    host = ""
    if mode == "join":
        while True:
            host = input("Host IP: ").strip()
            if host:
                break
            print(f"{LRED}Host IP cannot be empty{R}")

    # Room number
    while True:
        port_str = input(f"Room number {DM}(default 12345){R}: ").strip() or "12345"
        if port_str.isdigit():
            port = int(port_str)
            break
        print(f"{LRED}Room number must be a number{R}")

    return mode, name, host, port

# ── Main entry point ───────────────────────────────────────────────────────────

def netdog(args):
    '''
    Launch NetDog terminal LAN chat.
    Usage: netdog
    Commands once connected:
      /quit           - leave the chat
      /users          - list online users
      /file <path>    - send a file
      F?<path>        - send a file (shortcut)
    '''
    global _s
    _s = _State()

    try:
        mode, name, host, port = _startup()
    except (KeyboardInterrupt, EOFError):
        print(f"\n{DM}Cancelled.{R}")
        return

    _s.my_name = name
    _s.mode    = mode

    _save_config({
        "last_mode": mode,
        "last_name": name,
        "last_host": host,
        "last_port": port,
    })

    # ── Connect ──
    if mode == "host":
        try:
            _s.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            _s.server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            _s.server_sock.bind(("", port))
            _s.server_sock.listen(10)
        except Exception as e:
            print(f"{LRED}Could not start server: {e}{R}")
            return
        _s.running = True
        ip = _my_ip()
        print(f"\n{GREEN}● Hosting room {port}{R}  {DM}your IP: {ip}  •  share this with friends{R}")
        threading.Thread(target=_accept_loop, daemon=True).start()

    else:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((host, port))
            _s.conn_sock = sock
        except Exception as e:
            print(f"{LRED}Could not connect: {e}{R}")
            return
        _s.running = True
        print(f"\n{GREEN}● Connected to {host}:{port}{R}")
        _send_raw(_s.conn_sock, f"__NAME__{name}\n<<<END>>>".encode())
        _send_raw(_s.conn_sock, f"__WHOAMI__\n<<<END>>>".encode())
        threading.Thread(target=_recv_loop, args=(_s.conn_sock, host), daemon=True).start()

    print(f"{DM}Commands: /quit  /users  /file <path>  •  F?<path> to send file{R}\n")

    # ── Input loop ──
    while _s.running:
        try:
            _s.prompt = f"{GREEN}{name}{R}> "
            msg = input(_s.prompt).strip()
        except (KeyboardInterrupt, EOFError):
            break

        if not msg:
            continue

        # Commands
        if msg == "/quit":
            break

        if msg == "/users":
            print(f"{DM}● {name} (you){R}")
            for n in _s.client_names.values():
                print(f"{LCYAN}● {n}{R}")
            continue

        if msg.startswith("/file ") or msg.startswith("F?"):
            path = msg[6:].strip() if msg.startswith("/file ") else msg[2:].strip()
            if not os.path.isfile(path):
                print(f"{LRED}File not found: {path}{R}")
                continue
            try:
                _ensure_save_dir()
                with open(path, "rb") as f:
                    file_bytes = f.read()
                b64      = base64.b64encode(file_bytes).decode()
                filename = os.path.basename(path)
                payload  = f"__FILE__{filename}\n<<<SEP>>>{b64}<<<END>>>".encode()
                _send_to_all(payload)
                print(f"{YELLOW}📎 Sent {filename} ({len(file_bytes)/1024:.1f} KB){R}")
            except Exception as e:
                print(f"{LRED}File send error: {e}{R}")
            continue

        # Normal message
        try:
            payload = f"{name}: {msg}\n<<<END>>>".encode()
            _send_to_all(payload)
        except Exception as e:
            print(f"{LRED}Send error: {e}{R}")

    # ── Cleanup ──
    _s.running = False
    try:
        if _s.server_sock:
            _s.server_sock.close()
        if _s.conn_sock:
            _s.conn_sock.close()
        for sock in _s.clients.values():
            sock.close()
    except:
        pass

    print(f"\n{DM}🐕 NetDog disconnected.{R}\n")
