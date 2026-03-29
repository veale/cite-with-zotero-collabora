#!/usr/bin/env python3
"""Minimal WOPI server for local Collabora development.

Serves files from ./docs/ and provides a browser UI to open them.

Endpoints required by Collabora:
  GET  /wopi/files/<id>           CheckFileInfo
  GET  /wopi/files/<id>/contents  GetFile
  POST /wopi/files/<id>/contents  PutFile

Also serves:
  GET  /                          Lists documents with open links
  GET  /open/<id>                 HTML form that launches the editor
"""

import datetime
import os
import urllib.parse
import xml.etree.ElementTree as ET

from flask import Flask, Response, jsonify, render_template_string, request, send_file

app = Flask(__name__)

DOCS_DIR = os.path.join(os.path.dirname(__file__), "docs")
# Collabora as reachable from INSIDE the Docker network (for discovery fetch)
COLLABORA_INTERNAL_URL = os.environ.get("COLLABORA_INTERNAL_URL", "http://collabora:9980")
# Collabora as reachable from the BROWSER (used in the editor URL we hand to the browser)
COLLABORA_BROWSER_URL = os.environ.get("COLLABORA_BROWSER_URL", "http://localhost:9980")
# This server's address as seen from INSIDE the Collabora Docker container
WOPI_INTERNAL_URL = os.environ.get("WOPI_INTERNAL_URL", "http://wopi:8080")


def file_path(file_id):
    """Map a file_id (filename) to an absolute path, rejecting traversal."""
    name = os.path.basename(file_id)
    return os.path.join(DOCS_DIR, name)


def get_discovery_urlsrc():
    """Fetch the urlsrc for Writer ODT files from Collabora's discovery endpoint.

    Fetches via the internal Docker hostname, then rewrites the host in the
    returned URL to the browser-facing address so the browser can reach it.
    """
    import urllib.request
    try:
        with urllib.request.urlopen(f"{COLLABORA_INTERNAL_URL}/hosting/discovery", timeout=5) as r:
            tree = ET.fromstring(r.read())
        for action in tree.iter("action"):
            if action.get("ext") == "odt":
                urlsrc = action.get("urlsrc")
                # Replace the internal Docker host with the browser-facing host
                urlsrc = urlsrc.replace(COLLABORA_INTERNAL_URL, COLLABORA_BROWSER_URL)
                return urlsrc
    except Exception:
        return None


# ── Icon endpoint ─────────────────────────────────────────────────────────────

_ICON_COLORS = {
    'cite': '#c1392b', 'bib': '#2c3e50', 'ref': '#27ae60',
    'pref': '#8e44ad', 'note': '#d35400', 'unlink': '#7f8c8d', 'export': '#2980b9',
}
_ICON_LETTERS = {
    'cite': 'C+', 'bib': 'B', 'ref': 'R', 'pref': 'P',
    'note': 'N', 'unlink': 'U', 'export': 'E',
}

@app.route("/icons/<name>.svg")
def icon_svg(name):
    bg = _ICON_COLORS.get(name, '#c1392b')
    letter = _ICON_LETTERS.get(name, '?')
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
        f'<rect width="24" height="24" rx="4" fill="{bg}"/>'
        f'<text x="12" y="17" font-family="sans-serif" font-size="13" '
        f'font-weight="bold" fill="white" text-anchor="middle">{letter}</text>'
        f'</svg>'
    )
    return Response(svg, mimetype='image/svg+xml')


# ── WOPI endpoints ────────────────────────────────────────────────────────────

@app.route("/wopi/files/<path:file_id>", methods=["GET"])
def check_file_info(file_id):
    path = file_path(file_id)
    if not os.path.isfile(path):
        return "Not found", 404
    stat = os.stat(path)
    return jsonify({
        "BaseFileName": os.path.basename(path),
        "Size": stat.st_size,
        "LastModifiedTime": datetime.datetime.utcfromtimestamp(stat.st_mtime).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        ),
        "OwnerId": "dev",
        "UserId": "dev",
        "UserFriendlyName": "Dev",
        "UserCanWrite": True,
        "SupportsUpdate": True,
        "SupportsLocks": False,
        "DisablePrint": False,
        "PostMessageOrigin": "http://localhost:8080",
    })


@app.route("/wopi/files/<path:file_id>/contents", methods=["GET"])
def get_file(file_id):
    path = file_path(file_id)
    if not os.path.isfile(path):
        return "Not found", 404
    return send_file(path, as_attachment=False)


@app.route("/wopi/files/<path:file_id>/contents", methods=["POST"])
def put_file(file_id):
    path = file_path(file_id)
    with open(path, "wb") as f:
        f.write(request.data)
    # Collabora requires LastModifiedTime in the response or it logs errors
    # and may destabilise the session.
    now = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    return jsonify({"LastModifiedTime": now})


# ── Browser UI ────────────────────────────────────────────────────────────────

INDEX_HTML = """<!DOCTYPE html>
<html>
<head><title>Zotero-Collabora Dev</title>
<style>body{font-family:monospace;max-width:700px;margin:40px auto;padding:0 20px}
a{color:#d44}</style></head>
<body>
<h2>Zotero-Collabora WOPI Dev Server</h2>
<p>Documents in <code>wopi/docs/</code>:</p>
{% if files %}
<ul>{% for f in files %}
  <li><a href="/open/{{ f }}">{{ f }}</a></li>
{% endfor %}</ul>
{% else %}
<p><em>No documents found. Copy an .odt file into <code>wopi/docs/</code>.</em></p>
<pre>docker cp collabora:/opt/collaboraoffice/EULA.odt wopi/docs/test.odt</pre>
{% endif %}
<p style="margin-top:2em;color:#888">WOPI internal URL: {{ wopi_url }}</p>
</body></html>"""

OPEN_HTML = """<!DOCTYPE html>
<html>
<head><title>Opening {{ filename }}…</title></head>
<body onload="document.getElementById('f').submit()">
<form id="f"
      action="{{ editor_url }}"
      enctype="multipart/form-data"
      method="post"
      target="office_frame">
  <input name="access_token" value="dev-token" type="hidden"/>
  <input name="access_token_ttl" value="0" type="hidden"/>
</form>
<iframe name="office_frame"
        id="office_frame"
        style="width:100%;height:100vh;border:none;margin:0;padding:0;"
        allow="clipboard-read; clipboard-write">
</iframe>
<script>
// WOPI PostMessage handshake:
// Collabora sends App_LoadingStatus to the parent; the parent must reply
// with Host_PostmessageReady so that Collabora sets WOPIPostmessageReady=true
// and begins accepting PostMessage API calls.
window.addEventListener('message', function(e) {
  var frame = document.getElementById('office_frame');
  if (!frame || e.source !== frame.contentWindow) return;
  var msg;
  try { msg = JSON.parse(e.data); } catch(err) { return; }
  if (msg.MessageId === 'App_LoadingStatus') {
    frame.contentWindow.postMessage(
      JSON.stringify({ MessageId: 'Host_PostmessageReady', SendTime: Date.now(), Values: {} }),
      '*'
    );
  }
});
</script>
</body></html>"""


@app.route("/")
def index():
    files = sorted(
        f for f in os.listdir(DOCS_DIR)
        if not f.startswith(".") and os.path.isfile(os.path.join(DOCS_DIR, f))
    )
    return render_template_string(INDEX_HTML, files=files, wopi_url=WOPI_INTERNAL_URL)


@app.route("/open/<path:file_id>")
def open_doc(file_id):
    path = file_path(file_id)
    if not os.path.isfile(path):
        return "Not found", 404

    urlsrc = get_discovery_urlsrc()
    if not urlsrc:
        return f"Cannot reach Collabora at {COLLABORA_INTERNAL_URL}/hosting/discovery", 503

    wopi_src = f"{WOPI_INTERNAL_URL}/wopi/files/{urllib.parse.quote(file_id)}"
    editor_url = urlsrc + urllib.parse.urlencode({"WOPISrc": wopi_src})

    return render_template_string(
        OPEN_HTML,
        editor_url=editor_url,
        filename=os.path.basename(file_id),
    )


if __name__ == "__main__":
    os.makedirs(DOCS_DIR, exist_ok=True)
    print(f"Docs directory : {DOCS_DIR}")
    print(f"Collabora internal : {COLLABORA_INTERNAL_URL}")
    print(f"Collabora browser  : {COLLABORA_BROWSER_URL}")
    print(f"WOPI internal      : {WOPI_INTERNAL_URL}")
    app.run(host="0.0.0.0", port=8080, debug=True)
