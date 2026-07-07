"""Record a short video walkthrough of the app using Playwright.

One-time setup:
    ./venv/bin/pip install -r requirements-dev.txt
    ./venv/bin/playwright install chromium

Then, with the venv active:
    python record_demo.py

This reseeds the demo data (see seed_demo.py), launches the app on a scratch
port, drives a short walkthrough in a real headless browser, and writes
demo/grant_tracker_demo.mp4 (or .webm if ffmpeg isn't found anywhere).
"""
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

import seed_demo

BASE_DIR = Path(__file__).parent
DEMO_DIR = BASE_DIR / "demo"
PORT = 5057
BASE_URL = f"http://127.0.0.1:{PORT}"


def find_ffmpeg():
    system_ffmpeg = shutil.which("ffmpeg")
    if system_ffmpeg:
        return system_ffmpeg
    for cache_dir in (Path.home() / "Library" / "Caches" / "ms-playwright", Path.home() / ".cache" / "ms-playwright"):
        for candidate in cache_dir.glob("ffmpeg-*/ffmpeg*"):
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return str(candidate)
    return None


def wait_for_server(timeout=15):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(BASE_URL, timeout=1)
            return True
        except OSError:
            time.sleep(0.3)
    return False


def select_faculty(page, name):
    page.goto(f"{BASE_URL}/faculty")
    page.wait_for_timeout(600)
    row = page.locator("tr", has_text=name)
    row.locator("button").click()
    page.wait_for_load_state("networkidle")


def set_field(page, selector, value):
    """Set an input/select value via JS and fire the events Flask/browser form validation expects.

    Used instead of Playwright's fill()/select_option() convenience methods because <input type=month>
    fields don't reliably accept typed input the same way across headless Chromium versions.
    """
    page.eval_on_selector(
        selector,
        """(el, value) => {
            const proto = el.tagName === 'SELECT' ? window.HTMLSelectElement.prototype : window.HTMLInputElement.prototype;
            Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, value);
            el.dispatchEvent(new Event('input', { bubbles: true }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
        }""",
        value,
    )


def option_value(page, select_selector, label_substring):
    return page.eval_on_selector(
        select_selector,
        """(el, text) => {
            const opt = [...el.options].find(o => o.text.includes(text));
            return opt ? opt.value : null;
        }""",
        label_substring,
    )


def set_alloc_row_percent(page, row_index, percent):
    """Drag one of the allocation editor's sliders (see _allocation_editor.html) to a
    value and let its own JS update the row, running total, and stacked bar."""
    page.evaluate(
        "([i, v]) => { setAllocPercent(i, v); document.querySelectorAll('.alloc-row input[type=range]')[i].value = v; }",
        [row_index, percent],
    )


def run_walkthrough(page):
    page.set_viewport_size({"width": 1280, "height": 800})

    select_faculty(page, "Dr Maria Santos")
    page.wait_for_timeout(2000)

    # Dark/light theme toggle in the header.
    page.locator(".theme-toggle").click()
    page.wait_for_timeout(1400)
    page.locator(".theme-toggle").click()
    page.wait_for_timeout(600)

    # Grant category filter is multi-select: Internal alone, then also add Sponsored
    # (both pills active at once, showing the union), then back to All.
    page.locator("a.toggle", has_text="Internal").click()
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(1400)
    page.locator("a.toggle", has_text="Sponsored").click()
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(1600)
    page.get_by_role("link", name="All", exact=True).click()
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(800)

    # Hide-expired/overspent is a single toggle pill: on drops the expired DOE award
    # out of view, clicking it again (same pill) turns it back off.
    page.locator("a.toggle", has_text="Hide expired/overspent").click()
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(1600)
    page.locator("a.toggle", has_text="Hide expired/overspent").click()
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(800)

    # Drill into the grant with the overspending flag to see the risk badge and
    # explanation alongside its category badge on the detail page.
    page.get_by_role("link", name="Summer TA Support").click()
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(2200)

    page.locator("a.back").click()
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(600)

    # Departments: default stipend column, alongside tuition/fringe.
    page.get_by_role("link", name="Departments").click()
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(1800)

    page.locator("a.back").click()
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(600)

    # Add student form: picking a department auto-fills its default stipend --
    # editable afterward, but this shows the fill firing live.
    page.locator("details summary", has_text="Add student").click()
    page.wait_for_timeout(500)
    add_student_form = 'form[action*="students/add"]'
    stipend_input = f"{add_student_form} input[name='stipend']"
    page.locator(stipend_input).scroll_into_view_if_needed()
    page.wait_for_timeout(400)
    dept_value = option_value(page, f"{add_student_form} select[name='department_id']", "Mechanical Engineering")
    set_field(page, f"{add_student_form} select[name='department_id']", dept_value)
    page.wait_for_timeout(1800)

    # Scenarios: build a new what-if from scratch using the slider allocation editor.
    page.get_by_role("link", name="Scenarios").click()
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(1000)

    page.locator("details summary", has_text="New scenario").click()
    page.wait_for_timeout(500)

    create_form = 'form[action*="scenarios/add"]'
    page.fill(f"{create_form} input[name='name']", "Give Yuki more time on Sloan")
    page.select_option("#scenario-student", label="Yuki Tanaka")
    page.wait_for_timeout(300)
    set_field(page, "#scenario-month-start", "2026-08")
    set_field(page, f"{create_form} input[name='month_end']", "2026-12")
    page.wait_for_timeout(500)
    page.select_option("#alloc-add-grant", label="Sloan Research Fellowship")
    page.click('button:has-text("+ Add grant")')
    page.wait_for_timeout(300)
    set_alloc_row_percent(page, 0, 50)
    page.wait_for_timeout(1200)
    page.locator(f"{create_form} button[type=submit]").click()
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(1800)

    # Add a second student's change to the *same* scenario from its own detail page --
    # rebalancing Okafor's July effort between NIH and DOE -- to show the combined
    # multi-student effect, not just a single change.
    page.select_option("#scenario-student", label="David Okafor")
    page.wait_for_timeout(400)
    page.select_option("#alloc-add-grant", label="DOE Early Career Award")
    page.click('button:has-text("+ Add grant")')
    page.wait_for_timeout(300)
    set_alloc_row_percent(page, 0, 50)
    set_alloc_row_percent(page, 1, 50)
    page.wait_for_timeout(1200)
    page.locator('form[action*="allocations/add"] button[type=submit]').click()
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(3000)

    select_faculty(page, "Dr Alex Rivera")
    page.wait_for_timeout(2000)


def main():
    print("Seeding demo data...")
    seed_demo.seed_maria_santos()
    seed_demo.seed_alex_rivera()

    DEMO_DIR.mkdir(exist_ok=True)
    recording_dir = DEMO_DIR / "_recording"
    recording_dir.mkdir(exist_ok=True)
    for old in recording_dir.glob("*.webm"):
        old.unlink()

    env = {**os.environ, "PORT": str(PORT), "DISABLE_RELOADER": "1"}
    print("Starting app server...")
    server = subprocess.Popen([sys.executable, "app.py"], cwd=BASE_DIR, env=env)
    try:
        if not wait_for_server():
            raise RuntimeError("Server did not start in time")

        with sync_playwright() as p:
            browser = p.chromium.launch()
            context = browser.new_context(
                record_video_dir=str(recording_dir),
                record_video_size={"width": 1280, "height": 800},
                viewport={"width": 1280, "height": 800},
            )
            page = context.new_page()
            print("Recording walkthrough...")
            run_walkthrough(page)
            context.close()
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=10)

    recorded = next(recording_dir.glob("*.webm"))
    webm_path = DEMO_DIR / "grant_tracker_demo.webm"
    recorded.replace(webm_path)
    recording_dir.rmdir()

    ffmpeg = find_ffmpeg()
    if ffmpeg:
        mp4_path = DEMO_DIR / "grant_tracker_demo.mp4"
        subprocess.run(
            [ffmpeg, "-y", "-i", str(webm_path), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(mp4_path)],
            check=True,
            capture_output=True,
        )
        webm_path.unlink()
        print(f"Wrote {mp4_path}")
    else:
        print(f"ffmpeg not found; wrote {webm_path} (plays in Chrome/Firefox/VLC)")


if __name__ == "__main__":
    main()
