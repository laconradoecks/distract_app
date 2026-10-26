"""DistractApp waitlist: stores signup emails in SQLite and exports them as CSV.

Python standard library only. Runs behind nginx on 127.0.0.1, which handles
HTTPS, rate limiting and the password on /admin/.

  POST /api/waitlist          {"email": "...", "source": "hero|footer"}  -> {"ok": true}
  GET  /admin/                 signup count + download button
  GET  /admin/waitlist.csv     all signups as CSV
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
                total = conn.execute("SELECT COUNT(*) FROM signups").fetchone()[0]
                latest = conn.execute(
                    "SELECT email, created_at FROM signups ORDER BY created_at DESC LIMIT 5"
                ).fetchall()
            items = "".join(
                "<li><span>%s</span><time>%s</time></li>" % (html.escape(e), html.escape(t))
                for e, t in latest
            ) or "<li>No signups yet.</li>"
            return self.send(200, ADMIN_PAGE % {"total": total, "items": items},
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
main{max-width:520px;margin:0 auto;padding:48px 20px;display:flex;flex-direction:column;gap:24px}
h1{margin:0;font-size:28px}.n{font-size:64px;font-weight:800;color:#FF4FA3;line-height:1}
a.btn{display:inline-block;background:#FF4FA3;color:#1A0B33;font-weight:700;padding:14px 22px;border-radius:12px;text-decoration:none}
ul{list-style:none;margin:0;padding:0;border-top:1px solid #3A2268}
li{display:flex;justify-content:space-between;gap:12px;padding:10px 0;border-bottom:1px solid #3A2268;overflow-wrap:anywhere}
time{color:#A893D9;font-size:13px;white-space:nowrap}p{margin:0;color:#D6C8F2}
</style></head><body><main>
<h1>DistractApp waitlist</h1>
<div><div class="n">%(total)s</div><p>people signed up</p></div>
<div><a class="btn" href="/admin/waitlist.csv">Download CSV</a></div>
<div><p>Latest signups</p><ul>%(items)s</ul></div>
</main></body></html>"""


if __name__ == "__main__":
    db().close()
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
