#!/usr/bin/env python3
"""One-click "open all watched sondes" page for the radiosondy status mail.

Serves a single page that lists every sonde from the watcher's state file and
opens each of them in its own tab. Linked from the daily status e-mail.

Usage:
    python radiosondy_web.py [PORT]
"""

from __future__ import annotations

import argparse
import html
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

STATE_FILE = Path(
    os.environ.get("RADIOSONDY_STATE_FILE", "/home/hermes/.hermes/logs/radiosondy_status_state.json")
)
SONDE_PAGE_URL = "https://radiosondy.info/sonde_archive.php?sondenumber={sonde}"
HOST = "0.0.0.0"

PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Radiosondy – alle Sonden</title>
<style>
  body {{ margin: 0; padding: 24px; background: #0f141a; color: #e6edf3;
         font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
  h1 {{ font-size: 20px; margin: 0 0 4px 0; }}
  p.sub {{ color: #9aa7b4; margin: 0 0 20px 0; font-size: 14px; }}
  button {{ background: #1f6feb; color: #fff; border: 0; border-radius: 6px;
            padding: 10px 18px; font-size: 15px; cursor: pointer; margin-bottom: 20px; }}
  button:hover {{ background: #388bfd; }}
  table {{ border-collapse: collapse; width: 100%; max-width: 720px; }}
  th, td {{ text-align: left; padding: 8px 10px; border-bottom: 1px solid #2a343f;
            font-size: 14px; }}
  th {{ color: #8d9aa8; font-weight: 600; }}
  a {{ color: #58a6ff; text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}
</style>
</head>
<body>
<h1>Radiosondy – überwachte Sonden</h1>
<p class="sub">{count} Sonde(n) · Stand {stamp}</p>
<button type="button" id="open-all">Alle {count} Sonden in Tabs öffnen</button>
<table>
  <thead><tr><th>Sonde</th><th>Link</th></tr></thead>
  <tbody>
  {rows}
  </tbody>
</table>
<script>
  var urls = {urls};
  function openAll() {{
    urls.forEach(function (u) {{ window.open(u, "_blank"); }});
  }}
  document.getElementById("open-all").addEventListener("click", openAll);
  // One click in the mail should be enough: try immediately, the button stays
  // as a fallback if the browser blocks popups without a gesture.
  openAll();
</script>
</body>
</html>
"""


def load_sondes() -> list[str]:
    if not STATE_FILE.exists():
        return []
    try:
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    return sorted(state.get("sondes", {}))


def render(sondes: list[str]) -> bytes:
    from datetime import datetime

    rows = "\n  ".join(
        f'<tr><td>{html.escape(sonde)}</td>'
        f'<td><a href="{SONDE_PAGE_URL.format(sonde=sonde)}">radiosondy.info</a></td></tr>'
        for sonde in sondes
    )
    urls = json.dumps([SONDE_PAGE_URL.format(sonde=sonde) for sonde in sondes])
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    return PAGE_TEMPLATE.format(count=len(sondes), rows=rows, urls=urls, stamp=stamp).encode()


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path not in ("/", "/index.html"):
            self.send_error(404)
            return
        body = render(load_sondes())
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        pass  # keep the journal quiet; the page is hit once a day


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("port", nargs="?", type=int, default=12346)
    args = parser.parse_args()
    server = ThreadingHTTPServer((HOST, args.port), Handler)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
