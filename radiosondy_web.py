#!/usr/bin/env python3
"""One-click "open all watched sondes" opener for the radiosondy status mail.

Not a page you look at: the mail links here with the sonde numbers in the query
string, the opener opens every sonde but the first in its own tab and then turns
itself into the first sonde. One click in the mail therefore leaves exactly N
sonde tabs and no extra tab.

If the browser blocks the popups, a minimal fallback list of links is shown.

Usage:
    python radiosondy_web.py [PORT]
"""

from __future__ import annotations

import argparse
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

SONDE_PAGE_URL = "https://radiosondy.info/sonde_archive.php?sondenumber={sonde}"
HOST = "0.0.0.0"

PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Radiosondy</title>
<style>
  body {{ margin: 0; padding: 24px; background: #0f141a; color: #e6edf3;
         font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
  a {{ color: #58a6ff; }}
  li {{ margin: 6px 0; }}
</style>
</head>
<body>
<p id="msg">Sonden werden geoeffnet ...</p>
<script>
var urls = {urls};

function showLinks() {{
  document.getElementById("msg").textContent = "Bitte Tabs einzeln oeffnen:";
  var ul = document.createElement("ul");
  urls.forEach(function (u) {{
    var li = document.createElement("li");
    var a = document.createElement("a");
    a.href = u;
    a.textContent = u;
    li.appendChild(a);
    ul.appendChild(li);
  }});
  document.body.appendChild(ul);
}}

if (urls.length === 0) {{
  document.getElementById("msg").textContent = "Keine Sonde uebergeben.";
}} else if (urls.length === 1) {{
  window.location.replace(urls[0]);
}} else {{
  var blocked = false;
  for (var i = 1; i < urls.length; i++) {{
    var w = window.open(urls[i], "_blank");
    if (!w) {{ blocked = true; }}
  }}
  if (blocked) {{ showLinks(); }} else {{ window.location.replace(urls[0]); }}
}}
</script>
<noscript><p>JavaScript ist deaktiviert - bitte Tabs manuell oeffnen.</p></noscript>
</body>
</html>
"""


def requested_sondes(query: str) -> list[str]:
    """'?sondes=D1,D2' -> ['D1', 'D2'], order preserved, duplicates dropped."""
    values = parse_qs(query).get("sondes", [])
    if not values:
        return []
    sondes: list[str] = []
    for chunk in values[0].split(","):
        name = chunk.strip()
        if name and name not in sondes:
            sondes.append(name)
    return sondes


def render(sondes: list[str]) -> bytes:
    urls = json.dumps([SONDE_PAGE_URL.format(sonde=sonde) for sonde in sondes])
    return PAGE_TEMPLATE.format(urls=urls).encode()


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path not in ("/", "/index.html"):
            self.send_error(404)
            return
        body = render(requested_sondes(parsed.query))
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        pass  # keep the journal quiet; the page is hit once a day


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("port", nargs="?", type=int, default=int(os.environ.get("PORT", "12346")))
    args = parser.parse_args()
    server = ThreadingHTTPServer((HOST, args.port), Handler)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
