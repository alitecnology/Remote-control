import asyncio
import json
import os
import sys
import threading
import winreg

import pyautogui
import websockets
from PIL import Image, ImageDraw
import pystray

pyautogui.PAUSE = 0
pyautogui.FAILSAFE = True

APP_NAME = "KelasLiveKontrol"
DATA_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "KelasLive")
TOKEN_FILE = os.path.join(DATA_DIR, "token.txt")

W, H = pyautogui.size()
KEYS = {"enter", "backspace", "tab", "esc", "delete", "left", "right", "up", "down",
        "home", "end", "pageup", "pagedown", "space", "win"}

saved_token = None
tray_icon = None


def load_token():
    try:
        with open(TOKEN_FILE, "r", encoding="utf-8") as f:
            t = f.read().strip()
            return t or None
    except Exception:
        return None


def save_token(token):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(TOKEN_FILE, "w", encoding="utf-8") as f:
        f.write(token)


def forget_token():
    global saved_token
    saved_token = None
    try:
        os.remove(TOKEN_FILE)
    except Exception:
        pass
    refresh_menu()
    notify("Pasangan dilupakan. Buka ulang halaman murid untuk memasangkan lagi.")


def set_autostart():
    try:
        exe = sys.executable if getattr(sys, "frozen", False) else os.path.abspath(__file__)
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                              r"Software\Microsoft\Windows\CurrentVersion\Run",
                              0, winreg.KEY_SET_VALUE)
        winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, '"%s"' % exe)
        winreg.CloseKey(key)
    except Exception:
        pass


def pos(m):
    x = min(max(float(m.get("x", 0)), 0.0), 1.0)
    y = min(max(float(m.get("y", 0)), 0.0), 1.0)
    return (int(1 + x * (W - 3)), int(1 + y * (H - 3)))


def act(m):
    t = m.get("t")
    b = m.get("b", "left")
    if b not in ("left", "right"):
        b = "left"
    if "x" in m and "y" in m:
        px, py = pos(m)
        pyautogui.moveTo(px, py)
    if t == "click":
        pyautogui.click(button=b, clicks=2 if m.get("n") == 2 else 1)
    elif t == "down":
        pyautogui.mouseDown(button=b)
    elif t == "up":
        pyautogui.mouseUp(button=b)
    elif t == "scroll":
        d = int(max(-20, min(20, float(m.get("d", 0)))))
        pyautogui.scroll(d * 60)
    elif t == "key" and m.get("k") in KEYS:
        pyautogui.press(m["k"])
    elif t == "text":
        pyautogui.write(str(m.get("s", ""))[:200], interval=0.01)


async def handler(ws):
    global saved_token
    try:
        first = json.loads(await asyncio.wait_for(ws.recv(), 10))
    except Exception:
        return
    if first.get("t") != "auth":
        return
    token = str(first.get("token", ""))
    if not token:
        await ws.send(json.dumps({"t": "auth", "ok": False}))
        return

    if saved_token is None:
        saved_token = token
        save_token(token)
        refresh_menu()
        notify("Perangkat ini dipasangkan dengan halaman murid.")
    elif token != saved_token:
        await ws.send(json.dumps({"t": "auth", "ok": False}))
        return

    await ws.send(json.dumps({"t": "auth", "ok": True}))
    async for raw in ws:
        try:
            act(json.loads(raw))
        except pyautogui.FailSafeException:
            await ws.close()
            return
        except Exception:
            pass


async def serve():
    async with websockets.serve(handler, "127.0.0.1", 8765):
        await asyncio.Future()


def run_server():
    asyncio.run(serve())


def notify(text):
    try:
        if tray_icon:
            tray_icon.notify(text, "Kelas Live")
    except Exception:
        pass


def make_icon_image():
    img = Image.new("RGBA", (64, 64), (5, 7, 11, 255))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((10, 14, 54, 44), radius=8, fill=(23, 227, 122, 255))
    d.polygon([(26, 21), (26, 37), (40, 29)], fill=(5, 7, 11, 255))
    return img


def build_menu():
    status = "Dipasangkan" if saved_token else "Menunggu pemasangan"
    return pystray.Menu(
        pystray.MenuItem("Kelas Live - %s" % status, None, enabled=False),
        pystray.MenuItem("Lupakan pasangan", lambda: forget_token()),
        pystray.MenuItem("Keluar", lambda: tray_icon.stop()),
    )


def refresh_menu():
    try:
        if tray_icon:
            tray_icon.menu = build_menu()
            tray_icon.update_menu()
    except Exception:
        pass


def main():
    global saved_token, tray_icon
    set_autostart()
    saved_token = load_token()

    t = threading.Thread(target=run_server, daemon=True)
    t.start()

    tray_icon = pystray.Icon("kelas_live", make_icon_image(), "Kelas Live", build_menu())
    tray_icon.run()


if __name__ == "__main__":
    main()
