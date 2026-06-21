"""
Tiny HTTP server for the OBS overlay during development.
Run this alongside main.py, then point OBS Browser Source at:
  http://localhost:8765/index.html
"""
import http.server
import os

PORT = 8765
OVERLAY_DIR = os.path.join(os.path.dirname(__file__), "overlay")


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=OVERLAY_DIR, **kwargs)

    def log_message(self, format, *args):
        pass  # silence request logs


if __name__ == "__main__":
    with http.server.HTTPServer(("localhost", PORT), Handler) as httpd:
        print(f"Overlay server running at http://localhost:{PORT}/index.html")
        print("Point OBS Browser Source at that URL.")
        print("Ctrl+C to stop.")
        httpd.serve_forever()
