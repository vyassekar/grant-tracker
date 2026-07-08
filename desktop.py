"""Desktop entry point: runs the Flask app via waitress on a local-only port and
displays it in a native OS window (pywebview) instead of a browser tab.

This changes nothing about how the app works or where its data lives -- app.py's
Flask instance, routes, and DATA_DIR (see default_data_dir() there) are unchanged;
this file only changes how it's launched and viewed. The server binds to
127.0.0.1 only, so it's unreachable from anywhere else on the network, exactly
like `python app.py`.

Dev use: `python desktop.py` (needs requirements-desktop.txt installed).
Packaged use: this is the PyInstaller entry point (see GrantTracker.spec).
"""
import socket
import threading

import webview
from waitress import serve

from app import app as flask_app


def find_free_port():
    """An OS-assigned free port -- avoids clashing with anything else running
    locally (including a `python app.py` dev server on the default port)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main():
    port = find_free_port()
    server_thread = threading.Thread(
        target=serve, args=(flask_app,), kwargs={"host": "127.0.0.1", "port": port}, daemon=True
    )
    server_thread.start()

    webview.create_window("Grant Tracker", f"http://127.0.0.1:{port}", width=1280, height=860, min_size=(900, 600))
    # Blocks until the window is closed; the server thread is a daemon, so it's
    # torn down automatically when the process exits right after this returns.
    webview.start()


if __name__ == "__main__":
    main()
