"""DistractApp waitlist: stores signup emails in SQLite and exports them as CSV.

Python standard library only. Runs behind nginx on 127.0.0.1, which handles
HTTPS, rate limiting and the password on /admin/.

  POST /api/waitlist          {"email": "...", "source": "hero|footer"}  -> {"ok": true}
  GET  /admin/                 signup list with search, remove buttons, CSV download
  GET  /admin/waitlist.csv     all signups as CSV
  POST /admin/remove           {"email": "..."}  -> {"ok": true, "removed": 1}
"""
import csv
import datetime as dt
import html
import io
import json
import os
import re
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

DB_PATH = os.environ.get("WAITLIST_DB", "waitlist.db")
HOST = os.environ.get("WAITLIST_HOST", "127.0.0.1")
PORT = int(os.environ.get("WAITLIST_PORT", "8787"))
MAX_BODY = 4096
EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$")
SOURCES = {"hero", "footer"}
# /admin/remove only accepts requests from these origins (blocks cross-site form tricks).
ADMIN_ORIGINS = set(
    os.environ.get("ADMIN_ORIGINS", "https://distractapp.com,https://www.distractapp.com").split(",")
)


def db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS signups (
               email      TEXT PRIMARY KEY,
               source     TEXT NOT NULL,
               created_at TEXT NOT NULL
           )"""
    )
    return conn


def now_utc():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def csv_safe(value):
    # Stop spreadsheet apps from treating a cell as a formula.
    return "'" + value if value[:1] in ("=", "+", "-", "@", "\t", "\r") else value


class Handler(BaseHTTPRequestHandler):
    server_version = "waitlist"

    def send(self, status, body, ctype="application/json", extra=None):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def json(self, status, obj):
        self.send(status, json.dumps(obj))

    def do_POST(self):
        if self.path == "/admin/remove":
            return self.remove()
        if self.path != "/api/waitlist":
            return self.json(404, {"ok": False, "error": "not_found"})
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > MAX_BODY:
            return self.json(400, {"ok": False, "error": "bad_request"})
        raw = self.rfile.read(length).decode("utf-8", "replace")
        if (self.headers.get("Content-Type") or "").startswith("application/json"):
            try:
                data = json.loads(raw)
            except ValueError:
                return self.json(400, {"ok": False, "error": "bad_request"})
            if not isinstance(data, dict):
                return self.json(400, {"ok": False, "error": "bad_request"})
        else:
            data = {k: v[0] for k, v in parse_qs(raw).items()}

        # Honeypot: people never see this field, bots fill it in. Pretend it worked.
        if str(data.get("website") or "").strip():
            return self.json(200, {"ok": True})

        email = str(data.get("email") or "").strip().lower()
        if len(email) > 254 or not EMAIL_RE.match(email):
            return self.json(422, {"ok": False, "error": "invalid_email"})
        source = str(data.get("source") or "")
        source = source if source in SOURCES else "unknown"

        with db() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO signups (email, source, created_at) VALUES (?, ?, ?)",
                (email, source, now_utc()),
            )
        return self.json(200, {"ok": True})

    def remove(self):
        # The admin page sends this with fetch + a custom header; other sites can't, even
        # though the browser would attach the admin password to their requests.
        if (self.headers.get("X-Waitlist-Admin") != "1"
                or self.headers.get("Origin") not in ADMIN_ORIGINS):
            return self.json(403, {"ok": False, "error": "forbidden"})
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > MAX_BODY:
            return self.json(400, {"ok": False, "error": "bad_request"})
        try:
            data = json.loads(self.rfile.read(length).decode("utf-8", "replace"))
            email = str(data.get("email") or "").strip().lower()
        except (ValueError, AttributeError):
            return self.json(400, {"ok": False, "error": "bad_request"})
        with db() as conn:
            removed = conn.execute("DELETE FROM signups WHERE email = ?", (email,)).rowcount
        return self.json(200, {"ok": True, "removed": removed})

    def do_GET(self):
        if self.path == "/admin/waitlist.csv":
            with db() as conn:
                rows = conn.execute(
                    "SELECT email, source, created_at FROM signups ORDER BY created_at"
                ).fetchall()
            out = io.StringIO()
            w = csv.writer(out)
            w.writerow(["email", "signed_up_from", "signed_up_at"])
            for row in rows:
                w.writerow([csv_safe(c) for c in row])
            name = "distractapp-waitlist-%s.csv" % dt.date.today().isoformat()
            # BOM so Excel opens it as UTF-8.
            return self.send(200, "﻿" + out.getvalue(), "text/csv; charset=utf-8",
                             {"Content-Disposition": 'attachment; filename="%s"' % name})

        if self.path in ("/admin", "/admin/"):
            with db() as conn:
                rows = conn.execute(
                    "SELECT email, source, created_at FROM signups ORDER BY created_at DESC"
                ).fetchall()
            items = "".join(
                '<tr data-email="%(e)s"><td class="e">%(e)s</td><td>%(s)s</td><td><time>%(t)s</time></td>'
                '<td><button type="button" class="rm">Remove</button></td></tr>'
                % {"e": html.escape(e), "s": html.escape(src), "t": html.escape(t)}
                for e, src, t in rows
            )
            return self.send(200, ADMIN_PAGE % {"total": len(rows), "items": items},
                             "text/html; charset=utf-8")

        return self.json(404, {"ok": False, "error": "not_found"})

    def log_message(self, fmt, *args):
        # Keep emails out of the logs; nginx already logs requests.
        pass


ADMIN_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex"><title>DistractApp Waitlist</title><link rel="icon" href="/favicon.svg">
<style>
body{margin:0;background:#1A0B33;color:#fff;font:16px/1.5 system-ui,-apple-system,sans-serif}
main{max-width:760px;margin:0 auto;padding:48px 20px;display:flex;flex-direction:column;gap:24px}
h1{margin:0;font-size:28px}.n{font-size:64px;font-weight:800;color:#FF4FA3;line-height:1}
p{margin:0;color:#D6C8F2}.top{display:flex;flex-wrap:wrap;gap:16px;align-items:end;justify-content:space-between}
a.btn{display:inline-block;background:#FF4FA3;color:#1A0B33;font-weight:700;padding:14px 22px;border-radius:12px;text-decoration:none}
input{width:100%%;box-sizing:border-box;font:inherit;color:#fff;background:#2A1450;border:1px solid #4E2F88;border-radius:10px;padding:12px 14px}
input:focus-visible,button:focus-visible,a:focus-visible{outline:2px solid #FF4FA3;outline-offset:2px}
.wrap{overflow-x:auto;border:1px solid #3A2268;border-radius:12px}
table{width:100%%;border-collapse:collapse;min-width:520px}
th,td{text-align:left;padding:10px 12px;border-bottom:1px solid #3A2268;vertical-align:middle}
th{font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:#A893D9}
tr:last-child td{border-bottom:0}td.e{overflow-wrap:anywhere}time{color:#A893D9;font-size:13px;white-space:nowrap}
button.rm{font:inherit;font-size:13px;color:#FFB4D6;background:transparent;border:1px solid #6B2D5C;border-radius:8px;padding:5px 10px;cursor:pointer}
button.rm:hover{background:#3A1838}button.rm:disabled{opacity:.5;cursor:default}
.empty{padding:16px 12px;color:#A893D9}#note{min-height:1.5em;color:#7EF0C1}
</style></head><body><main>
<h1>DistractApp waitlist</h1>
<div class="top"><div><div class="n" id="total">%(total)s</div><p>people signed up</p></div>
<a class="btn" href="/admin/waitlist.csv">Download CSV</a></div>
<div><label for="q"><p>Find an email</p></label><input id="q" type="search" placeholder="Type part of an email" autocomplete="off"></div>
<p id="note" role="status"></p>
<div class="wrap"><table><thead><tr><th>Email</th><th>Form</th><th>Signed up</th><th></th></tr></thead>
<tbody id="rows">%(items)s</tbody></table>
<div class="empty" id="empty" hidden>No signups match.</div></div>
</main>
<script>
var rows = document.getElementById('rows'), q = document.getElementById('q'),
    empty = document.getElementById('empty'), note = document.getElementById('note'),
    total = document.getElementById('total');
function filter() {
  var term = q.value.trim().toLowerCase(), shown = 0;
  Array.prototype.forEach.call(rows.rows, function (tr) {
    var hit = tr.dataset.email.indexOf(term) !== -1; tr.hidden = !hit; if (hit) shown++;
  });
  empty.hidden = shown > 0;
}
q.addEventListener('input', filter); filter();
rows.addEventListener('click', function (e) {
  var b = e.target.closest('button.rm'); if (!b) return;
  var tr = b.closest('tr'), email = tr.dataset.email;
  if (!confirm('Remove ' + email + ' from the waitlist? This cannot be undone.')) return;
  b.disabled = true; b.textContent = 'Removing…';
  fetch('/admin/remove', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Waitlist-Admin': '1' },
    body: JSON.stringify({ email: email }) })
    .then(function (r) { return r.json(); })
    .then(function (d) {
      if (!d.ok) throw new Error();
      tr.remove(); total.textContent = rows.rows.length; filter();
      note.style.color = '#7EF0C1'; note.textContent = 'Removed ' + email + '.';
    })
    .catch(function () {
      b.disabled = false; b.textContent = 'Remove';
      note.style.color = '#FFB4D6'; note.textContent = "Couldn't remove " + email + '. Reload the page and try again.';
    });
});
</script></body></html>"""


if __name__ == "__main__":
    db().close()
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
