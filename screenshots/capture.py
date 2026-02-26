"""Capture screenshots of the scratchpad at localhost:9999.

Sets theme via the API so React applies it correctly on load,
then uses webshot (Playwright) to capture.
"""
import subprocess
import json
import urllib.request

API = "http://localhost:9999/api/prefs"

def set_theme(style, scheme):
    """Set style/scheme via the prefs API so React loads with correct theme."""
    data = json.dumps({"style": style, "scheme": scheme}).encode()
    req = urllib.request.Request(API, data=data, method="PUT",
                                headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req)

def shot(name, width, height, style, scheme, selector=None, viewport=False):
    set_theme(style, scheme)
    cmd = ["webshot", "http://localhost:9999",
           "--width", str(width), "--height", str(height),
           "--wait", "3000",
           "-o", f"screenshots/{name}", "-q"]
    if selector:
        cmd += ["-s", selector]
    if viewport:
        cmd.append("--viewport")
    print(f"  Capturing {name} ({width}x{height}, {style}/{scheme})...")
    subprocess.run(cmd, check=True)
    print(f"  ✓ {name}")

if __name__ == "__main__":
    shot("cockpit-dark.png",  800, 900, "cockpit", "dark")
    shot("widgets.png",       380, 800, "cockpit", "dark")
    shot("todo-board.png",    380, 400, "cockpit", "dark", viewport=True)
    shot("refined-dark.png",  380, 800, "refined", "dark")
    shot("cockpit-light.png", 380, 800, "cockpit", "light")
    print("\nDone! Screenshots saved to screenshots/")
