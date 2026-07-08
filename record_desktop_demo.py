"""Record a demo video of the standalone desktop app (GrantTracker.app) using a
real macOS screen recording.

This is deliberately NOT automated end-to-end the way record_demo.py's browser demo
is: pywebview's window is a real native OS window (WKWebView), not something a tool
like Playwright can drive or capture -- there's no browser to attach to. So this
script handles the parts that *can* be automated (reseeding demo data, finding your
screen-capture device, launching the app, timing/encoding the recording) and leaves
the actual clicking-through to you, guided by the walkthrough checklist it prints.

This can only be run on a real Mac with a real display -- it needs macOS's
screen-recording permission, which requires an interactive one-time approval and
can't be granted from a sandboxed/headless environment.

One-time setup:
    - Grant your terminal app (Terminal/iTerm/etc.) Screen Recording permission:
      System Settings -> Privacy & Security -> Screen Recording. If you haven't
      already, macOS will prompt for this automatically the first time this script
      tries to record -- after granting it, quit and reopen your terminal app for
      the permission to take effect, then run this again.
    - Build GrantTracker.app if you haven't (see README's "Install as a standalone
      desktop app" section), or use the one already committed under dist/.
    - `brew install ffmpeg` if you don't already have it.

Usage:
    python record_desktop_demo.py

Writes demo/grant_tracker_desktop_demo.mp4 -- a new, separate file. This never
touches demo/grant_tracker_demo.mp4 (the existing browser-driven web-app demo).
"""
import os
import re
import subprocess
import sys
from pathlib import Path

import seed_demo

BASE_DIR = Path(__file__).parent
DEMO_DIR = BASE_DIR / "demo"
APP_PATH = BASE_DIR / "dist" / "GrantTracker.app"
OUTPUT_PATH = DEMO_DIR / "grant_tracker_desktop_demo.mp4"
RECORD_SECONDS = 90

WALKTHROUGH = f"""
Suggested walkthrough (about {RECORD_SECONDS}s -- a pace guide, not a script to
follow exactly; re-run this as many times as you like):

  1. (0:00) Show Finder/the dist folder, double-click GrantTracker.app to launch
     it -- no terminal, no browser tab, just the app opening in its own window.
     (If this is the very first launch, you'll need to right-click -> Open once
     to get past Gatekeeper -- see the README -- do that *before* you start
     recording, so the warning dialog isn't the whole video.)
  2. (0:10) Pick "Dr. Maria Santos" on the faculty picker.
  3. (0:15) Click through the dashboard -- grants table, risk badges, students.
  4. (0:30) Open a grant detail page, then a student detail page.
  5. (0:45) Open Settings, Departments, or Scenarios -- whichever you like.
  6. (1:05) Cmd+Q to quit the app -- point out there's no server/terminal to stop.
"""


def find_ffmpeg():
    import shutil

    system_ffmpeg = shutil.which("ffmpeg")
    if system_ffmpeg:
        return system_ffmpeg
    for cache_dir in (Path.home() / "Library" / "Caches" / "ms-playwright", Path.home() / ".cache" / "ms-playwright"):
        for candidate in cache_dir.glob("ffmpeg-*/ffmpeg*"):
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return str(candidate)
    return None


def list_screen_capture_devices(ffmpeg):
    result = subprocess.run(
        [ffmpeg, "-f", "avfoundation", "-list_devices", "true", "-i", ""],
        capture_output=True,
        text=True,
    )
    devices = re.findall(r"\[(\d+)\] (.+)", result.stderr)
    return [(idx, name) for idx, name in devices if "capture screen" in name.lower()]


def main():
    if sys.platform != "darwin":
        raise SystemExit("This script drives macOS's screen-recording APIs; it only works on a Mac.")

    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        raise SystemExit("ffmpeg not found -- install it (e.g. `brew install ffmpeg`) and try again.")

    if not APP_PATH.exists():
        raise SystemExit(
            f"{APP_PATH} not found -- build it first (pyinstaller GrantTracker.spec --noconfirm, "
            "see the README's 'Install as a standalone desktop app' section)."
        )

    print("Reseeding demo data...")
    seed_demo.seed_maria_santos()
    seed_demo.seed_alex_rivera()

    screens = list_screen_capture_devices(ffmpeg)
    if not screens:
        raise SystemExit(
            "No screen-capture device found via `ffmpeg -f avfoundation -list_devices`. "
            "If this is your first time, macOS may need you to grant Screen Recording "
            "permission and then restart your terminal app before it shows up."
        )
    screen_index, screen_name = screens[0]
    print(f"Using screen-capture device [{screen_index}] {screen_name}")
    if len(screens) > 1:
        print(
            "(Multiple displays detected -- using the first one. Edit screen_index "
            "in this script if you want to record a different display.)"
        )

    DEMO_DIR.mkdir(exist_ok=True)
    raw_path = DEMO_DIR / "_desktop_recording.mov"

    print(WALKTHROUGH)
    input(f"Press Enter to launch GrantTracker.app and start a {RECORD_SECONDS}s recording (press 'q' in this terminal to stop early)...")
    subprocess.Popen(["open", str(APP_PATH)])

    print(f"Recording for up to {RECORD_SECONDS}s -- go!")
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-f",
            "avfoundation",
            "-i",
            f"{screen_index}:none",
            "-t",
            str(RECORD_SECONDS),
            "-vf",
            "scale=1280:-2",
            str(raw_path),
        ],
        check=True,
    )

    print("Encoding to mp4...")
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-i",
            str(raw_path),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(OUTPUT_PATH),
        ],
        check=True,
    )
    raw_path.unlink()
    print(f"Wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
