"""Capture screenshots of the scratchpad at localhost:9999 using Playwright."""
import subprocess
import sys

def shot(name, width, height, style, scheme, full_page=False, scroll_to_top=True):
    js_setup = f"""
    document.documentElement.setAttribute('data-style', '{style}');
    document.documentElement.setAttribute('data-scheme', '{scheme}');
    """
    if scroll_to_top:
        js_setup += """
        const container = document.querySelector('.notes-container');
        if (container) container.scrollTop = 0;
        """

    cmd = [
        sys.executable, "-m", "shot_scraper",
        "http://localhost:9999",
        "--width", str(width),
        "--height", str(height),
        "-o", f"screenshots/{name}",
        "--javascript", js_setup,
        "--wait", "5000",
    ]
    if not full_page:
        cmd.append("--viewport")

    print(f"  Capturing {name} ({width}x{height}, {style}/{scheme})...")
    subprocess.run(cmd, check=True)
    print(f"  ✓ {name}")

if __name__ == "__main__":
    # Hero — wide to show widgets nicely
    shot("cockpit-dark.png",  800, 900, "cockpit", "dark", full_page=True)
    # Narrow sidebar shots
    shot("widgets.png",       380, 800, "cockpit", "dark", full_page=True)
    shot("todo-board.png",    380, 400, "cockpit", "dark")
    shot("refined-dark.png",  380, 800, "refined", "dark", full_page=True)
    shot("cockpit-light.png", 380, 800, "cockpit", "light", full_page=True)
    print("\nDone! Screenshots saved to screenshots/")
